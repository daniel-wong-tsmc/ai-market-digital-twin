# gpu_agent/narrator/pin.py
"""Dedicated tripwire hash for the narrator's emitted prompt bundle.

This is the narrator's OWN pin -- it does NOT join the F6 baseline
(tests/test_evals_baseline_pin.py, fixtures/evals/*). That baseline hard-codes
the four SCORED seams and is MUST-NOT-TOUCH on this lane, so the narrator gets
an identical-in-spirit but separate red-by-design tripwire: any edit to the
narrator prompt (gpu_agent/narrator/prompt.py) changes the emitted bundle's
bytes, which flips this hash, which fails
tests/narrator/test_prompt_pin.py::test_narrator_prompt_hash_matches_pin until
someone deliberately re-records the pin (scripts/narrator-pin-record.py) in
the same commit as the prompt change.

Recipe copied from gpu_agent/evals/prompt_hash.py (reimplemented locally --
per the gated-lane rule, no narrator module may import from gpu_agent/evals/):
build inputs -> emit_narrator_bundle(inputs) ->
json.dumps(bundle, sort_keys=True, ensure_ascii=False) -> SHA-256 hex digest.
"""
from __future__ import annotations

import hashlib
import json

from gpu_agent.narrator.prompt import emit_narrator_bundle


def _emit(hash_input: dict) -> dict:
    return emit_narrator_bundle(hash_input)


def _canonical_json(bundle: dict) -> str:
    return json.dumps(bundle, sort_keys=True, ensure_ascii=False)


def compute_narrator_prompt_hash(hash_input: dict) -> str:
    bundle = _emit(hash_input)
    canonical = _canonical_json(bundle)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
