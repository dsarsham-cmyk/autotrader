"""Web dashboard: view live bot status from state.json.

Usage:
    python dashboard.py            # serves on http://127.0.0.1:8050

Reads the state file written by bot.py and renders a self-refreshing page
with balance, equity, risk status, strategy/config, per-symbol budget/P&L,
per-symbol signal details, P&L evolution, recent trades, and a live activity
log.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template_string

STATE_FILE = "state_low.json"       # primary (low-risk) bot
STATE_FILE_HIGH = "state_high.json"  # high-risk bot
STATE_FILE_CSMOM = "csmom_dashboard.json"  # leveraged momentum runner
CONFIG_FILE = "config_low.yaml"
LOG_FILE = "logs/trader_low.log"

app = Flask(__name__)

# Human-friendly labels for common ETFs (fallback: the ticker itself).
REGION_LABELS = {
    "QQQ": "US · Nasdaq 100", "SPY": "US · S&P 500", "DIA": "US · Dow Jones",
    "TQQQ": "US · Nasdaq 100 (3x)", "SPXL": "US · S&P 500 (3x)",
    "SOXL": "US · Semiconductors (3x)", "UPRO": "US · S&P 500 (3x)",
    "TNA": "US · Small Cap (3x)", "FAS": "US · Financials (3x)",
    "IWM": "US · Russell 2000", "EWJ": "Japan", "EWU": "UK", "EWG": "Germany",
    "EWQ": "France", "EZU": "Eurozone", "FEZ": "Euro Stoxx 50", "EWP": "Spain",
    "EWI": "Italy", "EEM": "Emerging Markets", "FXI": "China", "EWH": "Hong Kong",
    "EWY": "South Korea", "EWT": "Taiwan", "EWZ": "Brazil", "INDA": "India",
    "EWA": "Australia", "EWC": "Canada",
}

COLORS = ["#4ade80", "#f87171", "#60a5fa", "#fbbf24", "#c084fc", "#34d399",
          "#f472b6", "#fb923c", "#22d3ee", "#a3e635"]

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Auto Trader</title>
  <meta http-equiv="refresh" content="5">
  <style>
    :root { --bg:#0f1115; --card:#1a1d24; --line:#2a2e38; --txt:#e6e6e6;
            --muted:#8b8f98; --green:#4ade80; --red:#f87171; --amber:#fbbf24; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
           background: var(--bg); color: var(--txt); }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 24px; }
    h1 { font-size: 20px; margin: 0 0 4px; }
    .sub { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
    .grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
    .card { background: var(--card); border-radius: 10px; padding: 16px 20px; }
    .card + .card { margin-top: 18px; }
    .stat { flex: 1; min-width: 150px; }
    .stat .label { color: var(--muted); font-size: 12px; text-transform: uppercase;
                   letter-spacing: .04em; }
    .stat .value { font-size: 24px; font-weight: 600; margin-top: 4px; }
    .pos { color: var(--green); } .neg { color: var(--red); } .amb { color: var(--amber); }
    .badge { display:inline-block; padding: 2px 9px; border-radius: 20px;
             font-size: 12px; font-weight: 600; }
    .badge.open { background: rgba(74,222,128,.15); color: var(--green); }
    .badge.closed { background: rgba(248,113,113,.15); color: var(--red); }
    .badge.halt { background: rgba(248,113,113,.15); color: var(--red); }
    .badge.ok { background: rgba(74,222,128,.15); color: var(--green); }
    .badge.buy { background: rgba(74,222,128,.15); color: var(--green); }
    .badge.sell { background: rgba(248,113,113,.15); color: var(--red); }
    .badge.hold { background: rgba(139,143,152,.15); color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--line); }
    th:first-child, td:first-child { text-align: left; }
    th { color: var(--muted); font-weight: 500; font-size: 12px;
         text-transform: uppercase; letter-spacing: .03em; }
    .sym { font-weight: 600; }
    .region { color: var(--muted); font-size: 12px; }
    svg { width: 100%; height: 220px; display:block; }
    h2 { font-size: 15px; margin: 0 0 12px; }
    .legend { font-size: 13px; margin-top: 10px; display:flex; gap:14px; flex-wrap:wrap; }
    .legend span { white-space: nowrap; }
    .kv { font-size: 13px; color: var(--muted); line-height: 1.6; }
    .kv b { color: var(--txt); font-weight: 600; }
    .log { font-family: ui-monospace, Consolas, monospace; font-size: 12px;
           color: var(--muted); line-height: 1.7; white-space: pre-wrap; }
    .sigrow { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
    .sigrow .sym { min-width: 48px; }
    .detail { color: var(--muted); font-size: 13px; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>📈 Auto Trader</h1>
  <div class="sub">Live paper-trading status · updates every 5s</div>

  <div class="card">
    <h2>Risk scenarios — side by side</h2>
    <table>
      <tr><th>Scenario</th><th>Equity</th><th>Today's P&amp;L</th><th>Drawdown</th>
          <th>Positions</th><th>Trades</th><th>Status</th></tr>
      {% for s in scenarios %}
      <tr>
        <td><span class="sym">{{ s.name }}</span></td>
        <td>${{ '%.2f'|format(s.equity) }}</td>
        <td class="{{ 'pos' if s.daily_pnl >= 0 else 'neg' }}">{{ '%+.2f'|format(s.daily_pnl) }}%</td>
        <td class="{{ 'neg' if s.drawdown > 1 else '' }}">{{ '%.2f'|format(s.drawdown) }}%</td>
        <td>{{ s.open_count }}</td>
        <td>{{ s.trades }}</td>
        <td>{% if s.halted %}<span class="badge halt">HALTED</span>{% else %}<span class="badge ok">OK</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div class="grid">
    <div class="card stat"><div class="label">Equity</div>
      <div class="value">${{ '%.2f'|format(equity) }}</div></div>
    <div class="card stat"><div class="label">Cash</div>
      <div class="value">${{ '%.2f'|format(balance) }}</div></div>
    <div class="card stat"><div class="label">Open Positions</div>
      <div class="value">{{ total_open_count }}</div></div>
    <div class="card stat"><div class="label">Market</div>
      <div class="value" style="font-size:18px">
        {% if market_open %}<span class="badge open">OPEN</span>
        {% else %}<span class="badge closed">CLOSED</span>{% endif %}
      </div></div>
    <div class="card stat"><div class="label">Trades</div>
      <div class="value">{{ trades|length }}</div></div>
  </div>

  <div class="grid">
    <div class="card stat"><div class="label">Drawdown</div>
      <div class="value {{ 'neg' if drawdown_pct > 1 else '' }}">{{ '%.2f'|format(drawdown_pct) }}%</div></div>
    <div class="card stat"><div class="label">Today's P&amp;L</div>
      <div class="value {{ 'pos' if daily_pnl_pct >= 0 else 'neg' }}">{{ '%+.2f'|format(daily_pnl_pct) }}%</div></div>
    <div class="card stat"><div class="label">Risk Status</div>
      <div class="value" style="font-size:18px">
        {% if halted %}<span class="badge halt">HALTED</span>
        {% else %}<span class="badge ok">OK</span>{% endif %}
      </div></div>
    <div class="card stat"><div class="label">Strategy</div>
      <div class="value" style="font-size:16px">{{ strategy_name }}</div></div>
    <div class="card stat"><div class="label">Timeframe</div>
      <div class="value" style="font-size:16px">{{ timeframe }}</div></div>
  </div>

  <div class="card">
    <h2>Strategy &amp; configuration</h2>
    <div class="kv">
      <b>Strategy:</b> {{ strategy_name }} &nbsp;·&nbsp;
      <b>Params:</b> {{ strategy_params }} &nbsp;·&nbsp;
      <b>Mode:</b> {{ mode }} &nbsp;·&nbsp; <b>Market:</b> {{ market }}<br>
      <b>Risk:</b> {{ risk_per_trade }} per trade · {{ atr_stop_mult }}×ATR stop ·
      {{ atr_take_mult }}×ATR take · {{ daily_loss_limit }} daily-loss limit ·
      {{ max_drawdown }} max-drawdown kill switch<br>
      <b>Day trading:</b> {{ 'close at ' ~ eod_close_time if close_at_eod else 'off' }}
      {% if halt_reason %} &nbsp;·&nbsp; <span class="neg"><b>Halted:</b> {{ halt_reason }}</span>{% endif %}
    </div>
  </div>

  <div class="card">
    <h2>Open positions</h2>
    {% if open_positions %}
    <table>
      <tr><th>Scenario</th><th>Symbol</th><th>Region</th><th>Qty</th>
          <th>Entry</th><th>Current</th><th>Stop</th><th>Take</th><th>Unrealized</th></tr>
      {% for p in open_positions %}
      <tr>
        <td><span class="badge {{ 'ok' if p.scenario == 'LOW RISK' else 'amb' }}">{{ p.scenario }}</span></td>
        <td><span class="sym">{{ p.symbol }}</span></td>
        <td><span class="region">{{ p.region }}</span></td>
        <td>{{ '%.2f'|format(p.qty) }}</td>
        <td>{{ '%.2f'|format(p.entry) }}</td>
        <td>{{ '%.2f'|format(p.current) }}</td>
        <td>{{ '%.2f'|format(p.stop) if p.stop else '—' }}</td>
        <td>{{ '%.2f'|format(p.take) if p.take else '—' }}</td>
        <td class="{{ 'pos' if p.unrealized >= 0 else 'neg' }}">{{ '%+.2f'|format(p.unrealized) }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<p style="color:var(--muted)">No open positions.</p>{% endif %}
  </div>

  <div class="card">
    <h2>Signals &amp; indicators</h2>
    {% if signal_rows %}
    {% for r in signal_rows %}
    <div class="sigrow">
      <span class="sym">{{ r.symbol }}</span>
      {% if r.signal == 'buy' %}<span class="badge buy">BUY</span>
      {% elif r.signal == 'sell' %}<span class="badge sell">SELL</span>
      {% else %}<span class="badge hold">HOLD</span>{% endif %}
      <span class="detail">{{ r.detail }}</span>
    </div>
    {% endfor %}
    {% else %}<p style="color:var(--muted)">Waiting for bot…</p>{% endif %}
  </div>

  <div class="card">
    <h2>Budget &amp; P&amp;L per market</h2>
    {% if rows %}
    <table>
      <tr><th>Symbol</th><th>Region</th><th>Price</th><th>Allocated</th>
          <th>Stop</th><th>Take</th><th>Realized</th><th>Unrealized</th><th>Total</th></tr>
      {% for r in rows %}
      <tr>
        <td><span class="sym">{{ r.symbol }}</span></td>
        <td><span class="region">{{ r.region }}</span></td>
        <td>{{ '%.2f'|format(r.price) if r.price else '—' }}</td>
        <td>{{ '%.2f'|format(r.allocated) if r.allocated > 0 else '—' }}</td>
        <td>{{ '%.2f'|format(r.stop) if r.stop else '—' }}</td>
        <td>{{ '%.2f'|format(r.take) if r.take else '—' }}</td>
        <td class="{{ 'pos' if r.realized >= 0 else 'neg' }}">{{ '%+.2f'|format(r.realized) }}</td>
        <td class="{{ 'pos' if r.unrealized >= 0 else 'neg' }}">{{ '%+.2f'|format(r.unrealized) }}</td>
        <td class="{{ 'pos' if r.total >= 0 else 'neg' }}"><strong>{{ '%+.2f'|format(r.total) }}</strong></td>
      </tr>
      {% endfor %}
      <tr style="border-top:2px solid var(--line)">
        <td><span class="sym">TOTAL</span></td><td></td><td></td>
        <td>{{ '%.2f'|format(total_allocated) }}</td><td></td><td></td>
        <td class="{{ 'pos' if total_realized >= 0 else 'neg' }}">{{ '%+.2f'|format(total_realized) }}</td>
        <td class="{{ 'pos' if total_unrealized >= 0 else 'neg' }}">{{ '%+.2f'|format(total_unrealized) }}</td>
        <td class="{{ 'pos' if total_pnl >= 0 else 'neg' }}"><strong>{{ '%+.2f'|format(total_pnl) }}</strong></td>
      </tr>
    </table>
    {% else %}<p style="color:var(--muted)">Waiting for bot to report symbols…</p>{% endif %}
  </div>

  <div class="card">
    <h2>P&amp;L evolution per market</h2>
    {{ pnl_chart|safe }}
    {% if pnl_legend %}<div class="legend">{{ pnl_legend|safe }}</div>{% endif %}
  </div>

  <div class="card">
    <h2>Total equity</h2>
    {{ chart_svg|safe }}
  </div>

  <div class="card">
    <h2>Recent activity</h2>
    {% if log_tail %}<div class="log">{{ log_tail }}</div>
    {% else %}<p style="color:var(--muted)">No activity yet.</p>{% endif %}
  </div>

  <div class="card">
    <h2>Recent trades</h2>
    {% if trades %}
    <table><tr><th>Time</th><th>Side</th><th>Symbol</th><th>Price</th>
      <th>Amount</th><th>Value</th></tr>
    {% for t in trades[-20:]|reverse %}
      <tr><td style="color:var(--muted)">{{ t.ts[11:19] }}</td>
      <td class="{{ 'pos' if t.side == 'buy' else 'neg' }}">{{ t.side.upper() }}</td>
      <td><span class="sym">{{ t.symbol }}</span></td>
      <td>{{ '%.2f'|format(t.price) }}</td>
      <td>{{ '%.4f'|format(t.base_amount) }}</td>
      <td>{{ '%.2f'|format(t.quote_amount) }}</td></tr>
    {% endfor %}</table>
    {% else %}<p style="color:var(--muted)">No trades yet.</p>{% endif %}
  </div>

  <div class="sub" style="margin-top:18px">Last update: {{ last_updated }}</div>
</div>
</body>
</html>
"""


def load_state(path: str = STATE_FILE) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> dict:
    p = Path(CONFIG_FILE)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}


def region(symbol: str) -> str:
    return REGION_LABELS.get(symbol, symbol)


def format_details(details: dict) -> str:
    if not details:
        return ""
    parts = []
    for k, v in details.items():
        if isinstance(v, float):
            parts.append(f"{k} {v:.4f}")
        else:
            parts.append(f"{k} {v}")
    return " · ".join(parts)


def log_tail(n: int = 20) -> str:
    p = Path(LOG_FILE)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def equity_chart_svg(equity_history) -> str:
    if len(equity_history) < 2:
        return "<p style='color:var(--muted)'>Not enough data for a chart.</p>"
    values = [e["equity"] for e in equity_history]
    w, h = 900, 220
    pad = 20
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = h - pad - (h - 2 * pad) * (v - lo) / (hi - lo)
        pts.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(pts)
    color = "#4ade80" if values[-1] >= values[0] else "#f87171"
    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" '
        f'stroke-width="2"/></svg>'
    )


def pnl_chart_svg(pnl_history, symbols) -> str:
    series = {}
    for s in symbols:
        vals = [pt["pnl"] for pt in pnl_history.get(s, [])]
        if len(vals) >= 2:
            series[s] = vals
    if not series:
        return "<p style='color:var(--muted)'>Not enough P&L history yet.</p>"

    all_vals = [v for vals in series.values() for v in vals]
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        hi = lo + 1
    w, h = 900, 240
    pad = 20
    max_n = max(len(v) for v in series.values())
    lines = []
    for i, (s, vals) in enumerate(series.items()):
        color = COLORS[i % len(COLORS)]
        pts = []
        for j, v in enumerate(vals):
            x = pad + (w - 2 * pad) * j / (max_n - 1)
            y = h - pad - (h - 2 * pad) * (v - lo) / (hi - lo)
            pts.append(f"{x:.1f},{y:.1f}")
        lines.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
    y0 = h - pad - (h - 2 * pad) * (0 - lo) / (hi - lo)
    zero = (f'<line x1="{pad}" y1="{y0:.1f}" x2="{w - pad}" y2="{y0:.1f}" '
            f'stroke="#2a2e38" stroke-width="1"/>')
    return f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{zero}{"".join(lines)}</svg>'


def pnl_legend(pnl_history, symbols) -> str:
    items = []
    for i, s in enumerate(symbols):
        if len(pnl_history.get(s, [])) >= 2:
            color = COLORS[i % len(COLORS)]
            items.append(f'<span style="color:{color}">● {s}</span>')
    return " ".join(items)


@app.route("/")
def index():
    state = load_state()
    high_state = load_state(STATE_FILE_HIGH)
    csmom_state = load_state(STATE_FILE_CSMOM)
    config = load_config()

    def scenario_summary(name, s):
        bal = s.get("balance", 0.0)
        eq = s.get("equity", bal)
        positions = s.get("positions", {})
        return {
            "name": name,
            "equity": eq,
            "daily_pnl": s.get("daily_pnl_pct", 0.0),
            "drawdown": s.get("drawdown_pct", 0.0),
            "open_count": sum(1 for p in positions.values() if p.get("base_amount", 0) > 0),
            "trades": len(s.get("trades", [])),
            "halted": bool(s.get("halted", False)),
        }

    scenarios = [
        scenario_summary("LOW RISK", state),
        scenario_summary("HIGH RISK", high_state),
        scenario_summary(csmom_state.get("name", "RANGE+MOMENTUM"), csmom_state),
    ]

    balance = state.get("balance", 0.0)
    equity = state.get("equity", balance)
    market_open = bool(state.get("market_open", False))
    symbols = state.get("symbols", [])
    prices = state.get("prices", {})
    signals = state.get("signals", {})
    signal_details = state.get("signal_details", {})
    positions = state.get("positions", {})
    high_positions = high_state.get("positions", {})
    high_prices = high_state.get("prices", {})
    csmom_positions = csmom_state.get("positions", {})
    csmom_prices = csmom_state.get("prices", {})
    trades = state.get("trades", [])
    equity_history = state.get("equity_history", [])
    pnl = state.get("pnl", {})
    pnl_history = state.get("pnl_history", {})
    drawdown_pct = state.get("drawdown_pct", 0.0)
    daily_pnl_pct = state.get("daily_pnl_pct", 0.0)
    halted = bool(state.get("halted", False))
    halt_reason = state.get("halt_reason", "")
    last_updated = state.get("last_updated", "—")
    open_count = sum(1 for p in positions.values() if p.get("base_amount", 0) > 0)
    high_open_count = sum(1 for p in high_positions.values() if p.get("base_amount", 0) > 0)
    total_open_count = open_count + high_open_count

    # Combined open positions across both risk scenarios.
    open_positions = []
    for scenario, pos_map, price_map in (
        ("LOW RISK", positions, prices),
        ("HIGH RISK", high_positions, high_prices),
        (csmom_state.get("name", "RANGE+MOMENTUM"), csmom_positions, csmom_prices),
    ):
        for sym, p in pos_map.items():
            qty = p.get("base_amount", 0.0)
            if qty <= 0:
                continue
            entry = p.get("entry_price", 0.0)
            stop = p.get("stop_price", 0.0)
            take = p.get("take_price", 0.0)
            cur = price_map.get(sym, entry)
            unrealized = (cur - entry) * qty
            open_positions.append({
                "scenario": scenario, "symbol": sym, "region": region(sym),
                "qty": qty, "entry": entry, "current": cur,
                "stop": stop, "take": take, "unrealized": unrealized,
            })

    # Strategy / config info.
    strat_cfg = config.get("strategy", {})
    strategy_name = strat_cfg.get("name", "—")
    strategy_params = ", ".join(f"{k}={v}" for k, v in strat_cfg.items() if k != "name")
    risk_cfg = config.get("risk", {})
    dt_cfg = config.get("day_trading", {})
    mode = config.get("mode", "—")
    market = config.get("market", "—")
    timeframe = (config.get("stock", {}).get("timeframe")
                 or config.get("exchange", {}).get("timeframe")
                 or config.get("forex", {}).get("timeframe") or "—")
    risk_per_trade = f"{risk_cfg.get('risk_per_trade', 0.01) * 100:.0f}%"
    atr_stop_mult = risk_cfg.get("atr_stop_mult", 2.0)
    atr_take_mult = risk_cfg.get("atr_take_mult", 3.0)
    daily_loss_limit = f"{risk_cfg.get('daily_loss_limit_pct', 0.03) * 100:.0f}%"
    max_drawdown = f"{risk_cfg.get('max_drawdown_pct', 0.20) * 100:.0f}%"
    close_at_eod = bool(dt_cfg.get("close_at_eod", False))
    eod_close_time = dt_cfg.get("eod_close_time", "22:55")

    # Signal rows (symbol, signal, detail).
    signal_rows = []
    for s in symbols:
        signal_rows.append({
            "symbol": s,
            "signal": signals.get(s, "hold"),
            "detail": format_details(signal_details.get(s, {})),
        })

    # Budget/P&L rows.
    rows = []
    total_allocated = total_realized = total_unrealized = 0.0
    for s in symbols:
        p = prices.get(s)
        pos = positions.get(s, {})
        qty = pos.get("base_amount", 0.0)
        entry = pos.get("entry_price", 0.0)
        stop = pos.get("stop_price", 0.0)
        take = pos.get("take_price", 0.0)
        allocated = qty * p if p else 0.0
        realized = pnl.get(s, 0.0)
        unrealized = (p - entry) * qty if (p and qty > 0) else 0.0
        total = realized + unrealized
        total_allocated += allocated
        total_realized += realized
        total_unrealized += unrealized
        rows.append({
            "symbol": s, "region": region(s), "price": p,
            "allocated": allocated, "stop": stop, "take": take,
            "realized": realized, "unrealized": unrealized, "total": total,
        })
    total_pnl = total_realized + total_unrealized

    return render_template_string(
        PAGE,
        scenarios=scenarios,
        balance=balance, equity=equity, market_open=market_open,
        open_count=open_count, total_open_count=total_open_count,
        open_positions=open_positions,
        trades=trades, last_updated=last_updated,
        drawdown_pct=drawdown_pct, daily_pnl_pct=daily_pnl_pct,
        halted=halted, halt_reason=halt_reason,
        strategy_name=strategy_name, strategy_params=strategy_params,
        mode=mode, market=market, timeframe=timeframe,
        risk_per_trade=risk_per_trade, atr_stop_mult=atr_stop_mult,
        atr_take_mult=atr_take_mult, daily_loss_limit=daily_loss_limit,
        max_drawdown=max_drawdown, close_at_eod=close_at_eod,
        eod_close_time=eod_close_time,
        signal_rows=signal_rows,
        rows=rows, total_allocated=total_allocated,
        total_realized=total_realized, total_unrealized=total_unrealized,
        total_pnl=total_pnl,
        chart_svg=equity_chart_svg(equity_history),
        pnl_chart=pnl_chart_svg(pnl_history, symbols),
        pnl_legend=pnl_legend(pnl_history, symbols),
        log_tail=log_tail(20),
    )


@app.route("/api/state")
def api_state():
    return jsonify(load_state())


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8050"))
    app.run(host="0.0.0.0", port=port, debug=False)
