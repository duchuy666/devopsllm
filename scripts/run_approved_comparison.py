#!/usr/bin/env python3
"""Execute only after explicit approval of this packet; preserve attempt limits."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import yaml
from app.diagnosis import diagnose,observed_context
from app.gemini_provider import settings,prompt_fingerprint
from app.rag import retrieval_query

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--approved-packet',type=Path,required=True)
    parser.add_argument('--check-only',action='store_true',help='Validate locally; do not create execution state or invoke APIs')
    args=parser.parse_args()
    packet=args.approved_packet.resolve()
    manifest=json.loads((packet/'request-manifest.json').read_text())
    for name,expected in manifest['files_sha256'].items():
        if Path(name).name!=name or hashlib.sha256((packet/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Reviewed packet changed; no new API call')
    pin=manifest.get('prompt_fingerprint')
    if pin is None:
        if not args.check_only:raise RuntimeError('Legacy packet has no reviewed prompt pin; prepare a new packet for approval')
    elif pin!=prompt_fingerprint():raise RuntimeError('Reviewed prompt/schema changed; no new API call')
    if manifest['max_generation_requests']!=3 or manifest['max_query_embedding_requests']!=2 or manifest['automatic_retries']!=0:
        raise RuntimeError('Unexpected packet budget')
    source=json.loads((packet/'source-context.json').read_text())
    books=json.loads((packet/'allowed-runbooks.json').read_text())
    allowed={}
    for book in books:
        current=ROOT/'knowledge/runbooks'/book['file']
        if Path(book['file']).name!=book['file'] or current.read_text()!=book['text']:
            raise RuntimeError('Runbook sources changed')
        _,frontmatter,text=book['text'].split('---',2)
        meta=yaml.safe_load(frontmatter)
        allowed[meta['runbook_id']]={'version':meta['version'],'text':text.strip()}

    def guard():
        if pin is not None and pin!=prompt_fingerprint():raise RuntimeError('Reviewed prompt/schema changed')
        config=settings()
        for setting,field in [('model','model'),('embedding_model','embedding_model'),
                              ('dimension','embedding_dimension'),('thinking_level','thinking_level')]:
            if config[setting]!=manifest[field]:raise RuntimeError('Provider config changed')
        state=json.loads((ROOT/'.runtime/knowledge-index.json').read_text())
        if state['kb_version']!=manifest['kb_version'] or state['collection']!=manifest['collection']:
            raise RuntimeError('Knowledge index changed')
        hashes=[hashlib.sha256(book['text'].encode()).hexdigest() for book in books]
        if state['source_hashes']!=hashes:raise RuntimeError('Knowledge index source mismatch')

    def validate_hits(hits):
        if len(hits)>3:raise RuntimeError('Too many retrieved runbooks')
        for hit in hits:
            expected=allowed.get(hit.get('runbook_id'))
            if not expected or hit.get('version')!=expected['version'] or hit.get('text')!=expected['text'] or hit.get('kb_version')!=manifest['kb_version'] or hit.get('role')!='reference_runbook':
                raise RuntimeError('Retrieved knowledge differs from approved runbooks')

    guard()
    for mode in ('B1','B2','B3'):
        observed=observed_context(source,mode)
        if observed!=json.loads((packet/(mode+'-context.json')).read_text()):
            raise RuntimeError('Mode context changed')
        if mode!='B1' and retrieval_query(observed).strip()!=(packet/(mode+'-embedding-query.txt')).read_text().strip():
            raise RuntimeError('Mode embedding query changed')
        if (ROOT/'results/diagnoses'/source['incident_id']/mode/'result.json').exists():
            raise RuntimeError('Refuse to overwrite an existing report')
    if args.check_only:
        print(json.dumps({'packet_valid':True,'context_id':source['incident_id'],'api_called':False}))
        return 0
    # Exclusive creation: a failed/interrupted run cannot silently spend again.
    execution_path=packet/'execution.json'
    with execution_path.open('x') as handle:
        json.dump({'status':'started','attempts':[]},handle)
    execution={'status':'running','context_id':source['incident_id'],'attempts':[]}
    for mode in ('B1','B2','B3'):
        guard()
        attempt={'mode':mode,'status':'attempt_started','at':dt.datetime.now(dt.timezone.utc).isoformat()}
        execution['attempts'].append(attempt)
        execution_path.write_text(json.dumps(execution,indent=2)+'\n')
        try:
            result=diagnose(source,mode,ROOT/'results/diagnoses',knowledge_validator=validate_hits)
            attempt.update(status='completed',call_id=result['generated']['api_call_id'])
            print(mode,'completed',result['generated']['api_call_id'],flush=True)
        except Exception as exc:
            attempt.update(status='failed',error_type=type(exc).__name__)
            execution['status']='stopped_on_failure_no_retry'
            execution_path.write_text(json.dumps(execution,indent=2)+'\n')
            print(mode,'failed',type(exc).__name__,flush=True)
            return 1
        execution_path.write_text(json.dumps(execution,indent=2)+'\n')
    execution['status']='completed'
    execution_path.write_text(json.dumps(execution,indent=2)+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
