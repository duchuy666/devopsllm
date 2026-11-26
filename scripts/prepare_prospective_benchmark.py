#!/usr/bin/env python3
"""Prepare immutable observations/B0/cloud packets; never call Gemini or score pending cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import datetime as dt
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.collection_release import verify_release
from app.context_builder import build_context
from app.baseline import diagnose_rules,VERSION
from app.observation_window import crop


def verify_observation(path,ground):
    """Reconstruct the frozen window before producing model inputs."""
    anchor=dt.datetime.fromisoformat(ground['injection_confirmed_at']).timestamp()
    actual=path/'observation/telemetry'
    with tempfile.TemporaryDirectory() as temporary:
        expected=Path(temporary)/'observation'
        receipt=crop(path/'telemetry',expected,anchor-30,anchor+30)
        if json.loads((actual/'capture.json').read_text())!=receipt:
            raise ValueError('Observation receipt/raw hash mismatch: '+path.name)
        for name in ('metrics','logs','traces'):
            if json.loads((actual/(name+'.json')).read_text())!=json.loads((expected/(name+'.json')).read_text()):
                raise ValueError('Observation payload changed: '+path.name+'/'+name)


def stable_json(path,value):
    if path.exists():
        if json.loads(path.read_text())!=value:raise ValueError('Refuse to change a prepared input: '+str(path))
    else:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--split',choices=['reference','validation','test'],required=True)
    parser.add_argument('--allow-partial',action='store_true');args=parser.parse_args()
    if args.allow_partial and args.split!='reference':parser.error('Partial preparation is limited to reference')
    journal=json.loads(args.journal.read_text());release=Path(journal['release'])
    verify_release(release,ROOT,args.split)
    release_hash=hashlib.sha256(release.read_bytes()).hexdigest()
    if release_hash!=journal['release_sha256']:raise ValueError('Journal/release mismatch')
    planned=json.loads((ROOT/'experiments/scenario-plan.json').read_text())['scenarios']
    wanted={r['scenario_id']:r for r in planned if r['split']==args.split};selected={}
    for attempt in journal['attempts']:
        if attempt['status']!='captured_requires_review' or attempt['scenario_id'] not in wanted:continue
        if len(attempt['candidate_paths'])!=1:raise ValueError('Ambiguous candidate')
        path=ROOT/attempt['candidate_paths'][0];ground=json.loads((path/'ground-truth.json').read_text())
        expected_release=attempt.get('inherited_from_release_sha256',release_hash)
        if ground['scenario']!=wanted[attempt['scenario_id']] or ground.get('collection_release_sha256')!=expected_release:
            raise ValueError('Candidate setting/release mismatch')
        if attempt['scenario_id'] in selected:raise ValueError('Explicit selection required for repeated captures')
        selected[attempt['scenario_id']]=(path,ground)
    if not args.allow_partial and set(selected)!=set(wanted):
        raise ValueError(f'Complete split required: {len(selected)}/{len(wanted)} captured')
    if not selected:raise ValueError('No completed observations for this split')
    output=ROOT/'results/prospective-benchmark'/release_hash[:12]/args.split;output.mkdir(parents=True,exist_ok=True)
    approval=ROOT/'results/approval'/('prospective-'+release_hash[:12])/args.split
    cases=[]
    for key,(path,ground) in sorted(selected.items()):
        verify_observation(path,ground)
        context,index=build_context(path/'observation/telemetry')
        if context['missing_sources']:raise ValueError('Missing observation modality')
        directory=output/key
        stable_json(directory/'context.json',context);stable_json(directory/'evidence-index.json',index)
        baseline=ROOT/'results/baselines'/VERSION/context['incident_id']/'B0/result.json'
        if not baseline.exists():
            started=time.perf_counter();report=diagnose_rules(context);elapsed=time.perf_counter()-started
            stable_json(baseline,{'mode':'B0','context_id':context['incident_id'],'baseline_version':VERSION,
                'generated':{'report':report,'provider':'local_rules','latency_seconds':elapsed,'api_cost_usd':0}})
        else:
            saved=json.loads(baseline.read_text())
            if saved['context_id']!=context['incident_id'] or saved['baseline_version']!=VERSION:
                raise ValueError('Existing B0 identity mismatch')
        packet=approval/key
        if not packet.exists():
            subprocess.run([sys.executable,str(ROOT/'scripts/prepare_comparison.py'),str(path/'observation/telemetry'),
                            '--output',str(packet),'--dataset-role','prospective_'+args.split],check=True,capture_output=True)
        elif json.loads((packet/'source-context.json').read_text())!=context:
            raise ValueError('Prepared cloud context changed')
        # Ground truth is used for the scoring manifest after prediction, never in context/packets.
        row=ground['scenario']
        cases.append({'case_id':path.name,'scenario_id':key,'group_id':row['group_id'],
            'context_id':context['incident_id'],'split':args.split,'admission_status':ground['admission_status'],
            'context_file':os.path.relpath(directory/'context.json',output),
            'candidate_path':os.path.relpath(path,output),'approval_packet':os.path.relpath(packet,output),
            'expected':{'target':row['target'],'fault_type':row['fault_class']},
            'reports':{'B0':os.path.relpath(baseline,output),**{mode:os.path.relpath(
                ROOT/'results/diagnoses'/context['incident_id']/mode/'result.json',output) for mode in ('B1','B2','B3')}}})
    manifest={'dataset_role':'official_test' if args.split=='test' else 'development_pilot',
        'status':'prepared_for_scoring' if all(c['admission_status']=='admitted' for c in cases) else 'pending_admission_do_not_score',
        'modes':['B0','B1','B2','B3'],'release_sha256':release_hash,'cases':cases,
        'max_new_generation_requests_if_separately_approved':3*len(cases),
        'max_query_embedding_requests_if_separately_approved':2*len(cases),
        'generation_called':False,'embedding_called':False,
        'note':'Manifest report paths are relative to this directory. Pending admission cannot be scored as an official test. Preparation is not API authorization.'}
    # This manifest can refresh admission metadata; contexts/reports/packets above stay immutable.
    temporary=output/'manifest.json.tmp';temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(output/'manifest.json')
    print(json.dumps({'manifest':str(output/'manifest.json'),'cases':len(cases),'status':manifest['status'],
                      'cloud_called':False},indent=2))


if __name__=='__main__':main()
