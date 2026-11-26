"""Date-bound paid-tier estimates, never an assertion of actual billing."""
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path


def estimate_generation(model,usage,generated_at):
    if not usage: return {'cost_status':'usage_missing','estimated_paid_api_cost_usd':None}
    pricing=json.loads((Path(__file__).resolve().parents[1]/'config/gemini-pricing.json').read_text())
    date=dt.datetime.fromisoformat(generated_at).date().isoformat()
    if date<pricing['verified_on'] or date>pricing['valid_through'] or model not in pricing['models']:
        return {'cost_status':'pricing_not_valid_for_run_date','estimated_paid_api_cost_usd':None}
    rates=pricing['models'][model]
    if 'output_including_thinking_usd_per_million' not in rates:
        return {'cost_status':'not_a_generation_model','estimated_paid_api_cost_usd':None}
    prompt=int(usage.get('prompt_token_count',0))
    cached=int(usage.get('cached_content_token_count',0))
    candidates=int(usage.get('candidates_token_count',0))
    thoughts=usage.get('thoughts_token_count')
    if thoughts is None:
        total=usage.get('total_token_count')
        if total is None: return {'cost_status':'output_usage_incomplete','estimated_paid_api_cost_usd':None}
        thoughts=max(0,int(total)-prompt-candidates)
    output=candidates+int(thoughts)
    cost=(Decimal(max(0,prompt-cached))*Decimal(str(rates['input_usd_per_million']))
          +Decimal(cached)*Decimal(str(rates['cached_input_usd_per_million']))
          +Decimal(output)*Decimal(str(rates['output_including_thinking_usd_per_million'])))/Decimal(1000000)
    return {'cost_status':'estimated_paid_standard_not_invoice','estimated_paid_api_cost_usd':float(cost),
            'pricing_source':pricing['source'],'pricing_verified_on':pricing['verified_on'],
            'billing_verified':False,'embedding_and_index_cost_included':False}
