from copy import deepcopy
import base64
import json
import pytest
import research_commitment as c


def packet():
    return dict(schema=1,kind='synthetic',experiment_id='canary_v1',session_date='2026-10-31',
        nonce='a'*64,protocol_sha256='1'*64,model_manifest_sha256='2'*64,
        model_artifact_sha256='3'*64,private_ciphertext_sha256='4'*64,
        received_utc='2026-10-31T14:15:00Z',captured_utc='2026-10-31T14:15:01Z',
        hypothetical_entry_not_before_utc='2026-10-31T14:16:00Z',
        predictions=[dict(symbol='AAPL',probabilities={'target_004':.7,'target_010':.2})],
        orders=False,production_approved=False,independent_validation_pass=False)


def run(p):
    return dict(id=1,repository={'full_name':c.REPOSITORY},path=c.WORKFLOW,
        event='workflow_dispatch',run_attempt=1,head_sha='a'*40,head_branch=c.BRANCH,actor={'id':123},
        display_title=c.PREFIX+c.commitment(p),created_at='2026-10-31T14:15:02Z')


def test_exact_encoding_dispatch_builder_and_no_automatic_acceptance():
    p=packet();encoded=c.encode_packet(p)
    assert c.decode_packet(**encoded)==p
    assert c.packet_bytes(p)==c.canonical(p) and c.commitment(p)==encoded['commitment']
    request=c.dispatch_request(p)
    assert request['json']['inputs']==encoded and request['json']['return_run_details'] is True
    assert request['json']['ref']=='research-anchor-v1'
    with pytest.raises(ValueError):c.dispatch_request(p,ref='main')
    report=c.verify_anchor(p,run(p),'a'*40,123)
    assert report['timing_consistent'] and report['non_market']
    assert not any(report[k] for k in ['orders','production_approved','protocol_accepted',
        'verified_forward_observation','independent_validation_pass'])


@pytest.mark.parametrize('field,value',[('run_attempt',2),('head_sha','b'*40),
    ('head_branch','other'),('head_branch','main'),('event','schedule'),('path','other.yml'),
    ('repository',{'full_name':'other/repo'}),('display_title','fake'),('actor',{'id':456}),
    ('created_at','2026-10-31T14:16:00Z'),('created_at','2026-10-31T14:15:59Z'),
    ('created_at','2026-10-31T14:14:59Z'),('created_at',None)])
def test_remote_metadata_attacks_fail_closed(field,value):
    p=packet();metadata=run(p);metadata[field]=value
    with pytest.raises((ValueError,TypeError)):c.verify_anchor(p,metadata,'a'*40,123)


def test_packet_mutation_noncanonical_duplicate_keys_and_bad_encoding():
    encoded=c.encode_packet(packet());changed=packet();changed['predictions'][0]['probabilities']['target_004']=.9
    with pytest.raises(ValueError):c.decode_packet(c.encode_packet(changed)['packet_b64'],encoded['commitment'])
    for raw in [json.dumps(packet()).encode(),b'{"schema":1,"schema":1}']:
        with pytest.raises(ValueError):c.decode_packet(base64.b64encode(raw).decode(),c.sha(raw))
    with pytest.raises(ValueError):c.decode_packet('!!!!',encoded['commitment'])


@pytest.mark.parametrize('edit',[lambda p:p.update(secret='x'),lambda p:p.update(orders=True),
    lambda p:p.update(nonce='../bad'),lambda p:p.update(private_ciphertext_sha256='bad'),
    lambda p:p['predictions'][0].update(signal_price=100),
    lambda p:p['predictions'][0]['probabilities'].update(target_004=float('nan')),
    lambda p:p['predictions'][0]['probabilities'].update(target_004=True),
    lambda p:p.update(received_utc='2026-10-31T14:16:00Z'),
    lambda p:p.update(kind='unknown')])
def test_public_schema_and_information_delay_are_strict(edit):
    p=packet();edit(p)
    with pytest.raises(ValueError):c.encode_packet(p)


def test_duplicates_and_incomplete_discovery_never_count_as_extra_days():
    p=packet();encoded=c.encode_packet(p);record=dict(encoded,run=run(p))
    with pytest.raises(ValueError):c.verify_series([record],expected_head='a'*40,expected_actor_id=123,discovery_complete=False)
    with pytest.raises(ValueError,match='Duplicate'):
        c.verify_series([record,deepcopy(record)],expected_head='a'*40,expected_actor_id=123,discovery_complete=True)
    other=packet();other['nonce']='b'*64;other['predictions'][0]['probabilities']['target_004']=.9
    encoded2=c.encode_packet(other);second=dict(encoded2,run=dict(run(other),id=2))
    with pytest.raises(ValueError,match='Duplicate'):
        c.verify_series([record,second],expected_head='a'*40,expected_actor_id=123,discovery_complete=True)
    result=c.verify_series([record],expected_head='a'*40,expected_actor_id=123,discovery_complete=True)
    assert result['verified_forward_observations']==0 and not result['protocol_accepted']


def test_record_event_only_copies_public_packet_and_does_not_execute_inputs(tmp_path,monkeypatch):
    inputs=c.encode_packet(packet());event=tmp_path/'event.json';event.write_text(json.dumps({'inputs':inputs}))
    for name,value in {'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1',
        'GITHUB_REPOSITORY':c.REPOSITORY,'GITHUB_REF':'refs/heads/'+c.BRANCH,
        'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'1'}.items():monkeypatch.setenv(name,value)
    result=c.record_event(event,tmp_path/'out')
    assert json.loads((tmp_path/'out'/'packet.json').read_bytes())==packet()
    assert not result['orders'] and result['verified_forward_observations']==0
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    with pytest.raises(ValueError):c.record_event(event,tmp_path/'retry')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('GITHUB_REF','refs/heads/main')
    with pytest.raises(ValueError):c.record_event(event,tmp_path/'wrong-branch')


def test_market_mode_keeps_delayed_sip_window():
    p=packet();p['kind']='market'
    assert c.validate_packet(p)==p
    p['received_utc']='2026-10-31T14:14:59Z'
    with pytest.raises(ValueError):c.validate_packet(p)
    p['received_utc']='2026-10-31T14:15:00Z'
    p['hypothetical_entry_not_before_utc']='2026-10-31T14:17:00Z'
    with pytest.raises(ValueError):c.validate_packet(p)


def test_api_seconds_use_conservative_upper_bound_not_subsecond_false_precision():
    p=packet();p['captured_utc']='2026-10-31T14:15:02.500000Z'
    metadata=run(p)
    result=c.verify_anchor(p,metadata,'a'*40,123)
    assert result['creation_upper_bound_utc']=='2026-10-31T14:15:03+00:00'
    metadata['created_at']='2026-10-31T14:15:01Z'
    with pytest.raises(ValueError):c.verify_anchor(p,metadata,'a'*40,123)


def test_title_binds_ciphertext_and_protocol_and_actor_boolean_is_not_id():
    p=packet();metadata=run(p)
    for name in ['private_ciphertext_sha256','protocol_sha256','nonce']:
        modified=deepcopy(p);modified[name]='f'*64
        with pytest.raises(ValueError):c.verify_anchor(modified,metadata,'a'*40,123)
    metadata['actor']['id']=True
    with pytest.raises(ValueError):c.verify_anchor(p,metadata,'a'*40,1)
