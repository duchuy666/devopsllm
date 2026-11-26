#!/usr/bin/env python3
"""Apply an actual independent review consistently; default is preview only."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.review_case import review
from app.observation_window import crop

CHECKS=('target_effect_confirmed','recovery_confirmed','telemetry_relevant','near_duplicate_review')


def validate_review(record):
    if record.get('decision')!='approved' or any(record.get(k) is not True for k in CHECKS):
        raise ValueError('Actual approved review and all four explicit checks required')
    for key in ('reviewer_id','reason'):
        if not isinstance(record.get(key),str) or not record[key].strip():
            raise ValueError('Reviewer identity and reason required')
    timestamp=dt.datetime.fromisoformat(record.get('reviewed_at') or '')
    if timestamp.utcoffset() is None or timestamp>dt.datetime.now(dt.timezone.utc):
        raise ValueError('Review timestamp must have timezone and cannot be in the future')
    if not isinstance(record.get('evidence_locations'),list) or not record['evidence_locations']:
        raise ValueError('Raw evidence locations required')


def atomic_write(path, payload):
    temporary=path.with_suffix(path.suffix+'.admission-tmp')
    temporary.write_bytes(payload);temporary.replace(path)


def transaction(updates, root):
    parent=root/'results/admission-transactions';parent.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='admission-',dir=parent))
    before={path:path.read_bytes() if path.exists() else None for path in updates}
    manifest={'status':'prepared','files':[str(path.relative_to(root)) for path in updates]}
    for i,(path,payload) in enumerate(updates.items()):
        for name,data in ((f'after-{i}.json',payload),(f'before-{i}.json',before[path])):
            if data is not None:
                target=directory/name;target.write_bytes(data);target.chmod(0o600)
    log=directory/'transaction.json';log.write_text(json.dumps(manifest,indent=2)+'\n')
    changed=[]
    try:
        manifest['status']='applying';log.write_text(json.dumps(manifest,indent=2)+'\n')
        for path,payload in updates.items():
            atomic_write(path,payload);changed.append(path)
    except BaseException:
        for path in reversed(changed):
            if before[path] is None:path.unlink()
            else:
                # Direct rollback is independent of the failed write helper.
                restore=path.with_suffix(path.suffix+'.restore-tmp');restore.write_bytes(before[path]);restore.replace(path)
        manifest['status']='rolled_back';log.write_text(json.dumps(manifest,indent=2)+'\n');raise
    manifest['status']='committed';log.write_text(json.dumps(manifest,indent=2)+'\n')
    return directory


def propose(candidate, packet, root=ROOT):
    candidate=candidate.resolve()
    if not candidate.is_relative_to((root/'data/candidates').resolve()):
        raise ValueError('Candidate must be inside data/candidates')
    ground=json.loads((candidate/'ground-truth.json').read_text());record=packet['independent_review']
    validate_review(record)
    if packet['candidate_id']!=candidate.name or packet['scenario']!=ground['scenario']:
        raise ValueError('Review candidate/scenario mismatch')
    if ground.get('dataset_role')!='prospective_candidate' or ground['execution_status']!='captured_requires_review':
        raise ValueError('Only completed prospective cases can be admitted by this workflow')
    if ground['admission_status']=='admitted':raise ValueError('Case already admitted')
    if not all(review(candidate)['checks'].values()):raise ValueError('Structural audit failed')
    release=candidate/'collection-release.json'
    if hashlib.sha256(release.read_bytes()).hexdigest()!=ground.get('collection_release_sha256'):
        raise ValueError('Precommitted release identity mismatch')
    capture=json.loads((candidate/'observation/telemetry/capture.json').read_text())
    if set(capture.get('source_sha256',{}))!={'metrics','logs','traces'}:
        raise ValueError('All three raw source hashes required')
    for name,digest in capture['source_sha256'].items():
        if hashlib.sha256((candidate/'telemetry'/f'{name}.json').read_bytes()).hexdigest()!=digest:
            raise ValueError('Raw telemetry changed after observation export')
    if packet.get('observation_capture')!=ground.get('observation_capture'):
        raise ValueError('Reviewed observation differs from recorded observation')
    anchor=dt.datetime.fromisoformat(ground['injection_confirmed_at']).timestamp()
    with tempfile.TemporaryDirectory() as temporary:
        expected=Path(temporary)/'observation'
        receipt=crop(candidate/'telemetry',expected,anchor-30,anchor+30)
        if receipt!=capture:raise ValueError('Observation receipt differs from the precommitted window')
        for name in ('metrics','logs','traces'):
            if json.loads((expected/(name+'.json')).read_text())!=json.loads((candidate/'observation/telemetry'/(name+'.json')).read_text()):
                raise ValueError('Observation payload changed after export')
    for location in record['evidence_locations']:
        name=location.get('file') if isinstance(location,dict) else location
        if not isinstance(name,str):raise ValueError('Evidence file path required')
        path=(candidate/name).resolve()
        if not path.is_relative_to(candidate) or not path.is_file():raise ValueError('Evidence file outside candidate or missing')
    provenance=json.loads((candidate/'provenance.json').read_text())
    for name,digest in provenance['files_sha256'].items():
        path=candidate/'provenance'/name if name=='scenario-plan.json' or name.startswith('baseline/') else candidate/'provenance/files'/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Provenance checksum mismatch')
    plan=json.loads((candidate/'provenance/scenario-plan.json').read_text())
    planned=[r for r in plan['scenarios'] if r['scenario_id']==ground['scenario']['scenario_id']]
    if len(planned)!=1 or planned[0]!=ground['scenario']:raise ValueError('Scenario differs from pinned plan')
    registry_path=root/'experiments/candidate-registry.json';registry=json.loads(registry_path.read_text())
    matches=[r for r in registry['attempts'] if r['candidate_id']==candidate.name]
    if len(matches)!=1:raise ValueError('Expected exactly one matching registry entry')
    if any(matches[0][key]!=ground['scenario'][key] for key in ('scenario_id','split')) or matches[0]['execution_status']!=ground['execution_status']:
        raise ValueError('Registry identity/execution mismatch')
    if any(r['scenario_id']==ground['scenario']['scenario_id'] and r['admission_status']=='admitted' for r in registry['attempts']):
        raise ValueError('Another attempt already admitted for this scenario')
    handoff_path=root/'results/review-handoff/admission-review.json';handoff=json.loads(handoff_path.read_text())
    records=[r for r in handoff['cases'] if r['candidate_id']==candidate.name]
    if len(records)!=1:raise ValueError('Expected one admission handoff record')
    effect_path=candidate/'effect-review.json';effect=json.loads(effect_path.read_text())
    effect.update(status='effect_verified_by_independent_human_review',independent_human_review='approved',
                  reviewer=record['reviewer_id'],reviewed_at=record['reviewed_at'],reason=record['reason'])
    ground.update(admission_status='admitted',fault_effect_status='independently_reviewed_effect')
    matches[0].update(admission_status='admitted',effect_review_status=effect['status'])
    registry['official_admitted']=sum(r['admission_status']=='admitted' for r in registry['attempts'])
    registry['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    records[0].update(decision='approved',official_admitted=True,independent_reviewer=record['reviewer_id'],
                      independent_reviewed_at=record['reviewed_at'],reason=record['reason'])
    handoff['official_admitted']=sum(r.get('official_admitted') is True for r in handoff['cases'])
    handoff['status']='review_in_progress' if handoff['official_admitted']<200 else 'review_records_complete'
    receipt={'candidate_id':candidate.name,'review':record,'applied_at':registry['updated_at'],
             'raw_source_sha256':capture['source_sha256'],'note':'Reviewer record completeness checked; identity is not authenticated by this tool.'}
    documents={candidate/'ground-truth.json':ground,effect_path:effect,registry_path:registry,
               handoff_path:handoff,candidate/'admission-receipt.json':receipt}
    return {path:(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode() for path,data in documents.items()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--review',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();packet=json.loads(args.review.read_text())
    if not args.apply:
        updates=propose(args.candidate,packet)
        print(json.dumps({'status':'preview_only','changed_files':[str(p.relative_to(ROOT)) for p in updates]},indent=2))
    else:
        # Collection owns the registry while active; avoid clobbering new attempts.
        with (ROOT/'.runtime/collection-controller.lock').open('a+') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Finish/pause collection at a safe checkpoint before applying reviews; preview remains available')
            updates=propose(args.candidate,packet);directory=transaction(updates,ROOT)
            print(json.dumps({'status':'applied','transaction':str(directory)},indent=2))
