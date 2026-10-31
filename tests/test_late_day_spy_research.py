from copy import deepcopy
import json
import pytest
import late_day_spy_research as study


def bars(price=100.):
    return {m:[price,price+.01,price-.01,price,100.] for m in range(570,960)}


def calendar():
    return {'2026-01-02':{'close_minute':960}, '2026-01-05':{'close_minute':960}}


def test_frozen_protocol_and_exact_cases():
    p=study.load_protocol()
    assert p['cases']==[dict(cost_bps_per_side=10,entry_minute_ny=931),
                       dict(cost_bps_per_side=20,entry_minute_ny=931),
                       dict(cost_bps_per_side=10,entry_minute_ny=932)]
    assert p['orders'] is False and p['independent_validation_pass'] is False


def test_signal_future_independence_previous_halfday_and_effective_split():
    cal=calendar();cal['2026-01-02']['close_minute']=780
    sessions={'2026-01-02':bars(200.),'2026-01-05':bars(101.)}
    sessions['2026-01-02'][959]=[400.,400.,400.,400.,100.]
    events=[dict(ex_date='2026-01-05',ratio=2)]
    before=study.signals(sessions,cal,events)
    assert before[-1]['morning_return']==pytest.approx(.01)
    for m in range(600,960):sessions['2026-01-05'][m]=[300.,300.,300.,300.,100.]
    assert study.signals(sessions,cal,events)==before
    assert study.signals(sessions,cal,events+[dict(ex_date='2027-01-01',ratio=10)])==before


def test_entry_price_uses_only_1514_not_future_price():
    b=bars();b[914]=[101.,101.,101.,101.,100.]
    first=study.trade_path(b,10,931)
    b[915]=[10.,10.,10.,10.,100.]
    assert study.trade_path(b,10,931)==first
    assert first['filled'] and first['entry_minute']==931
    assert first['exit_minute']==955 and first['reason']=='scheduled_exit'


def test_stop_entry_bar_and_gap_are_conservative():
    b=bars();b[914]=[101.,101.,101.,101.,100.]
    b[931]=[100.,101.,98.,100.,100.]
    o=study.trade_path(b,10,931)
    assert o['exit']==pytest.approx(99*.999)
    b=bars();b[914]=[101.,101.,101.,101.,100.]
    b[932]=[97.,98.,96.,97.,100.]
    assert study.trade_path(b,10,931)['exit']==pytest.approx(97*.999)


def test_unfilled_needs_no_future_but_selected_missing_is_unknown():
    b=bars();b[914]=[90.,90.,90.,90.,100.]
    del b[932]
    assert study.trade_path(b,10,931)['filled'] is False
    b[914]=[101.,101.,101.,101.,100.]
    assert study.trade_path(b,10,931) is None


def test_continuous_ledger_never_skips_unknown_or_counts_abstention_as_win():
    rows=[dict(date=d,status='known_signal',morning_return=r) for d,r in [('a',-.1),('b',.1),('c',.1)]]
    sessions={d:bars() for d in ['a','b','c']}
    del sessions['b'][932]
    result=study.evaluate(rows,sessions,10,931)
    assert not result['complete'] and result['profit_usd'] is None
    assert result['known_prefix_sessions']==1 and result['active_days']==0
    assert result['winning_active_day_pct'] is None
    assert result['internal_statistical_screen_pass'] is False
    assert result['observed_target_hit'] is False


def test_control_identical_when_all_signals_positive_and_sizing_caps():
    rows=[dict(date='a',status='known_signal',morning_return=.1)]
    sessions={'a':bars()}
    a=study.evaluate(rows,sessions,10,931)
    b=study.evaluate(rows,sessions,10,931,True)
    assert a['trades']==b['trades'] and a['daily']==b['daily']
    trade=a['trades'][0]
    assert trade['reserved_usd']<=1000
    assert trade['qty']*(trade['entry']-trade['stop']*(1-trade['cost']))<=50
    assert a['profit_usd']<0 and a['winning_days']==0


def test_half_day_exclusion_is_calendar_not_missing_outcome():
    cal=calendar();cal['2026-01-05']['close_minute']=780
    rows=study.signals({},cal,[])
    assert rows[-1]['status']=='excluded_official_half_day'
    result=study.evaluate(rows,{},10,931)
    assert result['complete'] and result['active_days']==0


def test_wrong_split_scope_fails_closed(tmp_path,monkeypatch):
    data=tmp_path/'SPY.csv';data.write_text('fixture')
    metadata=dict(sha256=study.sha(data),feed='sip',adjustment='raw',symbol='SPY')
    data.with_suffix('.metadata.json').write_text(json.dumps(metadata))
    monkeypatch.setattr(study,'load_protocol',lambda:dict(data_sha256=study.sha(data)))
    cal=tmp_path/'calendar.json'
    cal.write_text(json.dumps(dict(url='https://paper-api.alpaca.markets/v2/calendar',
        query=dict(start='2024-01-01',end='2026-10-01'),rows=[dict(date='2026-01-02',open='09:30',close='16:00')])) )
    split=tmp_path/'split.json'
    split.write_text(json.dumps(dict(url=study.SPLIT_URL,query=dict(study.QUERY,symbols='AAPL'),pages=[{}])))
    with pytest.raises(ValueError,match='SPY-specific'):
        study.load_inputs(data,cal,split)


def test_breakeven_active_day_is_not_win_and_eod_drawdown_includes_initial(monkeypatch):
    rows=[dict(date='a',status='known_signal',morning_return=.1)]
    outcome=dict(filled=True,entry=100.,exit=100.,limit=101.,stop=99.,cost=.001,
                 entry_minute=931,exit_minute=955,reason='scheduled_exit')
    monkeypatch.setattr(study,'trade_path',lambda *args:outcome)
    result=study.evaluate(rows,{'a':bars()},10,931)
    assert result['active_days']==1 and result['breakeven_days']==1
    assert result['winning_days']==0 and result['observed_target_hit'] is False
    assert result['max_drawdown_pct']==0
    outcome['exit']=99.
    result=study.evaluate(rows,{'a':bars()},10,931)
    assert result['max_drawdown_pct']==pytest.approx(.009)
