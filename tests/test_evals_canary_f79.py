"""F79 seeded-regression canary: replay a captured damaged-prompt run (the extract
prompt with the six new series-indicator ids stripped from the vocabulary) through the
seam-scoped eval-v2 gate and assert the gate REJECTS it on the EXTRACT seam — the only
seam whose prompt hash moved for F79, hence the only seam that binds.

Standing proof that the F79 prompt change has teeth. SKIPPED until the one-time live
capture lands in the G3 re-gate run: the fixture
`fixtures/evals/canary/extract-series-vocab-stripped/report.json` must be produced by a
real eval run (Opus brains + Opus graders) — it MUST NOT be hand-authored. Once the live
capture is committed, delete the PENDING marker and remove this skip.
"""
from __future__ import annotations
import json
import pathlib
import pytest
from gpu_agent.evals.harness import evaluate_v2, load_baseline

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANARY = ROOT / "fixtures/evals/canary/extract-series-vocab-stripped/report.json"


# PARKED (F99, 2026-07-18, user-directed): the F98b upstreamLeadTimes rebaseline widened the
# extract seam's noise band (eps 0.382 -> 0.901, bar 6.285 -> 5.599) below this canary's damaged-run
# extract score (6.25), so the seam-scoped gate no longer rejects it and this "gate has teeth" proof
# fails. The damage was calibrated too tightly to survive real extract-seam noise (the old bar caught
# it by only 0.035). Re-capturing with more-severe damage needs a human-driven eval run (a safety
# guard blocks an agent from running the gate on an edited prompt) — tracked as F99 in docs/fix-backlog.md.
# See docs/superpowers/eval-notes/2026-07-18-f98b-upstreamLeadTimes-regate-note.md.
@pytest.mark.skip(reason="F99: canary lost teeth after the F98b extract rebaseline widened the noise "
                         "band below its 6.25 damaged score; needs re-capture with harder damage.")
@pytest.mark.skipif(not CANARY.exists(),
                    reason="F79 canary fixture pending live capture in the G3 re-gate run")
def test_f79_series_vocab_stripped_is_rejected():
    baseline = load_baseline(ROOT / "fixtures/evals/baseline.json")
    report = json.loads(CANARY.read_text("utf-8"))
    v = evaluate_v2(baseline, [report])
    assert v["pass"] is False                       # the gate has teeth
    assert v["decision"] in ("marginal-fail", "hard-fail")
    assert any("extract" in r for r in v["reasons"])   # rejected on the seam that moved
