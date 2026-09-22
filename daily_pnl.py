"""Read-only daily portfolio attribution, including positions closed today.

P&L = current marked value - previous-close inventory value
      + today's sale proceeds - today's purchase costs.
Previous-close inventory is reconstructed from current quantity and every
individual fill (never cum_qty or a deduplicated order summary).
Dividends, fees, transfers, corporate actions and quote timing can leave an
explicit unallocated difference versus the broker account equity change.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
import json

EASTERN = ZoneInfo("America/New_York")
_CLOSE_CACHE = {}


def _get(url, key, secret):
    request = Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
    })
    try:
        with urlopen(request, timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Daily accounting API returned HTTP {exc.code}") from None


def activities_today(key, secret, now):
    """Read all pages; fail rather than silently truncate a busy trading day."""
    start = now.astimezone(EASTERN).replace(hour=0, minute=0, second=0, microsecond=0)
    return activities_between(key, secret, start, now)


def activities_between(key, secret, start, end):
    """One activity ID per execution, preserving partial-fill quantities."""
    params = {"after": start.isoformat(), "until": end.isoformat(),
              "direction": "asc", "page_size": 100}
    seen = set()
    result = []
    for _ in range(100):
        page = _get("https://paper-api.alpaca.markets/v2/account/activities?"
                    + urlencode(params), key, secret)
        if not isinstance(page, list):
            raise ValueError("Invalid activity response")
        for item in page:
            ident = item.get("id")
            if not ident:
                raise ValueError("Activity has no identifier")
            if ident not in seen:
                seen.add(ident)
                result.append(item)
        if len(page) < 100:
            return result
        token = page[-1]["id"]
        if token == params.get("page_token"):
            raise ValueError("Activity pagination did not advance")
        params["page_token"] = token
    raise ValueError("Activity pagination limit reached")


def previous_close(symbol, key, secret, now):
    """SIP raw daily close for an asset fully sold today; never today's bar."""
    day = now.astimezone(EASTERN).date()
    cache_key = (symbol, day.isoformat())
    if cache_key not in _CLOSE_CACHE:
        end = datetime.combine(day, datetime.min.time(), EASTERN)
        params = {"start": (end-timedelta(days=14)).isoformat(),
                  "end": end.isoformat(), "timeframe": "1Day",
                  "adjustment": "raw", "feed": "sip", "sort": "desc", "limit": 10}
        data = _get(f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?"
                    + urlencode(params), key, secret)
        bars = [bar for bar in data.get("bars", [])
                if datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
                .astimezone(EASTERN).date() < day]
        if not bars:
            raise ValueError(f"Previous close unavailable for {symbol}")
        _CLOSE_CACHE.clear() if len(_CLOSE_CACHE) > 100 else None
        _CLOSE_CACHE[cache_key] = float(bars[0]["c"])
    return _CLOSE_CACHE[cache_key]


def calculate_daily(meta, positions, activities, closes, account_change, now):
    dec = lambda v: Decimal(str(v))
    day = now.astimezone(EASTERN).date().isoformat()
    owner = {}
    for key, scenario in meta.items():
        for symbol in scenario["symbols"]:
            if symbol in owner:
                raise ValueError("Portfolio symbols overlap")
            owner[symbol] = key
    fills = []
    seen = set()
    for a in activities:
        if a.get("activity_type") != "FILL":
            if a.get("symbol") in owner and a.get("activity_type") in {
                "SPLIT", "SPIN", "MA", "REORG", "JNLS",
            }:
                raise ValueError("Corporate action requires separate daily reconciliation")
            continue
        ident = a["id"]
        if ident in seen:
            continue
        seen.add(ident)
        ts = datetime.fromisoformat(a["transaction_time"].replace("Z", "+00:00"))
        if ts.astimezone(EASTERN).date().isoformat() != day:
            continue
        if a["side"] not in {"buy", "sell"}:
            raise ValueError("Unsupported fill side")
        if dec(a["qty"]) <= 0 or dec(a["price"]) < 0:
            raise ValueError("Invalid execution quantity or price")
        fills.append(a)
    result = {}
    for key, scenario in meta.items():
        total = Decimal(0)
        breakdown = []
        for symbol in scenario["symbols"]:
            trades = [a for a in fills if a["symbol"] == symbol]
            pos = positions.get(symbol, {})
            quantity = dec(pos.get("qty", 0))
            net = sum((dec(a["qty"]) * (1 if a["side"] == "buy" else -1)
                       for a in trades), Decimal(0))
            initial = quantity - net
            if abs(initial) < Decimal("0.00000001"):
                initial = Decimal(0)
            if initial and (symbol not in closes or dec(closes[symbol]) <= 0):
                raise ValueError(f"Previous close missing for {symbol}")
            baseline = initial * dec(closes.get(symbol, 0))
            cash = sum((dec(a["qty"]) * dec(a["price"])
                        * (1 if a["side"] == "sell" else -1) for a in trades), Decimal(0))
            pnl = dec(pos.get("market_value", 0)) - baseline + cash
            total += pnl
            if quantity or trades or initial:
                breakdown.append({"symbol": symbol, "day_pnl": round(float(pnl), 2),
                                  "start_qty": float(initial), "current_qty": float(quantity),
                                  "previous_close": closes.get(symbol),
                                  "execution_count": len(trades)})
        result[key] = {"day_pnl": round(float(total), 2), "market_date": day,
                       "daily_buy_executions": sum(a["side"] == "buy" and a["symbol"] in scenario["symbols"] for a in fills),
                       "daily_sell_executions": sum(a["side"] == "sell" and a["symbol"] in scenario["symbols"] for a in fills),
                       "daily_symbols": breakdown}
    subtotal = sum(v["day_pnl"] for v in result.values())
    residual = None if account_change is None else round(float(account_change) - subtotal, 2)
    return {"status": "calculated", "market_date": day,
            "generated_at": now.isoformat(), "portfolios": result,
            "portfolio_day_pnl": round(subtotal, 2),
            "unallocated_day_pnl": residual,
            "buy_executions": sum(a["side"] == "buy" for a in fills),
            "sell_executions": sum(a["side"] == "sell" for a in fills),
            "executions": [{"execution_id": a["id"], "order_id": a.get("order_id"),
                            "time": a["transaction_time"], "symbol": a["symbol"],
                            "side": a["side"], "qty": float(a["qty"]),
                            "price": float(a["price"])} for a in reversed(fills)],
            "note": "Daily marked trading P&L, including today's closed trades. "
                    "Fees, dividends, transfers, unassigned assets and sampling differences "
                    "remain in the unallocated account change; not guaranteed net profit."}


def build_daily(meta, positions, key, secret, account_change, now):
    activities = activities_today(key, secret, now)
    closes = {s: p["previous_close"] for s, p in positions.items()
              if p.get("previous_close") is not None}
    symbols = {a["symbol"] for a in activities if a.get("activity_type") == "FILL"}
    assigned = {s for m in meta.values() for s in m["symbols"]}
    for symbol in symbols & assigned:
        if symbol not in closes:
            # A same-day round trip needs no prior close, but retrieving it
            # also covers an overnight holding completely sold today.
            closes[symbol] = previous_close(symbol, key, secret, now)
    return calculate_daily(meta, positions, activities, closes, account_change, now)
