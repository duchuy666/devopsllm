"""Operational memory: retrieve resolved reference incidents alongside runbooks (proposal §3.1, §5.4).

Leakage rules enforced here, not left to the caller:
  * only cases that are admitted AND in the reference split can be indexed (never validation/test);
  * the document is built from the same model-facing observation window, plus the reviewed label;
  * retrieval is filtered on role/version so stale or foreign points are never returned.
Kept separate from app/rag.py, which the collection release pins by hash.
"""
import hashlib
import json
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.runtime/case-memory-index.json'
ROLE='reference_case'


def eligible(ground):
    scenario=ground.get('scenario',{})
    if ground.get('admission_status')!='admitted':raise ValueError('Only independently admitted cases can enter case memory')
    if scenario.get('split')!='reference':raise ValueError('Only reference-split cases can enter case memory; validation/test never')
    if ground.get('dataset_role')!='prospective_candidate':raise ValueError('Only prospective dataset cases')


def case_document(folder):
    """Symptoms from the observation window + the reviewed outcome. No chaos parameters or qdisc."""
    from app.context_builder import build_context
    from app.rag import retrieval_query
    folder=Path(folder);ground=json.loads((folder/'ground-truth.json').read_text());eligible(ground)
    scenario=ground['scenario'];context,_=build_context(folder/'observation/telemetry')
    symptoms=retrieval_query(context)
    case_id='CASE-'+hashlib.sha256(folder.name.encode()).hexdigest()[:12]
    text=(f'Sự cố đã xác nhận {case_id}: {scenario["fault_class"]} tại {scenario["target"]}.\n'
          f'Triệu chứng quan sát được trong cửa sổ chẩn đoán:\n{symptoms}')
    return {'case_id':case_id,'fault_class':scenario['fault_class'],'service_or_edge':scenario['target'],
            'group_id':scenario['group_id'],'text':text,'source_sha256':hashlib.sha256(text.encode()).hexdigest()}


def index_cases(root=ROOT,embed=None,client=None):
    """Embed every eligible case; returns the state. Each embedding is one Gemini call (ledgered by rag.embed)."""
    from qdrant_client import QdrantClient,models
    from app.gemini_provider import settings
    if embed is None:from app.rag import embed
    root=Path(root);config=settings()
    registry=json.loads((root/'experiments/candidate-registry.json').read_text())
    documents=[]
    for attempt in registry['attempts']:
        folder=root/'data/candidates'/attempt['candidate_id']
        try:ground=json.loads((folder/'ground-truth.json').read_text());eligible(ground)
        except (OSError,ValueError):continue
        documents.append(case_document(folder))
    if not documents:raise RuntimeError('No admitted reference cases yet; nothing indexed')
    version=hashlib.sha256(json.dumps(sorted(d['source_sha256'] for d in documents)).encode()).hexdigest()[:16]
    collection=f'cases_{config["dimension"]}_{hashlib.sha256(config["embedding_model"].encode()).hexdigest()[:8]}'
    qdrant=client or QdrantClient(url='http://127.0.0.1:6333',timeout=30)
    if not qdrant.collection_exists(collection):
        qdrant.create_collection(collection,vectors_config=models.VectorParams(size=config['dimension'],distance=models.Distance.COSINE))
    points=[models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,version+d['case_id'])),vector=embed(d['text'],'RETRIEVAL_DOCUMENT'),
                               payload={'role':ROLE,'case_memory_version':version,**d}) for d in documents]
    qdrant.upsert(collection,points=points,wait=True)
    state={'collection':collection,'case_memory_version':version,'embedding_model':config['embedding_model'],
           'dimension':config['dimension'],'case_count':len(points),'groups':sorted({d['group_id'] for d in documents}),
           'source_hashes':sorted(d['source_sha256'] for d in documents)}
    STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(state,indent=2)+'\n')
    return state


def retrieve_cases(context,top_k=2,embed=None,client=None,state_path=None):
    from qdrant_client import QdrantClient,models
    from app.gemini_provider import settings
    from app.rag import retrieval_query
    if embed is None:from app.rag import embed
    path=Path(state_path or STATE)
    if not path.exists():raise RuntimeError('Case memory is not indexed; run scripts/index_case_memory.py')
    state=json.loads(path.read_text());config=settings()
    if state['embedding_model']!=config['embedding_model'] or state['dimension']!=config['dimension']:
        raise RuntimeError('Embedding configuration changed; rebuild case memory')
    qdrant=client or QdrantClient(url='http://127.0.0.1:6333',timeout=30)
    result=qdrant.query_points(state['collection'],query=embed(retrieval_query(context),'RETRIEVAL_QUERY'),limit=top_k,with_payload=True,
        query_filter=models.Filter(must=[models.FieldCondition(key='role',match=models.MatchValue(value=ROLE)),
            models.FieldCondition(key='case_memory_version',match=models.MatchValue(value=state['case_memory_version']))]))
    hits=[{'score':p.score,**p.payload} for p in result.points]
    if any(h.get('role')!=ROLE for h in hits):raise RuntimeError('Non-case point returned from case memory')
    return hits
