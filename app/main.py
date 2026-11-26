"""Alert ingestion and bounded telemetry snapshots. No diagnosis is fabricated."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from app.telemetry import query_logs,query_traces
from app.metric_queries import QUERIES
from app.capture_jobs import run_serialized,persist_source

app = FastAPI(title='SHYN incident collector', version='0.3.1')
DATA = Path(os.getenv('DATA_DIR', '/data'))
PRE = int(os.getenv('CONTEXT_PRE_SECONDS', '120'))
POST = int(os.getenv('CONTEXT_POST_SECONDS', '30'))
URLS = {
    'prometheus': os.getenv('PROMETHEUS_URL', 'http://prometheus-server.monitoring.svc.cluster.local'),
    'loki': os.getenv('LOKI_URL', 'http://loki.monitoring.svc.cluster.local:3100'),
    'jaeger': os.getenv('JAEGER_URL', 'http://jaeger.monitoring.svc.cluster.local:16686'),
}


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def database():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / 'incidents.sqlite', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, dedup TEXT UNIQUE, received_at TEXT, status TEXT, alert TEXT, error TEXT)')
    conn.commit()
    return conn


def get_json(base, path, params=None):
    url = base + path + ('?' + urllib.parse.urlencode(params) if params else '')
    with urllib.request.urlopen(url, timeout=30) as response:
        remaining = response.read().decode().strip()
    decoder, documents = json.JSONDecoder(), []
    while remaining:
        document, end = decoder.raw_decode(remaining)
        documents.append(document)
        remaining = remaining[end:].lstrip()
    return documents[0] if len(documents) == 1 else documents


def capture_source(source, start, end):
    if source == 'prometheus':
        return {name: {'query': query, 'response': get_json(URLS[source], '/api/v1/query_range',
                {'query': query, 'start': start, 'end': end, 'step': 15})} for name, query in QUERIES.items()}
    if source == 'loki':
        return query_logs(lambda url,params:get_json('',url,params),URLS[source],int(start*10**9),int(end*10**9))
    return query_traces(lambda url,params:get_json('',url,params),URLS[source],start,end)


def collect(incident_id, trigger_time):
    return run_serialized(_collect,incident_id,trigger_time)


def _collect(incident_id, trigger_time):
    directory = DATA / incident_id
    directory.mkdir(parents=True, exist_ok=True)
    conn = database()
    conn.execute('UPDATE incidents SET status=? WHERE id=?', ('collecting', incident_id))
    conn.commit()
    conn.close()
    # Waiting is part of TTD and is recorded. No telemetry beyond this end is used.
    end = trigger_time + POST
    time.sleep(max(0, end-time.time()))
    started, errors, sources = stamp(), {}, {}
    trace_services = []
    trace_profiles = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(persist_source,
            lambda source:capture_source(source,trigger_time-PRE,end),source,directory):source for source in URLS}
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                saved = future.result()
                if source == 'jaeger':
                    trace_services = saved['queried_services']
                    trace_profiles = saved['query_profiles']
                sources[source] = {'file':saved['file'],'status':saved['status']}
                if saved['incomplete']:
                    errors[source]='Bounded export incomplete; inspect export_metadata'
                    sources[source]['status']='partial'
            except Exception as exc:
                errors[source] = f'{type(exc).__name__}: {exc}'
                sources[source] = {'status': 'error'}
    metadata = {'incident_id': incident_id, 'window_start': trigger_time-PRE, 'window_end': end,
                'capture_started_at': started, 'context_ready_at': stamp(), 'sources': sources,
                'errors': errors, 'limits': {'log_lines_per_page': 5000, 'log_max_pages': 32, 'traces_per_query': 500, 'trace_query_services':trace_services, 'trace_query_profiles':trace_profiles, 'metrics_step_seconds': 15},
                'diagnosis_status': 'not_implemented'}
    (directory / 'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    conn = database()
    conn.execute('UPDATE incidents SET status=?, error=? WHERE id=?',
                 ('partial' if errors else 'captured', json.dumps(errors) if errors else None, incident_id))
    conn.commit()
    conn.close()


def enqueue(alert, background, dedup):
    received = stamp()
    incident_id = 'INC-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    conn = database()
    try:
        conn.execute('INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?)',
                     (incident_id, dedup, received, 'queued', json.dumps(alert), None))
        conn.commit()
    except sqlite3.IntegrityError:
        existing = conn.execute('SELECT id FROM incidents WHERE dedup=?', (dedup,)).fetchone()
        return existing['id'], False
    finally:
        conn.close()
    background.add_task(collect, incident_id, time.time())
    return incident_id, True


@app.get('/health')
def health():
    conn = database()
    conn.close()
    return {'status': 'ok', 'diagnosis': 'not_implemented'}


@app.post('/alerts', status_code=202)
def alerts(payload: dict, background: BackgroundTasks):
    rows = payload.get('alerts')
    if not isinstance(rows, list):
        raise HTTPException(400, 'alerts must be a list')
    accepted = []
    for alert in rows:
        if not isinstance(alert, dict) or alert.get('status') != 'firing':
            continue
        labels = alert.get('labels', {})
        if labels.get('namespace') != 'sock-shop':
            continue
        identity = json.dumps({'labels': labels, 'startsAt': alert.get('startsAt')}, sort_keys=True)
        dedup = hashlib.sha256(identity.encode()).hexdigest()
        incident_id, created = enqueue(alert, background, dedup)
        accepted.append({'incident_id': incident_id, 'created': created})
    return {'incidents': accepted}


@app.post('/incidents/manual', status_code=202)
def manual(background: BackgroundTasks):
    # Development capture only. Never counted as an automatically detected incident.
    incident_id, _ = enqueue({'trigger': 'manual_development_capture'}, background, uuid.uuid4().hex)
    return {'incident_id': incident_id, 'trigger': 'manual'}


@app.get('/incidents')
def incidents():
    conn = database()
    rows = conn.execute('SELECT id, received_at, status, error FROM incidents ORDER BY received_at DESC LIMIT 100').fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get('/incidents/{incident_id}')
def incident(incident_id: str):
    conn = database()
    row = conn.execute('SELECT id, received_at, status, error FROM incidents WHERE id=?', (incident_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, 'Unknown incident')
    manifest = DATA / row['id'] / 'manifest.json'
    return {**dict(row), 'manifest': json.loads(manifest.read_text()) if manifest.exists() else None}


@app.get('/incidents/{incident_id}/files/{source}')
def incident_file(incident_id: str, source: Literal['metrics','logs','traces','manifest']):
    conn=database()
    row=conn.execute('SELECT id FROM incidents WHERE id=?',(incident_id,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404,'Unknown incident')
    filename={'metrics':'prometheus.json','logs':'loki.json','traces':'jaeger.json','manifest':'manifest.json'}[source]
    path=DATA/row['id']/filename
    if not path.is_file(): raise HTTPException(404,'This source was not captured')
    return FileResponse(path,media_type='application/json',filename=source+'.json')


@app.on_event('startup')
def mark_interrupted_jobs():
    conn=database()
    conn.execute('UPDATE incidents SET status=?,error=? WHERE status IN (?,?)',
                 ('interrupted','Collector restarted before capture completed; original window needs review','queued','collecting'))
    conn.commit()
    conn.close()
