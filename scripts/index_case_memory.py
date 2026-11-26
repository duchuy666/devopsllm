#!/usr/bin/env python3
"""Index admitted reference cases into Qdrant case memory. Preview by default (no API call).

--execute makes one Gemini embedding call per case. Run after reference admission and before the
validation/test benchmark; never re-index once test reports have been generated.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.case_memory import case_document,eligible,index_cases


def preview(root=ROOT):
    registry=json.loads((root/'experiments/candidate-registry.json').read_text());rows=[];skipped={}
    for attempt in registry['attempts']:
        folder=root/'data/candidates'/attempt['candidate_id']
        try:
            ground=json.loads((folder/'ground-truth.json').read_text());eligible(ground)
            doc=case_document(folder);rows.append({k:doc[k] for k in ('case_id','fault_class','service_or_edge','group_id')})
        except (OSError,ValueError) as exc:skipped[str(exc)]=skipped.get(str(exc),0)+1
    return {'status':'preview_only_no_api','eligible_cases':len(rows),'embedding_calls_if_executed':len(rows),
            'cases':rows,'skipped_by_reason':skipped}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    print(json.dumps(index_cases(ROOT) if args.execute else preview(ROOT),ensure_ascii=False,indent=2))
