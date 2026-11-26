"""Observed human sessions only; no synthesized timings or correctness feedback."""
import datetime as dt
import hashlib
import json
from pathlib import Path


def snapshot_inputs(destination,context_file,report_file):
    """Keep exactly the preloaded material shown to a real participant."""
    destination=Path(destination)
    payloads={'context.json':Path(context_file).read_bytes(),'report.json':Path(report_file).read_bytes()}
    for name,payload in payloads.items():
        path=destination/name
        if path.exists() and path.read_bytes()!=payload:
            raise ValueError('Refuse to replace human task material')
    destination.mkdir(parents=True,exist_ok=True)
    for name,payload in payloads.items():
        (destination/name).write_bytes(payload)
    return {name:hashlib.sha256(payload).hexdigest() for name,payload in payloads.items()}


def read_inputs(destination,hashes):
    if set(hashes)!={'context.json','report.json'}:raise ValueError('Task input hashes required')
    values={}
    for name,digest in hashes.items():
        payload=(Path(destination)/name).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Human task material changed')
        values[name]=json.loads(payload)
    return values['context.json'],values['report.json']


def timing(start_at,end_at,start_monotonic,end_monotonic):
    utc=(dt.datetime.fromisoformat(end_at)-dt.datetime.fromisoformat(start_at)).total_seconds()
    active=end_monotonic-start_monotonic
    valid=utc>0 and active>0 and abs(utc-active)<=5
    return {'observed_seconds':utc if valid else None,'utc_elapsed_seconds':utc,
            'monotonic_elapsed_seconds':active,'valid_timing':valid,
            'limitation':'Preloaded replay decision time; not live incident TTD.'}


def study_complete(root):
    path=root/'experiments/human-study-plan.json'
    if not path.exists():return False
    protocol_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    plan=json.loads(path.read_text());expected={t['case_opaque_id']:t['condition'] for t in plan['tasks']}
    for path in (root/'results/human-study'/plan['study_id']).glob('*/session.json'):
        try:
            session=json.loads(path.read_text());finished=session.get('completed_tasks',[])
            ids=[t['case_opaque_id'] for t in finished]
            if session.get('consent') is True and session.get('protocol_sha256')==protocol_hash and len(ids)==len(expected) and set(ids)==set(expected) and all(
                    t.get('ended_at') and t.get('final_diagnosis') and t.get('condition')==expected[t['case_opaque_id']] for t in finished):return True
        except (ValueError,KeyError,TypeError):continue
    return False


def study_cancelled(root):
    """An explicit, recorded cancellation before any session (user decision) also unlocks test review."""
    record=root/'experiments/human-study-cancelled.json'
    try:data=json.loads(record.read_text())
    except (OSError,ValueError):return False
    return data.get('status')=='cancelled_before_any_session' and data.get('sessions_started')==0 and bool(data.get('decided_by'))


def test_review_unlocked(root):
    return study_complete(root) or study_cancelled(root)


def hidden_test_contexts(root):
    if test_review_unlocked(root):return set()
    hidden=set()
    for path in (root/'results/prospective-benchmark').glob('*/test/manifest.json'):
        hidden.update(c['context_id'] for c in json.loads(path.read_text()).get('cases',[]))
    return hidden
