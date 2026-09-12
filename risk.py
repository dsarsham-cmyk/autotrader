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
        risk_dollars = equity * self.config.risk_per_trade
        stop_distance = atr_value * self.config.atr_stop_mult
        units = risk_dollars / stop_distance
        # Cap by max position value.
        max_units = (equity * self.config.max_position_pct) / price
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
    def update_equity(self, equity: float, day_key: str) -> None:
        if self.day_start_equity is None or day_key != self.current_day:
            self.day_start_equity = equity
            self.current_day = day_key
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

    def halt(self, reason: str) -> None:
        if not self.halted:
            self.halted = True
            self.halt_reason = reason

    def allow_trading(self) -> bool:
        return not self.halted
