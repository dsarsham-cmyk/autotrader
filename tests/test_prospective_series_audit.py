from copy import deepcopy
from datetime import datetime,timedelta
import numpy as np
import pytest
from prospective_forecast_evidence import digest
from tests.test_prospective_outcome_audit import fixture
import prospective_series_audit as series


def bundle(date='2026-10-12',probability=.7,lose=False):
    packet,meta,envelope,raw,bars=fixture(probability)
    offset=datetime.fromisoformat(date)-datetime.fromisoformat('2026-10-12')
    record=packet['record'];record['session_date']=date
    for key in ['captured_utc','hypothetical_entry_not_before_utc']:
        record[key]=(datetime.fromisoformat(record[key])+offset).isoformat()
    for key in ['feature_cutoff_utc','last_bar_end_utc','received_utc']:
        record['input_receipt'][key]=(datetime.fromisoformat(record['input_receipt'][key])+offset).isoformat()
    for key in ['created_at','verified_upload_completed_at']:
        meta[key]=(datetime.fromisoformat(meta[key])+offset).isoformat()
    price=99.89
    bars['AAPL'][:]=[price,price+.2,price-.2,price,1000]
    bars['AAPL'][60,1]=price+1
    if lose: bars['AAPL'][60,2]=price-2
    for row in raw['bars']['AAPL']:
        row['t']=(datetime.fromisoformat(row['t'])+offset).isoformat()
        row.update(o=price,h=price+.2,l=price-.2,c=price,v=1000)
    packet['record_sha256']=digest(record)
    return dict(packet=packet,metadata=meta,raw_opening=raw,completed_bars=bars,
        input_predictions_reproduced=True,outcome_sip_sha256='synthetic-outcome-only'),envelope


def test_loss_carries_capital_and_changes_next_day_quantity():
    first,envelope=bundle(lose=True);second,_=bundle('2026-10-13')
    report=series.simulate_series([second,first],envelope,['2026-10-12','2026-10-13'])
    result=report['outcomes'][0]
    assert [t['quantity'] for t in result['trades']]==[10,9]
    assert result['daily'][1]['equity']==pytest.approx(100000+sum(t['pnl'] for t in result['trades']))
    assert result['metrics']['end_of_day_max_drawdown_pct']>0
    assert result['metrics']['losing_active_days']==1 and result['metrics']['winning_active_days']==1
    assert result['active_day_win_rate_pct']==50
    assert report['cumulative_risk_checks_pass'] and report['coverage_complete']
    assert not report['performance_screen_pass'] and not report['independent_validation_pass']
    assert not report['orders'] and not report['production_approved']


def test_missing_session_is_not_a_no_trade_day():
    first,envelope=bundle()
    report=series.simulate_series([first],envelope,['2026-10-12','2026-10-13'])
    assert report['missing_completed_sessions']==['2026-10-13']
    assert report['completed_calendar_coverage_pct']==50
    assert report['outcomes'][0]['no_trade_days']==0
    assert not report['coverage_complete'] and not report['performance_screen_pass']


def test_no_trade_and_empty_period_never_pass_target():
    first,envelope=bundle(probability=.1)
    report=series.simulate_series([first],envelope,['2026-10-12'])
    assert report['outcomes'][0]['active_days']==0
    assert report['outcomes'][0]['active_day_win_rate_pct'] is None
    assert report['outcomes'][0]['no_trade_days']==1
    assert not report['performance_screen_pass']
    empty=series.simulate_series([],envelope,[])
    assert empty['completed_calendar_coverage_pct'] is None and not empty['coverage_complete']
    assert not empty['performance_screen_pass'] and empty['outcomes'][0]['profit_usd']==0


def test_duplicates_and_uncompleted_sessions_fail_closed():
    first,envelope=bundle()
    with pytest.raises(ValueError,match='Duplicate session'):
        series.simulate_series([first,first],envelope,['2026-10-12'])
    with pytest.raises(ValueError,match='Duplicate expected'):
        series.simulate_series([],envelope,['2026-10-12','2026-10-12'])
    with pytest.raises(ValueError,match='completed calendar'):
        series.simulate_series([first],envelope,[])


def test_unreproduced_or_late_input_not_counted():
    first,envelope=bundle();first['input_predictions_reproduced']=False
    with pytest.raises(ValueError,match='reproduction'):
        series.simulate_series([first],envelope,['2026-10-12'])
    first['input_predictions_reproduced']=True
    first['metadata']['verified_upload_completed_at']='2026-10-12T14:16:01+00:00'
    with pytest.raises(ValueError,match='Late external'):
        series.simulate_series([first],envelope,['2026-10-12'])


def test_probability_quality_uses_assumed_fills_not_calendar_wins():
    first,envelope=bundle(probability=.9,lose=True)
    report=series.simulate_series([first],envelope,['2026-10-12'])
    diagnostic=report['probability_diagnostic']
    assert diagnostic['filled_candidates']==1 and diagnostic['brier']==pytest.approx(.81)
    assert diagnostic['bins'][-1]['mean_probability']==.9
    assert diagnostic['bins'][-1]['observed_positive_net_fraction']==0


def test_cumulative_accounting_tampering_rejected():
    first,envelope=bundle()
    report=series.simulate_series([first],envelope,['2026-10-12'])
    result=deepcopy(report['outcomes'][0]);result['daily'][0]['equity']+=1
    with pytest.raises(ValueError,match='capital/accounting'):
        series.accounting_metrics(result,[])


def test_calendar_includes_half_days_and_excludes_uncompleted_session(tmp_path,monkeypatch):
    _,envelope=bundle()
    rows=[dict(date='2026-10-12',open='09:30',close='16:00'),
        dict(date='2026-10-13',open='09:30',close='13:00'),
        dict(date='2026-10-14',open='09:30',close='16:00')]
    monkeypatch.setattr(series,'get_json',lambda *a:rows)
    report=series.completed_calendar(envelope,tmp_path,datetime.fromisoformat('2026-10-14T19:00:00+00:00'))
    assert report['completed_sessions']==['2026-10-12','2026-10-13']
    assert report['unsupported_sessions']==['2026-10-13']
    assert len(list((tmp_path/'calendar').glob('*.json')))==1


def test_future_start_calendar_performs_no_broker_request(tmp_path,monkeypatch):
    _,envelope=bundle()
    monkeypatch.setattr(series,'get_json',lambda *a:pytest.fail('No calendar GET before forward start'))
    assert series.completed_calendar(envelope,tmp_path,
        datetime.fromisoformat('2026-10-10T19:00:00+00:00'))['completed_sessions']==[]
