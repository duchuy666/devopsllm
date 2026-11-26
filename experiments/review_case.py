#!/usr/bin/env python3
"""Prepare a quality review from local evidence; never grant official admission."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import statistics


def load(path,default=None):
    return json.loads(path.read_text()) if path.exists() else default


def identity(pod):
    return (pod['metadata']['uid'],tuple((c['name'],c['restartCount'])
        for c in pod.get('status',{}).get('containerStatuses',[])))


def non_target_lifecycle(state,source):
    return {p['metadata']['namespace']+'/'+p['metadata']['name']:identity(p)
        for p in state.get('pods',[])+state.get('support_pods',[])
        if p['metadata'].get('namespace')!='sock-shop' or p['metadata'].get('labels',{}).get('name')!=source}


def phase_statistics(points,start,end):
    values={'baseline':[],'fault':[],'recovery':[]}
    if start is None or end is None:return {}
    for timestamp,value in points:
        number=float(value)
        if not math.isfinite(number):continue
        phase='baseline' if timestamp<start else ('fault' if timestamp<=end else 'recovery')
        values[phase].append(number)
    return {phase:{'count':len(rows),'mean':statistics.mean(rows) if rows else None,
                   'min':min(rows) if rows else None,'max':max(rows) if rows else None}
            for phase,rows in values.items()}


def review(directory):
    ground=load(directory/'ground-truth.json',{})
    scenario=ground.get('scenario',{})
    source=ground.get('resolved',{}).get('source_service')
    before=load(directory/'warmup-state.json',load(directory/'preflight-state.json',{}))
    after=load(directory/'recovery-state.json',{})
    chaos=load(directory/'chaos-status.json',{})
    capture=load(directory/'telemetry/capture.json',{})
    quality=capture.get('quality',{})
    traffic=load(directory/'traffic.json',{})
    checks={
        'pipeline_completed':ground.get('execution_status')=='captured_requires_review',
        'controller_all_injected':any(c.get('type')=='AllInjected' and c.get('status')=='True'
            for c in chaos.get('status',{}).get('conditions',[])),
        'cleanup_recorded':bool(ground.get('cleanup_completed_at')) and not ground.get('cleanup_error'),
        'raw_sources_present':all(quality.get(k) for k in ('metrics_present','logs_present','traces_present')),
        'exports_not_truncated':bool(quality) and not quality.get('log_export_incomplete') and not quality.get('trace_limit_reached'),
        'exports_no_errors':bool(capture) and not capture.get('errors'),
        'recovery_recorded':bool(ground.get('recovered_at')) and not ground.get('recovery_issues'),
        'traffic_exercised':traffic.get('completed_journeys',0)>0 and ground.get('traffic_exit_code')==0,
        'non_target_lifecycle_unchanged':bool(before and after) and non_target_lifecycle(before,source)==non_target_lifecycle(after,source),
    }
    left=before.get('node_cgroup',{});right=after.get('node_cgroup',{})
    checks['node_local_oom_unchanged']=(left.get('events_source')==right.get('events_source')=='memory.events.local'
        and left.get('events',{}).get('oom_kill')==right.get('events',{}).get('oom_kill'))
    target_pods={p['metadata']['name'] for state in (before,after) for p in state.get('pods',[])
                 if p['metadata'].get('labels',{}).get('name')==source}
    start=ground.get('injection_requested_at');end=ground.get('cleanup_completed_at')
    start=dt.datetime.fromisoformat(start).timestamp() if start else None
    end=dt.datetime.fromisoformat(end).timestamp() if end else None
    metric_summaries=[]
    metrics=load(directory/'telemetry/metrics.json',{})
    for kind in ('cpu','memory','cpu_limit','memory_limit','ready','restarts'):
        for series in metrics.get(kind,{}).get('response',{}).get('data',{}).get('result',[]):
            pod=series.get('metric',{}).get('pod')
            if pod in target_pods:
                metric_summaries.append({'metric':kind,'pod':pod,
                    'phases':phase_statistics(series.get('values',[]),start,end)})
    before_uids={p['metadata']['uid'] for p in before.get('pods',[]) if p['metadata'].get('labels',{}).get('name')==source}
    after_uids={p['metadata']['uid'] for p in after.get('pods',[]) if p['metadata'].get('labels',{}).get('name')==source}
    counters=load(directory/'network-counters.json',{})
    return {'review_status':'structural_checks_passed_effect_review_required' if all(checks.values()) else 'structural_review_failed',
        'dataset_role':'development_candidate','admission_status':'requires_review','official_admitted':False,
        'scenario_id':scenario.get('scenario_id'),'variant':scenario.get('variant'),'checks':checks,
        'observations':{'target_metric_phases':metric_summaries,
            'target_pod_uid_changed':bool(before_uids and after_uids and before_uids!=after_uids),
            'qdisc_max_reported_drops':counters.get('max_reported_drops'),
            'traffic_completed_journeys':traffic.get('completed_journeys'),'traffic_failed_requests':traffic.get('failed_requests')},
        'human_review_required':['Verify actual selected target in controller records.',
            'Confirm fault effect from baseline/fault/recovery, not just AllInjected.',
            'Verify traffic crossed the target service or directed edge.',
            'Review target relevance of logs/traces against the actual export query profiles and limits.',
            'Record detector miss independently; a miss alone does not reject a real failure case.',
            'Review collateral impact, near duplicates and frozen protocol before official admission.'],
        'note':'Failed requests during an injected fault are recorded, not automatically rejected. No data sent to an LLM.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    args=parser.parse_args();result=review(args.directory)
    path=args.directory/'quality-review.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'path':str(path),'status':result['review_status'],'checks':result['checks'],
                      'official_admitted':False},indent=2))
