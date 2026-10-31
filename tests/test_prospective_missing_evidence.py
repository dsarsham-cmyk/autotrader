"""Missing scheduled evidence is retained as a gap, never as a no-trade win."""
import json
from types import SimpleNamespace

import pytest
import prospective_outcome_audit as audit
import prospective_full_audit as full
import prospective_series_audit as series
import causal_shadow_audit as shadow
from tests.test_prospective_outcome_audit import fixture


def empty_run(monkeypatch):
    def get(path,auth,params=None):
        if path.endswith('/artifacts'):
            result=dict(artifacts=[],total_count=0)
        elif path.endswith('/jobs'):
            result=dict(jobs=[dict(id=7,steps=[dict(
                name='Collect prospective forecast - data GET only',
                conclusion='skipped',completed_at=None)])])
        else:
            assert path=='/actions/runs/1'
            result=dict(path='.github/workflows/predictive-prospective.yml',
                status='completed',conclusion='success',html_url='https://example.invalid/run/1')
        return SimpleNamespace(json=lambda:result)
    monkeypatch.setattr(audit,'headers',lambda:{})
    monkeypatch.setattr(audit,'get',get)


def test_successful_workflow_without_artifacts_retains_missing_inspection(tmp_path,monkeypatch):
    empty_run(monkeypatch)
    _,_,envelope,_,_=fixture()
    report=audit.inspect_run(1,tmp_path/'backup',envelope)
    saved=json.loads((tmp_path/'backup'/'1'/'inspection.json').read_text())
    assert saved==report
    assert report['status']=='evidence_unavailable_not_a_no_trade_day'
    assert report['forecast_packets']==report['timely_anchored_packets']==0
    assert not report['authenticated_archive_digests']
    assert not report['absence_is_no_trade'] and not report['orders']
    # A repeat read can refresh the inspection but never invents a packet.
    assert audit.inspect_run(1,tmp_path/'backup',envelope)==report


def test_missing_artifact_chain_keeps_completed_day_missing(tmp_path,monkeypatch):
    empty_run(monkeypatch)
    _,_,envelope,_,_=fixture()
    monkeypatch.setattr(full,'read_manifest',lambda _:envelope)
    inspection,accepted,rejected=full.load_verified_sessions(1,tmp_path/'backup',tmp_path/'model')
    assert accepted==rejected==[]
    assert inspection['status']=='evidence_unavailable_not_a_no_trade_day'
    report=series.simulate_series(accepted,envelope,['2026-10-12'])
    assert report['missing_completed_sessions']==['2026-10-12']
    assert report['verified_input_sessions']==0
    assert report['outcomes'][0]['active_days']==0
    assert report['outcomes'][0]['no_trade_days']==0
    assert report['outcomes'][0]['active_day_win_rate_pct'] is None
    assert not report['performance_screen_pass'] and not report['coverage_complete']


def test_nonterminal_or_wrong_workflow_still_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'headers',lambda:{})
    monkeypatch.setattr(audit,'get',lambda *a,**k:SimpleNamespace(json=lambda:dict(
        path='.github/workflows/other.yml',status='completed')))
    with pytest.raises(ValueError,match='Wrong workflow'):
        audit.inspect_run(1,tmp_path,{})


def test_shadow_zero_artifacts_retains_gap_and_cannot_become_no_trade(tmp_path):
    def request(path,auth,params=None):
        if path.endswith('/artifacts'):
            data=dict(artifacts=[],total_count=0)
        elif path.endswith('/jobs'):
            data=dict(jobs=[],total_count=0)
        else:
            data=dict(path='.github/workflows/causal-shadow-prospective.yml',
                status='completed',run_attempt=1,conclusion='success')
        return SimpleNamespace(json=lambda:data)
    inspected,accepted=shadow.inspect_run(1,tmp_path/'unused-model',tmp_path/'backup',{},request)
    saved=json.loads((tmp_path/'backup'/'1'/'inspection.json').read_text())
    assert saved==inspected and accepted==[]
    assert inspected['status']=='evidence_unavailable_not_a_no_trade_day'
    assert not inspected['absence_is_no_trade']
    assert inspected['forecast_packets']==inspected['reproduced_packets']==0
    report=shadow.evaluate_series([dict(date='2026-10-12')],accepted)
    assert report['missing_completed_sessions']==['2026-10-12']
    assert not report['performance_screen_pass']
    for case in report['cases']:
        for outcome in case['outcomes']:
            assert outcome['profit_usd'] is None
            assert outcome['active_days']==outcome['no_trade_days']==0
            assert outcome['active_day_win_rate_pct'] is None
