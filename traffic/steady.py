#!/usr/bin/env python3
"""Bounded pilot traffic: independent synthetic journeys continue after errors."""
import argparse
import datetime
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from run import worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=150)
    parser.add_argument('--profile', choices=['browse', 'checkout'], default='checkout')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--pause',type=float,default=1.0)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('Pilot duration must be 1..600 seconds')
    if not 0<=args.pause<=5:parser.error('Pause must be 0..5 seconds')
    started = datetime.datetime.now(datetime.timezone.utc)
    run_id = started.strftime('%Y%m%d%H%M%S%f')
    end = time.monotonic() + args.seconds
    requests, errors, completed, attempts = [], [], 0, 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() < end:
        rows, count, error = worker(attempts, SimpleNamespace(url='http://127.0.0.1:8080', profile=args.profile,
                                                          seed=args.seed, journeys=1, pause=0), run_id)
        requests.extend(rows)
        attempts += 1
        completed += count
        if error:
            errors.append({'journey': attempts, 'error': error})
        report = {'started_at': started.isoformat(), 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'profile': args.profile, 'seed': args.seed, 'duration_seconds': args.seconds,'pause_seconds':args.pause,
                  'attempted_journeys': attempts, 'completed_journeys': completed,
                  'failed_requests': sum(not r['ok'] for r in requests), 'errors': errors, 'requests': requests}
        temp = out.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2)+'\n')
        os.replace(temp, out)
        time.sleep(args.pause)
    print(json.dumps({'attempted': attempts, 'completed': completed, 'failed_requests': report['failed_requests']}), flush=True)


if __name__ == '__main__':
    main()
