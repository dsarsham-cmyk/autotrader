"""Walk-forward sweep for stop, take-profit, and trailing-stop parameters.

Candidates are ranked on the earlier part of the requested history, then only
the strongest training candidates are evaluated on the untouched final 30%.
This keeps exit tuning from simply selecting the best full-period backtest.
"""
from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import replace
from pathlib import Path

from scenario_backtest import (
    FEE_PCT,
    STARTING_BALANCE,
    fetch_symbols,
    load_config,
    risk_config,
    run_portfolio,
)


def score(result: dict) -> float:
    """Favor repeatable risk-adjusted returns, with a drawdown penalty."""
    return (
        result["sharpe"]
        + 0.5 * result["sortino"]
        + result["annualized_return_pct"] / 20.0
        - result["max_drawdown_pct"] / 50.0
    )


def split_history(candles_by_symbol: dict, train_fraction: float = 0.70) -> tuple[dict, dict]:
    """Chronologically split each symbol without leaking validation bars."""
    train, validation = {}, {}
    for symbol, candles in candles_by_symbol.items():
        cut = int(len(candles) * train_fraction)
        train[symbol] = candles[:cut]
        validation[symbol] = candles[cut:]
    return train, validation


def params(rc) -> dict:
    return {
        "atr_stop_mult": rc.atr_stop_mult,
        "atr_take_mult": rc.atr_take_mult,
        "break_even_atr": rc.break_even_atr,
        "trail_atr": rc.trail_atr,
        "trail_distance_atr": rc.trail_distance_atr,
    }


def sweep(config_path: str, years: int, finalists: int) -> dict:
    cfg = load_config(config_path)
    base = risk_config(cfg)
    all_data = fetch_symbols(cfg["stock"]["symbols"], years)
    train_data, validation_data = split_history(all_data)

    candidates = []
    grid = itertools.product(
        (1.25, 1.5, 2.0),            # initial stop
        (3.0, 4.0, 5.0),            # take profit
        (1.0, 1.5),                 # break even trigger
        (2.0, 2.5, 3.0),            # trailing trigger
        (1.0, 1.5, 2.0),            # trailing distance
    )
    for stop, take, break_even, trail, distance in grid:
        if trail < break_even:
            continue
        rc = replace(
            base,
            atr_stop_mult=stop,
            atr_take_mult=take,
            break_even_atr=break_even,
            trail_atr=trail,
            trail_distance_atr=distance,
        )
        result = run_portfolio(
            train_data, cfg["strategy"], rc, FEE_PCT, STARTING_BALANCE
        )
        candidates.append((score(result), rc, result))

    candidates.sort(key=lambda item: item[0], reverse=True)
    baseline_train = run_portfolio(
        train_data, cfg["strategy"], base, FEE_PCT, STARTING_BALANCE
    )
    baseline_validation = run_portfolio(
        validation_data, cfg["strategy"], base, FEE_PCT, STARTING_BALANCE
    )

    validated = []
    for training_score, rc, training in candidates[:finalists]:
        validation = run_portfolio(
            validation_data, cfg["strategy"], rc, FEE_PCT, STARTING_BALANCE
        )
        validated.append(
            {
                "params": params(rc),
                "training_score": round(training_score, 4),
                "validation_score": round(score(validation), 4),
                "training": training,
                "validation": validation,
            }
        )
    validated.sort(key=lambda item: item["validation_score"], reverse=True)

    return {
        "scenario": cfg.get("name", config_path),
        "years": years,
        "train_fraction": 0.70,
        "baseline": {
            "params": params(base),
            "training_score": round(score(baseline_train), 4),
            "validation_score": round(score(baseline_validation), 4),
            "training": baseline_train,
            "validation": baseline_validation,
        },
        "finalists": validated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward exit-parameter sweep")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--finalists", type=int, default=20)
    parser.add_argument("--save", default="exit_sweep_results.json")
    args = parser.parse_args()

    results = {
        path: sweep(path, args.years, args.finalists)
        for path in ("config_high.yaml", "config_low.yaml")
    }
    Path(args.save).write_text(json.dumps(results, indent=2), encoding="utf-8")
    for path, result in results.items():
        baseline = result["baseline"]
        winner = result["finalists"][0]
        print(f"\n{result['scenario']} ({path})")
        print(f"  baseline validation: {baseline['validation']}")
        print(f"  best parameters:     {winner['params']}")
        print(f"  best validation:     {winner['validation']}")
    print(f"\nSaved full sweep to {args.save}")


if __name__ == "__main__":
    main()
