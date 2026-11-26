#!/usr/bin/env python3
"""Run B0 on captured reference observations, then score development only."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.baseline import VERSION,diagnose_rules
from app.context_builder import build_context
from experiments.evaluate import evaluate

ROOT=Path(__file__).resolve().parents[1]


def main():
    registry=json.loads((ROOT/'experiments/candidate-registry.json').read_text());cases=[]
    for entry in registry['attempts']:
        if entry['execution_status']!='captured_requires_review':continue
        directory=ROOT/entry['path'];context,_=build_context(directory/'telemetry')
        started=time.perf_counter();report=diagnose_rules(context);elapsed=time.perf_counter()-started
        out=ROOT/'results/baselines'/VERSION/context['incident_id']/'B0/result.json';out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps({'mode':'B0','context_id':context['incident_id'],'baseline_version':VERSION,
            'generated':{'report':report,'latency_seconds':elapsed,'provider':'local_rules','api_cost_usd':0}},ensure_ascii=False,indent=2)+'\n')
        # Ground truth is read only after prediction, exclusively for offline scoring.
        ground=json.loads((directory/'ground-truth.json').read_text());row=ground['scenario']
        cases.append({'case_id':entry['candidate_id'],'context_id':context['incident_id'],
            'split':row['split'],'admission_status':'reviewed_for_development_scoring',
            'expected':{'target':row['target'],'fault_type':row['fault_class']},
            'reports':{'B0':str(out.relative_to(ROOT))}})
    manifest={'dataset_role':'development_pilot','modes':['B0'],'cases':cases}
    result=evaluate(manifest,ROOT);result['baseline_version']=VERSION
    result['limitations'].append('Includes repeated network scenarios and post-recovery observations; not a frozen benchmark or independent sample.')
    out=ROOT/'results/evaluation/b0-development.json';out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'summary':result['summaries'][0]},indent=2))


if __name__=='__main__':main()
