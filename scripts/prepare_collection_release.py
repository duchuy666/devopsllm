#!/usr/bin/env python3
"""Pin collection and evaluation code before prospective observations exist."""
import argparse
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.audit_plan import audit
from app.gemini_provider import settings,prompt_fingerprint
from app.collection_release import verify_release


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists() or args.output.parent.exists():parser.error('Use a new release directory; never replace a release')
    plan=json.loads((ROOT/'experiments/scenario-plan.json').read_text())
    if audit(plan)['errors']:raise ValueError('Invalid plan')
    protocol=yaml.safe_load((ROOT/'config/collection-protocol.yaml').read_text())
    if protocol['status']!='collection_precommitted':raise ValueError('Collection protocol not committed')
    names=['experiments/scenario-plan.json','experiments/generate_plan.py','experiments/audit_plan.py',
           'config/collection-protocol.yaml','config/experiment-protocol.yaml',
           'scripts/prepare_collection_release.py','scripts/run_dataset_collection.py','scripts/run_scenario.py',
           'scripts/check_stability.py','scripts/ensure_frontend_tunnel.py','scripts/capture_window.py',
           'scripts/capture_qdisc.py','experiments/scenario.py','experiments/review_case.py','experiments/evaluate.py',
           'app/collection_release.py','app/observation_window.py','app/context_builder.py','app/gemini_provider.py',
           'app/report_schema.py','app/baseline.py','app/rag.py','app/diagnosis.py','app/telemetry.py','app/metric_queries.py',
           'app/stability_timing.py','app/experiment_runtime.py','traffic/run.py','traffic/steady.py',
           'infra/sock-shop/local-emulated.yaml','infra/tracing/frontend-tracing.js','infra/tracing/frontend-policy.json',
           'infra/sock-shop/mysql-memory.cnf','infra/sock-shop/mysql-memory-policy.json',
           'infra/sock-shop/db-cache-policy.json','infra/sock-shop/db-cache-init.sh',
           'infra/native/active-images.json','.runtime/knowledge-index.json','requirements-assistant.lock',
           'app/main.py','app/capture_jobs.py','app/Dockerfile','app/requirements.lock',
           'infra/observability/collector.yaml','scripts/deploy_collector.sh']
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'knowledge/runbooks').glob('*.md'))]
    config=settings()
    release={'status':'collection_precommitted','version':'prospective-collection-v1-plan-'+plan['plan_version'],
             'plan_version':plan['plan_version'],'distinct_nominal_settings':audit(plan)['distinct_nominal_settings'],
             'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'case_count':200,
             'allowed_splits':['reference','validation','test'],'observation':protocol['observation'],
             'provider':{key:config[key] for key in ('model','embedding_model','dimension','thinking_level')},
             'prompt_fingerprint':prompt_fingerprint(),
             'admission':'independent_review_required_not_automatic','gemini_called':False,
             'files_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for name in names:
        destination=args.output.parent/'sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,destination)
    with args.output.open('x') as handle:json.dump(release,handle,ensure_ascii=False,indent=2);handle.write('\n')
    verify_release(args.output,ROOT,'test')
    print(json.dumps({'release':str(args.output),'pinned_files':len(names),'case_count':200,'cloud_called':False},indent=2))


if __name__=='__main__':main()
