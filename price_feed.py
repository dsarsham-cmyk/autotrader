"""Price feeds for crypto (ccxt) and stocks (yfinance).

Both implement the same interface so the broker doesn't care which market
it's trading. Public data only — no API keys required.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod


def _retry_call(fn, *args, retries: int = 2, base_delay: float = 1.0, **kwargs):
    """Call fn(*args, **kwargs), retrying transient failures with backoff.

    Alpaca's paper API occasionally returns "backend request timeout" under
    load; a short retry with exponential backoff absorbs most of these.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - retry any transient failure
            last_exc = e
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc


class PriceFeed(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        """Return OHLCV candles as [[ts, open, high, low, close, volume], ...]."""

    @abstractmethod
    def last_price(self, symbol: str) -> float:
        """Return the latest price for a symbol."""


class CryptoPriceFeed(PriceFeed):
    def __init__(self, exchange_id: str):
        import ccxt
        self.exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def last_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        price = ticker.get("last") or ticker.get("close")
        if price is None:
            raise RuntimeError(f"Could not get last price for {symbol}")
        return float(price)


class StockPriceFeed(PriceFeed):
    """Free stock data via yfinance (no keys)."""

    # Map our timeframe strings to yfinance interval strings.
    _INTERVAL_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1wk": "1wk", "1mo": "1mo",
    }

    def __init__(self):
        import yfinance as yf
        self.yf = yf

    def _interval(self, timeframe: str) -> str:
        return self._INTERVAL_MAP.get(timeframe, timeframe)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        interval = self._interval(timeframe)
        # yfinance needs more raw rows than `limit` because of its period logic;
        # fetch a generous period and trim to the last `limit` rows.
        period = self._period_for(interval, limit)
        df = self.yf.Ticker(symbol).history(period=period, interval=interval)
        if df.empty:
            return []
        candles = []
        for ts, row in df.iterrows():
            candles.append([
                int(ts.timestamp() * 1000),
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(row["Volume"]),
            ])
        return candles[-limit:]

    @staticmethod
    def _period_for(interval: str, limit: int) -> str:
        # yfinance limits intraday history; use the max supported period.
        if interval == "1m":
            return "7d"
        if interval in ("5m", "15m", "30m"):
            return "60d"
        if interval in ("1h", "4h"):
            return "730d"
        if interval == "1d":
            return f"{max(limit, 60)}d"
        if interval == "1wk":
            return f"{max(limit, 60)}mo"
        return f"{max(limit, 60)}mo"

    def last_price(self, symbol: str) -> float:
        df = self.yf.Ticker(symbol).history(period="1d", interval="1m")
        if df.empty:
            raise RuntimeError(f"Could not get last price for {symbol}")
        return float(df["Close"].iloc[-1])


class AlpacaPriceFeed(PriceFeed):
    """Alpaca market data (real-time bars, no delay).

    Used by AlpacaBroker so the bot trades on the broker's own data feed
    rather than a third-party source (yfinance), which can be delayed.
    """

    # timeframe string -> (multiplier, TimeFrameUnit name)
    _TIMEFRAME = {
        "1m": (1, "Minute"),
        "5m": (5, "Minute"),
        "15m": (15, "Minute"),
        "30m": (30, "Minute"),
        "1h": (1, "Hour"),
        "4h": (4, "Hour"),
        "1d": (1, "Day"),
        "1wk": (1, "Week"),
        "1mo": (1, "Month"),
    }

    # approximate minutes per bar, used to compute a fetch start time
    _MINUTES_PER_BAR = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440, "1wk": 10080, "1mo": 43200,
    }

    def __init__(self, api_key: str, api_secret: str):
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        self._client = StockHistoricalDataClient(api_key, api_secret)
        self._TimeFrame = TimeFrame
        self._TimeFrameUnit = TimeFrameUnit

    def _timeframe(self, timeframe: str):
        amount, unit = self._TIMEFRAME.get(timeframe, (1, "Hour"))
        return self._TimeFrame(amount, getattr(self._TimeFrameUnit, unit))

    def _start(self, timeframe: str, limit: int):
        import datetime
        minutes = self._MINUTES_PER_BAR.get(timeframe, 60) * (limit + 50)
        # Intraday bars only exist during market hours (~6.5h/day), so widen
        # the calendar window to ensure we fetch enough bars.
        if timeframe in ("1m", "5m", "15m", "30m", "1h", "4h"):
            minutes = int(minutes * 4)
        return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        from alpaca.data.requests import StockBarsRequest
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=self._timeframe(timeframe),
            start=self._start(timeframe, limit),
        )
        bars = _retry_call(self._client.get_stock_bars, req).df
        if bars is None or bars.empty:
            return []
        df = bars.reset_index()
        candles = []
        for _, row in df.iterrows():
            ts = row.get("timestamp")
            if ts is None:
                continue
            candles.append([
                int(ts.timestamp() * 1000),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
            ])
        return candles[-limit:]

    def last_price(self, symbol: str) -> float:
        candles = self.fetch_ohlcv(symbol, "1m", 1)
        if not candles:
            raise RuntimeError(f"Could not get last price for {symbol}")
        return candles[-1][4]


class ForexPriceFeed(StockPriceFeed):
    """Forex data via yfinance. Accepts 'EUR/USD' or 'EURUSD=X'."""

    @staticmethod
    def _ticker(symbol: str) -> str:
        if symbol.endswith("=X"):
            return symbol
        return symbol.replace("/", "") + "=X"

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return super().fetch_ohlcv(self._ticker(symbol), timeframe, limit)

    def last_price(self, symbol: str) -> float:
        return super().last_price(self._ticker(symbol))


def build_price_feed(market: str, exchange_id: str = "") -> PriceFeed:
    if market == "crypto":
        return CryptoPriceFeed(exchange_id)
    if market == "stock":
        return StockPriceFeed()
    if market == "forex":
        return ForexPriceFeed()
    raise ValueError(f"Unknown market: {market!r}")
