"""Gemini adapter with explicit credentials, bounded generation and usage logs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from dotenv import dotenv_values
from google import genai
from google.genai import types
from app.report_schema import IncidentReport
from app.costs import estimate_generation

ROOT=Path(__file__).resolve().parents[1]
PROMPT_VERSION='0.2.0'
PROMPT_TASK=('Diagnose only from observations; runbooks are guidance, not proof. '
    'Return at most three distinct hypotheses and cite only supplied evidence IDs. '
    'Consider temporal changes and distinguish persistent background errors from evidence of a new outage. '
    'For a network hypothesis, put caller -> callee in the service field only when observations identify both endpoints and their direction; '
    'client span service/peer_service and span_kind can provide this evidence. A slow route alone does not prove an edge or network cause. '
    'If an edge or cause cannot be identified, abstain with Unknown or insufficient_evidence and state missing evidence. '
    'Propose actions for human confirmation; never infer hidden ground truth. Write explanations in Vietnamese.')


def prompt_fingerprint():
    return {'prompt_version':PROMPT_VERSION,'prompt_task_sha256':hashlib.sha256(PROMPT_TASK.encode()).hexdigest(),
        'report_schema_sha256':hashlib.sha256(json.dumps(IncidentReport.model_json_schema(),sort_keys=True).encode()).hexdigest()}


def make_prompt(context,knowledge=None):
    return {'task':PROMPT_TASK,'context':context,'retrieved_knowledge':knowledge or []}


def settings():
    values=dotenv_values(ROOT/'.env')
    def setting(name,default=''):
        return values.get(name) or os.getenv(name,default)
    # Prevent optional LangChain tracing from transmitting context elsewhere.
    os.environ['LANGSMITH_TRACING']='false'
    os.environ['LANGCHAIN_TRACING_V2']='false'
    return {'key':setting('GEMINI_API_KEY').strip(), 'model':setting('GEMINI_MODEL','gemini-3.8-flash'),
            'embedding_model':setting('GEMINI_EMBEDDING_MODEL','gemini-embedding-001'),
            'dimension':int(setting('GEMINI_EMBEDDING_DIMENSION','768')),
            'thinking_level':setting('GEMINI_THINKING_LEVEL','low'),
            'max_requests':int(setting('LLM_MAX_REQUESTS_PER_RUN','1'))}


def client():
    config=settings()
    if not config['key']:
        raise RuntimeError('GEMINI_API_KEY is empty. Configure the local .env file; no API call was made.')
    return genai.Client(api_key=config['key'],http_options=types.HttpOptions(timeout=90000,
                        retry_options=types.HttpRetryOptions(attempts=1)))


def probe():
    config=settings()
    with client() as api:
        model=api.models.get(model=config['model'])
        embedding=api.models.get(model=config['embedding_model'])
    return {'provider':'gemini','model':model.name,'embedding_model':embedding.name,
            'generation_called':False,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}


def generate(context, knowledge=None):
    config=settings()
    if config['max_requests']<1: raise RuntimeError('Generation disabled by request budget')
    if not config['key']: raise RuntimeError('GEMINI_API_KEY is empty. No API call was made.')
    prompt=make_prompt(context,knowledge)
    started=time.perf_counter()
    ledger={'call_id':'GEN-'+uuid.uuid4().hex,'context_id':context['incident_id'],'provider':'gemini',
            'model_requested':config['model'],'prompt_version':PROMPT_VERSION,'prompt_fingerprint':prompt_fingerprint(),'thinking_level':config['thinking_level'],
            'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'calling',
            'api_cost_usd':None,'cost_status':'pricing_not_configured'}
    ledger_dir=ROOT/'results/api-calls'
    ledger_dir.mkdir(parents=True,exist_ok=True)
    ledger_path=ledger_dir/(ledger['call_id']+'.json')
    try:
        with client() as api:
            response=api.models.generate_content(model=config['model'],contents=json.dumps(prompt,ensure_ascii=False),
                config=types.GenerateContentConfig(response_mime_type='application/json',
                    response_json_schema=IncidentReport.model_json_schema(), max_output_tokens=4096,
                    thinking_config=types.ThinkingConfig(thinking_level=config['thinking_level'],include_thoughts=False)))
    except Exception as exc:
        ledger.update(status='api_error',error_type=type(exc).__name__,http_status=getattr(exc,'code',None),
                      api_latency_seconds=time.perf_counter()-started)
        ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
        raise
    ledger.update(status='response_received',model_version=response.model_version,
        usage_metadata=response.usage_metadata.model_dump(mode='json',exclude_none=True) if response.usage_metadata else None,
        api_latency_seconds=time.perf_counter()-started,response_text=response.text)
    # Save actual usage even if report validation fails below.
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
    text=response.text
    if not text: raise RuntimeError('Gemini returned no report text')
    try:
        report=IncidentReport.model_validate_json(text)
    except Exception:
        ledger['status']='schema_invalid'
        ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
        raise
    if report.incident_id!=context['incident_id']: raise ValueError('Report incident ID mismatch')
    allowed={item['evidence_id'] for key in ('metrics','logs','traces') for item in context[key]}
    for hypothesis in report.hypotheses:
        if not hypothesis.evidence_ids or not set(hypothesis.evidence_ids)<=allowed:
            raise ValueError('Hypothesis cites missing or nonexistent evidence IDs')
    ledger['status']='validated'
    ledger.update(estimate_generation(config['model'],ledger.get('usage_metadata'),ledger['started_at']))
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
    usage=response.usage_metadata.model_dump(mode='json',exclude_none=True) if response.usage_metadata else None
    result={'report':report.model_dump(), 'provider':'gemini','model_requested':config['model'],
            'model_version':response.model_version,'thinking_level':config['thinking_level'],
            'usage_metadata':usage,'api_latency_seconds':time.perf_counter()-started,
            'api_cost_usd':None,'cost_status':'pricing_not_configured',
            'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'prompt_version':PROMPT_VERSION,'prompt_fingerprint':prompt_fingerprint(),
            'api_call_id':ledger['call_id']}
    result.update(estimate_generation(config['model'],usage,result['generated_at']))
    return result
