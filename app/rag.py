"""Gemini embeddings and Qdrant retrieval over explicitly curated runbooks."""
import hashlib
import json
import math
from pathlib import Path
import uuid
import datetime
from google.genai import types
from qdrant_client import QdrantClient,models
import yaml
from app.gemini_provider import client,settings

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.runtime/knowledge-index.json'


def embed(text,task):
    config=settings()
    identity=json.dumps([config['embedding_model'],config['dimension'],task,text],ensure_ascii=False)
    cache=ROOT/'.runtime/embeddings'/f'{hashlib.sha256(identity.encode()).hexdigest()}.json'
    if cache.exists(): return json.loads(cache.read_text())['vector']
    with client() as api:
        result=api.models.embed_content(model=config['embedding_model'],contents=text,
            config=types.EmbedContentConfig(task_type=task,output_dimensionality=config['dimension']))
    if not result.embeddings or len(result.embeddings)!=1: raise ValueError('Expected exactly one embedding')
    vector=result.embeddings[0].values
    if not vector or len(vector)!=config['dimension']: raise ValueError('Unexpected embedding dimension')
    norm=math.sqrt(sum(x*x for x in vector))
    if not norm: raise ValueError('Zero embedding vector')
    vector=[x/norm for x in vector]
    cache.parent.mkdir(parents=True,exist_ok=True)
    usage=result.usage_metadata.model_dump(mode='json',exclude_none=True) if result.usage_metadata else None
    entry={'model':config['embedding_model'],'dimension':config['dimension'],'task':task,'vector':vector,
           'usage_metadata':usage,'truncated':result.truncated}
    cache.write_text(json.dumps(entry)+'\n')
    ledger=ROOT/'results/embedding-calls';ledger.mkdir(parents=True,exist_ok=True)
    (ledger/(cache.stem+'.json')).write_text(json.dumps({'model':config['embedding_model'],'dimension':config['dimension'],
        'task':task,'input_characters':len(text),'input_hash':cache.stem,'usage_metadata':usage,
        'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'api_cost_usd':None,
        'cost_status':'pricing_not_configured'},indent=2)+'\n')
    return vector


def index_runbooks():
    config=settings()
    if not config['key']: raise RuntimeError('GEMINI_API_KEY is empty; no embeddings or collection were created.')
    paths=sorted((ROOT/'knowledge/runbooks').glob('*.md'))
    if not paths: raise RuntimeError('No curated runbooks found')
    documents=[]
    for path in paths:
        raw=path.read_text()
        pieces=raw.split('---',2)
        if len(pieces)!=3: raise ValueError(f'Runbook metadata is missing: {path.name}')
        metadata=yaml.safe_load(pieces[1])
        if not metadata.get('runbook_id') or not metadata.get('version'): raise ValueError('Runbook ID/version required')
        documents.append({'metadata':metadata,'text':pieces[2].strip(),'hash':hashlib.sha256(raw.encode()).hexdigest()})
    kb_version=hashlib.sha256(json.dumps([d['hash'] for d in documents]).encode()).hexdigest()[:16]
    collection=f'runbooks_{config["dimension"]}_{hashlib.sha256(config["embedding_model"].encode()).hexdigest()[:8]}'
    qdrant=QdrantClient(url='http://127.0.0.1:6333',timeout=30)
    points=[]
    for doc in documents:
        vector=embed(doc['text'],'RETRIEVAL_DOCUMENT')
        meta=doc['metadata']
        points.append(models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,kb_version+meta['runbook_id'])),
            vector=vector,payload={'role':'reference_runbook','kb_version':kb_version,'runbook_id':meta['runbook_id'],
              'version':meta['version'],'status':meta.get('status'),'fault_class':meta.get('fault_class'),'text':doc['text']}))
    if not qdrant.collection_exists(collection):
        qdrant.create_collection(collection,vectors_config=models.VectorParams(size=config['dimension'],distance=models.Distance.COSINE))
    qdrant.upsert(collection,points=points,wait=True)
    state={'collection':collection,'kb_version':kb_version,'embedding_model':config['embedding_model'],
           'dimension':config['dimension'],'runbook_count':len(points),'source_hashes':[d['hash'] for d in documents]}
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    qdrant.close()
    return state


def retrieval_query(context):
    pieces=[]
    for metric in ('cpu','memory','latency_mean','error_rate','request_rate','ready','restarts','created'):
        selected=[r for r in context['metrics'] if r['metric']==metric][:2]
        for row in selected:
            target=row.get('pod') or str(row.get('service'))+' '+str(row.get('route'))
            pieces.append(f'{metric} {target} initial={row["initial_window_mean"]:.4g} max={row["max"]:.4g} min={row["min"]:.4g}')
    pieces.extend('log '+r['service']+' '+r['template'][:150] for r in context['logs'][:4])
    pieces.extend(f'span {r["service"]} {r["operation"][:60]} {r["duration_ms"]:.3g}ms' for r in context['traces'][:4])
    return '\n'.join(pieces)


def retrieve(context,top_k=3):
    if not STATE.exists(): raise RuntimeError('Knowledge base is not indexed. Run make rag-index after configuring Gemini key.')
    state=json.loads(STATE.read_text())
    config=settings()
    if state['embedding_model']!=config['embedding_model'] or state['dimension']!=config['dimension']:
        raise RuntimeError('Embedding configuration changed; reindex before retrieval')
    query=retrieval_query(context)
    vector=embed(query,'RETRIEVAL_QUERY')
    qdrant=QdrantClient(url='http://127.0.0.1:6333',timeout=30)
    result=qdrant.query_points(state['collection'],query=vector,limit=top_k,with_payload=True,
        query_filter=models.Filter(must=[models.FieldCondition(key='role',match=models.MatchValue(value='reference_runbook')),
                                       models.FieldCondition(key='kb_version',match=models.MatchValue(value=state['kb_version']))]))
    hits=[{'score':p.score,**p.payload} for p in result.points]
    qdrant.close()
    return hits
