#!/usr/bin/env python3
"""Prepare a reviewable B1/B2/B3 packet locally; never invoke an API."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.context_builder import build_context
from app.diagnosis import observed_context
from app.gemini_provider import settings,prompt_fingerprint
from app.rag import retrieval_query

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('telemetry_dir',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dataset-role',choices=['development_pilot','prospective_reference','prospective_validation','prospective_test'],default='development_pilot')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Refuse to overwrite an existing review packet')
    context,index=build_context(args.telemetry_dir)
    prospective=args.dataset_role.startswith('prospective_')
    if prospective:
        capture=json.loads((args.telemetry_dir/'capture.json').read_text())
        if abs(capture['window_end']-capture['window_start']-60)>.01 or not capture.get('source_sha256') or context['missing_sources']:
            raise ValueError('Prospective packets require a complete precommitted 60-second observation')
    config=settings()
    args.output.mkdir(parents=True)
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    write('source-context.json',context)
    write('evidence-index.json',index)
    modes=[]
    for mode in ('B1','B2','B3'):
        observed=observed_context(context,mode)
        write(mode+'-context.json',observed)
        if mode!='B1':
            (args.output/(mode+'-embedding-query.txt')).write_text(retrieval_query(observed)+'\n')
        modes.append({'mode':mode,'evidence_counts':{k:len(observed[k]) for k in ('metrics','logs','traces')},
                      'context_file':mode+'-context.json','embedding_query_file':None if mode=='B1' else mode+'-embedding-query.txt'})
    books=[]
    for path in sorted((ROOT/'knowledge/runbooks').glob('*.md')):
        books.append({'file':path.name,'text':path.read_text()})
    write('allowed-runbooks.json',books)
    state=json.loads((ROOT/'.runtime/knowledge-index.json').read_text())
    manifest={'status':'prepared_not_approved_not_executed','provider':'Google Gemini API',
              'dataset_role':args.dataset_role,
              'context_id':context['incident_id'],'model':config['model'],'embedding_model':config['embedding_model'],
              'embedding_dimension':config['dimension'],'thinking_level':config['thinking_level'],
              'max_generation_requests':3,'max_query_embedding_requests':2,'reindex_allowed':False,
              'automatic_retries':0,'max_output_tokens_per_generation':4096,
              'modes':modes,'kb_version':state['kb_version'],'collection':state['collection'],
              'knowledge_policy':'B1 has none; B2/B3 retrieve at most 3 of the 5 included runbooks.',
              'estimate_note':'Paid generation reference roughly $0.03-$0.10; not a hard dollar cap or invoice. Embedding usage may be unavailable.',
              'data_note':'Redacted local Sock Shop observation; no API key, ground truth, injection parameters or qdisc counters.',
              'limitations':('Precommitted offline observation: injection-confirmed minus 30 to plus 30 seconds, completed spans only; not live TTD. Admission and scoring status tracked separately.' if prospective else 'Comparison development only. Observation may include recovery; not live TTD. Archived reports belong to their original context IDs.'),
              'prompt_fingerprint':prompt_fingerprint(),
              'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.iterdir())}}
    write('request-manifest.json',manifest)
    print(json.dumps({'packet':str(args.output),'context_id':context['incident_id'],'generation_called':False,
                      'embedding_called':False,'modes':modes},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
