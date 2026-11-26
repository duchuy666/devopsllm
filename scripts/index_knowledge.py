#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag import index_runbooks

try:
    print(json.dumps(index_runbooks(),indent=2))
except RuntimeError as exc:
    print(str(exc)); raise SystemExit(2)
except Exception as exc:
    print(f'Knowledge indexing failed: {type(exc).__name__}, status={getattr(exc,"code",None)}')
    raise SystemExit(1)
