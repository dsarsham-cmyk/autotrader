"""Original strict completed-upload anchor; NOT a run-created-time substitute.

The immutable GitHub ZIP/digest and successful upload step must precede entry.
Identity/source/title are additional checks, not a weaker timing alternative.
No private-input reproduction, protocol approval or profitable-market claim is
performed here. Pure caller-provided fixtures are not authenticated API reads.
"""
from datetime import timedelta
import io
import json
import zipfile
import research_commitment as c

UPLOAD_STEP='Retain experimental public commitment only'


def normalized_sha(raw):
    return c.sha(raw.replace(b'\r\n',b'\n'))


def verify_upload_anchor(packet,run,jobs,metadata,archive,*,expected_head,
        expected_actor_id,script_bytes,workflow_bytes,expected_script_sha256,
        expected_workflow_sha256):
    """Return only transport verification; exact source registration required."""
    c.validate_packet(packet)
    # This verifies source/run/actor/nonce/title identity. Its created-time
    # consistency is NEVER sufficient: upload completion below is mandatory.
    identity=c.verify_anchor(packet,run,expected_head,expected_actor_id)
    for raw,expected in [(script_bytes,expected_script_sha256),(workflow_bytes,expected_workflow_sha256)]:
        c.hash_value(expected)
        if normalized_sha(raw)!=expected: raise ValueError('Registered workflow/script source mismatch')
    if run.get('status')!='completed' or run.get('conclusion')!='success':
        raise ValueError('Successful terminal run required')
    if not isinstance(jobs,list) or len(jobs)!=1: raise ValueError('One exact pinned-workflow job required')
    job=jobs[0]
    if (job.get('run_id')!=run['id'] or type(job.get('run_attempt')) is not int or
        job['run_attempt']!=1 or job.get('head_sha')!=expected_head or
        job.get('head_branch')!=c.BRANCH or job.get('name')!='record' or
        job.get('status')!='completed' or job.get('conclusion')!='success'):
        raise ValueError('Pinned job identity/attempt mismatch')
    uploads=[s for s in job.get('steps',[]) if s.get('name')==UPLOAD_STEP]
    if len(uploads)!=1: raise ValueError('One exact upload step required')
    step=uploads[0]
    if step.get('status')!='completed' or step.get('conclusion')!='success':
        raise ValueError('Successful completed upload step required')
    finished=c.timestamp(step.get('completed_at'))
    started=c.timestamp(step.get('started_at'))
    upper=finished+timedelta(seconds=1)
    entry=c.timestamp(packet['hypothetical_entry_not_before_utc'])
    if started>finished or not c.timestamp(packet['captured_utc'])<=upper<entry:
        raise ValueError('Upload completion upper bound not before entry')
    if metadata.get('name')!='research-commitment-'+str(run['id']) or metadata.get('expired') is not False:
        raise ValueError('Wrong/expired artifact')
    owner=metadata.get('workflow_run',{})
    if owner.get('id')!=run['id'] or owner.get('head_sha')!=expected_head or owner.get('head_branch')!=c.BRANCH:
        raise ValueError('Artifact ownership/source mismatch')
    if not c.timestamp(run['created_at'])<=c.timestamp(metadata['created_at'])<=upper:
        raise ValueError('Artifact creation inconsistent with successful upload')
    if metadata.get('digest')!='sha256:'+c.sha(archive):
        raise ValueError('GitHub archive digest mismatch')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        names=zipped.namelist()
        if len(names)!=3 or set(names)!={'packet.json','dispatch_inputs.json','status.json'}:
            raise ValueError('Exactly three root public files required')
        if sum(x.file_size for x in zipped.infolist())>1024*1024:
            raise ValueError('Oversized public evidence archive')
        files={name:zipped.read(name) for name in names}
    if files['packet.json']!=c.packet_bytes(packet):
        raise ValueError('Archived packet not exact canonical committed bytes')
    inputs=json.loads(files['dispatch_inputs.json'],object_pairs_hook=c.unique_object)
    if set(inputs)!={'packet_b64','commitment'} or files['dispatch_inputs.json']!=c.canonical(inputs):
        raise ValueError('Exact canonical dispatch inputs required')
    if c.decode_packet(**inputs)!=packet: raise ValueError('Archived dispatch packet mismatch')
    status=json.loads(files['status.json'],object_pairs_hook=c.unique_object)
    if any(status.get(k) is not False for k in ('orders','production_approved','independent_validation_pass','protocol_accepted')):
        raise ValueError('Unsafe/unapproved evidence status')
    if (status.get('status')!='experimental_commitment_recorded_not_forward_validation' or
        status.get('workflow_sha')!=expected_head or status.get('workflow_run_id')!=str(run['id']) or
        type(status.get('run_attempt')) is not int or status['run_attempt']!=1 or
        status.get('script_sha256')!=expected_script_sha256 or
        status.get('commitment')!=c.commitment(packet) or
        status.get('non_market') is not (packet['kind']=='synthetic') or
        type(status.get('verified_forward_observations')) is not int or status['verified_forward_observations']!=0):
        raise ValueError('Archived workflow/script/kind/nonce binding mismatch')
    if not c.timestamp(packet['captured_utc'])<=c.timestamp(status['recorded_utc'])<=upper:
        raise ValueError('Recorded status chronology invalid')
    return dict(status='strict_successful_upload_transport_anchor_only',run_id=run['id'],
        head_sha=expected_head,actor_id=expected_actor_id,kind=packet['kind'],
        commitment=c.commitment(packet),nonce=packet['nonce'],
        artifact_id=metadata['id'],artifact_digest=metadata['digest'],
        upload_step_completed_utc=step['completed_at'],
        upload_completion_upper_bound_utc=upper.isoformat(),
        entry_utc=packet['hypothetical_entry_not_before_utc'],
        script_sha256=expected_script_sha256,workflow_sha256=expected_workflow_sha256,
        timely_artifact_anchor_verified=True,verified_forward_observation=False,
        private_input_reproduction_verified=False,market_observations=0,
        protocol_accepted=False,independent_validation_pass=False,production_approved=False,orders=False,
        limitation='Requires authenticated API source retrieval and full private-input reproduction; synthetic probes never count as market evidence')
