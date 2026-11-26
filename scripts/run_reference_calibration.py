#!/usr/bin/env python3
"""A bounded sequential calibration batch, not a 200-case runner or cloud job."""
import argparse
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def validate_selection(ids,plan):
    if not 1<=len(ids)<=4 or len(set(ids))!=len(ids):
        raise ValueError('Use 1..4 unique reference scenarios')
    by_id={row['scenario_id']:row for row in plan['scenarios']}
    for index,key in enumerate(ids):
        row=by_id.get(key)
        if not row or row['split']!='reference':
            raise ValueError('Only existing reference scenarios allowed')
        if row['variant']=='pod-failure' and index!=len(ids)-1:
            raise ValueError('Pod failure must be last: it invalidates the baseline Pod identity receipt')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario-ids',nargs='+',required=True)
    parser.add_argument('--stability-result',type=Path,required=True)
    args=parser.parse_args()
    plan=json.loads((ROOT/'experiments/scenario-plan.json').read_text())
    try:validate_selection(args.scenario_ids,plan)
    except ValueError as exc:parser.error(str(exc))
    directory=ROOT/'results/calibration-batches'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    journal={'status':'running','scenario_ids':args.scenario_ids,'attempts':[],'gemini_called':False,'official_admitted':0}
    child=None
    def save():(directory/'batch.json').write_text(json.dumps(journal,indent=2)+'\n')
    def stop(*_):
        if child and child.poll() is None:child.send_signal(signal.SIGTERM)
        raise KeyboardInterrupt('Calibration interrupted; child cleans its own chaos resource')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    save();print('Batch journal: '+str(directory),flush=True)
    try:
        for key in args.scenario_ids:
            before=set((ROOT/'data/candidates').glob('CANDIDATE-*'))
            attempt={'scenario_id':key,'status':'started'};journal['attempts'].append(attempt);save()
            child=subprocess.Popen([sys.executable,str(ROOT/'scripts/run_scenario.py'),'--scenario-id',key,
                '--execute','--stability-result',str(args.stability_result.resolve())],cwd=ROOT)
            code=child.wait()
            created=sorted(set((ROOT/'data/candidates').glob('CANDIDATE-*'))-before)
            attempt.update(returncode=code,status='captured_requires_review' if code==0 else 'failed',
                           candidate_paths=[str(p.relative_to(ROOT)) for p in created]);save()
            if code:
                journal['status']='stopped_on_failure_no_retry';save();return 1
        journal['status']='completed_requires_review';save();return 0
    except BaseException:
        if child and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=180)
            except subprocess.TimeoutExpired:
                # Do not SIGKILL the cleanup worker or start another case.
                journal['cleanup_status']='child_cleanup_not_confirmed'
        journal['status']='interrupted_requires_resource_review';save();raise
    finally:print('Calibration status: '+journal['status'],flush=True)


if __name__=='__main__':raise SystemExit(main())
