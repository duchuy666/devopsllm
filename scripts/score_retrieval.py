#!/usr/bin/env python3
"""Offline Recall@3/MRR@3 from actual independent relevance labels, no cloud."""
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.apply_admission_review import validate_review


def metrics(relevant,hits,k=3):
    if len(hits)!=len(set(hits)):raise ValueError('Duplicate runbook IDs change retrieval ranks')
    relevant=set(relevant)
    if not relevant:return {'recall_at_3':None,'reciprocal_rank_at_3':None,'status':'no_relevant_runbook'}
    ranks=[i for i,item in enumerate(hits[:k],1) if item in relevant]
    return {'recall_at_3':len(ranks)/len(relevant),'reciprocal_rank_at_3':1/min(ranks) if ranks else 0,
            'status':'scored'}


def evaluate(manifest,base,root=ROOT):
    rows=[];books={p.stem for p in (root/'knowledge/runbooks').glob('*.md')}
    for case in manifest['cases']:
        reason=None;packet_path=root/'results/review-handoff/prospective-review'/(case['case_id']+'.json')
        try:
            packet=json.loads(packet_path.read_text());record=packet['independent_review'];validate_review(record)
            if packet['candidate_id']!=case['case_id']:raise ValueError('Reviewer candidate identity mismatch')
            if record.get('runbook_relevance_reviewed') is not True:raise ValueError('Relevance not explicitly reviewed')
            relevant=record['relevant_runbook_ids']
            if not isinstance(relevant,list) or len(relevant)!=len(set(relevant)) or not set(relevant)<=books:
                raise ValueError('Unknown or duplicate relevant runbook IDs')
            if case['admission_status']!='admitted':raise ValueError('Case admission pending')
        except (OSError,KeyError,ValueError,TypeError) as exc:reason=type(exc).__name__+': '+str(exc)
        for mode in ('B2','B3'):
            row={'case_id':case['case_id'],'mode':mode,'status':'pending_review_or_admission',
                 'recall_at_3':None,'reciprocal_rank_at_3':None}
            if reason:row['reason']=reason;rows.append(row);continue
            hits=[];row['report_status']='missing_report'
            try:
                saved=json.loads((base/case['reports'][mode]).read_text())
                if saved['mode']!=mode or saved['generated']['report']['incident_id']!=case['context_id']:
                    raise ValueError('Report context/mode mismatch')
                hits=[h['runbook_id'] for h in saved['knowledge']]
                if not set(hits)<=books or len(hits)!=len(set(hits)):raise ValueError('Unknown or duplicate retrieval IDs')
                row['report_status']='valid_retrieval'
            except FileNotFoundError:pass
            except (OSError,ValueError,KeyError,TypeError):row['report_status']='invalid_retrieval';hits=[]
            row.update(metrics(relevant,hits));row['retrieved_runbook_ids']=hits;rows.append(row)
    summaries={}
    for mode in ('B2','B3'):
        group=[r for r in rows if r['mode']==mode];scored=[r for r in group if r['status']=='scored']
        summaries[mode]={'declared_cases':len(group),'scored_relevance_cases':len(scored),
            'pending_review_or_admission':sum(r['status']=='pending_review_or_admission' for r in group),
            'no_relevant_runbook':sum(r['status']=='no_relevant_runbook' for r in group),
            'missing_or_invalid_retrieval':sum(r.get('report_status') in ('missing_report','invalid_retrieval') for r in scored),
            'mean_recall_at_3':statistics.mean(r['recall_at_3'] for r in scored) if scored else None,
            'mrr_at_3':statistics.mean(r['reciprocal_rank_at_3'] for r in scored) if scored else None}
    return {'dataset_role':manifest['dataset_role'],'status':'complete' if not any(v['pending_review_or_admission'] for v in summaries.values()) else 'incomplete_do_not_claim_final_metrics',
        'rows':rows,'summaries':summaries,'cloud_called':False,
        'limitations':['Human relevance labels required; never inferred from cosine scores or injected fault class.',
            'Missing/invalid retrievals score zero when relevant books exist; pending labels are explicitly reported.',
            'Cases with no relevant book have undefined Recall/MRR and are counted separately.',
            'Relevance completeness does not establish semantic claim grounding or reviewer identity authenticity.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve prior analyses; select a new output')
    m=json.loads(a.manifest.read_text());result=evaluate(m,a.manifest.resolve().parent)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'summaries':result['summaries']},ensure_ascii=False))


if __name__=='__main__':main()
