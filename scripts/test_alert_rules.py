#!/usr/bin/env python3
"""Validate repository rules using the testbed's promtool; no rule deployment."""
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE


def main():
    rules=yaml.safe_load((ROOT/'infra/observability/prometheus-values.yaml').read_text())['serverFiles']['alerting_rules.yml']
    prefix=KUBE+['-n','monitoring','exec','-i','deployment/prometheus-server','-c','prometheus-server','--']
    for filename,payload in (
        ('/tmp/shyn-network-rules.yaml',yaml.safe_dump(rules)),
        ('/tmp/shyn-network-rules.test.yaml',(ROOT/'tests/prometheus/network-rules.test.yaml').read_text())):
        subprocess.run(prefix+['sh','-c','cat > '+filename],input=payload,text=True,check=True,timeout=30)
    outputs=[]
    for args in (['check','rules','/tmp/shyn-network-rules.yaml'],['test','rules','/tmp/shyn-network-rules.test.yaml']):
        result=subprocess.run(prefix+['/bin/promtool']+args,capture_output=True,text=True,timeout=60)
        outputs.append({'command':args,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    directory=ROOT/'results/detector-validation';directory.mkdir(parents=True,exist_ok=True)
    (directory/'promtool.json').write_text(json.dumps(outputs,indent=2)+'\n')
    print(json.dumps(outputs,indent=2))
    return int(any(r['returncode'] for r in outputs))


if __name__=='__main__':raise SystemExit(main())
