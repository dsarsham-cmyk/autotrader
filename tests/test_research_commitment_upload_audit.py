from copy import deepcopy
import io
import zipfile
import pytest
import research_commitment as c
import research_commitment_upload_audit as audit
from tests.test_research_commitment import packet,run


def fixture(kind='synthetic'):
    p=packet();p['kind']=kind;r=run(p);r.update(status='completed',conclusion='success')
    script=b'fixed source';workflow=b'fixed workflow'
    status=dict(status='experimental_commitment_recorded_not_forward_validation',workflow_sha='a'*40,
        workflow_run_id='1',run_attempt=1,script_sha256=audit.normalized_sha(script),
        commitment=c.commitment(p),non_market=kind=='synthetic',verified_forward_observations=0,
        orders=False,production_approved=False,protocol_accepted=False,independent_validation_pass=False,
        recorded_utc='2026-10-31T14:15:10Z')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('packet.json',c.packet_bytes(p));z.writestr('dispatch_inputs.json',c.canonical(c.encode_packet(p)))
        z.writestr('status.json',c.canonical(status))
    raw=buffer.getvalue()
    meta=dict(id=9,name='research-commitment-1',expired=False,digest='sha256:'+c.sha(raw),
        created_at='2026-10-31T14:15:20Z',workflow_run=dict(id=1,head_sha='a'*40,head_branch=c.BRANCH))
    jobs=[dict(run_id=1,run_attempt=1,head_sha='a'*40,head_branch=c.BRANCH,name='record',
        status='completed',conclusion='success',steps=[dict(name=audit.UPLOAD_STEP,status='completed',
        conclusion='success',started_at='2026-10-31T14:15:19Z',completed_at='2026-10-31T14:15:20Z')])]
    kwargs=dict(expected_head='a'*40,expected_actor_id=123,script_bytes=script,workflow_bytes=workflow,
        expected_script_sha256=audit.normalized_sha(script),expected_workflow_sha256=audit.normalized_sha(workflow))
    return [p,r,jobs,meta,raw],kwargs


@pytest.mark.parametrize('kind',['synthetic','market'])
def test_only_original_strict_upload_anchor_can_pass_not_market_validation(kind):
    args,kw=fixture(kind);result=audit.verify_upload_anchor(*args,**kw)
    assert result['timely_artifact_anchor_verified']
    assert result['upload_completion_upper_bound_utc']=='2026-10-31T14:15:21+00:00'
    assert not result['verified_forward_observation'] and not result['private_input_reproduction_verified']
    assert result['market_observations']==0 and not result['protocol_accepted'] and not result['orders']


@pytest.mark.parametrize('edit',[
    lambda a:a[2][0]['steps'][0].update(completed_at='2026-10-31T14:15:59Z'),
    lambda a:a[2][0]['steps'][0].update(conclusion='failure'),
    lambda a:a[2][0]['steps'].append(deepcopy(a[2][0]['steps'][0])),
    lambda a:a[2][0].update(run_attempt=2),lambda a:a[1].update(run_attempt=2),
    lambda a:a[3].update(created_at='2026-10-31T14:15:22Z'),
    lambda a:a[3]['workflow_run'].update(id=2),
    lambda a:a[3].update(digest='sha256:'+'0'*64),
    lambda a:a[1].update(display_title='fake'),
    lambda a:a[0].update(private_ciphertext_sha256='f'*64),
    lambda a:a[1].update(head_branch='main')])
def test_upload_identity_timing_and_packet_attacks_are_rejected(edit):
    args,kw=fixture();edit(args)
    with pytest.raises(ValueError):audit.verify_upload_anchor(*args,**kw)


def test_source_mutation_and_archive_member_substitution_fail_closed():
    args,kw=fixture();kw['script_bytes']=b'changed'
    with pytest.raises(ValueError):audit.verify_upload_anchor(*args,**kw)
    args,kw=fixture();buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('packet.json',b'{}')
    args[4]=buffer.getvalue();args[3]['digest']='sha256:'+c.sha(args[4])
    with pytest.raises(ValueError):audit.verify_upload_anchor(*args,**kw)
