"""Main trading bot loop.

Loads config, builds a broker + strategy + risk manager, then periodically
checks for signals and executes trades across multiple symbols. Supports crypto
(ccxt), stocks (Alpaca/yfinance), and forex (yfinance). Includes ATR-based
position sizing, stop-loss/take-profit, portfolio-level risk limits, state
persistence, logging, and trade alerts.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import yaml

from strategy import Signal, build_strategy, atr
from broker import PaperBroker, LiveCryptoBroker, AlpacaBroker
from price_feed import build_price_feed
from risk import RiskConfig, RiskManager
from logger import setup_logger
from alerts import AlertManager
from state import StateStore


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def append_logbook(path: str, row: list) -> None:
    """Append a completed-trade row to an append-only CSV logbook.

    The logbook survives bot restarts and is easy to open in Excel for
    performance tracking.
    """
    p = Path(path)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "symbol", "side", "entry_price", "exit_price",
                        "qty", "realized_pnl", "cumulative_pnl", "equity"])
        w.writerow(row)


def build_status(name: str, state: dict, market_open: bool) -> str:
    """Build a human-readable status summary for periodic alerts."""
    equity = state.get("equity", 0.0)
    daily = state.get("daily_pnl_pct", 0.0)
    dd = state.get("drawdown_pct", 0.0)
    positions = state.get("positions", {})
    open_count = sum(1 for p in positions.values() if p.get("base_amount", 0) > 0)
    trades = len(state.get("trades", []))
    halted = state.get("halted", False)
    status = "HALTED" if halted else ("OPEN" if market_open else "CLOSED")
    return (
        f"📊 {name} — {time.strftime('%H:%M')}\n"
        f"Equity: ${equity:,.2f}\n"
        f"Today: {daily:+.2f}% | Drawdown: {dd:.2f}%\n"
        f"Positions: {open_count} | Trades: {trades}\n"
        f"Market: {status}"
    )


def market_settings(config: dict) -> tuple[list[str], str]:
    """Return (list of symbols, timeframe) from config."""
    market = config["market"]
    if market == "crypto":
        return [config["exchange"]["symbol"]], config["exchange"]["timeframe"]
    if market == "stock":
        symbols = config["stock"].get("symbols")
        if not symbols:
            symbols = [config["stock"].get("symbol", "SPY")]
        return list(symbols), config["stock"]["timeframe"]
    if market == "forex":
        return [config["forex"]["symbol"]], config["forex"]["timeframe"]
    raise ValueError(f"Unknown market: {market!r}")


def risk_config(config: dict) -> RiskConfig:
    r = config.get("risk", {})
    return RiskConfig(
        risk_per_trade=r.get("risk_per_trade", 0.01),
        atr_stop_mult=r.get("atr_stop_mult", 2.0),
        atr_take_mult=r.get("atr_take_mult", 3.0),
        max_position_pct=r.get("max_position_pct", 0.25),
        daily_loss_limit_pct=r.get("daily_loss_limit_pct", 0.03),
        max_drawdown_pct=r.get("max_drawdown_pct", 0.20),
        starting_equity=r.get("starting_equity", 0.0),
        max_account_loss_pct=r.get("max_account_loss_pct", 0.10),
        break_even_atr=r.get("break_even_atr", 1.0),
        trail_atr=r.get("trail_atr", 2.0),
        trail_distance_atr=r.get("trail_distance_atr", 1.0),
        capital_fraction=r.get("capital_fraction", 1.0),
    )


def build_broker(config: dict):
    market = config["market"]
    mode = config["mode"]

    if mode == "paper":
        # Internal simulation (no API keys, public market data only).
        feed = build_price_feed(market, config["exchange"]["name"])
        return PaperBroker(
            balance=config["paper"]["starting_balance"],
            fee_pct=config["paper"]["fee_pct"],
            price_feed=feed,
        )

    if mode in ("alpaca_paper", "live"):
        from dotenv import load_dotenv
        import os
        load_dotenv()
        if (mode == "live" and
                os.getenv("AUTOTRADER_LIVE_CONFIRM") != "I_ACCEPT_REAL_MONEY_RISK"):
            raise RuntimeError(
                "Live trading is locked. Keep mode=alpaca_paper until the "
                "paper audit is approved, then set AUTOTRADER_LIVE_CONFIRM."
            )
        if market == "crypto":
            return LiveCryptoBroker(
                config["exchange"]["name"],
                api_key=os.getenv("EXCHANGE_API_KEY", ""),
                api_secret=os.getenv("EXCHANGE_API_SECRET", ""),
            )
        if market == "stock":
            # alpaca_paper -> paper endpoint (demo); live -> real endpoint.
            return AlpacaBroker(
                api_key=os.getenv("ALPACA_API_KEY", ""),
                api_secret=os.getenv("ALPACA_API_SECRET", ""),
                paper=(mode == "alpaca_paper"),
            )
        if market == "forex":
            raise NotImplementedError("Live forex trading is not implemented yet.")
        raise ValueError(f"Unknown market: {market!r}")

    raise ValueError(f"Unknown mode: {mode!r}")


def run(config: dict) -> None:
    # Load .env (Alpaca keys, Telegram token/chat, ntfy topic, etc.) up front
    # so every component that reads env vars (e.g. AlertManager) sees them.
    from dotenv import load_dotenv
    load_dotenv()

    symbols, timeframe = market_settings(config)
    interval = config["loop"]["interval_seconds"]
    fetch_limit = config.get("data", {}).get("fetch_limit", 300)
    dt_cfg = config.get("day_trading", {})
    close_at_eod = dt_cfg.get("close_at_eod", False)
    eod_close_time = dt_cfg.get("eod_close_time", "22:55")

    log_cfg = config.get("logging", {})
    log = setup_logger(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file", "logs/trader.log"),
    )
    logbook_file = log_cfg.get("logbook", "logs/logbook.csv")
    alerts = AlertManager(enabled=config.get("alerts", {}).get("enabled", False))
    name = config.get("name", "bot")
    status_interval = config.get("status_interval_seconds", 900)
    last_status_time = 0.0

    broker = build_broker(config)
    strategy = build_strategy(config["strategy"])
    risk = RiskManager(risk_config(config))

    state = StateStore(config.get("state_file", "state.json"))
    risk.restore(state.data.get("risk_state"))
    if state.data["balance"] == 0.0 and config["mode"] == "paper":
        state.data["balance"] = config["paper"]["starting_balance"]
    state.data["started_at"] = state.data["started_at"] or time.strftime("%Y-%m-%d %H:%M:%S")
    state.data["symbols"] = symbols

    log.info("Bot started | mode=%s market=%s symbols=%s timeframe=%s strategy=%s",
             config["mode"], config["market"], ",".join(symbols), timeframe,
             config["strategy"]["name"])

    # Broker position per symbol from the previous loop iteration (used to
    # detect server-side stop/take closures without mistaking a fresh buy).
    last_pos_base = {s: 0.0 for s in symbols}

    while True:
        # --- Portfolio-level equity + risk (once per loop) ---
        try:
            equity = broker.equity(symbols[0])
        except Exception:
            equity = state.data.get("equity", 0.0)
        day_key = time.strftime("%Y-%m-%d")
        previous_close_equity = getattr(broker, "previous_close_equity", None)
        risk.update_equity(equity, day_key, previous_close_equity)
        market_open = broker.market_open()

        prices: dict[str, float] = {}
        signals: dict[str, str] = {}
        details: dict[str, dict] = {}
        iteration_failures = 0

        # Total notional this bot currently has deployed across ALL its
        # symbols. `capital_fraction` must cap the WHOLE portfolio, not just
        # each individual position, otherwise two scenarios sharing one paper
        # account can over-leverage (e.g. 8 positions x 12.5% = 100% each).
        deployed = 0.0
        for s in symbols:
            try:
                p = broker.get_position(s)
                if p.base_amount > 0 and p.entry_price > 0:
                    deployed += p.base_amount * p.entry_price
            except Exception:
                pass

        for symbol in symbols:
            try:
                candles = broker.fetch_ohlcv(symbol, timeframe, limit=fetch_limit)
                if not candles:
                    log.warning("%s: no candle data", symbol)
                    continue

                price = candles[-1][4]
                a = atr(candles, period=14)[-1]
                signal = strategy.evaluate(candles)
                pos = broker.get_position(symbol)
                prev = last_pos_base.get(symbol, 0.0)

                prices[symbol] = price
                signals[symbol] = signal.value
                details[symbol] = strategy.describe(candles)

                stored = state.get_position(symbol)
                stop_price = stored.get("stop_price", 0.0)
                take_price = stored.get("take_price", 0.0)

                # Railway's local state can disappear on a redeploy. Rebuild
                # an exit plan from Alpaca's real average entry so an existing
                # position never comes back with a zero stop.
                if pos.base_amount > 0 and pos.entry_price > 0 and stop_price <= 0:
                    stop_price, take_price = risk.stops(pos.entry_price, a)
                    state.set_position(symbol, pos.base_amount, pos.entry_price,
                                       stop_price, take_price, price)

                action = None
                sell_base = 0.0
                sell_price = 0.0

                # --- Server-side stop/take closure (bracket orders) ---
                if broker.server_stops and prev > 0 and pos.base_amount <= 0:
                    action = f"STOP/TAKE (server) @ {price:.4f}"
                    sell_base = prev
                    sell_price = price

                # --- Client-side fallback stops ---
                # Also check these when a broker supports bracket orders. This
                # protects positions inherited from older simple orders.
                elif pos.base_amount > 0:
                    if stop_price > 0 and price <= stop_price:
                        broker.market_sell(symbol, pos.base_amount)
                        action = f"STOP-LOSS @ {price:.4f}"
                        sell_base = pos.base_amount
                        sell_price = price
                    elif take_price > 0 and price >= take_price:
                        broker.market_sell(symbol, pos.base_amount)
                        action = f"TAKE-PROFIT @ {price:.4f}"
                        sell_base = pos.base_amount
                        sell_price = price

                # --- Trailing stop (lock in profits) ---
                # Runs for every broker (including server-side stops): once a
                # trade is in profit, raise the stop to break-even and then
                # trail it so gains are locked in instead of given back at EOD.
                if action is None and pos.base_amount > 0:
                    # Fall back to the broker's avg entry price after a restart
                    # (state is ephemeral on Railway), so the trailing stop is
                    # anchored to the real entry instead of 0.
                    entry = stored.get("entry_price", 0.0) or pos.entry_price
                    trailing_high = max(stored.get("trailing_high", entry), price)
                    new_stop = risk.trailing_stop(entry, trailing_high, a, stop_price)
                    if new_stop > stop_price:
                        stop_price = new_stop
                    if stop_price > 0 and price <= stop_price:
                        broker.market_sell(symbol, pos.base_amount)
                        action = f"TRAIL-STOP @ {price:.4f}"
                        sell_base = pos.base_amount
                        sell_price = price
                    else:
                        state.set_position(symbol, pos.base_amount, entry,
                                           stop_price, take_price, trailing_high)

                # --- End-of-day close (day trading) ---
                # Only close WINNING positions at EOD; hold losers overnight
                # (the stop-loss still protects them) instead of locking in a
                # loss just because the clock hit the close time.
                if action is None and close_at_eod and pos.base_amount > 0:
                    if time.strftime("%H:%M") >= eod_close_time:
                        entry = stored.get("entry_price", 0.0) or pos.entry_price
                        if entry > 0 and price > entry:
                            broker.market_sell(symbol, pos.base_amount)
                            action = f"EOD-CLOSE (profit) @ {price:.4f}"
                            sell_base = pos.base_amount
                            sell_price = price
                        else:
                            log.info("%s: holding losing position overnight @ %.4f",
                                     symbol, price)

                # --- Strategy signals ---
                if action is None and risk.allow_trading():
                    if signal == Signal.BUY and pos.base_amount <= 0:
                        # Don't open new positions after the EOD close time.
                        past_eod = close_at_eod and time.strftime("%H:%M") >= eod_close_time
                        if market_open and not past_eod:
                            units = risk.position_size(equity, price, a)
                            if units > 0:
                                notional = units * price
                                # Enforce the total-deployment cap: this bot
                                # may hold at most `capital_fraction` of the
                                # account equity across all its positions.
                                cap = equity * risk.config.capital_fraction
                                if deployed + notional > cap:
                                    log.warning(
                                        "%s: total deployment cap reached "
                                        "(deployed %.2f + %.2f > cap %.2f); skipping",
                                        symbol, deployed, notional, cap)
                                else:
                                    bp = getattr(broker, "buying_power", None)
                                    if bp is not None and notional > bp:
                                        log.warning(
                                            "%s: insufficient buying power "
                                            "(need %.2f, have %.2f); skipping",
                                            symbol, notional, bp)
                                    else:
                                        stop, take = risk.stops(price, a)
                                        broker.market_buy(symbol, notional,
                                                          stop_price=stop, take_price=take)
                                        state.set_position(symbol, units, price, stop, take, price)
                                        state.record_trade("buy", symbol, price, units,
                                                           notional, 0.0)
                                        deployed += notional
                                        action = f"BUY {units:.6f} @ {price:.4f}"
                        elif not market_open:
                            log.debug("%s: market closed; skipping entry", symbol)
                    elif signal == Signal.SELL and pos.base_amount > 0:
                        broker.market_sell(symbol, pos.base_amount)
                        action = f"SELL @ {price:.4f}"
                        sell_base = pos.base_amount
                        sell_price = price

                # --- Per-symbol action: record + notify ---
                if action:
                    if sell_base > 0:
                        entry_price = stored.get("entry_price", 0.0)
                        realized = (sell_price - entry_price) * sell_base
                        state.add_realized_pnl(symbol, realized)
                        cumulative = state.data["pnl"].get(symbol, 0.0)
                        append_logbook(logbook_file, [
                            time.strftime("%Y-%m-%d %H:%M:%S"), symbol, "sell",
                            round(entry_price, 4), round(sell_price, 4),
                            round(sell_base, 6), round(realized, 2),
                            round(cumulative, 2), round(equity, 2),
                        ])
                        state.record_trade("sell", symbol, sell_price, sell_base,
                                           sell_base * sell_price, 0.0)
                        state.set_position(symbol, 0.0, 0.0, 0.0, 0.0)
                    log.info("%s %s | equity=%.2f", symbol, action, equity)
                    alerts.send(f"{symbol} {action}")

                # Per-symbol total P&L snapshot (realized + unrealized) for
                # the dashboard's per-market evolution chart.
                sp = state.get_position(symbol)
                e = sp.get("entry_price", 0.0)
                q = sp.get("base_amount", 0.0)
                unrealized = (price - e) * q if q > 0 else 0.0
                state.record_pnl_history(symbol, state.data["pnl"].get(symbol, 0.0) + unrealized)

                last_pos_base[symbol] = pos.base_amount

            except Exception as e:
                iteration_failures += 1
                msg = str(e)
                if "timeout" in msg.lower() or "backend request" in msg.lower():
                    log.warning("%s: transient error (will retry next loop): %s", symbol, msg)
                else:
                    log.error("%s: loop error: %s", symbol, e)

        if risk.halted:
            log.warning("Trading halted: %s", risk.halt_reason)

        # --- Persist portfolio state once per loop ---
        state.data["balance"] = broker.balance
        state.data["equity"] = equity
        state.data["market_open"] = market_open
        state.data["prices"] = prices
        state.data["signals"] = signals
        state.data["signal_details"] = details
        state.data["drawdown_pct"] = (
            (risk.peak_equity - equity) / risk.peak_equity * 100
            if risk.peak_equity and risk.peak_equity > 0 else 0.0
        )
        state.data["daily_pnl_pct"] = (
            (equity - risk.day_start_equity) / risk.day_start_equity * 100
            if risk.day_start_equity and risk.day_start_equity > 0 else 0.0
        )
        state.data["halted"] = risk.halted
        state.data["halt_reason"] = risk.halt_reason
        state.data["risk_state"] = risk.snapshot()
        state.record_equity(equity)
        state.save()

        # --- Periodic status update (Telegram/Discord) ---
        # Only send the heartbeat while the market is open; stay silent
        # overnight / weekends / holidays.
        now = time.time()
        if now - last_status_time >= status_interval:
            last_status_time = now
            if market_open:
                alerts.send(build_status(name, state.data, market_open))

        # Backoff: if the API is failing (e.g. Alpaca overloaded), slow the
        # loop down to avoid hammering it, then recover once it's healthy.
        if iteration_failures > 0:
            sleep_time = min(interval * (2 ** min(iteration_failures, 4)), 300)
        else:
            sleep_time = interval
        time.sleep(sleep_time)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(path)
    run(cfg)
