#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
lock=json.loads((root/'infra/charts.lock.json').read_text())

def run(*args):subprocess.run(args,cwd=root,check=True)

run('helm','repo','add','prometheus-community','https://prometheus-community.github.io/helm-charts')
run('helm','repo','add','grafana','https://grafana.github.io/helm-charts')
for release in ('prometheus','loki','alloy','grafana'):
    spec=lock[release]
    run('helm','upgrade','--install',release,spec['chart'],'--version',spec['version'],
        '--kube-context','shyn-thesis','--namespace','monitoring','--create-namespace',
        '-f',str(root/f'infra/observability/{release}-values.yaml'),'--wait','--timeout','5m')
run('kubectl','--context=shyn-thesis','apply','-f',str(root/'infra/observability/jaeger.yaml'))
run('kubectl','--context=shyn-thesis','-n','monitoring','rollout','status','deployment/jaeger','--timeout=120s')
