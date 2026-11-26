#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
entry=json.loads((root/'results/environment/qdrant-image-audit.json').read_text())['images'][0]
if entry['status']!='ok' or not entry['arm64_native']: raise SystemExit('Qdrant image must pass ARM64 audit')
image='qdrant/qdrant@'+entry['digest']
result=subprocess.run(['docker','container','inspect','shyn-qdrant'],text=True,capture_output=True)
if result.returncode==0:
    existing=json.loads(result.stdout)[0]
    if existing['Config']['Image']!=image: raise SystemExit('Existing Qdrant container has another image; review first')
    if not existing['State']['Running']: subprocess.run(['docker','start','shyn-qdrant'],check=True)
    else: print('shyn-qdrant is already running with the verified image')
else:
    subprocess.run(['docker','run','-d','--name','shyn-qdrant','--memory=256m','--cpus=0.5',
                    '-p','127.0.0.1:6333:6333','-v','shyn-qdrant-data:/qdrant/storage',image],check=True)
