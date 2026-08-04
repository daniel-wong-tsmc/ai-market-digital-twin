"""F68(a) wire-up: the thesis path enforces its own Sec 2b VOICE rules deterministically.

`lint_thesis_prose` (thesis.py) has existed since the lane-polish branch but had ZERO
callers — the rules were prompt text plus a dead function. This module pins the wiring:

  * `lint_answer_prose(answer)` maps a whole ThesisAnswer onto that per-field lint,
    labelling each violation with the thesis id (judgments) or the routed slug
    (proposals), the same labels `gate_answer` uses.
  * `thesis --recorded` runs it BEFORE the gate/apply and BLOCKS on violation, exactly
    as `judge --recorded` does for judgment prose (`voice-lint: ` stderr prefix, exit 1,
    store never written).

Which fields get linted, and why:
  - proposals carry a brand-new `statement` + `mechanism` -> both linted.
  - judgments carry `mechanism` -> linted. They have NO `statement` field; an `adjusted`
    verdict's replacement statement is parsed out of its `"ADJUSTED:"`-prefixed rationale
    (see `_adjusted_statement`, shared with `_apply_judgment_record` so the lint can never
    check different text than the apply writes). A non-adjusted verdict writes no new
    statement, so there is nothing to lint — its rationale is a history field, not
    exec-facing book prose.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from gpu_agent.thesis import ThesisAnswer, lint_answer_prose

PY = sys.executable
CLEAN_ANSWER = Path("tests/fixtures/thesis-answer-clean.json")


def _clean_dict() -> dict:
    return json.loads(CLEAN_ANSWER.read_text("utf-8"))


def _answer(d: dict) -> ThesisAnswer:
    return ThesisAnswer.model_validate(d)


# --- lint_answer_prose: the answer -> violations mapping -------------------------------


def test_clean_recorded_answer_has_no_prose_violations():
    """The committed clean fixture must stay clean — this is the guard that the wire-up
    does not retroactively reject the answers the rest of the suite replays."""
    assert lint_answer_prose(_answer(_clean_dict())) == []


def test_judgment_two_sentence_mechanism_is_flagged_and_labelled_by_thesis_id():
    d = _clean_dict()
    target = d["judgments"][0]
    target["mechanism"] = "Capex converts to shipments with a lag. The lag is two quarters."

    violations = lint_answer_prose(_answer(d))

    assert any(
        v.startswith(f"{target['thesisId']}: mechanism:") and "2 sentences (max 1)" in v
        for v in violations
    ), violations


def test_adjusted_verdict_new_statement_is_linted_from_its_rationale():
    """An `adjusted` verdict rewrites the book's statement via its ADJUSTED:-prefixed
    rationale — that replacement text is exec-facing book prose and must be linted."""
    d = _clean_dict()
    target = d["judgments"][0]
    target["verdict"] = "adjusted"
    target["rationale"] = (
        "ADJUSTED: Demand stays firm through the cycle. Backlog growth confirms it."
    )

    violations = lint_answer_prose(_answer(d))

    assert any(
        v.startswith(f"{target['thesisId']}: statement:") and "2 sentences (max 1)" in v
        for v in violations
    ), violations


def test_non_adjusted_verdict_rationale_is_not_statement_linted():
    """A reaffirmed judgment writes no new statement, so its multi-sentence rationale is
    NOT a statement violation — rationale is a history field, not book prose."""
    d = _clean_dict()
    target = d["judgments"][0]
    target["verdict"] = "reaffirmed"
    target["rationale"] = "Demand held up. Backlog grew again. Pricing stayed firm."

    violations = lint_answer_prose(_answer(d))

    assert not any(v.startswith(f"{target['thesisId']}: statement:") for v in violations)


def test_adjusted_verdict_without_the_prefix_yields_no_statement_violation():
    """No ADJUSTED: prefix -> the apply path keeps the entry's existing statement, so the
    lint has no new statement to check (lint and apply must agree on this)."""
    d = _clean_dict()
    target = d["judgments"][0]
    target["verdict"] = "adjusted"
    target["rationale"] = "Demand stays firm. Backlog growth confirms it."

    violations = lint_answer_prose(_answer(d))

    assert not any(v.startswith(f"{target['thesisId']}: statement:") for v in violations)


def test_proposal_statement_and_mechanism_are_linted_and_labelled_by_slug():
    d = _clean_dict()
    d["proposed"] = [{
        "title": "Packaging spreads beyond one supplier",
        "statement": "Packaging work spreads to more suppliers. Wait times drive it.",
        "lens": "supply",
        "rationale": "r",
        "findingIds": d["judgments"][0]["findingIds"],
        "mechanism": "Shorter quoted waits pull work to alternative packagers.",
        "falsifiableTrigger": "S10 stops tightening",
        "sensitivity": "s",
    }]

    violations = lint_answer_prose(_answer(d))

    assert any(
        v.startswith("packaging-spreads-beyond-one-supplier: statement:")
        and "2 sentences (max 1)" in v
        for v in violations
    ), violations


def test_off_allowlist_acronym_in_proposal_statement_is_flagged():
    """The lint reuses reader.lint_prose, so the acronym allowlist applies to thesis prose
    too — the check that makes registry/acronyms.json the single source of truth."""
    d = _clean_dict()
    d["proposed"] = [{
        "title": "Zzz unknown acronym probe",
        "statement": "Capacity shifts toward QQQZ suppliers this year.",
        "lens": "supply",
        "rationale": "r",
        "findingIds": d["judgments"][0]["findingIds"],
        "mechanism": "Shorter quoted waits pull work to alternative packagers.",
        "falsifiableTrigger": "S10 stops tightening",
        "sensitivity": "s",
    }]

    violations = lint_answer_prose(_answer(d))

    assert any("QQQZ" in v and "acronym" in v for v in violations), violations


def test_ase_is_allowlisted_so_packaging_prose_passes():
    """F68(f) recurrence: ASE (the packaging supplier) is now on the allowlist, so live
    packaging prose naming it does not trip the newly-blocking lint."""
    d = _clean_dict()
    d["judgments"][0]["mechanism"] = (
        "Accelerator makers route packaging to ASE because it quotes shorter waits."
    )
    assert lint_answer_prose(_answer(d)) == []


# --- the ADJUSTED: parse shared by the lint and the apply ------------------------------


def test_adjusted_statement_distinguishes_no_replacement_from_an_empty_one():
    """Refactor guard. `_adjusted_statement` was lifted out of `_apply_judgment_record` so
    the lint and the apply read the same text. None means "no replacement written" (keep
    the standing statement); "" means a bare `ADJUSTED:` wrote an EMPTY replacement, which
    the pre-existing apply behaviour stores as-is. Collapsing the two would silently change
    what the book holds, so the distinction is pinned here."""
    from gpu_agent.thesis import _adjusted_statement

    assert _adjusted_statement("reaffirmed", "ADJUSTED: ignored on a non-adjusted verdict") is None
    assert _adjusted_statement("adjusted", "no prefix here") is None
    assert _adjusted_statement("adjusted", None) is None
    assert _adjusted_statement("adjusted", "ADJUSTED:") == ""
    assert _adjusted_statement("adjusted", "ADJUSTED:   ") == ""
    assert _adjusted_statement("adjusted", "ADJUSTED:  Demand stays firm.  ") == "Demand stays firm."


# --- CLI wiring: thesis --recorded blocks, and never writes the store ------------------


def _run(*args):
    return subprocess.run([PY, "-m", "gpu_agent.cli", *args], capture_output=True, text=True)


def _seeded_store(tmp_path: Path) -> Path:
    """Seed the thesis store via the real CLI, then return it (mirrors test_cli_thesis)."""
    store = tmp_path / "store"
    out = _run("thesis", "--emit-prompt", "--findings", "fixtures/golden/findings.json",
               "--store", str(store), "--category", "chips.merchant-gpu",
               "--as-of", "2026-07-03")
    assert out.returncode == 0, out.stderr
    return store


def _book_bytes(store: Path) -> bytes:
    return (store / "theses" / "chips.merchant-gpu" / "book.json").read_bytes()


def test_recorded_violating_prose_blocks_with_voice_lint_prefix_and_leaves_book_unchanged(tmp_path):
    store = _seeded_store(tmp_path)
    before = _book_bytes(store)

    d = _clean_dict()
    d["judgments"][0]["mechanism"] = (
        "Capex converts to shipments with a lag. The lag is roughly two quarters."
    )
    bad = tmp_path / "violating-answer.json"
    bad.write_text(json.dumps(d), encoding="utf-8")

    out = _run("thesis", "--recorded", str(bad),
               "--findings", "fixtures/golden/findings.json",
               "--store", str(store), "--category", "chips.merchant-gpu",
               "--as-of", "2026-07-03")

    assert out.returncode == 1, out.stdout
    # same stderr prefix the run-cycle skill already greps for on the judge path
    assert "voice-lint:" in out.stderr, out.stderr
    assert "mechanism:" in out.stderr
    # blocked BEFORE apply — the book is byte-unchanged
    assert _book_bytes(store) == before


def test_recorded_clean_prose_still_applies(tmp_path):
    """Regression guard: the block fires only on violations — a clean answer still writes."""
    store = _seeded_store(tmp_path)
    before = _book_bytes(store)

    out = _run("thesis", "--recorded", str(CLEAN_ANSWER),
               "--findings", "fixtures/golden/findings.json",
               "--store", str(store), "--category", "chips.merchant-gpu",
               "--as-of", "2026-07-03")

    assert out.returncode == 0, out.stderr
    assert _book_bytes(store) != before
