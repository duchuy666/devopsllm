#!/usr/bin/env python3
"""Audit planned and collected data locally without admitting or uploading cases."""
import argparse
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.audit_plan import audit
from experiments.review_case import review


def evaluate(root=ROOT):
    plan=json.loads((root/'experiments/scenario-plan.json').read_text())
    planned={r['scenario_id']:r for r in plan['scenarios']}
    registry=json.loads((root/'experiments/candidate-registry.json').read_text())
    errors=[];cases=[];payloads=defaultdict(list);seen=set()
    for entry in registry['attempts']:
        key=entry['candidate_id'];path=root/entry['path']
        if key in seen:errors.append('Duplicate registry candidate: '+key)
        seen.add(key)
        if not path.resolve().is_relative_to((root/'data/candidates').resolve()):
            errors.append('Candidate outside data/candidates: '+key);continue
        try:
            ground=json.loads((path/'ground-truth.json').read_text());row=ground['scenario']
            if row['scenario_id'] not in planned:raise ValueError('Unknown scenario')
            for name in ('scenario_id','group_id','split','fault_class','variant','target','parameters','duration_seconds','seed'):
                if row[name]!=planned[row['scenario_id']][name]:raise ValueError('Plan mismatch: '+name)
            if entry['scenario_id']!=row['scenario_id'] or entry['split']!=row['split']:
                raise ValueError('Registry identity/split mismatch')
            if entry['admission_status']!=ground['admission_status']:
                raise ValueError('Registry admission mismatch')
            if entry['execution_status']!=ground['execution_status']:
                raise ValueError('Registry execution mismatch')
            if ground['admission_status']=='admitted' and ground['execution_status']!='captured_requires_review':
                raise ValueError('Failed/preflight attempt cannot be officially admitted')
            result={'candidate_id':key,'scenario_id':row['scenario_id'],'split':row['split'],
                    'variant':row['variant'],'execution_status':ground['execution_status'],
                    'admission_status':ground['admission_status'],'official_admitted':ground['admission_status']=='admitted'}
            if ground['execution_status']=='captured_requires_review':
                result['structural_checks']=review(path)['checks']
                if not all(result['structural_checks'].values()):raise ValueError('Captured case failed structural review')
                for name in ('metrics','logs','traces'):
                    data=(path/'telemetry'/f'{name}.json').read_bytes();json.loads(data)
                    payloads[(name,hashlib.sha256(data).hexdigest())].append((key,row['split']))
                provenance=path/'provenance.json'
                if provenance.exists():
                    record=json.loads(provenance.read_text());bad=[]
                    for name,digest in record['files_sha256'].items():
                        source=path/'provenance'/name if name=='scenario-plan.json' or name.startswith('baseline/') else path/'provenance/files'/name
                        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:bad.append(name)
                    if bad:raise ValueError('Provenance checksum mismatch: '+str(bad))
                    result['provenance']='checksums_verified'
                else:result['provenance']='legacy_candidate_without_source_snapshot'
                effect=json.loads((path/'effect-review.json').read_text())
                result['technical_effect_status']=effect['status']
                result['independent_human_review']=effect.get('independent_human_review','pending')
                if entry['effect_review_status']!=effect['status']:
                    raise ValueError('Registry effect review mismatch')
                if result['official_admitted'] and result['independent_human_review']!='approved':
                    raise ValueError('Official admission lacks independent human approval')
            else:result['note']='Failed/preflight attempt retained; not a captured or admitted case'
            cases.append(result)
        except (OSError,ValueError,KeyError,TypeError) as exc:errors.append(key+': '+str(exc))
    unregistered=sorted(p.name for p in (root/'data/candidates').glob('CANDIDATE-*') if p.name not in seen)
    if unregistered:errors.append('Unregistered attempts: '+str(unregistered))
    duplicates=[{'source':name,'candidates':rows,'cross_split':len({s for _,s in rows})>1}
                for (name,_),rows in payloads.items() if len(rows)>1]
    if any(x['cross_split'] for x in duplicates):errors.append('Exact observed telemetry duplicates cross split')
    admitted=sum(c['official_admitted'] for c in cases)
    if admitted!=registry['official_admitted']:errors.append('Registry official count mismatch')
    structural=audit(plan);errors+=structural['errors']
    scenario_attempts=defaultdict(list)
    for case in cases:scenario_attempts[case['scenario_id']].append(case['candidate_id'])
    return {'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'status':'failed' if errors else 'local_checks_passed_official_dataset_incomplete',
        'errors':errors,'plan_audit':structural,'registered_attempts':len(registry['attempts']),
        'captured_cases':sum(c['execution_status']=='captured_requires_review' for c in cases),
        'official_admitted':admitted,'official_required':200,'remaining_official':200-admitted,
        'captured_variant_counts':dict(Counter(c['variant'] for c in cases if c['execution_status']=='captured_requires_review')),
        'repeated_scenario_attempts':{key:ids for key,ids in scenario_attempts.items() if len(ids)>1},
        'exact_telemetry_duplicates':duplicates,'cases':cases,'cloud_called':False,
        'limitations':['Plan/split checks are not evidence that 200 cases were executed.',
            'Exact file hashes do not establish absence of semantic near duplicates.',
            'Independent human/admission review and frozen protocol are still required.',
            'No official test accuracy or missing-case imputation is produced.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'results/evaluation/dataset-validation.json')
    args=parser.parse_args();result=evaluate();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','errors','registered_attempts','captured_cases','official_admitted','remaining_official','captured_variant_counts')},indent=2))
    raise SystemExit(bool(result['errors']))
