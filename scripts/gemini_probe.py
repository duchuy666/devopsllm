#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.gemini_provider import probe

try:
    result=probe()
    target=Path('results/environment/gemini-probe.json')
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
except RuntimeError as exc:
    print(str(exc))
    raise SystemExit(2)
except Exception as exc:
    # Do not print SDK request objects or credentials in failure logs.
    print(f'Gemini probe failed: {type(exc).__name__}, status={getattr(exc,"code",None)}')
    raise SystemExit(1)
