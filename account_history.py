"""Complete paginated execution history and broker end-of-day account values.

No inference of P&L from order prices or rolling samples. Daily equity change
is calculated from successive broker equity values, not the API's potentially
cumulative profit_loss series. The first funded point is a baseline, not profit.
"""
from datetime import datetime, timedelta, timezone
import time
from daily_pnl import _get, activities_between, EASTERN

_CACHE = {}


def compact_executions(activities):
    result = []
    seen = set()
    for a in activities:
        if a.get("activity_type") != "FILL" or a["id"] in seen:
            continue
        seen.add(a["id"])
        result.append({"execution_id": a["id"], "order_id": a.get("order_id"),
                       "time": a["transaction_time"], "symbol": a["symbol"],
                       "side": a["side"], "qty": float(a["qty"]),
                       "price": float(a["price"])})
    return sorted(result, key=lambda x: x["time"], reverse=True)


def history_base(key, secret, now):
    """Past days are cached for five minutes; today's executions are fresh."""
    day = now.astimezone(EASTERN).date().isoformat()
    cache_key = (key, day)
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    end = now.astimezone(EASTERN).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=32)
    raw = _get("https://paper-api.alpaca.markets/v2/account/portfolio/history?"
               "period=1M&timeframe=1D", key, secret)
    activities = activities_between(key, secret, start, end)
    value = {"raw": raw, "activities": activities,
             "fetched_at": now.isoformat(), "coverage_start": start.date().isoformat()}
    _CACHE.clear()
    _CACHE[cache_key] = (time.monotonic(), value)
    return value


def build_history(base, today_executions, account, now, market_open):
    today = now.astimezone(EASTERN).date().isoformat()
    executions = compact_executions(base["activities"])
    # Do not overlap the cached midnight boundary with today's fresh ledger.
    executions = [x for x in executions if _day(x["time"]) < today]
    current = today_executions
    if current is not None:
        executions += current
    executions.sort(key=lambda x: x["time"], reverse=True)
    by_day = {}
    for x in executions:
        by_day.setdefault(_day(x["time"]), []).append(x)
    raw = base["raw"]
    if len(raw.get("timestamp", [])) != len(raw.get("equity", [])):
        raise ValueError("Broker history timestamps and equity do not match")
    points = sorted(zip(raw.get("timestamp", []), raw.get("equity", [])))
    daily_points = {}
    for stamp, equity in points:
        date = datetime.fromtimestamp(stamp, timezone.utc).astimezone(EASTERN).date().isoformat()
        if date < today:
            daily_points[date] = equity
    rows = []
    previous = None
    started = False
    for date, equity in sorted(daily_points.items()):
        if not started and (equity is None or equity <= 0):
            continue
        change = round(equity - previous, 2) if equity is not None and previous is not None else None
        pct = round(change / previous * 100, 3) if change is not None and previous else None
        rows.append(_row(date, equity, change, pct, by_day.get(date, []), True,
                         "baseline" if not started else
                         ("closed" if change is not None else "missing_equity")))
        previous = equity
        started = True
    # Current date is explicitly a latest mark, never a fabricated final close.
    if account.get("equity") is not None:
        rows.append(_row(today, account["equity"], account.get("day_pnl"),
                         account.get("day_pnl_pct"), by_day.get(today, []),
                         current is not None, "intraday" if market_open else "latest"))
    # Preserve fills even on dates for which the broker supplies no equity point.
    known = {r["date"] for r in rows}
    for date in sorted(by_day):
        if date not in known:
            rows.append(_row(date, None, None, None, by_day[date], True, "missing_equity"))
    rows.sort(key=lambda row: row["date"], reverse=True)
    return {"status": "available", "timezone": "America/New_York",
            "past_days_updated_at": base["fetched_at"],
            "coverage_start": base["coverage_start"], "days": rows,
            "executions": executions,
            "note": "Daily account equity change, not guaranteed realized profit. "
                    "Includes holdings' price changes and may include transfers or "
                    "other account adjustments. First funded observation is a baseline. "
                    "Partial fills count as separate executions. Past portfolio attribution "
                    "and historical open-position lists are not reconstructed."}


def _day(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(EASTERN).date().isoformat()


def _row(date, equity, change, pct, executions, complete, status):
    return {"date": date, "equity": equity, "day_change": change, "day_change_pct": pct,
            "status": status, "executions_complete": complete,
            "buys": sum(x["side"] == "buy" for x in executions) if complete else None,
            "sells": sum(x["side"] == "sell" for x in executions) if complete else None,
            "execution_count": len(executions) if complete else None,
            "order_count": len({x.get("order_id") for x in executions if x.get("order_id")}) if complete and all(x.get("order_id") for x in executions) else None,
            "executions": executions}
