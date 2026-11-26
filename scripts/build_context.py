#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.context_builder import build_context

parser=argparse.ArgumentParser()
parser.add_argument('telemetry_dir')
parser.add_argument('--output',default='results/contexts')
args=parser.parse_args()
context,evidence=build_context(args.telemetry_dir)
out=Path(args.output)/context['incident_id']
out.mkdir(parents=True,exist_ok=True)
(out/'context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n')
(out/'evidence-index.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
(out/'local-source.json').write_text(json.dumps({'telemetry_dir':str(Path(args.telemetry_dir).resolve())},indent=2)+'\n')
print(json.dumps({'context_id':context['incident_id'],'counts':{k:len(context[k]) for k in ('metrics','logs','traces')},
                  'missing_sources':context['missing_sources'],'path':str(out)},indent=2))
