"""Seeded-regression canary (F79 origin, re-captured under F99): replay a captured
damaged-prompt run through the seam-scoped eval-v2 gate and assert the gate REJECTS it
on the EXTRACT seam — the only seam whose prompt hash moved, hence the only seam that
binds.

Standing proof that the eval gate has teeth. The fixture
`fixtures/evals/canary/extract-rules-stripped/report.json` was produced by a real live
eval run (Opus brains + Opus graders, 2026-08-04, F99 re-capture) — it MUST NOT be
hand-authored or edited. The D1 damage (capture worktree only, never committed): the
extract system prompt was capped to "the single most eye-catching claim", the
anti-invention rule deleted, and the name-every-affected-category nudge deleted. The
damaged run scored extract seamMean 5.375 vs hard bar 5.533 (bar 6.163) -> hard-fail,
with all five calibration negatives <= 2. The prior fixture
`extract-series-vocab-stripped/` (2026-07-15 capture, damaged score 6.25) is retained
as history; it lost its teeth when the F98b/F105 rebaselines honestly widened the
extract noise band below its damaged score.
See docs/superpowers/eval-notes/2026-08-04-f99-canary-recapture-note.md.
"""
from __future__ import annotations
import json
import pathlib
import pytest
from gpu_agent.evals.harness import evaluate_v2, load_baseline

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANARY = ROOT / "fixtures/evals/canary/extract-rules-stripped/report.json"


@pytest.mark.skipif(not CANARY.exists(),
                    reason="F99 canary fixture pending live capture")
def test_f79_series_vocab_stripped_is_rejected():
    baseline = load_baseline(ROOT / "fixtures/evals/baseline.json")
    report = json.loads(CANARY.read_text("utf-8"))
    v = evaluate_v2(baseline, [report])
    assert v["pass"] is False                       # the gate has teeth
    assert v["decision"] in ("marginal-fail", "hard-fail")
    assert any("extract" in r for r in v["reasons"])   # rejected on the seam that moved
