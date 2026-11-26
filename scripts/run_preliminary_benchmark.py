#!/usr/bin/env python3
"""Preliminary B0–B3 on captured test cases that have NOT passed independent review. Preview by default.

User decision 2026-11-26 ("chạy benchmark đi rồi hoàn thiện"): score before review, report clearly as
preliminary and separate from the official benchmark. Generations are capped at --max-generations across
all runs (approval "Duyệt tối đa 40 lượt"), no retries; failures stay in the denominator. The result is
marked reportable only with >=10 cases covering all three fault classes (same floor as the early-stop rule).
"""
import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.evaluate import score,wilson
from app.report_schema import IncidentReport

OUTPUT=ROOT/'results/evaluation/preliminary-test-B0-B3.json'
MODES=('B0','B1','B2','B3')


def spent(folder,manifest):
    total=0
    for case in manifest['cases']:
        execution=(folder/case['approval_packet']/'execution.json')
        if execution.exists():
            total+=len(json.loads(execution.read_text()).get('attempts',[]))
    return total


def evaluate(manifest,base):
    rows=[]
    for case in manifest['cases']:
        for mode in MODES:
            row={'case_id':case['case_id'],'scenario_id':case['scenario_id'],'mode':mode,'fault_type':case['expected']['fault_type'],
                 'status':'missing_report','top1_correct':False,'top3_correct':False}
            path=base/case['reports'][mode]
            if path.exists():
                try:
                    saved=json.loads(path.read_text());report=IncidentReport.model_validate(saved['generated']['report'])
                    if saved['mode']!=mode or report.incident_id!=case['context_id']:raise ValueError('mismatch')
                    row.update(score(case['expected'],[h.model_dump() for h in report.hypotheses]),status='valid_report',report=str(path))
                except (ValueError,KeyError,TypeError) as exc:row.update(status='invalid_report',error_type=type(exc).__name__)
            rows.append(row)
    groups=defaultdict(list)
    for row in rows:groups[(row['mode'],'all')].append(row);groups[(row['mode'],row['fault_type'])].append(row)
    summaries=[]
    for (mode,fault),group in sorted(groups.items()):
        n=len(group);s={'mode':mode,'fault_class':fault,'denominator':n,'valid_reports':sum(r['status']=='valid_report' for r in group),
                        'missing_or_invalid_reports':sum(r['status']!='valid_report' for r in group)}
        for metric in ('top1_correct','top3_correct'):
            k=sum(r[metric] for r in group);s[metric]={'count':k,'rate':k/n,'wilson_95_ci':wilson(k,n)}
        summaries.append(s)
    faults={c['expected']['fault_type'] for c in manifest['cases']}
    return {'dataset_role':'preliminary_unreviewed_test','case_count':len(manifest['cases']),
            'reportable':len(manifest['cases'])>=10 and len(faults)==3,'rows':rows,'summaries':summaries,
            'scored_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'limitations':['Cases were captured under the frozen protocol but NOT independently reviewed; some may later be rejected.',
                           'Separate from the official early-stop benchmark; do not merge.','Missing/invalid reports count as incorrect.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--journal',type=Path,required=True);parser.add_argument('--max-generations',type=int,default=40)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    subprocess.run([sys.executable,str(ROOT/'scripts/prepare_prospective_benchmark.py'),'--journal',str(args.journal),
                    '--split','test','--preliminary'],cwd=ROOT,check=True,capture_output=True)
    journal=json.loads(args.journal.read_text());folder=ROOT/'results/prospective-benchmark'/journal['release_sha256'][:12]/'test'
    manifest=json.loads((folder/'manifest-preliminary.json').read_text())
    pending=[c for c in manifest['cases'] if not (folder/c['approval_packet']/'execution.json').exists()]
    used=spent(folder,manifest);needed=3*len(pending)
    plan={'cases':len(manifest['cases']),'pending_cases':[c['scenario_id'] for c in pending],'generations_used':used,
          'generations_needed':needed,'cap':args.max_generations}
    if used+needed>args.max_generations:
        # Run as many whole cases as the remaining budget allows, in manifest order.
        allowed=max(0,(args.max_generations-used)//3);plan['budget_limited_to_cases']=allowed;pending=pending[:allowed]
    if not args.execute:print(json.dumps({'status':'preview_only_no_api',**plan},indent=2));return 0
    if pending:
        record=(folder/pending[0]['approval_packet']).resolve().parent/'authorization-record-preliminary.json'
        if not record.exists():
            record.write_text(json.dumps({'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'User replies in chat',
                'user_reply':['Duyệt tối đa 40 lượt','chạy benmark đi rồi hoàn thiện'],'scope':'B1–B3 on captured, not yet reviewed test cases',
                'max_generation_requests_total':args.max_generations,'automatic_retries':0,'reindex_allowed':False},ensure_ascii=False,indent=2)+'\n')
    for case in pending:
        code=subprocess.call([sys.executable,str(ROOT/'scripts/run_approved_comparison.py'),'--approved-packet',
                              str((folder/case['approval_packet']).resolve())],cwd=ROOT)
        print(case['scenario_id'],'ok' if code==0 else 'failed (kept in denominator)',flush=True)
    result=evaluate(manifest,folder);result['generations_used']=spent(folder,manifest)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'cases':result['case_count'],'reportable':result['reportable'],'generations_used':result['generations_used'],
                      'top1':{s['mode']:f"{s['top1_correct']['count']}/{s['denominator']}" for s in result['summaries'] if s['fault_class']=='all'}},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
