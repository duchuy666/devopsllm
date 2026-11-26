import copy
import json
from pathlib import Path
import time
from langchain_core.runnables import RunnableLambda,RunnableParallel,RunnablePassthrough
from app.gemini_provider import generate,settings
from app.rag import retrieve


def observed_context(context,mode):
    if mode not in ('B1','B2','B3'): raise ValueError('Mode must be B1, B2 or B3')
    observed=copy.deepcopy(context)
    if mode in ('B1','B2'):
        observed['metrics'],observed['traces']=[],[]
        observed['excluded_modalities']=['metrics','traces']
    if not any(observed[key] for key in ('metrics','logs','traces')):
        raise ValueError('No observed evidence available; generation was not called')
    return observed


def diagnose(context,mode='B3',output_root='results/diagnoses',knowledge_validator=None):
    settings()
    observed=observed_context(context,mode)
    def checked_retrieval(value):
        hits=retrieve(value)
        if knowledge_validator is not None: knowledge_validator(hits)
        return hits
    retrieval=RunnableLambda(checked_retrieval) if mode!='B1' else RunnableLambda(lambda value:[])
    chain=RunnableParallel(context=RunnablePassthrough(),knowledge=retrieval) | RunnableLambda(
        lambda values:{'generated':generate(values['context'],values['knowledge']),'knowledge':values['knowledge']})
    start=time.perf_counter()
    result=chain.invoke(observed,config={'callbacks':[]})
    result.update(mode=mode,analysis_latency_seconds=time.perf_counter()-start,
                  context_id=context['incident_id'],is_replay=True)
    out=Path(output_root)/context['incident_id']/mode
    out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'context.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2)+'\n')
    return result
