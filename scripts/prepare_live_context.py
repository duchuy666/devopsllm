#!/usr/bin/env python3
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.live_context import prepare_live

parser=argparse.ArgumentParser()
parser.add_argument('incident_id')
args=parser.parse_args()
context,index,directory=prepare_live(args.incident_id)
print(json.dumps({'context_id':context['incident_id'],'counts':{k:len(context[k]) for k in ('metrics','logs','traces')},
                  'missing_sources':context['missing_sources'],'telemetry_dir':str(directory),'gemini_called':False},indent=2))
