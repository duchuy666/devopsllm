"""Validate precommitted collection inputs, never grant human admission."""
import hashlib
import json
from pathlib import Path


def verify_release(path, root, split):
    release = json.loads(Path(path).read_text())
    if release.get('status') != 'collection_precommitted' or split not in release.get('allowed_splits', []):
        raise ValueError('Collection release does not allow this split')
    if release.get('observation') != {'anchor': 'injection_confirmed_at', 'pre_seconds': 30, 'post_seconds': 30,
                                      'completed_spans_only': True}:
        raise ValueError('Unsupported precommitted observation policy')
    required = {'experiments/scenario-plan.json', 'scripts/run_scenario.py', 'app/collection_release.py',
                'app/observation_window.py', 'scripts/run_dataset_collection.py',
                'config/collection-protocol.yaml', 'app/context_builder.py', 'app/gemini_provider.py',
                'app/baseline.py', 'app/telemetry.py', 'infra/sock-shop/local-emulated.yaml'}
    pins = release.get('files_sha256', {})
    if not required <= set(pins):
        raise ValueError('Collection release lacks required source pins')
    for name, digest in pins.items():
        source = (root / name).resolve()
        if not source.is_relative_to(root.resolve()) or any(p.startswith('.env') for p in Path(name).parts):
            raise ValueError('Unsafe collection source path')
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError('Collection source changed: ' + name)
    from app.gemini_provider import settings,prompt_fingerprint
    config=settings()
    if release.get('provider')!={key:config[key] for key in ('model','embedding_model','dimension','thinking_level')}:
        raise ValueError('Provider configuration changed after precommitment')
    if release.get('prompt_fingerprint')!=prompt_fingerprint():
        raise ValueError('Prompt/schema changed after precommitment')
    return release
