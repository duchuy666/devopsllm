#!/usr/bin/env python3
"""Finite, seeded local-only browse/checkout traffic with per-request evidence."""
import argparse
import concurrent.futures
import datetime
import http.cookiejar
import json
from pathlib import Path
import random
import time
import urllib.error
import urllib.parse
import urllib.request


def worker(index, args, run_id):
    rng = random.Random(args.seed + index)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    records = []
    completed = 0

    def call(path, method='GET', payload=None):
        started = time.perf_counter()
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(args.url.rstrip('/') + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        status, body, error = 0, b'', None
        try:
            with opener.open(request, timeout=15) as response:
                status, body = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, body, error = exc.code, exc.read(), f'HTTP {exc.code}'
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        ok = 200 <= status < 300
        records.append({'worker': index, 'timestamp': stamp, 'method': method, 'path': path,
                        'status': status, 'latency_ms': round((time.perf_counter()-started)*1000, 3),
                        'ok': ok, 'error': error})
        if not ok:
            raise RuntimeError(f'{method} {path}: {error or status}')
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body.decode(errors='replace')

    try:
        call('/')
        if args.profile == 'checkout':
            # Synthetic account/card in the local demo only, never a real payment.
            user = call('/register', 'POST', {'username': f'thesis_{run_id}_{index}',
                        'password': 'local-demo-only', 'email': f'worker{index}@example.invalid'})
            if not isinstance(user, dict) or not user.get('id'):
                raise ValueError('Registration returned no customer ID')
            call('/addresses', 'POST', {'number': '1', 'street': 'Test Street', 'city': 'Test City',
                                       'postcode': '00000', 'country': 'Test'})
            call('/cards', 'POST', {'longNum': '0000000000000000', 'expires': '12/30', 'ccv': '000'})
        for journey in range(args.journeys):
            products = call('/catalogue')
            if not isinstance(products, list) or not products:
                raise ValueError('Catalogue is empty or has invalid schema')
            # Limit the stub payment total and avoid unlimited cart growth.
            candidates = [p for p in products if p.get('id') and 0 < float(p.get('price', 0)) < 40]
            if not candidates:
                raise ValueError('No affordable catalogue item for synthetic checkout')
            product = rng.choice(candidates)
            detail = call('/catalogue/' + urllib.parse.quote(product['id'], safe=''))
            if not isinstance(detail, dict) or detail.get('id') != product['id']:
                raise ValueError('Product detail mismatch')
            call('/tags')
            if args.profile == 'checkout':
                call('/cart', 'POST', {'id': product['id']})
                cart = call('/cart')
                if not isinstance(cart, list) or not cart:
                    raise ValueError('Cart is empty after add')
                order = call('/orders', 'POST', {})
                if not isinstance(order, dict) or not order.get('id'):
                    raise ValueError('Order creation returned no order ID')
                call('/orders')
            completed += 1
            if journey + 1 < args.journeys:
                time.sleep(args.pause)
        return records, completed, None
    except Exception as exc:
        return records, completed, str(exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--profile', choices=['browse', 'checkout'], default='browse')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--journeys', type=int, default=3)
    parser.add_argument('--pause', type=float, default=1.0)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', default='results/traffic-latest.json')
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password:
        parser.error('Only local HTTP testbed URLs are allowed')
    if not 1 <= args.workers <= 8 or not 1 <= args.journeys <= 10000 or args.pause < 0:
        parser.error('Invalid traffic bounds')
    started = datetime.datetime.now(datetime.timezone.utc)
    run_id = started.strftime('%Y%m%d%H%M%S%f')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda i: worker(i, args, run_id), range(args.workers)))
    records = [record for rows, _, _ in results for record in rows]
    latencies = sorted(r['latency_ms'] for r in records)
    report = {'started_at': started.isoformat(), 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'config': vars(args), 'completed_journeys': sum(n for _, n, _ in results),
              'expected_journeys': args.workers * args.journeys,
              'request_count': len(records), 'failed_requests': sum(not r['ok'] for r in records),
              'p95_request_latency_ms': latencies[min(len(latencies)-1, int(len(latencies)*0.95))] if latencies else None,
              'errors': [e for _, _, e in results if e], 'requests': records}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('requests', 'config')}, indent=2))
    print(f'Evidence: {out}')
    return 0 if not report['errors'] and report['completed_journeys'] == report['expected_journeys'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
