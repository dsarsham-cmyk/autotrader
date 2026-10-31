from copy import deepcopy
from datetime import datetime,timezone
from email.utils import format_datetime
import pytest
import research_commitment as c
import research_commitment_canary as canary


def test_queued_proof_requires_remote_and_local_pre_entry_observation():
    moment=datetime(2026,10,31,16,0,tzinfo=timezone.utc);p=canary.synthetic_packet(moment)
    run=dict(id=1,repository={'full_name':c.REPOSITORY},path=c.WORKFLOW,event='workflow_dispatch',
        run_attempt=1,head_sha=canary.HEAD,head_branch=c.BRANCH,actor={'id':canary.ACTOR_ID},
        display_title=c.PREFIX+c.commitment(p),created_at=moment.isoformat(),status='queued')
    assert canary.pre_entry_proof(p,run,[],format_datetime(moment,usegmt=True),moment)
    active=deepcopy(run);active['status']='in_progress'
    assert not canary.pre_entry_proof(p,active,[],format_datetime(moment,usegmt=True),moment)
    assert not canary.pre_entry_proof(p,run,[{'status':'in_progress','started_at':moment.isoformat()}],format_datetime(moment,usegmt=True),moment)
    after=c.timestamp(p['hypothetical_entry_not_before_utc'])
    assert not canary.pre_entry_proof(p,run,[],format_datetime(after,usegmt=True),after)


def test_existing_intent_never_resends_post(tmp_path):
    (tmp_path/'intent.json').write_text('{}')
    class NoNetwork:
        def post(self,*a,**kw):pytest.fail('No duplicate POST')
        def get(self,*a,**kw):pytest.fail('No network after existing intent')
    with pytest.raises(ValueError,match='never resend'):canary.start(tmp_path,NoNetwork())


def test_invalid_early_run_response_is_retained_before_rejection(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import json
    p=canary.synthetic_packet(datetime(2026,10,31,16,0,tzinfo=timezone.utc))
    canary.retain(tmp_path/'intent.json',{'packet':p})
    canary.retain(tmp_path/'dispatch_response.json',{'body':{'workflow_run_id':1}})
    monkeypatch.setattr(canary,'headers',lambda:{})
    class Transport:
        def get(self,*a,**kw):
            return SimpleNamespace(raise_for_status=lambda:None,
                headers={'Date':'Sat, 31 Oct 2026 16:00:01 GMT'},
                json=lambda:{'display_title':'placeholder'})
    with pytest.raises(ValueError):canary.poll(tmp_path,Transport())
    saved=list(tmp_path.glob('run_read_*.json'))
    assert len(saved)==1
    assert json.loads(saved[0].read_bytes())['run']['display_title']=='placeholder'


def test_calibrated_clock_is_explicit_synthetic_only_and_does_not_use_host_time(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import json
    monkeypatch.setattr(canary,'headers',lambda:{})
    monkeypatch.setattr(canary,'now',lambda:datetime(2026,10,31,16,0,20,tzinfo=timezone.utc))
    times=iter([100.,100.5,100.5]);monkeypatch.setattr(canary.time,'monotonic',lambda:next(times))
    class Transport:
        def get(self,*a,**kw):
            return SimpleNamespace(raise_for_status=lambda:None,
                headers={'Date':'Sat, 31 Oct 2026 16:00:00 GMT'},
                json=lambda:{'object':{'sha':canary.HEAD}})
        def post(self,*a,**kw):
            return SimpleNamespace(raise_for_status=lambda:None,status_code=200,
                content=b'{}',headers={'Date':'Sat, 31 Oct 2026 16:00:01 GMT'},
                json=lambda:{'workflow_run_id':1})
    assert canary.start(tmp_path,Transport(),canary_calibrated=True,
        experiment_id='distinct_canary',entry_seconds=10)==1
    intent=json.loads((tmp_path/'intent.json').read_bytes());p=intent['packet']
    assert p['captured_utc']=='2026-10-31T16:00:00+00:00'
    assert p['hypothetical_entry_not_before_utc']=='2026-10-31T16:00:10+00:00'
    assert p['kind']=='synthetic'
    clock=json.loads((tmp_path/'canary_clock.json').read_bytes())
    assert clock['scope']=='SYNTHETIC_CANARY_ONLY_NOT_MARKET'
    assert clock['round_trip_seconds']==.5
    assert clock['upper_utc']=='2026-10-31T16:00:01.500000+00:00'
