"""Risk management: position sizing, stops, and portfolio-level limits.

All sizing is volatility-adjusted (ATR-based) so the bot risks a consistent
dollar amount per trade regardless of how volatile the asset is.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01      # fraction of equity risked per trade (1%)
    atr_stop_mult: float = 2.0        # stop-loss distance in ATRs
    atr_take_mult: float = 3.0        # take-profit distance in ATRs
    max_position_pct: float = 0.25    # cap any single position at 25% of equity
    daily_loss_limit_pct: float = 0.03  # stop trading for the day after -3%
    max_drawdown_pct: float = 0.20    # hard kill switch after -20% from peak
    starting_equity: float = 0.0      # fixed account baseline; survives restarts
    max_account_loss_pct: float = 0.10  # halt after losing 10% of baseline
    capital_fraction: float = 1.0     # fraction of account capital this bot may deploy
                                      # (lets two scenarios share one paper account)
    # Trailing-stop exit plan (locks in profits as a trade moves in favour).
    break_even_atr: float = 1.0       # move stop to break-even once +1 ATR in profit
    trail_atr: float = 2.0            # start trailing once +2 ATR in profit
    trail_distance_atr: float = 1.0   # trail the stop this many ATRs below the high


@dataclass
class PositionState:
    base_amount: float = 0.0
    entry_price: float = 0.0
    stop_price: float = 0.0
    take_price: float = 0.0
    trailing_high: float = 0.0


class RiskManager:
    """Computes position sizes and enforces portfolio-level limits."""

    def __init__(self, config: RiskConfig):
        self.config = config
        self.peak_equity: float | None = None
        self.day_start_equity: float | None = None
        self.current_day: str | None = None
        self.halted = False
        self.halt_reason = ""

    # --- Position sizing ---
    def position_size(self, equity: float, price: float, atr_value: float) -> float:
        """Return the number of base units to buy, volatility-adjusted.

        Risk-based sizing: risk_dollars = equity * risk_per_trade.
        Stop distance = atr_value * atr_stop_mult.
        units = risk_dollars / stop_distance.
        """
        if atr_value <= 0 or price <= 0:
            return 0.0
        # Size against this bot's allocated slice of the account so that two
        # scenarios (high/low risk) sharing one paper account don't over-allocate.
        base = equity * self.config.capital_fraction
        risk_dollars = base * self.config.risk_per_trade
        stop_distance = atr_value * self.config.atr_stop_mult
        units = risk_dollars / stop_distance
        # Cap by max position value.
        max_units = (base * self.config.max_position_pct) / price
        return min(units, max_units)

    def stops(self, entry_price: float, atr_value: float) -> tuple[float, float]:
        """Return (stop_price, take_price) for a long entry."""
        stop = entry_price - atr_value * self.config.atr_stop_mult
        take = entry_price + atr_value * self.config.atr_take_mult
        return stop, take

    def trailing_stop(self, entry_price: float, trailing_high: float,
                      atr_value: float, current_stop: float) -> float:
        """Return the updated stop price for a long position.

        Exit plan:
          * once the price is +break_even_atr ATR in profit, raise the stop to
            break-even (entry) so the trade can no longer lose money;
          * once the price is +trail_atr ATR in profit, trail the stop
            trail_distance_atr ATRs below the highest price seen so far.

        The stop only ever moves UP (never down).
        """
        if atr_value <= 0:
            return current_stop
        stop = current_stop
        if trailing_high >= entry_price + self.config.break_even_atr * atr_value:
            stop = max(stop, entry_price)
        if trailing_high >= entry_price + self.config.trail_atr * atr_value:
            stop = max(stop, trailing_high - self.config.trail_distance_atr * atr_value)
        return stop

    # --- Portfolio-level limits ---
    def update_equity(self, equity: float, day_key: str,
                      day_start_equity: float | None = None) -> None:
        if self.day_start_equity is None or day_key != self.current_day:
            # Alpaca's previous-close equity is the authoritative daily
            # reference and remains stable if Railway restarts intraday.
            self.day_start_equity = (
                day_start_equity if day_start_equity and day_start_equity > 0
                else equity
            )
            self.current_day = day_key
            # A daily halt expires on the next trading day. Account-loss and
            # drawdown kill switches remain latched until manually reviewed.
            if self.halt_reason == "daily loss limit":
                self.halted = False
                self.halt_reason = ""
        if self.peak_equity is None:
            self.peak_equity = equity
        self.peak_equity = max(self.peak_equity, equity)

        # Daily loss limit
        if self.day_start_equity > 0:
            daily_pnl = (equity - self.day_start_equity) / self.day_start_equity
            if daily_pnl <= -self.config.daily_loss_limit_pct:
                self.halt("daily loss limit")

        # Max drawdown kill switch
        if self.peak_equity > 0:
            dd = (self.peak_equity - equity) / self.peak_equity
            if dd >= self.config.max_drawdown_pct:
                self.halt("max drawdown")

        # Fixed loss budget from the configured starting balance. Unlike an
        # in-memory peak, this protection cannot be erased by a process restart.
        if self.config.starting_equity > 0:
            floor = self.config.starting_equity * (1 - self.config.max_account_loss_pct)
            if equity <= floor:
                self.halt("account loss budget")

    def restore(self, value: dict | None) -> None:
        """Restore risk state when local persistent storage is available."""
        value = value or {}
        self.peak_equity = value.get("peak_equity")
        self.day_start_equity = value.get("day_start_equity")
        self.current_day = value.get("current_day")
        self.halted = bool(value.get("halted", False))
        self.halt_reason = str(value.get("halt_reason", ""))

    def snapshot(self) -> dict:
        return {
            "peak_equity": self.peak_equity,
            "day_start_equity": self.day_start_equity,
            "current_day": self.current_day,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }

    def halt(self, reason: str) -> None:
        if not self.halted:
            self.halted = True
            self.halt_reason = reason

    def allow_trading(self) -> bool:
        return not self.halted
