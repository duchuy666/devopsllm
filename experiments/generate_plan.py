#!/usr/bin/env python3
"""Prepare 200 grouped scenarios; this does not execute or create incident data."""
from collections import Counter
import itertools
import json
from pathlib import Path
import random

TARGETS=['catalogue','payment','user','carts','orders','shipping']
EDGES=[('front-end','catalogue'),('front-end','user'),('front-end','carts'),('orders','payment'),('orders','shipping')]
TRAFFIC={'checkout-low':1.5,'checkout-medium':0.75,'checkout-high':0.25}
POD_EXTRA_PAUSES=[0.1,0.4,0.6,0.9,1.1,1.3,1.7,1.9,2.1,2.3,2.5,2.7,2.9,3.1,3.3,3.5,3.7]
SPECS=[
 ('Resource Exhaustion',['cpu','memory'],TARGETS,{'reference':[7,7,7,7,6,6],'validation':[5,4,4],'test':[5,5,4]}),
 ('Network Delay / Packet Loss',['network-delay','network-loss'],EDGES,{'reference':[7,7,7,7,6,6],'validation':[7,7],'test':[7,6]}),
 ('Pod Failure',['pod-failure'],TARGETS,{'reference':[20,20],'validation':[7,6],'test':[7,6]}),
]


def main():
    scenarios=[]; groups=[]
    for class_index,(fault_class,variants,targets,splits) in enumerate(SPECS):
        families=list(itertools.product(variants,targets))
        boundaries=[]; start=0
        for sizes in splits.values():
            boundaries.append((start,len(sizes)));start+=len(sizes)
        rng=random.Random(42+class_index)
        for _ in range(1000):
            rng.shuffle(families)
            chosen=families
            if all({row[0] for row in chosen[start:start+count]}==set(variants)
                   for start,count in boundaries):break
        else:raise RuntimeError('Cannot allocate variant coverage across grouped splits')
        family_index=0
        for split,sizes in splits.items():
            for size in sizes:
                variant,target=chosen[family_index];family_index+=1
                group_id=f'G{len(groups)+1:03d}'
                family={'fault_class':fault_class,'variant':variant,'target':target}
                groups.append({'group_id':group_id,'split':split,'family':family,'case_count':size})
                for offset in range(size):
                    case_number=len(scenarios)+1
                    profile=list(TRAFFIC)[offset%len(TRAFFIC)]
                    pause=TRAFFIC[profile]
                    if variant=='pod-failure' and offset>=3:
                        pause=POD_EXTRA_PAUSES[offset-3]
                        profile=f'checkout-pause-{pause:.2f}s'
                    level=offset%5
                    if variant=='cpu': parameters={'workers':1+(offset%2),'load_percent':100}
                    elif variant=='memory':parameters={'additional_memory_fraction_of_declared_limit':[0.6,0.7,0.8,0.75,0.65][level]}
                    elif variant=='network-delay':parameters={'latency_ms':[100,200,300,450,600][level],'jitter_ms':20}
                    elif variant=='network-loss':parameters={'loss_percent':[10,15,20,25,30][level]}
                    else:parameters={'action':'pod-kill','replicas':1}
                    scenarios.append({'scenario_id':f'S{case_number:04d}','group_id':group_id,'split':split,
                        **family,'target':list(target) if isinstance(target,tuple) else target,
                        'traffic_profile':profile,'replicate_index':1 if variant=='pod-failure' else offset//len(TRAFFIC)+1,
                        'parameters':parameters,'duration_seconds':0 if variant=='pod-failure' else [30,45,60,90,120][level],
                        'traffic_pause_seconds':pause,'seed':42+case_number*13,
                        'execution_status':'planned_not_run','admission_status':'not_collected'})
    counts=Counter(row['fault_class'] for row in scenarios)
    split_counts=Counter(row['split'] for row in scenarios)
    assert len(scenarios)==200 and counts=={'Resource Exhaustion':67,'Network Delay / Packet Loss':67,'Pod Failure':66}
    assert split_counts=={'reference':120,'validation':40,'test':40}
    assert len({json.dumps(group['family'],sort_keys=True) for group in groups})==len(groups)
    plan={'status':'collection_plan_precommitted','plan_version':'0.3.0','execution_status':'planned_only','official_cases_collected':0,
          'note':'200 distinct nominal settings by variant/target/parameters/duration/traffic pause; 28 grouped scenario families, not 200 distinct failure mechanisms. Pod traffic pauses vary; first three settings per family are preserved from v0.2. Observed near-duplicate/effect review still required. This is a plan, not admitted data.',
          'seed':42,'fault_counts':dict(counts),'split_counts':dict(split_counts),'groups':groups,'scenarios':scenarios}
    target=Path('experiments/scenario-plan.json')
    target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'planned':len(scenarios),'collected_official':0,'groups':len(groups),
                      'fault_counts':dict(counts),'split_counts':dict(split_counts),'path':str(target)},indent=2))


if __name__=='__main__':main()
