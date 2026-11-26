#!/usr/bin/env python3
"""Screen planned grouped splits without reading observations or calling APIs."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def audit(plan):
    rows=plan['scenarios']
    errors=[]
    if len(rows)!=200 or len({r['scenario_id'] for r in rows})!=len(rows):
        errors.append('Expected 200 unique scenario IDs')
    if Counter(r['fault_class'] for r in rows)!={'Resource Exhaustion':67,'Network Delay / Packet Loss':67,'Pod Failure':66}:
        errors.append('Fault class allocation differs from 67/67/66')
    if Counter(r['split'] for r in rows)!={'reference':120,'validation':40,'test':40}:
        errors.append('Split allocation differs from 120/40/40')
    families=defaultdict(set)
    groups=defaultdict(set)
    variants=defaultdict(set)
    settings=defaultdict(list)
    for row in rows:
        # Traffic, intensity, duration and seed cannot move a family across splits.
        key=json.dumps([row['fault_class'],row['variant'],row['target']],ensure_ascii=False)
        families[key].add(row['split'])
        groups[row['group_id']].add(row['split'])
        variants[(row['fault_class'],row['split'])].add(row['variant'])
        signature=json.dumps([row['variant'],row['target'],row['parameters'],row['duration_seconds'],row['traffic_pause_seconds']],sort_keys=True)
        settings[signature].append(row['scenario_id'])
    cross=[{'signature':json.loads(k),'splits':sorted(v)} for k,v in families.items() if len(v)>1]
    if cross:errors.append('Fault/variant/target family crosses splits')
    if any(len(v)>1 for v in groups.values()):errors.append('Group ID crosses splits')
    repeated=[ids for ids in settings.values() if len(ids)>1]
    if plan.get('plan_version')=='0.3.0' and repeated:errors.append('Duplicate nominal settings; IDs, seeds and profile names do not make a new setting')
    for fault_class,wanted in [('Resource Exhaustion',{'cpu','memory'}),
                               ('Network Delay / Packet Loss',{'network-delay','network-loss'}),
                               ('Pod Failure',{'pod-failure'})]:
        for split in ('reference','validation','test'):
            if variants[(fault_class,split)]!=wanted:errors.append(f'Missing variant coverage: {fault_class}/{split}')
    return {'status':'structural_checks_failed' if errors else 'draft_structural_checks_passed',
            'errors':errors,'case_count':len(rows),'group_count':len(groups),
            'risk_count':len(cross),'cross_split_signatures':cross,
            'distinct_nominal_settings':len(settings),'repeated_setting_groups':repeated,
            'limitations':['This is a planned split, not collected/admitted data.',
                            'Observed log/trace near duplicates still require review.',
                            'Distinct traffic settings within a family are correlated; 200 settings are not 200 failure mechanisms.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=audit(json.loads(args.plan.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(1 if result['errors'] else 0)
