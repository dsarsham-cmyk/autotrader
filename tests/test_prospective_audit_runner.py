from copy import deepcopy
from types import SimpleNamespace
import pytest
import prospective_audit_runner as runner

ENV={'manifest':{'created_utc':'2026-10-10T14:00:00Z'}}


def item(i,status='completed',conclusion='success',created='2026-10-12T14:00:00Z'):
    return dict(id=i,status=status,conclusion=conclusion,created_at=created,
        path='.github/workflows/predictive-prospective.yml',event='schedule',head_sha='x')


def request_for(pages):
    return lambda path,auth,params: SimpleNamespace(json=lambda:dict(workflow_runs=pages[params['page']-1]))


def test_failed_runs_not_filtered_and_pending_not_terminal():
    r=runner.discover(ENV,request_for([[item(1),item(2,conclusion='failure'),item(3,'in_progress')]]),{})
    assert r['terminal_run_ids']==[1,2] and r['pending_run_ids']==[3]
    assert not r['orders']


def test_old_runs_excluded_without_claiming_forecasts():
    r=runner.discover(ENV,request_for([[item(1,created='2026-10-09T14:00:00Z')]]),{})
    assert not r['terminal_run_ids'] and not r['runs']


def test_all_pages_and_duplicates_rejected():
    first=[item(i) for i in range(100)]
    r=runner.discover(ENV,request_for([first,[item(100)]]),{})
    assert len(r['terminal_run_ids'])==101
    with pytest.raises(ValueError,match='Duplicate'):
        runner.discover(ENV,request_for([first,[item(0)]]),{})


def test_wrong_workflow_rejected():
    bad=item(1);bad['path']='other.yml'
    with pytest.raises(ValueError,match='workflow'):
        runner.discover(ENV,request_for([[bad]]),{})


def prepared(monkeypatch):
    env=deepcopy(ENV);env['manifest']['artifact_sha256']='x'
    monkeypatch.setattr(runner,'read_manifest',lambda _:env)
    monkeypatch.setattr(runner,'source_matches',lambda _:True)
    monkeypatch.setattr(runner,'file_digest',lambda _:'x')
    monkeypatch.setattr(runner,'evidence_key',lambda:b'fixture')


def test_validate_only_never_collects_or_counts_forward(monkeypatch,tmp_path):
    prepared(monkeypatch)
    monkeypatch.setattr(runner,'discover',lambda _:pytest.fail('Unexpected remote collection'))
    r=runner.run(tmp_path,tmp_path/'backup',tmp_path/'out',True)
    assert r['verified_forecast_sessions']==0 and not r['independent_validation_pass']


def test_pending_run_prevents_screen_pass(monkeypatch,tmp_path):
    prepared(monkeypatch)
    monkeypatch.setattr(runner,'discover',lambda _:dict(terminal_run_ids=[1],pending_run_ids=[2]))
    monkeypatch.setattr(runner,'audit_series',lambda *a:dict(performance_screen_pass=True,
        independent_validation_pass=False,orders=False))
    r=runner.run(tmp_path,tmp_path/'backup',tmp_path/'out')
    assert not r['performance_screen_pass'] and not r['discovery_complete']


def test_source_mismatch_stops_before_discovery(monkeypatch,tmp_path):
    prepared(monkeypatch);monkeypatch.setattr(runner,'source_matches',lambda _:False)
    with pytest.raises(ValueError,match='source mismatch'):
        runner.run(tmp_path,tmp_path,tmp_path/'out')
