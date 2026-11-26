#!/usr/bin/env python3
"""Export the per-case dataset schema of the proposal (section 5.3) from admitted cases.

Read-only over ground truth and reviewer packets: expected_evidence and runbook_id come from the
independent reviewer's record, never inferred. Ground truth files themselves are not modified.
Output is reviewer/scorer-facing only; never index it or send it as model context.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.admission_progress import review_record

OUT=ROOT/'results/dataset-labels/labels.json'


def case_labels(root,candidate):
    folder=root/'data/candidates'/candidate;ground=json.loads((folder/'ground-truth.json').read_text())
    scenario=ground['scenario'];record=review_record(root,candidate)
    relevance_done=record.get('runbook_relevance_reviewed') is True
    return {'incident_id':candidate,'scenario_id':scenario['scenario_id'],'group_id':scenario['group_id'],'split':scenario['split'],
            'fault_type':scenario['fault_class'],'variant':scenario['variant'],'target':scenario['target'],
            'resolved_target':ground.get('resolved'),'chaos_parameters':ground.get('chaos_parameters',scenario.get('parameters')),
            'start_time':ground.get('injection_confirmed_at'),'end_time':ground.get('cleanup_completed_at'),
            'expected_root_cause':{'service_or_edge':scenario['target'],'fault_type':scenario['fault_class']},
            'expected_evidence':[loc if isinstance(loc,dict) else {'file':loc} for loc in record.get('evidence_locations',[])],
            'runbook_id':record.get('relevant_runbook_ids') if relevance_done else None,
            'runbook_relevance_status':'reviewed' if relevance_done else 'pending_reviewer_label',
            'metrics_window':f'data/candidates/{candidate}/observation/telemetry/metrics.json',
            'log_window':f'data/candidates/{candidate}/observation/telemetry/logs.json',
            'trace_window':f'data/candidates/{candidate}/observation/telemetry/traces.json',
            'raw_telemetry':f'data/candidates/{candidate}/telemetry/',
            'reviewer_id':record.get('reviewer_id'),'reviewed_at':record.get('reviewed_at')}


def export(root=ROOT):
    root=Path(root);registry=json.loads((root/'experiments/candidate-registry.json').read_text())
    def admitted(candidate):
        try:return json.loads((root/'data/candidates'/candidate/'ground-truth.json').read_text()).get('admission_status')=='admitted'
        except (OSError,ValueError):return False
    cases=[case_labels(root,a['candidate_id']) for a in registry['attempts'] if admitted(a['candidate_id'])]
    return {'status':'admitted_cases_only','exported_at':dt.datetime.now(dt.timezone.utc).isoformat(),'case_count':len(cases),
            'runbook_labels_reviewed':sum(c['runbook_relevance_status']=='reviewed' for c in cases),'cases':cases,
            'note':'Ground truth for scoring/review only. Do not index into Qdrant or include in model context.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args();data=export(ROOT)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.output.with_suffix('.json.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(args.output)
    print(json.dumps({k:data[k] for k in ('case_count','runbook_labels_reviewed')}|{'output':str(args.output)},indent=2))


if __name__=='__main__':main()
