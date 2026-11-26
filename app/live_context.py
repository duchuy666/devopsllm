"""Prepare live incident context locally; this module never calls Gemini."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from app.context_builder import build_context

ROOT=Path(__file__).resolve().parents[1]


def prepare_live(incident_id):
    if not re.fullmatch(r'INC-\d{8}T\d{6}-[a-f0-9]{8}',incident_id):
        raise ValueError('Invalid collector incident ID')
    base='http://127.0.0.1:8000/incidents/'+incident_id
    with urllib.request.urlopen(base,timeout=15) as response:
        status=json.load(response)
    if status['status'] not in ('captured','partial'):
        raise RuntimeError('Incident capture is not complete; review status before preparing context')
    directory=ROOT/'data/live'/incident_id/'telemetry'
    directory.mkdir(parents=True,exist_ok=True)
    missing=[]
    for source in ('metrics','logs','traces'):
        try:
            with urllib.request.urlopen(base+'/files/'+source,timeout=30) as response:
                payload=json.load(response)
            (directory/(source+'.json')).write_text(json.dumps(payload)+'\n')
        except urllib.error.HTTPError as exc:
            if exc.code!=404:raise
            missing.append(source)
    context,index=build_context(directory)
    out=ROOT/'results/contexts'/context['incident_id']
    out.mkdir(parents=True,exist_ok=True)
    (out/'context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n')
    (out/'evidence-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    (out/'local-source.json').write_text(json.dumps({'collector_incident_id':incident_id,'missing_files':missing},indent=2)+'\n')
    return context,index,directory
