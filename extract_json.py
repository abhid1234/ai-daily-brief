#!/usr/bin/env python3
"""Extract + validate the first top-level JSON object from stdin -> /tmp/brief/draft.json.

The reasoning stage (Stage 2) is told to emit raw JSON, but models sometimes wrap it in prose or
``` fences. This deterministically pulls the outermost {...}, validates it, and writes draft.json.
Exit 1 if no valid JSON object is found (Stage 3 then skips — no brief is sent rather than a broken one).
"""
import json
import sys
from pathlib import Path

raw = sys.stdin.read()
start = raw.find("{")
if start == -1:
    sys.exit("extract_json: no JSON object in stage-2 output")

depth, end, in_str, esc = 0, -1, False, False
for i in range(start, len(raw)):
    c = raw[i]
    if in_str:
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            in_str = False
    else:
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
if end == -1:
    sys.exit("extract_json: unterminated JSON object")

try:
    obj = json.loads(raw[start:end])
except json.JSONDecodeError as e:
    sys.exit(f"extract_json: invalid JSON: {e}")

out = Path("/tmp/brief/draft.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(obj, ensure_ascii=False))
print(f"extract_json: {len(obj.get('items', []))} items", file=sys.stderr)
