#!/usr/bin/env python3
"""Read Docker Hub manifests/configs without pulling layers or requiring Docker.

No credentials are read. Public, short-lived registry tokens stay in memory.
Every manifest is resolved to a digest for the experiment provenance.
"""
import concurrent.futures
import argparse
import datetime
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ', '.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])


def fetch(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
        return json.load(r), dict(r.headers)


def inspect(ref):
    result = {'image': ref}
    try:
        name, sep, tag = ref.rpartition(':')
        if not sep:
            name, tag = ref, 'latest'
        repo = name if '/' in name else 'library/' + name
        query = urllib.parse.urlencode({'service': 'registry.docker.io', 'scope': f'repository:{repo}:pull'})
        token, _ = fetch('https://auth.docker.io/token?' + query)
        headers = {'Authorization': 'Bearer ' + token['token'], 'Accept': ACCEPT}
        manifest, response_headers = fetch(f'https://registry-1.docker.io/v2/{repo}/manifests/{tag}', headers)
        result['digest'] = next((v for k, v in response_headers.items() if k.lower() == 'docker-content-digest'), None)
        if 'manifests' in manifest:
            platforms = [m.get('platform', {}) for m in manifest['manifests']]
        elif 'config' in manifest:
            config, _ = fetch(f"https://registry-1.docker.io/v2/{repo}/blobs/{manifest['config']['digest']}", headers)
            platforms = [{'os': config.get('os'), 'architecture': config.get('architecture')}]
        else:
            raise ValueError('Unsupported manifest format; no platform proof')
        result['platforms'] = platforms
        result['arm64_native'] = any(p.get('os') == 'linux' and p.get('architecture') == 'arm64' for p in platforms)
        result['status'] = 'ok'
    except Exception as exc:
        result.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', action='append', help='Audit explicit Docker Hub image instead of upstream manifest')
    parser.add_argument('--output', default='results/environment/image-audit.json')
    args = parser.parse_args()
    manifest = ROOT / 'infra/sock-shop/upstream.yaml'
    images = sorted(set(args.image or re.findall(r'^\s*image:\s*([^\s#]+)', manifest.read_text(), re.M)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        entries = list(pool.map(inspect, images))
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'images': entries}
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    for entry in entries:
        state = 'ERROR' if entry['status'] != 'ok' else ('ARM64' if entry['arm64_native'] else 'NO_ARM64')
        print(f"{state:9} {entry['image']}")
    print(f'Report: {target}')
    return 0 if entries and all(e['status'] == 'ok' and e['arm64_native'] for e in entries) else 2


if __name__ == '__main__':
    raise SystemExit(main())
