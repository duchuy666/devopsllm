#!/usr/bin/env python3
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.context_builder import build_context
from app.diagnosis import diagnose

parser=argparse.ArgumentParser()
parser.add_argument('telemetry_dir')
parser.add_argument('--mode',choices=['B1','B2','B3'],default='B3')
parser.add_argument('--approved-context',help='Require context/query to match the locally reviewed transmission packet')
args=parser.parse_args()
try:
    context,evidence=build_context(args.telemetry_dir)
    if args.approved_context:
        approved=Path(args.approved_context)
        if json.loads(approved.read_text())!=context:
            raise RuntimeError('Context changed since approval; no API call was made.')
        from app.rag import retrieval_query
        query_file=approved.parent/'embedding-query.txt'
        if not query_file.exists() or query_file.read_text().strip()!=retrieval_query(context).strip():
            raise RuntimeError('Embedding query changed since approval; no API call was made.')
    result=diagnose(context,args.mode)
    print(json.dumps(result,ensure_ascii=False,indent=2))
except RuntimeError as exc:
    print(str(exc)); raise SystemExit(2)
except Exception as exc:
    print(f'Diagnosis failed: {type(exc).__name__}, status={getattr(exc,"code",None)}')
    raise SystemExit(1)
