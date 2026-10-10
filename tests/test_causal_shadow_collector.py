from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
import active_stock_research as stocks
import causal_shadow_bundle as bundle
import causal_shadow_collector as collector


def raw_packet(session='2026-10-12'):
    opening=collector.timing(session)[0]
    return dict(bars={s:[dict(t=(opening+timedelta(minutes=i)).astimezone(timezone.utc).isoformat(),
        o=100,h=101,l=99,c=100,v=1000) for i in range(30)] for s in stocks.SYMBOLS},next_page_token=None)


def test_opening_timestamp_identity_and_invalid_packets():
    raw=raw_packet();current=collector.opening_observations(raw,'2026-10-12')
    assert len(current)==20 and all(len(frame)==30 for frame in current.values())
    for change in ('duplicate','future','nanosecond','missing_symbol','page'):
        invalid=deepcopy(raw)
        if change=='duplicate': invalid['bars']['AAPL'][1]=invalid['bars']['AAPL'][0]
        if change=='future': invalid['bars']['AAPL'][-1]['t']='2026-10-12T14:00:00Z'
        if change=='nanosecond': invalid['bars']['AAPL'][0]['t']='2026-10-12T13:30:00.000000001Z'
        if change=='missing_symbol': del invalid['bars']['AAPL']
        if change=='page': invalid['next_page_token']='more'
        with pytest.raises(ValueError): collector.opening_observations(invalid,'2026-10-12')


def test_dst_preparation_no_weekend_or_naive_clock():
    assert collector.preparation_window(datetime.fromisoformat('2026-10-12T13:57:00+00:00'),'2026-10-12')
    assert collector.preparation_window(datetime.fromisoformat('2026-12-14T14:57:00+00:00'),'2026-10-12')
    assert not collector.preparation_window(datetime.fromisoformat('2026-10-10T13:57:00+00:00'),'2026-10-12')
    assert not collector.preparation_window(datetime.fromisoformat('2026-10-12T14:16:00+00:00'),'2026-10-12')
    with pytest.raises(ValueError): collector.preparation_window(datetime(2026,10,12,10),'2026-10-12')


def history_receipt(tmp_path):
    refs={};meta={}
    for s in stocks.SYMBOLS:
        for target,container in [(tmp_path/(s+'.csv'),refs),(tmp_path/(s+'.metadata.json'),meta)]:
            collector.evidence.write_once(target,dict(test_fixture_only=True))
            container[str(target)]=collector.evidence.file_digest(target)
    return dict(feed='sip',adjustment='raw',end_exclusive='2026-10-12',history_files=refs,metadata_files=meta,
        download_started_utc='2026-10-12T13:50:00Z',prepared_utc='2026-10-12T14:00:00Z')


def setup_capture(monkeypatch,tmp_path):
    manifest=dict(forward_start='2026-10-12',created_utc='2026-10-10T19:00:00Z')
    protocol=dict(protocol_sha256='collector',protocol=dict(created_utc='2026-10-10T20:00:00Z'))
    monkeypatch.setattr(collector,'validate',lambda d:(manifest,protocol))
    monkeypatch.setattr(collector.evidence,'read_manifest',lambda d:dict(manifest_sha256='model'))
    monkeypatch.setattr(bundle,'infer',lambda *args:dict(predictions=[dict(symbol='AAPL',signal_price=100,
        probabilities=dict(target_004=.6,target_010=.4))],authenticated_prospective_evidence=False))
    return ({s:{} for s in stocks.SYMBOLS},[dict(corporate_actions={},next_page_token=None)],
        [dict(date='2026-10-12',open='09:30',close='16:00')],history_receipt(tmp_path))


def test_capture_is_local_only_private_inputs_and_no_overwrite(monkeypatch,tmp_path):
    prior,actions,calendar,history=setup_capture(monkeypatch,tmp_path)
    get=lambda url,params:raw_packet()
    times=iter(datetime.fromisoformat(f'2026-10-12T14:15:0{i}+00:00') for i in (1,2,3))
    directory=tmp_path/'experiment'
    packet=collector.collect_packet(directory,prior,actions,calendar,history,'2026-10-12',get,lambda:next(times))
    assert packet['record']['orders'] is False and packet['record']['independent_validation_pass'] is False
    assert packet['record']['external_timestamp_anchor_verified'] is False
    assert 'signal_price' not in packet['record']['predictions'][0]
    assert set(packet['record']['receipts'])=={'opening','calendar','corporate_actions','history_provenance','inference'}
    old=(directory/'predictions'/'2026-10-12.json').read_bytes()
    times=iter(datetime.fromisoformat(f'2026-10-12T14:15:0{i}+00:00') for i in (4,5,6))
    with pytest.raises(FileExistsError):
        collector.collect_packet(directory,prior,actions,calendar,history,'2026-10-12',get,lambda:next(times))
    assert (directory/'predictions'/'2026-10-12.json').read_bytes()==old


def test_late_data_or_inference_cannot_claim_forecast(monkeypatch,tmp_path):
    prior,actions,calendar,history=setup_capture(monkeypatch,tmp_path)
    for index,seconds in enumerate(((1,60),(1,2,60))):
        times=iter(datetime.fromisoformat('2026-10-12T14:15:00+00:00')+timedelta(seconds=i) for i in seconds)
        directory=tmp_path/f'late{index}'
        with pytest.raises(ValueError):
            collector.collect_packet(directory,prior,actions,calendar,history,'2026-10-12',lambda *a:raw_packet(),lambda:next(times))
        assert not (directory/'predictions').exists()


def test_historical_hash_and_feed_are_required(tmp_path):
    receipt=history_receipt(tmp_path);moment=datetime.fromisoformat('2026-10-12T14:15:00+00:00')
    collector.verify_history_receipt(receipt,'2026-10-12',moment)
    with pytest.raises(ValueError): collector.verify_history_receipt(dict(receipt,feed='iex'),'2026-10-12',moment)
    wrong=deepcopy(receipt);wrong['history_files'][next(iter(wrong['history_files']))]='bad'
    with pytest.raises(ValueError): collector.verify_history_receipt(wrong,'2026-10-12',moment)


def test_calendar_and_pagination_fail_closed():
    collector.calendar_session([dict(date='2026-10-12',open='09:30',close='13:00')],'2026-10-12')
    for rows in ([],[dict(date='2026-10-12',open='09:30',close='11:00')],[dict(date='2026-10-13',open='09:30',close='16:00')]):
        with pytest.raises(ValueError): collector.calendar_session(rows,'2026-10-12')
    with pytest.raises(ValueError): collector.split_pages(lambda *a:dict(next_page_token='repeat'),'2026-10-12','2026-07-01')


def test_status_cannot_override_order_safety(monkeypatch,tmp_path):
    monkeypatch.setattr(collector,'STATUS',tmp_path/'status.json')
    assert collector.status('test',recorded_sessions=1)['recorded_sessions']==1
    with pytest.raises(ValueError): collector.status('test',orders=True)
