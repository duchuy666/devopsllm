#!/usr/bin/env python3
"""Copy ready reviewer packets without overwriting completed human work."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.apply_admission_review import validate_review


def export(output,root=ROOT):
    output.mkdir(parents=True,exist_ok=True);rows=[]
    for case in sorted((root/'data/candidates').glob('CANDIDATE-*')):
        source=case/'review-packet.json'
        if not source.exists():continue
        ground=json.loads((case/'ground-truth.json').read_text())
        if ground.get('dataset_role')!='prospective_candidate' or ground['execution_status']!='captured_requires_review':continue
        destination=output/(case.name+'.json')
        if not destination.exists():shutil.copyfile(source,destination)
        packet=json.loads(destination.read_text());record=packet['independent_review'];complete=False
        try:validate_review(record);complete=True
        except (ValueError,TypeError):pass
        rows.append({'candidate_id':case.name,'scenario_id':ground['scenario']['scenario_id'],
            'split':ground['scenario']['split'],'variant':ground['scenario']['variant'],
            'candidate_path':str(case.resolve()),'review_file':str(destination.resolve()),
            'review_decision':record.get('decision','pending'),'approved_record_complete':complete,
            'admission_status':ground['admission_status']})
    queue={'status':'review_queue_not_admission','ready_packets':len(rows),
            'complete_approved_records':sum(r['approved_record_complete'] for r in rows),'cases':rows,
            'note':'Ground truth for human review only; never index or transmit as model context.'}
    temporary=output/'queue.json.tmp';temporary.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(output/'queue.json')
    return queue


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,
        default=ROOT/'results/review-handoff/prospective-review');args=parser.parse_args()
    queue=export(args.output)
    print(json.dumps({'ready_packets':queue['ready_packets'],'complete_approved_records':queue['complete_approved_records'],
                      'queue':str(args.output/'queue.json')},indent=2))


if __name__=='__main__':main()
