import pytest
from net_opportunity_inventory import inventory,capture


def test_hindsight_not_validation_unknown_kept(monkeypatch):
    forecasts=[dict(date=d,symbol=s,signal_price=100,probability=.8)
               for d,s in [('one','A'),('one','B'),('two','A'),('three','A')]]
    outcomes=iter([dict(filled=True,label=1,entry=100,exit=101),None,dict(filled=False),
                   dict(filled=True,label=0,entry=100,exit=99)])
    monkeypatch.setattr('net_opportunity_inventory.path',lambda *a,**k:next(outcomes))
    report=inventory(forecasts,{},.004)
    assert report['candidates']==4 and report['unknown_paths']==1
    assert report['days_with_known_positive_path']==1
    assert report['days_without_known_positive_and_complete']==2
    assert report['uses_future_outcomes'] and not report['tradable']
    assert all(report[k] is False for k in ['orders','target_screen_pass','independent_validation_pass','production_approved'])
    selected=capture(forecasts,report)
    assert selected['selected_unknown_paths']==1
    assert selected['known_positive_paths_rank_selected']==1 and not selected['actual_executed_capture']


def test_missing_only_day_not_counted_impossible_or_winning(monkeypatch):
    monkeypatch.setattr('net_opportunity_inventory.path',lambda *a,**k:None)
    f=dict(date='one',symbol='A',signal_price=100,probability=.9)
    result=inventory([f],{},.01)
    assert result['days_without_known_positive_but_unknown']==1
    assert result['days_without_known_positive_and_complete']==0
    assert result['days_with_known_positive_path']==0
    assert capture([f],result)['selection_recall_known_positive'] is None
    with pytest.raises(ValueError,match='Duplicate'): inventory([f,f],{},.01)


def test_capture_is_gate_limited_top_three_not_all_hindsight_winners():
    forecasts=[dict(date='d',symbol=s,probability=p) for s,p in zip('ABCDE',[.64,.7,.8,.9,.9])]
    report=dict(daily=[dict(date='d',known_positive=[dict(symbol=s) for s in 'ABCDE'],unknown_paths=[])])
    result=capture(forecasts,report)
    assert result['known_positive_paths_available']==5
    assert result['known_positive_paths_rank_selected']==3
    assert result['selection_recall_known_positive']==.6
    assert not result['actual_executed_capture']
