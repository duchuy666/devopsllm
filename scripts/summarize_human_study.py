#!/usr/bin/env python3
"""Summarize actual completed blinded sessions, without reading test answers."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.human_study import timing,read_inputs
from app.report_schema import IncidentReport


def summarize(plan,protocol_hash,session,hourly_cost_vnd=None):
    if session.get('consent') is not True or session.get('protocol_sha256')!=protocol_hash:
        raise ValueError('Consent and exact precommitted protocol required')
    tasks={t['case_opaque_id']:t for t in plan['tasks']}
    rows=session.get('completed_tasks',[])
    ids=[r['case_opaque_id'] for r in rows]
    if len(ids)!=len(tasks) or set(ids)!=set(tasks) or session.get('active_task'):
        raise ValueError('Complete the full blinded session before summarizing')
    if hourly_cost_vnd is not None and (not math.isfinite(hourly_cost_vnd) or hourly_cost_vnd<0):
        raise ValueError('Hourly cost assumption must be finite and nonnegative')
    measured=[]
    for row in rows:
        task=tasks[row['case_opaque_id']]
        if row['condition']!=task['condition'] or row.get('group_id')!=task['group_id'] or not row.get('final_diagnosis'):
            raise ValueError('Task assignment or human diagnosis missing/mismatched')
        if any(dt.datetime.fromisoformat(row[k]).utcoffset() is None for k in ('started_at','ended_at')):
            raise ValueError('Timezone required for actual observations')
        result=timing(row['started_at'],row['ended_at'],row['start_monotonic'],row['start_monotonic']+row['monotonic_elapsed_seconds'])
        if row.get('valid_timing') is not result['valid_timing'] or row.get('observed_seconds')!=result['observed_seconds']:
            raise ValueError('Stored timing differs from independently recomputed timing')
        measured.append({'case_opaque_id':row['case_opaque_id'],'group_id':task['group_id'],
                         'condition':task['condition'],**result})
    conditions={}
    for condition in ('B0_dashboard','B3_assistant'):
        group=[r for r in measured if r['condition']==condition]
        values=[r['observed_seconds'] for r in group if r['valid_timing']]
        conditions[condition]={'completed':len(group),'valid_timing':len(values),'invalid_timing':len(group)-len(values),
            'mean_seconds':statistics.mean(values) if values else None,
            'median_seconds':statistics.median(values) if values else None}
    pairs=[]
    for group in sorted({t['group_id'] for t in tasks.values()}):
        members=[r for r in measured if r['group_id']==group]
        by_condition={r['condition']:r for r in members}
        if len(members)!=2 or set(by_condition)!={'B0_dashboard','B3_assistant'}:
            raise ValueError('Exactly two different tasks, one per condition, required per family')
        valid=all(r['valid_timing'] for r in members)
        pairs.append({'group_id':group,'both_timings_valid':valid,'dashboard_minus_assistant_seconds':
            by_condition['B0_dashboard']['observed_seconds']-by_condition['B3_assistant']['observed_seconds'] if valid else None})
    deltas=[p['dashboard_minus_assistant_seconds'] for p in pairs if p['both_timings_valid']]
    delta=statistics.mean(deltas) if deltas else None
    return {'status':'completed_observed_pilot','participant_id':session.get('participant_id'),
        'protocol_sha256':protocol_hash,'conditions':conditions,'matched_family_pairs':pairs,
        'valid_pair_count':len(deltas),'mean_family_difference_seconds':delta,
        'labor_value_sensitivity':{'assumed_hourly_vnd':hourly_cost_vnd,
            'gross_vnd_per_task':delta/3600*hourly_cost_vnd if delta is not None and hourly_cost_vnd is not None else None,
            'meaning':'Assumed gross labor value only; excludes API, infrastructure and review cost. Negative differences remain negative.'},
        'correctness':'not_scored_by_this_tool','ground_truth_read':False,'cloud_called':False,
        'observations':measured,'limitations':plan['limitations']+[
            'Precomputed assistant report and preloaded context; not live alert-to-diagnosis time.',
            'Different cases matched by family; descriptive contrast, not a causal treatment estimate.',
            'No population confidence interval or production ROI inferred from one participant.',
            'Invalid timings excluded explicitly; never imputed.']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--hourly-cost-vnd',type=float)
    args=parser.parse_args();path=ROOT/'experiments/human-study-plan.json';plan=json.loads(path.read_text())
    session=json.loads(args.session.read_text())
    for row in session.get('completed_tasks',[]):
        context,saved=read_inputs(args.session.parent/'inputs'/row['case_opaque_id'],row['input_sha256'])
        report=IncidentReport.model_validate(saved['generated']['report'])
        mode='B0' if row['condition']=='B0_dashboard' else 'B3'
        if saved['mode']!=mode or context['incident_id']!=row['context_id'] or report.incident_id!=row['context_id']:
            raise ValueError('Observed task input/report identity mismatch')
    result=summarize(plan,hashlib.sha256(path.read_bytes()).hexdigest(),session,args.hourly_cost_vnd)
    result['session_sha256']=hashlib.sha256(args.session.read_bytes()).hexdigest()
    if args.output.exists():raise ValueError('Preserve existing summaries; select a new output path')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'valid_pairs':result['valid_pair_count'],'output':str(args.output)}))


if __name__=='__main__':main()
