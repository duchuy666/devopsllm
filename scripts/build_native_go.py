#!/usr/bin/env python3
"""Experimental cross-build using source/dependency commits already locked upstream.

Restores only missing packages, never resolves dependency branches or latest versions.
Does not build Docker images, load images, or change Kubernetes workloads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request
import yaml

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.runtime/native-dependencies'


def archive(repository,revision):
    if not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('A full dependency commit is required')
    repository=repository.removesuffix('.git')
    key=hashlib.sha256((repository+'@'+revision).encode()).hexdigest()
    target=CACHE/key
    if (target/'complete.json').exists():return Path(json.loads((target/'complete.json').read_text())['source'])
    if repository.startswith('https://code.googlesource.com/'):
        repo={'gocloud':'googleapis/google-cloud-go','google-api-go-client':'googleapis/google-api-go-client'}[repository.rsplit('/',1)[1]]
    elif repository.startswith('https://go.googlesource.com/'):
        repo='golang/'+repository.rsplit('/',1)[1]
    elif repository.startswith('https://github.com/'):
        repo=repository.removeprefix('https://github.com/')
    elif repository.startswith('https://gopkg.in/'):
        aliases={'https://gopkg.in/mgo.v2':'https://github.com/go-mgo/mgo',
                 'https://gopkg.in/tomb.v2':'https://github.com/go-tomb/tomb',
                 'https://gopkg.in/yaml.v2':'https://github.com/go-yaml/yaml'}
        if repository in aliases:return archive(aliases[repository],revision)
        html=urllib.request.urlopen(repository+'?go-get=1',timeout=30).read().decode()
        found=re.search(r'content=["\']([^"\']+ git [^"\']+)["\']',html)
        if not found:raise RuntimeError('Cannot resolve pinned gopkg repository')
        canonical=found.group(1).split()[-1]
        if canonical==repository:raise RuntimeError('gopkg metadata is self-referential; explicit commit mirror required')
        # Use the same commit; a mirror is not a dependency upgrade.
        return archive(canonical,revision)
    else:raise ValueError('Unsupported dependency source: '+repository)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository path')
    target.mkdir(parents=True,exist_ok=True)
    url=f'https://codeload.github.com/{repo}/tar.gz/{revision}'
    package=target/'source.tar.gz'
    if not package.exists():
        temp=target/'download.tmp';urllib.request.urlretrieve(url,temp);temp.replace(package)
    with tarfile.open(package) as tar:
        prefix=tar.getnames()[0].split('/')[0]
        # Procfs test fixtures contain absolute /proc links. They are not source
        # inputs for this cross-build; do not extract any links/devices.
        tar.extractall(target,members=(m for m in tar.getmembers() if m.isfile() or m.isdir()),filter='data')
    source=target/prefix
    (target/'complete.json').write_text(json.dumps({'source':str(source),'url':url,
        'revision':revision,'archive_sha256':hashlib.sha256(package.read_bytes()).hexdigest()})+'\n')
    return source


def dependencies(source,service):
    if service!='user':return json.loads((source/'vendor/manifest').read_text())['dependencies']
    rows=[]
    for entry in yaml.safe_load((source/'glide.lock').read_text())['imports']:
        name=entry['name'];parts=name.split('/')
        if name.startswith('github.com/'):
            repository='https://'+'/'.join(parts[:3]);path='/'.join(parts[3:])
        elif name.startswith('golang.org/x/'):
            repository='https://go.googlesource.com/'+parts[2];path='/'.join(parts[3:])
        elif name.startswith('gopkg.in/'):
            repository='https://'+name;path=''
        elif name=='google.golang.org/grpc':
            repository='https://github.com/grpc/grpc-go';path=''
        else:raise ValueError('Unsupported locked dependency: '+name)
        rows.append({'importpath':name,'repository':repository,'revision':entry['version'],'path':path})
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('service',choices=['payment','catalogue','user'])
    args=parser.parse_args();service=args.service
    lock=json.loads((ROOT/'infra/native/sources.lock.json').read_text())
    spec=next(r for r in lock['services'] if r['service']==service)
    source=ROOT/'.runtime/native-sources'/service
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=spec['commit']:raise ValueError('Source commit changed')
    if hashlib.sha256((source/spec['dependency_lock_path']).read_bytes()).hexdigest()!=spec['dependency_lock_sha256']:
        raise ValueError('Upstream dependency lock changed')
    work=ROOT/'.runtime/native-gopath';project=work/'src/github.com/microservices-demo'/service
    if not project.exists():
        project.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,project,ignore=shutil.ignore_patterns('.git'))
    patches=[]
    if service=='user':
        path=project/'users/links.go';text=path.read_text()
        old='\tstring `json:"href"`';new='\tURL string `json:"href"`'
        if old in text:path.write_text(text.replace(old,new,1))
        elif new not in text:raise RuntimeError('Unexpected Href implementation; review compatibility patch')
        patch=ROOT/'infra/native/user-href-compat.patch'
        patches.append({'path':str(patch.relative_to(ROOT)),'sha256':hashlib.sha256(patch.read_bytes()).hexdigest()})
        shutil.copyfile(ROOT/'infra/native/user_href_contract_test.go',project/'users/native_contract_test.go')
    deps=dependencies(source,service)
    compiler=ROOT/'.runtime/toolchains/go1.23.12/go/bin/go'
    env=dict(os.environ,GO111MODULE='off',GOOS='linux',GOARCH='arm64',CGO_ENABLED='0',GOMAXPROCS='2',
             GOPATH=str(work),GOCACHE=str(ROOT/'.runtime/native-gocache'),GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local')
    output=ROOT/'.runtime/native-builds'/service;output.mkdir(parents=True,exist_ok=True)
    package='github.com/microservices-demo/'+service+('' if service=='user' else '/cmd/'+('paymentsvc' if service=='payment' else 'cataloguesvc'))
    restored=[]
    for iteration in range(30):
        result=subprocess.run([str(compiler),'build','-p','2','-trimpath','-o',str(output/'app'),package],
                              cwd=project,env=env,text=True,capture_output=True,timeout=300)
        (output/'build.log').write_text(result.stdout+result.stderr)
        if result.returncode==0:
            metadata={'status':'binary_built_not_deployed','service':service,'commit':spec['commit'],
                'compiler':'go1.23.12','target':'linux/arm64','cgo_enabled':False,
                'compatibility_patches':patches,
                'vendor_content_sha256':hashlib.sha256(json.dumps([(str(p.relative_to(project/'vendor')),
                    hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((project/'vendor').rglob('*')) if p.is_file()]).encode()).hexdigest(),
                'binary_sha256':hashlib.sha256((output/'app').read_bytes()).hexdigest(),'restored_packages':restored}
            (output/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
            print(json.dumps({k:v for k,v in metadata.items() if k!='restored_packages'},indent=2),flush=True)
            return 0
        missing=sorted(set(re.findall(r'cannot find package "([^"]+)"',result.stderr)))
        if not missing:
            print(result.stderr[-5000:],flush=True);return 1
        print(service,'dependency pass',iteration+1,'missing',len(missing),flush=True)
        for name in missing:
            options=[d for d in deps if name==d['importpath'] or name.startswith(d['importpath']+'/')]
            if not options:raise RuntimeError('Missing package absent from upstream lock: '+name)
            entry=max(options,key=lambda d:len(d['importpath']))
            tree=archive(entry['repository'],entry['revision'])
            suffix=name[len(entry['importpath']):].strip('/')
            origin=tree/entry.get('path','').strip('/')/suffix
            if not origin.is_dir():raise RuntimeError('Locked package directory absent: '+name)
            destination=project/'vendor'/name;destination.mkdir(parents=True,exist_ok=True)
            count=0
            for file in origin.iterdir():
                if file.is_file():shutil.copyfile(file,destination/file.name);count+=1
            if not count:raise RuntimeError('No package files restored: '+name)
            restored.append({'importpath':name,'repository':entry['repository'],'revision':entry['revision']})
    raise RuntimeError('Dependency restoration did not converge; inspect saved build.log')


if __name__=='__main__':raise SystemExit(main())
