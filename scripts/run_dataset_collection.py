#!/usr/bin/env python3
"""Collect a precommitted plan sequentially, with soak and no cloud/admission."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.collection_release import verify_release
from experiments.review_case import review


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def stratified_order(rows,done=()):
    """Deterministic interleaving so that any stopping point stays representative.

    Counting already-captured settings, each next pick goes to the split with the largest deficit against
    its planned share (120/40/40), then the fault class with the largest deficit inside that split, then the
    scenario family picked least often so far, then plan order. No randomness; the plan is unchanged.
    """
    done=set(done);remaining=[r for r in rows if r['scenario_id'] not in done]
    total={};cell_total={};count={};cell_count={};family={}
    for r in rows:
        total[r['split']]=total.get(r['split'],0)+1;key=(r['split'],r['fault_class'])
        cell_total[key]=cell_total.get(key,0)+1
    for r in rows:
        if r['scenario_id'] in done:
            count[r['split']]=count.get(r['split'],0)+1;key=(r['split'],r['fault_class'])
            cell_count[key]=cell_count.get(key,0)+1;family[r['group_id']]=family.get(r['group_id'],0)+1
    n=len(done);order=[];position={r['scenario_id']:i for i,r in enumerate(rows)}
    while remaining:
        splits={r['split'] for r in remaining}
        split=max(splits,key=lambda s:(total[s]/len(rows)*(n+1)-count.get(s,0),total[s],-['reference','validation','test'].index(s)))
        pool=[r for r in remaining if r['split']==split];m=count.get(split,0)
        fault=max({r['fault_class'] for r in pool},key=lambda f:(cell_total[(split,f)]/total[split]*(m+1)-cell_count.get((split,f),0),f))
        pool=[r for r in pool if r['fault_class']==fault]
        pick=min(pool,key=lambda r:(family.get(r['group_id'],0),position[r['scenario_id']]))
        order.append(pick);remaining.remove(pick);n+=1
        count[split]=m+1;cell_count[(split,fault)]=cell_count.get((split,fault),0)+1
        family[pick['group_id']]=family.get(pick['group_id'],0)+1
    return order


def batches(rows,done=(),lookahead=6):
    """At most four settings per soak batch; a Pod failure always closes its batch.

    To avoid one-case batches (each costs a 600 s soak), a batch that would close early on a Pod failure
    first pulls up to three non-Pod settings from the next `lookahead` positions of the stratified order.
    """
    queue=list(stratified_order(rows,done));result=[]
    while queue:
        current=[]
        while queue and len(current)<4:
            if queue[0]['variant']!='pod-failure':current.append(queue.pop(0));continue
            pulled=[i for i in range(1,min(len(queue),lookahead+1)) if queue[i]['variant']!='pod-failure'][:3-len(current)]
            current.extend(queue[i] for i in pulled)
            for i in reversed(pulled):queue.pop(i)
            current.append(queue.pop(0));break
        result.append([r['scenario_id'] for r in current])
    return result


SCHEDULE_KEYS={'split_order','schedule','early_stop'}


def protocol_without_schedule(text):
    """Collection protocol minus schedule/early-stop keys: the only part allowed to change on inheritance."""
    data=yaml.safe_load(text);return {k:v for k,v in data.items() if k not in SCHEDULE_KEYS}


def schedule_only(name,archived,digest=None):
    """True when the only difference in the collection protocol is its schedule/early-stop section."""
    if name!='config/collection-protocol.yaml':return False
    current=(ROOT/name).read_text()
    if digest is None:return protocol_without_schedule(archived.read_text())==protocol_without_schedule(current)
    # Origin releases keep their own source archive next to release.json; find the pinned copy by hash.
    for source in sorted((ROOT/'results/collection-releases').glob('*/sources/'+name)):
        if hashlib.sha256(source.read_bytes()).hexdigest()==digest:
            return protocol_without_schedule(source.read_text())==protocol_without_schedule(current)
    return False


def inherit_cases(journal_path,release,rows):
    """Reuse unchanged reference captures after a pre-heldout plan correction."""
    previous=json.loads(journal_path.read_text())
    if previous.get('status')!='superseded_before_heldout_collection':
        raise ValueError('Only an explicitly closed pre-heldout journal can be inherited')
    old_path=Path(previous['release']);old=json.loads(old_path.read_text())
    old_hash=hashlib.sha256(old_path.read_bytes()).hexdigest()
    if old_hash!=previous['release_sha256']:raise ValueError('Historical release changed')
    for key in ('observation','provider','prompt_fingerprint'):
        if old[key]!=release[key]:raise ValueError('Inference/window configuration changed; cannot inherit captures')
    mutable={'experiments/scenario-plan.json','scripts/run_dataset_collection.py','scripts/prepare_collection_release.py'}
    for name,digest in old['files_sha256'].items():
        archived=old_path.parent/'sources'/name
        if not archived.is_file() or hashlib.sha256(archived.read_bytes()).hexdigest()!=digest:
            raise ValueError('Historical source archive mismatch: '+name)
        if name not in mutable and release['files_sha256'].get(name)!=digest and not schedule_only(name,archived):
            raise ValueError('Scientific pipeline changed: '+name)
    by_id={r['scenario_id']:r for r in rows};inherited=[]
    for attempt in previous['attempts']:
        if attempt['status']!='captured_requires_review':continue
        if len(attempt.get('candidate_paths',[]))!=1:raise ValueError('Ambiguous inherited attempt')
        case=ROOT/attempt['candidate_paths'][0];ground=json.loads((case/'ground-truth.json').read_text())
        if ground['scenario']['split']!='reference':raise ValueError('Cannot revise a plan after accessing heldout captures')
        if ground['scenario']!=by_id.get(attempt['scenario_id']):raise ValueError('Completed setting changed: '+attempt['scenario_id'])
        origin_hash=attempt.get('inherited_from_release_sha256',old_hash)
        if ground.get('collection_release_sha256')!=origin_hash:raise ValueError('Candidate release identity mismatch')
        origin_path=case/'collection-release.json'
        if not origin_path.is_file() or hashlib.sha256(origin_path.read_bytes()).hexdigest()!=origin_hash:
            raise ValueError('Original candidate release missing or changed')
        origin=json.loads(origin_path.read_text())
        for key in ('observation','provider','prompt_fingerprint'):
            if origin[key]!=release[key]:raise ValueError('Inherited origin scientific configuration changed')
        for name,digest in origin['files_sha256'].items():
            if name not in mutable and release['files_sha256'].get(name)!=digest and not schedule_only(name,case/'collection-release.json',digest):
                raise ValueError('Inherited origin scientific source changed: '+name)
        if not all(review(case)['checks'].values()):raise ValueError('Inherited case quality check failed')
        inherited.append({**attempt,'inherited_from_release_sha256':origin_hash})
    return inherited


def register(directory):
    ground=json.loads((directory/'ground-truth.json').read_text())
    if ground['execution_status']=='captured_requires_review':
        quality=review(directory);write(directory/'quality-review.json',quality)
        if not (directory/'effect-review.json').exists():
            write(directory/'effect-review.json',{'status':'requires_technical_effect_review',
                'reviewer':None,'independent_human_review':'pending','official_admitted':False,
                'note':'Capture and structural checks are not an effect/admission decision.'})
        if not (directory/'review-packet.json').exists():
            write(directory/'review-packet.json',{'candidate_id':directory.name,'scenario':ground['scenario'],
                'structural_review':quality,'observation_capture':ground.get('observation_capture'),
                'evidence_files':['ground-truth.json','chaos-status.json','network-counters.json',
                                  'warmup-state.json','recovery-state.json','traffic.json',
                                  'telemetry','observation/telemetry','provenance.json'],
                'independent_review':{'reviewer_id':None,'reviewed_at':None,'decision':'pending',
                    'target_effect_confirmed':None,'recovery_confirmed':None,'telemetry_relevant':None,
                    'near_duplicate_review':None,'reason':None,'evidence_locations':[]},
                'note':'Reviewer-facing ground truth; never include this packet in LLM context or KB.'})
    effect_path=directory/'effect-review.json'
    effect=json.loads(effect_path.read_text())['status'] if effect_path.exists() else 'not_verified'
    path=ROOT/'experiments/candidate-registry.json';registry=json.loads(path.read_text())
    if not any(r['candidate_id']==directory.name for r in registry['attempts']):
        registry['attempts'].append({'candidate_id':directory.name,'scenario_id':ground['scenario']['scenario_id'],
            'split':ground['scenario']['split'],'execution_status':ground['execution_status'],
            'admission_status':ground['admission_status'],'effect_review_status':effect,
            'path':str(directory.relative_to(ROOT))})
        registry['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat();write(path,registry)
    handoff_path=ROOT/'results/review-handoff/admission-review.json'
    handoff=json.loads(handoff_path.read_text())
    if not any(r['candidate_id']==directory.name for r in handoff['cases']):
        handoff['cases'].append({'candidate_id':directory.name,'scenario_id':ground['scenario']['scenario_id'],
            'split':ground['scenario']['split'],'execution_status':ground['execution_status'],
            'technical_checks':review(directory)['checks'] if ground['execution_status']=='captured_requires_review' else None,
            'evidence_path':str(directory.relative_to(ROOT)),'independent_reviewer':None,
            'independent_reviewed_at':None,'decision':'pending' if ground['execution_status']=='captured_requires_review' else 'failed_attempt_not_admissible',
            'reason':None,'official_admitted':False})
        write(handoff_path,handoff)
    return ground


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--resume',type=Path)
    parser.add_argument('--initial-stability-result',type=Path)
    parser.add_argument('--inherit-journal',type=Path,help='Closed reference-only predecessor with unchanged scientific inputs')
    parser.add_argument('--max-cases',type=int,default=200)
    args=parser.parse_args()
    if not 1<=args.max_cases<=200:parser.error('Use 1..200 cases')
    release=verify_release(args.release,ROOT,'reference')
    release_hash=hashlib.sha256(args.release.read_bytes()).hexdigest()
    rows=json.loads((ROOT/'experiments/scenario-plan.json').read_text())['scenarios']
    if not args.execute:
        schedule=batches(rows)
        print(json.dumps({'cases':len(rows),'batches':len(schedule),'schedule':'stratified_interleaved_v1',
                          'gemini_called':False,'first_batches':schedule[:3]},indent=2));return 0
    lock=(ROOT/'.runtime/collection-controller.lock').open('a+')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Another collection controller is active')
    directory=args.resume or ROOT/'results/dataset-collection'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory.mkdir(parents=True,exist_ok=True);journal_path=directory/'journal.json'
    if args.resume:
        journal=json.loads(journal_path.read_text())
        if journal['release_sha256']!=release_hash:raise ValueError('Cannot resume with another release')
        if any(a['status']=='started' for a in journal['attempts']):
            raise ValueError('Unfinished attempt requires recovery/registration before resume')
    else:
        journal={'status':'running','release':str(args.release.resolve()),'release_sha256':release_hash,
                 'attempts':[],'soaks':[],'gemini_called':False,'official_admitted':0}
        if args.inherit_journal:
            journal['attempts']=inherit_cases(args.inherit_journal,release,rows)
            journal['inherited_journal']=str(args.inherit_journal.resolve())
        write(directory/'collection-plan.json',{'batches':batches(rows,{a['scenario_id'] for a in journal['attempts'] if a['status']=='captured_requires_review'}),
                                               'case_count':len(rows),'schedule':'stratified_interleaved_v1'})
    child=None
    def stop(*_):
        if child and child.poll() is None:child.send_signal(signal.SIGTERM)
        raise KeyboardInterrupt('Stop requested; child owns cleanup')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def run(command):
        nonlocal child
        child=subprocess.Popen(command,cwd=ROOT);return child.wait()
    try:
        journal['status']='running';write(journal_path,journal)
        done={a['scenario_id'] for a in journal['attempts'] if a['status']=='captured_requires_review'}
        # Recomputed from the captured set on every start/resume; deterministic for a given set.
        schedule=batches(rows,done);count=0
        for group in schedule:
            if count>=args.max_cases:
                journal['status']='bounded_segment_completed';write(journal_path,journal);return 0
            remaining=[key for key in group if key not in done]
            if not remaining:continue
            for key in remaining:
                split=next(r['split'] for r in rows if r['scenario_id']==key)
                verify_release(args.release,ROOT,split)
            if run([sys.executable,str(ROOT/'scripts/ensure_frontend_tunnel.py')]):raise RuntimeError('Frontend tunnel not ready')
            if args.initial_stability_result and not journal['soaks']:
                receipts=[args.initial_stability_result.resolve()]
                result=json.loads(receipts[0].read_text())
                code=0 if result.get('status')=='passed_short_soak' else 1
            else:
                before=set((ROOT/'results/stability').glob('*/result.json'))
                code=run([sys.executable,str(ROOT/'scripts/check_stability.py'),'--seconds','600'])
                receipts=sorted(set((ROOT/'results/stability').glob('*/result.json'))-before)
            journal['soaks'].append({'returncode':code,'result':str(receipts[-1]) if receipts else None});write(journal_path,journal)
            if code or len(receipts)!=1:raise RuntimeError('Fresh soak failed; no scenario in this batch started')
            for key in remaining:
                if count>=args.max_cases:
                    journal['status']='bounded_segment_completed';write(journal_path,journal);return 0
                before=set((ROOT/'data/candidates').glob('CANDIDATE-*'))
                attempt={'scenario_id':key,'status':'started','started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
                journal['attempts'].append(attempt);write(journal_path,journal)
                code=run([sys.executable,str(ROOT/'scripts/run_scenario.py'),'--scenario-id',key,'--execute',
                    '--stability-result',str(receipts[0]),'--collection-release',str(args.release.resolve())])
                created=sorted(set((ROOT/'data/candidates').glob('CANDIDATE-*'))-before)
                records=[register(p) for p in created]
                attempt.update(returncode=code,candidate_paths=[str(p.relative_to(ROOT)) for p in created],
                               status=records[0]['execution_status'] if len(records)==1 else 'failed_unknown_attempt_count')
                write(journal_path,journal)
                if code or len(records)!=1 or attempt['status']!='captured_requires_review':
                    raise RuntimeError('Scenario failed; retained and registered, no automatic retry')
                quality=review(created[0])
                if not all(quality['checks'].values()):raise RuntimeError('Structural review failed; stop before next scenario')
                done.add(key);count+=1
                print('Collection captured '+str(len(done))+'/200; admission remains pending',flush=True)
        journal['status']='collection_completed_requires_review';write(journal_path,journal);return 0
    except BaseException as exc:
        if child and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=180)
            except subprocess.TimeoutExpired:journal['cleanup_status']='child_cleanup_not_confirmed'
        journal.update(status='stopped_requires_review',error_type=type(exc).__name__,error=str(exc));write(journal_path,journal)
        print(str(exc),flush=True);return 1
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close();print('Collection journal: '+str(journal_path),flush=True)


if __name__=='__main__':raise SystemExit(main())
