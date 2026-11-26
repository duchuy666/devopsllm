#!/usr/bin/env python3
"""Re-run a reviewer-rejected scenario with its pinned setting; preview by default.

Kept outside run_dataset_collection.py so the precommitted release hashes stay valid. Same release,
same plan row, fresh 600 s soak, controller lock held, no Gemini call, old attempt retained. The new
capture needs a new independent review; nothing here admits a case.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.admission_progress import progress,review_record
from app.collection_release import verify_release


def eligibility(root,scenario_id):
    """Only a scenario whose every completed capture was explicitly rejected by a reviewer."""
    row=next((r for r in progress(root)['scenarios'] if r['scenario_id']==scenario_id),None)
    if row is None:raise ValueError('Scenario not in pinned plan')
    if row['state']!='rejected_requires_new_attempt':
        raise ValueError(f'{scenario_id} is {row["state"]}; only reviewer-rejected scenarios can be recaptured')
    rejections=[]
    for case in row['candidates']:
        record=review_record(root,case['candidate_id'])
        if not (record.get('reviewer_id') and record.get('reason') and record.get('reviewed_at')):
            raise ValueError('Rejection must carry reviewer, timestamp and reason: '+case['candidate_id'])
        rejections.append({'candidate_id':case['candidate_id'],'reviewer_id':record['reviewer_id'],
                           'reviewed_at':record['reviewed_at'],'reason':record['reason']})
    return row,rejections


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True);parser.add_argument('--scenario-id',required=True)
    parser.add_argument('--reason',required=True,help='Coordinator decision, e.g. what was fixed before rerun')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.reason.strip():parser.error('Reason required')
    row,rejections=eligibility(ROOT,args.scenario_id)
    verify_release(args.release,ROOT,row['split'])
    plan={'scenario_id':args.scenario_id,'split':row['split'],'rejected_attempts':rejections,
          'coordinator_reason':args.reason.strip(),'release':str(args.release.resolve())}
    if not args.execute:
        print(json.dumps({'status':'preview_only',**plan},ensure_ascii=False,indent=2));return 0
    from scripts.run_dataset_collection import register
    folder=ROOT/'results/recaptures';folder.mkdir(parents=True,exist_ok=True)
    log=folder/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+args.scenario_id+'.json')
    record={**plan,'status':'started','started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'gemini_called':False}
    def save():log.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    with (ROOT/'.runtime/collection-controller.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Collection controller is active; recapture after it stops')
        save()
        try:
            if subprocess.call([sys.executable,str(ROOT/'scripts/ensure_frontend_tunnel.py')],cwd=ROOT):
                raise RuntimeError('Frontend tunnel not ready')
            before=set((ROOT/'results/stability').glob('*/result.json'))
            code=subprocess.call([sys.executable,str(ROOT/'scripts/check_stability.py'),'--seconds','600'],cwd=ROOT)
            receipts=sorted(set((ROOT/'results/stability').glob('*/result.json'))-before)
            record['soak']={'returncode':code,'result':str(receipts[-1]) if receipts else None};save()
            if code or len(receipts)!=1:raise RuntimeError('Fresh soak failed; scenario not started')
            verify_release(args.release,ROOT,row['split'])
            existing=set((ROOT/'data/candidates').glob('CANDIDATE-*'))
            code=subprocess.call([sys.executable,str(ROOT/'scripts/run_scenario.py'),'--scenario-id',args.scenario_id,
                '--execute','--stability-result',str(receipts[0]),'--collection-release',str(args.release.resolve())],cwd=ROOT)
            created=sorted(set((ROOT/'data/candidates').glob('CANDIDATE-*'))-existing)
            grounds=[register(p) for p in created]
            record.update(returncode=code,candidate_paths=[str(p.relative_to(ROOT)) for p in created],
                          status=grounds[0]['execution_status'] if len(grounds)==1 else 'failed_unknown_attempt_count')
        except BaseException as exc:
            record.update(status='stopped_requires_review',error=type(exc).__name__+': '+str(exc));save();raise
        record['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();save()
    print(json.dumps({k:record[k] for k in ('scenario_id','status','candidate_paths')},indent=2)+'\nLog: '+str(log))
    return 0 if record['status']=='captured_requires_review' else 1


if __name__=='__main__':raise SystemExit(main())
