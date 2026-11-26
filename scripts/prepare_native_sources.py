#!/usr/bin/env python3
"""Fetch pinned public sources/toolchain into ignored local directories."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    lock=json.loads((ROOT/'infra/native/sources.lock.json').read_text())
    for row in lock['services']:
        target=ROOT/'.runtime/native-sources'/row['service']
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['git','clone','--depth','1','--branch',row['tag'],row['repository'],str(target)],check=True)
        actual=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip()
        if actual!=row['commit']:raise RuntimeError('Source tag/commit mismatch')
        if hashlib.sha256((target/row['dependency_lock_path']).read_bytes()).hexdigest()!=row['dependency_lock_sha256']:
            raise RuntimeError('Dependency lock mismatch')
    toolchain=json.loads((ROOT/'infra/native/toolchain.lock.json').read_text())
    package=ROOT/'.runtime/toolchains'/toolchain['file']['filename']
    if not package.exists():
        package.parent.mkdir(parents=True,exist_ok=True)
        temp=package.with_suffix('.download')
        urllib.request.urlretrieve('https://go.dev/dl/'+package.name,temp);temp.replace(package)
    if hashlib.sha256(package.read_bytes()).hexdigest()!=toolchain['file']['sha256']:
        raise RuntimeError('Toolchain SHA256 mismatch')
    target=ROOT/'.runtime/toolchains'/toolchain['version']
    if not (target/'go/bin/go').exists():
        target.mkdir(exist_ok=True)
        with tarfile.open(package) as tar:tar.extractall(target,filter='data')
    print('Verified three source commits, dependency locks and the Darwin ARM64 compiler archive.')


if __name__=='__main__':main()
