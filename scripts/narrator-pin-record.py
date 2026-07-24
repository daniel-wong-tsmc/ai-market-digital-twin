#!/usr/bin/env python
"""Deliberate re-record helper for the narrator prompt pin.

Run this ONLY when you have intentionally changed the narrator prompt
(gpu_agent/narrator/prompt.py) and want to accept the new hash. Commit the
rewritten fixtures/narrator/prompt-pin.json in the SAME commit as the prompt
change.

Usage (from repo root):
    .venv/Scripts/python scripts/narrator-pin-record.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from gpu_agent.narrator.pin import compute_narrator_prompt_hash  # noqa: E402

HASH_INPUT = _REPO_ROOT / "fixtures" / "narrator" / "hash-input.json"
PIN = _REPO_ROOT / "fixtures" / "narrator" / "prompt-pin.json"


def main() -> None:
    hash_input = json.loads(HASH_INPUT.read_text(encoding="utf-8"))
    prompt_hash = compute_narrator_prompt_hash(hash_input)
    pin = {
        "schemaVersion": 1,
        "promptHash": prompt_hash,
        "recordedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": "re-record ONLY deliberately: .venv/Scripts/python scripts/narrator-pin-record.py",
    }
    PIN.write_text(json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Recorded narrator prompt hash: {prompt_hash}")


if __name__ == "__main__":
    main()
