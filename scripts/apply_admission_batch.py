#!/usr/bin/env python3
"""Apply every completed independent approval toward the 200-case target; preview by default.

Each case still goes through apply_admission_review.propose (all integrity checks) and its own
transaction. Pending, rejected or incomplete reviews are reported, never filled in or admitted.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.admission_progress import progress,REVIEW_DIR
from scripts.apply_admission_review import propose,transaction
from scripts.export_review_queue import export


def run(root=ROOT,apply=False):
    root=Path(root);export(root/REVIEW_DIR,root)
    before=progress(root);results=[]
    for row in before['scenarios']:
        for case in row['candidates']:
            if case['state']!='approved_ready_to_apply':continue
            entry={'scenario_id':row['scenario_id'],'split':row['split'],'candidate_id':case['candidate_id']}
            try:
                packet=json.loads((root/REVIEW_DIR/(case['candidate_id']+'.json')).read_text())
                updates=propose(root/'data/candidates'/case['candidate_id'],packet,root)
                if apply:
                    entry.update(status='applied',transaction=str(transaction(updates,root).relative_to(root)))
                else:
                    entry.update(status='would_apply',changed_files=[str(p.relative_to(root)) for p in updates])
            except (OSError,ValueError,KeyError,TypeError) as exc:
                # One bad record must not block the others; it stays un-admitted with a reason.
                entry.update(status='refused',error=type(exc).__name__+': '+str(exc))
            results.append(entry)
            # Only one admission per scenario; a replicate approval is refused by propose anyway.
            if entry['status'] in ('applied','would_apply'):break
    after=progress(root) if apply else before
    summary={'mode':'apply' if apply else 'preview_only','at':dt.datetime.now(dt.timezone.utc).isoformat(),
             'admitted_before':before['admitted'],'admitted_after':after['admitted'],
             'would_admit':sum(r['status']=='would_apply' for r in results),
             'refused':sum(r['status']=='refused' for r in results),'target':before['target'],
             'remaining_to_target':after['remaining_to_target'] if apply else
                 before['remaining_to_target']-sum(r['status']=='would_apply' for r in results),
             'counts':after['counts'],'results':results,
             'rejected_requires_new_attempt':[r['scenario_id'] for r in after['scenarios']
                                              if r['state']=='rejected_requires_new_attempt'],
             'note':'Reviewer identity/independence is not authenticated; the coordinator is accountable.'}
    if apply:
        folder=root/'results/admission-batches';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');summary['receipt']=str(path.relative_to(root))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Write admissions; requires collection controller idle')
    args=parser.parse_args()
    if not args.apply:
        summary=run(ROOT,False)
    else:
        with (ROOT/'.runtime/collection-controller.lock').open('a+') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise SystemExit('Collection controller is active; pause at a safe checkpoint, preview remains available')
            summary=run(ROOT,True)
    brief={k:v for k,v in summary.items() if k!='results'}
    brief['results']=[{k:r[k] for k in ('scenario_id','candidate_id','status','error') if k in r} for r in summary['results']]
    print(json.dumps(brief,ensure_ascii=False,indent=2))
    return 1 if summary['refused'] else 0


if __name__=='__main__':raise SystemExit(main())
