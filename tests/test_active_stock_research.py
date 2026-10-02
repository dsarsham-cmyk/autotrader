import numpy as np
import pytest
from active_stock_research import rank, replay, RULES, main, hash_file, download_edges


def stock(ratio=3):
    bars=np.tile([100.,101.,99.,100.,1000.],(390,1))
    info=dict(relative_volume=ratio,prior_dollars=100000000,
              opening_price=100.,opening_high=101.,stop=99.)
    return bars,info


def test_rank_uses_opening_relative_volume_and_deterministic_ties():
    assert rank({"B":stock(4),"A":stock(4),"C":stock(1)}) == ["A","B"]


def test_portfolio_no_leverage_and_one_attempt_per_symbol():
    stocks={f"S{i}":stock() for i in range(5)}
    for bars,_ in stocks.values():
        bars[5,3]=102
        bars[6:,2]=100
    daily,trades,signals=replay({"2026-09-01":stocks})
    assert len(trades)==5
    assert sum(t["quantity"]*t["entry"] for t in trades)<=75000
    assert len([s for s in signals if s["event"]=="signal"])==5
    assert all(t["exit_minute"]==385 for t in trades)
    assert daily[-1]["equity"]>0


def test_next_minute_signal_no_same_bar_fill():
    bars,info=stock()
    bars[5,3]=102
    daily,trades,_=replay({"2026-09-01":{"A":(bars,info)}})
    assert trades[0]["entry_minute"]==6
    assert trades[0]["reason"]=="entry_bar_stop"
    assert daily[0]["return_pct"]>=-.101


def test_fill_above_known_limit_rejected():
    bars,info=stock()
    bars[5,3]=102
    bars[6,0]=104
    _,trades,signals=replay({"2026-09-01":{"A":(bars,info)}})
    assert not trades
    assert any(s["event"]=="fill_rejected" for s in signals)


def test_daily_exit_still_works_after_entry_halt(monkeypatch):
    # Force a deterministic guard sequence: pause then larger adverse move.
    monkeypatch.setitem(RULES,"daily_entry_cutoff",.0001)
    monkeypatch.setitem(RULES,"daily_exit_trigger",.0002)
    bars,info=stock()
    bars[5,3]=102
    bars[6:,2]=100
    bars[6,2]=99.8
    bars[7,2]=99.4
    _,trades,_=replay({"2026-09-01":{"A":(bars,info)}})
    assert trades[0]["reason"]=="account_guard"
    assert trades[0]["exit_minute"]==8


def test_future_day_cannot_change_prefix():
    first={"2026-09-01":{"A":stock()}}
    future={**first,"2026-09-02":{"A":stock(100)}}
    assert replay(first)[0] == replay(future)[0][:1]


def test_permanent_drawdown_halt_carries_to_next_session(monkeypatch):
    monkeypatch.setitem(RULES,"permanent_drawdown",.0002)
    bars,info=stock()
    bars[5,3]=102
    daily,trades,_=replay({"2026-09-01":{"A":(bars,info)},
                          "2026-09-02":{"A":(bars.copy(),info.copy())}})
    assert len(trades)==1
    assert daily[0]["permanent_halt"] and daily[1]["permanent_halt"]
    assert daily[1]["pnl"]==0


def test_forward_rejects_changed_source_before_reading_data(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr("sys.argv",["research","--forward","--output",str(tmp_path)])
    (tmp_path/"forward_manifest.json").write_text(json.dumps(dict(rules=RULES,source_hash="tampered")))
    with pytest.raises(ValueError,match="code/rules changed"):
        main()


def test_research_has_no_trading_client_imports():
    import ast
    from pathlib import Path
    source=ast.parse(Path("active_stock_research.py").read_text())
    modules=[node.module for node in ast.walk(source) if isinstance(node,ast.ImportFrom)]
    assert not any(name and (name.startswith("alpaca.trading") or name in ("broker","safe_paper_engine")) for name in modules)


def test_source_hash_portable_but_market_data_hash_byte_exact(tmp_path):
    lf=tmp_path/"lf.py"
    crlf=tmp_path/"crlf.py"
    lf.write_bytes(b"print('test')\n")
    crlf.write_bytes(b"print('test')\r\n")
    assert hash_file(lf)==hash_file(crlf)
    a=tmp_path/"a.csv"
    b=tmp_path/"b.csv"
    a.write_bytes(b"value\n")
    b.write_bytes(b"value\r\n")
    assert hash_file(a)!=hash_file(b)


def test_download_excludes_subscription_restricted_recent_minutes():
    import pandas as pd
    edges=download_edges("2026-09-01","2026-10-03",now=pd.Timestamp("2026-10-02T14:00:00Z"))
    assert edges[-1]==pd.Timestamp("2026-10-02T13:44:00Z")
    older=download_edges("2026-09-01","2026-09-20",now=pd.Timestamp("2026-10-02T14:00:00Z"))
    assert older[-1]==pd.Timestamp("2026-09-20T00:00:00Z")
