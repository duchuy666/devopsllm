#!/usr/bin/env python3
"""Package a verified static binary into a local image; never push or deploy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('service',choices=['payment','catalogue','user'])
    service=parser.parse_args().service
    build=ROOT/'.runtime/native-builds'/service
    meta=json.loads((build/'build.json').read_text())
    if meta['target']!='linux/arm64' or hashlib.sha256((build/'app').read_bytes()).hexdigest()!=meta['binary_sha256']:
        raise ValueError('Binary identity mismatch')
    context=build/'image-context';context.mkdir(exist_ok=True)
    source=ROOT/'.runtime/native-sources'/service
    shutil.copyfile(build/'app',context/'app');(context/'app').chmod(0o755)
    shutil.copyfile(source/'LICENSE',context/'LICENSE')
    shutil.copyfile(ROOT/'infra/native/Dockerfile',context/'Dockerfile')
    images=context/'images'
    if not images.exists():
        if (source/'images').exists():shutil.copytree(source/'images',images)
        else:images.mkdir()
    licenses=context/'licenses';licenses.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'.runtime/toolchains/go1.23.12/go/LICENSE',licenses/'Go-LICENSE')
    for entry in (ROOT/'.runtime/native-dependencies').glob('*/complete.json'):
        dependency=Path(json.loads(entry.read_text())['source'])
        for file in dependency.iterdir():
            if file.is_file() and file.name.upper().startswith(('LICENSE','NOTICE','COPYRIGHT')):
                shutil.copyfile(file,licenses/(entry.parent.name+'-'+file.name))
    tag=f'shyn-{service}-native:{meta["commit"][:12]}-go1.23.12-{meta["binary_sha256"][:12]}'
    subprocess.run(['docker','build','--network=none','--platform=linux/arm64',
        '--build-arg','SERVICE='+service,'--build-arg','SOURCE_COMMIT='+meta['commit'],
        '-t',tag,str(context)],check=True,timeout=180)
    image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True))[0]
    result={'status':'local_image_built_not_deployed','service':service,'tag':tag,'image_id':image['Id'],
            'architecture':image['Architecture'],'os':image['Os'],'source_commit':meta['commit'],
            'binary_sha256':meta['binary_sha256'],'published':False}
    result['compatibility_patches']=meta.get('compatibility_patches',[])
    (build/'image.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
