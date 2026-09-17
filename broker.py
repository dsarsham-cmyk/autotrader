"""Broker abstraction: paper (simulated) and live brokers for crypto + stocks.

All brokers implement the same small interface so the bot doesn't care which
market or mode it is running in.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from price_feed import _retry_call


@dataclass
class Position:
    symbol: str
    base_amount: float = 0.0       # amount of base asset held (BTC, AAPL shares, ...)
    entry_price: float = 0.0       # average entry price


class Broker(ABC):
    """Minimal interface the bot depends on."""

    # Whether this broker enforces stop-loss/take-profit server-side
    # (e.g. Alpaca bracket orders). When False, the bot must check stops
    # client-side on every loop iteration.
    server_stops: bool = False

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        """Return OHLCV candles as [[ts, open, high, low, close, volume], ...]."""

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        """Return the current position for a symbol."""

    @abstractmethod
    def market_buy(self, symbol: str, quote_amount: float,
                   stop_price: float = 0.0, take_price: float = 0.0) -> None:
        """Buy using `quote_amount` of quote currency (USD/USDT).

        `stop_price` / `take_price` (optional) attach a stop-loss / take-profit
        for brokers that support server-side bracket orders.
        """

    @abstractmethod
    def market_sell(self, symbol: str, base_amount: float) -> None:
        """Sell `base_amount` of the base asset."""

    def market_open(self) -> bool:
        """Whether the market is currently open for trading."""
        return True


class PaperBroker(Broker):
    """Simulated broker backed by a simple in-memory ledger."""

    def __init__(self, balance: float, fee_pct: float, price_feed):
        self.balance = balance
        self.fee_pct = fee_pct
        self.price_feed = price_feed
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return self.price_feed.fetch_ohlcv(symbol, timeframe, limit)

    def get_position(self, symbol: str) -> Position:
        return self.positions.get(symbol, Position(symbol))

    def market_buy(self, symbol: str, quote_amount: float,
                   stop_price: float = 0.0, take_price: float = 0.0) -> None:
        price = self.price_feed.last_price(symbol)
        fee = quote_amount * self.fee_pct
        base_amount = (quote_amount - fee) / price
        self.balance -= quote_amount
        pos = self.positions.setdefault(symbol, Position(symbol))
        total_cost = pos.base_amount * pos.entry_price + quote_amount
        pos.base_amount += base_amount
        pos.entry_price = total_cost / pos.base_amount if pos.base_amount else 0.0
        self.trades.append({"side": "buy", "symbol": symbol, "price": price,
                            "base_amount": base_amount, "quote_amount": quote_amount,
                            "fee": fee})

    def market_sell(self, symbol: str, base_amount: float) -> None:
        price = self.price_feed.last_price(symbol)
        pos = self.positions.get(symbol)
        if pos is None or pos.base_amount <= 0:
            return
        base_amount = min(base_amount, pos.base_amount)
        gross = base_amount * price
        fee = gross * self.fee_pct
        self.balance += gross - fee
        pos.base_amount -= base_amount
        if pos.base_amount <= 1e-12:
            pos.base_amount = 0.0
            pos.entry_price = 0.0
        self.trades.append({"side": "sell", "symbol": symbol, "price": price,
                            "base_amount": base_amount, "quote_amount": gross,
                            "fee": fee})

    def equity(self, symbol: str = "") -> float:
        """Cash + value of all held base assets at current prices."""
        total = self.balance
        for sym, pos in self.positions.items():
            if pos.base_amount > 0:
                total += pos.base_amount * self.price_feed.last_price(sym)
        return total


class LiveCryptoBroker(Broker):
    """ccxt-backed broker. Requires API keys for private methods."""

    def __init__(self, exchange_id: str, api_key: str = "", api_secret: str = ""):
        import ccxt
        self.exchange = getattr(ccxt, exchange_id)({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def get_position(self, symbol: str) -> Position:
        balance = self.exchange.fetch_balance()
        base = symbol.split("/")[0]
        amount = float(balance.get(base, {}).get("free", 0) or 0)
        return Position(symbol, base_amount=amount)

    def market_buy(self, symbol: str, quote_amount: float,
                   stop_price: float = 0.0, take_price: float = 0.0) -> None:
        self.exchange.create_market_buy_order(symbol, quote_amount)

    def market_sell(self, symbol: str, base_amount: float) -> None:
        self.exchange.create_market_sell_order(symbol, base_amount)

    @property
    def balance(self) -> float:
        bal = self.exchange.fetch_balance()
        total = bal.get("total", {})
        for q in ("USDT", "USD", "USDC"):
            if q in total and total[q]:
                return float(total[q])
        return 0.0

    def equity(self, symbol: str) -> float:
        return self.balance


class AlpacaBroker(Broker):
    """Alpaca-backed broker for stocks. `paper=True` uses the paper endpoint.

    Uses Alpaca's own market data (real-time) and places bracket orders so
    stop-loss / take-profit are enforced server-side (survive bot restarts).
    """

    server_stops = True

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        from alpaca.trading.client import TradingClient
        from price_feed import AlpacaPriceFeed
        self.client = TradingClient(api_key, api_secret, paper=paper)
        self._price_feed = AlpacaPriceFeed(api_key, api_secret)
        self._last_account = None

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return self._price_feed.fetch_ohlcv(symbol, timeframe, limit)

    def get_position(self, symbol: str) -> Position:
        try:
            pos = _retry_call(self.client.get_open_position, symbol)
            return Position(symbol, base_amount=float(pos.qty),
                            entry_price=float(pos.avg_entry_price))
        except Exception:
            return Position(symbol)

    @property
    def balance(self) -> float:
        return float(_retry_call(self.client.get_account).cash)

    @property
    def buying_power(self) -> float:
        return float(_retry_call(self.client.get_account).buying_power)

    def equity(self, symbol: str) -> float:
        self._last_account = _retry_call(self.client.get_account)
        return float(self._last_account.equity)

    @property
    def previous_close_equity(self) -> float | None:
        """Previous session equity used for a restart-safe daily loss limit."""
        if self._last_account is None:
            return None
        value = getattr(self._last_account, "last_equity", None)
        return float(value) if value is not None else None

    def market_open(self) -> bool:
        """Whether the US market is currently open (per Alpaca's clock)."""
        try:
            return bool(_retry_call(self.client.get_clock).is_open)
        except Exception:
            return True  # fail open: let the order be rejected rather than skip

    def market_buy(self, symbol: str, quote_amount: float,
                   stop_price: float = 0.0, take_price: float = 0.0) -> None:
        from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce

        req = MarketOrderRequest(
            symbol=symbol, notional=round(quote_amount, 2),
            side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
        )
        if stop_price > 0:
            req.stop_loss = StopLossRequest(stop_price=round(stop_price, 2))
        if take_price > 0:
            req.take_profit = TakeProfitRequest(limit_price=round(take_price, 2))
        self.client.submit_order(req)

    def market_sell(self, symbol: str, base_amount: float) -> None:
        # close_position cancels any open bracket legs and sells the full
        # position, avoiding orphaned stop/take orders.
        self.client.close_position(symbol)

    def market_sell_short(self, symbol: str, quote_amount: float) -> None:
        """Open a short position (sell to open) using `quote_amount` notional."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = MarketOrderRequest(
            symbol=symbol, notional=round(quote_amount, 2),
            side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
        )
        self.client.submit_order(req)

    def close_short(self, symbol: str) -> None:
        """Close a short position (buy to cover). `close_position` is
        side-agnostic — it offsets whatever position is currently open."""
        self.client.close_position(symbol)

    def cancel_open_orders(self) -> None:
        """Cancel all open orders (e.g. bracket legs) without closing positions."""
        try:
            self.client.cancel_orders()
        except Exception:
            pass
