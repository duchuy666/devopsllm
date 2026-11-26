"""Bound collector peak memory without changing query windows or source limits."""
import json
from pathlib import Path
import threading

_CAPTURE_SLOT=threading.BoundedSemaphore(1)


def run_serialized(callback,*args):
    with _CAPTURE_SLOT:
        return callback(*args)


def persist_source(callback,source,directory):
    payload=callback(source)
    metadata=payload.get('export_metadata',{})
    result={'file':source+'.json','status':'partial' if metadata.get('incomplete') else 'captured',
            'incomplete':bool(metadata.get('incomplete')),
            'queried_services':metadata.get('queried_services',[]),
            'query_profiles':metadata.get('query_profiles',[])}
    path=Path(directory)/(source+'.json')
    temporary=path.with_suffix('.json.partial')
    with temporary.open('w') as handle:
        json.dump(payload,handle);handle.write('\n')
    temporary.replace(path)
    # Return small metadata only; futures must not retain all source payloads.
    return result
