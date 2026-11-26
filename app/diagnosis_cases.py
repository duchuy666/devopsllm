"""B2/B3 diagnosis with runbooks AND resolved reference cases in the prompt.

Same chain as app.diagnosis (pinned by the collection release, so not edited). Runbook hits stay in
result['knowledge'] (unchanged shape for scripts/score_retrieval.py); case hits go to
result['retrieved_cases']. B1 still retrieves nothing.
"""
import json
from pathlib import Path
import time
from langchain_core.runnables import RunnableLambda,RunnableParallel,RunnablePassthrough
from app.case_memory import retrieve_cases
from app.diagnosis import observed_context
from app.gemini_provider import generate,settings
from app.rag import retrieve

MODE_SUFFIX='-cases'


def diagnose_with_cases(context,mode='B3',output_root='results/diagnoses',case_top_k=2):
    settings();observed=observed_context(context,mode)
    if mode=='B1':raise ValueError('B1 is the no-retrieval baseline; use app.diagnosis.diagnose')
    retrieval=RunnableParallel(runbooks=RunnableLambda(retrieve),cases=RunnableLambda(lambda c:retrieve_cases(c,case_top_k)))
    chain=RunnableParallel(context=RunnablePassthrough(),knowledge=retrieval) | RunnableLambda(
        lambda v:{'generated':generate(v['context'],v['knowledge']['runbooks']+v['knowledge']['cases']),
                  'knowledge':v['knowledge']['runbooks'],'retrieved_cases':v['knowledge']['cases']})
    start=time.perf_counter();result=chain.invoke(observed,config={'callbacks':[]})
    result.update(mode=mode,retrieval='runbooks+reference_cases',analysis_latency_seconds=time.perf_counter()-start,
                  context_id=context['incident_id'],is_replay=True)
    out=Path(output_root)/context['incident_id']/(mode+MODE_SUFFIX);out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'context.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2)+'\n')
    return result
