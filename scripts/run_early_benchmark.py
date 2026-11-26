#!/usr/bin/env python3
"""Early-stop benchmark on admitted test cases: B0 local + approved B1–B3, then score. Preview by default.

Follows the precommitted early_stop rule in config/collection-protocol.yaml (>=10 admitted test cases
covering all three fault classes). Generation spend is capped by --max-generations (user approval on
2026-11-26: "Duyệt tối đa 40 lượt"); a run that would exceed the cap is refused before any call.
Failures are not retried and stay in the denominator as missing reports.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'results/evaluation/official-test-B0-B3.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--journal',type=Path,required=True);parser.add_argument('--max-generations',type=int,default=40)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    subprocess.run([sys.executable,str(ROOT/'scripts/prepare_prospective_benchmark.py'),'--journal',str(args.journal),
                    '--split','test','--early-stop'],cwd=ROOT,check=True)
    journal=json.loads(args.journal.read_text());release_hash=journal['release_sha256']
    folder=ROOT/'results/prospective-benchmark'/release_hash[:12]/'test';manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['status']!='prepared_for_scoring':raise SystemExit('Manifest contains non-admitted cases; refusing to score')
    pending=[c for c in manifest['cases'] if not all((folder/c['reports'][m]).exists() for m in ('B1','B2','B3'))]
    needed=3*len(pending)
    plan={'cases':len(manifest['cases']),'cases_needing_generation':len(pending),'generation_calls':needed,
          'query_embedding_calls':2*len(pending),'cap':args.max_generations}
    if needed>args.max_generations:raise SystemExit(f'Refused: {needed} generations exceed the approved cap {args.max_generations}: {plan}')
    if not args.execute:
        print(json.dumps({'status':'preview_only_no_api',**plan},indent=2));return 0
    approval=(folder/pending[0]['approval_packet']).resolve().parent if pending else None
    if approval:
        record=approval/'authorization-record.json'
        if not record.exists():
            record.write_text(json.dumps({'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'User reply in chat',
                'user_reply':'Duyệt tối đa 40 lượt','scope':'B1–B3 on admitted early-stop test cases only','max_generation_requests':args.max_generations,
                'automatic_retries':0,'reindex_allowed':False,
                'manifest_sha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
    failures=[]
    for case in pending:
        packet=(folder/case['approval_packet']).resolve()
        code=subprocess.call([sys.executable,str(ROOT/'scripts/run_approved_comparison.py'),'--approved-packet',str(packet)],cwd=ROOT)
        if code:failures.append(case['scenario_id'])
    subprocess.run([sys.executable,str(ROOT/'experiments/evaluate.py'),str(folder/'manifest.json'),'--output',str(OUTPUT)],cwd=ROOT,check=True)
    result=json.loads(OUTPUT.read_text())
    print(json.dumps({'scored_cases':result['case_count'],'failed_cases_kept_in_denominator':failures,
                      'top1':{s['mode']:f"{s['top1_correct']['count']}/{s['denominator']}" for s in result['summaries'] if s['fault_class']=='all'},
                      'output':str(OUTPUT)},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
