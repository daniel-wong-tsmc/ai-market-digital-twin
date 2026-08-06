"""F101b Task 8 step 1: stub-brain end-to-end narrator + fallback.

Not a live-brain test -- the answer JSON in the happy path is written by hand,
in the exact shape tests/narrator/test_gate.py's _ok() produces (a
NarratorAnswer aligned with the fixture store's finding ids, series-pool ids,
and month keys). This is the plan's Task 8 step 1: prove the whole pipe --
`narrator --emit-prompt` -> a recorded answer -> `narrator --recorded` ->
`build_site(...)` -- renders the narrated page end to end with a stub brain,
and that a fallback (two invalid answers, `--record-fallback`) renders the
Phase A assembler page instead. The first live-dispatched narrated cycle is a
post-merge criterion (spec Sec8), explicitly not forced in this test.
"""
from __future__ import annotations

import datetime as dt
import json

from gpu_agent.cli import main
from gpu_agent.dashboard.site_build import build_site
from gpu_agent.dashboard.story_render import lint_story_copy
from tests.narrator.test_gate import _ok
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_site_build import story_front_html
from tests.dashboard.test_story_model import _store

DATE = "2026-07-23"
DATE_OBJ = dt.date(2026, 7, 23)

_CONF = {"level": "medium", "basis": "single-source"}


def _fill_scorecards_for_dashboard(store, cat=CAT):
    """`tests.dashboard.test_story_model._store` builds scorecard JSON just
    rich enough for `build_story_model` (which reads it as a lenient raw
    dict, per `gpu_agent/dashboard/scorecards.py`). The dashboard half of
    `build_site` goes through `gpu_agent.report.load_scorecard`, which
    validates the SAME file against the strict `Scorecard`/`Finding` pydantic
    models (`gpu_agent/schema/scorecard.py`, `finding.py`) -- a materially
    larger required-field set. This backfills exactly those extra required
    fields, in place, on the fixture's own files, without touching finding
    ids, demand/supply numbers, or anything `build_story_model` already
    depends on -- so both halves of `build_site` read the same store."""
    for p in sorted((store / cat).glob("*-v1.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        d.setdefault("categoryId", cat)
        d["narrative"] = "Fixture narrative."
        d["confidence"] = _CONF
        for f in d["findings"]:
            f.setdefault("kind", "observed")
            f.setdefault("trend", "rising")
            f.setdefault("why", "Fixture rationale.")
            f.setdefault("impact", {"targets": [cat], "direction": "negative",
                                     "mechanism": "Fixture mechanism."})
            f.setdefault("confidence", _CONF)
            f.setdefault("asOf", d["asOf"])
            f.setdefault("indicatorId", "S9")   # registered in registry/indicators.json
            f.setdefault("side", "supply")
            f.setdefault("polarityDemand", 0)
            f.setdefault("polaritySupply", -1)
            f.setdefault("magnitude", 2)
            f.setdefault("entity", "fixture-entity")
            f.setdefault("observedAt", d["asOf"])
            f.setdefault("capturedAt", f"{d['asOf']}-01T00:00:00Z")
        for dr in d["dimensionRatings"].values():
            dr.setdefault("confidence", _CONF)
        p.write_text(json.dumps(d), encoding="utf-8")


def test_stub_brain_happy_path_renders_narrated_page(tmp_path, capsys):
    # --emit-prompt against the fixture store: capture the bundle a real brain
    # would be handed.
    store = _store(tmp_path / "store")
    rc_emit = main(["narrator", "--emit-prompt", "--store", str(store),
                     "--category", CAT, "--date", DATE])
    assert rc_emit == 0
    bundle = json.loads(capsys.readouterr().out)
    assert set(bundle) == {"system", "schema", "user"}

    # Hand-write a VALID answer -- the Task 3 gate's _ok() shape, aligned with
    # the fixture store's finding ids (f-1, f-2), series-pool id
    # (hbmSupplyCapex), and month key (2026-07).
    answer = _ok(tmp_path)
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(answer.model_dump_json(), encoding="utf-8")

    rc_recorded = main(["narrator", "--recorded", str(answer_path),
                         "--store", str(store), "--category", CAT,
                         "--date", DATE, "--model", "opus", "--retries", "0"])
    assert rc_recorded == 0
    capsys.readouterr()   # discard the "wrote <path>" line

    _fill_scorecards_for_dashboard(store)

    # build_site's dashboard half wants the flat category scorecard directory
    # (production's `site` CLI default is `store/<category>`); its story half
    # (build_story_model) does its own root-vs-category detection and resolves
    # either shape back to the same store root. Pass store/CAT, matching the
    # real CLI convention.
    summary = build_site(CAT, str(store / CAT), work_dir="work-nonexistent",
                          plain_path=None, out_dir=str(tmp_path / "site"),
                          today=DATE_OBJ)
    assert summary["story_lint"] == []

    # F110 Task 12: the category index.html is the compiled dashboard app now,
    # a committed build input. The story page this test is about is still
    # assembled on every build (it feeds the copy lint, and its scene renderer
    # is the one the story permalinks use) -- assert against that.
    html = story_front_html(store / CAT, DATE_OBJ)
    assert answer.headline in html
    assert lint_story_copy(html) == []
    # The dynamic KPI pick caption (from the hand-written answer's kpiPicks,
    # not a hardcoded Phase A string) must render on the page.
    assert "relief lever" in html


def test_two_invalid_answers_fall_back_to_assembler_page(tmp_path, capsys):
    store = _store(tmp_path / "store")

    # Invalid answer 1: banned word (gate check 5).
    bad1 = _ok(tmp_path)
    bad1.deck = "Demand momentum is strengthening."
    bad1_path = tmp_path / "bad1.json"
    bad1_path.write_text(bad1.model_dump_json(), encoding="utf-8")
    rc1 = main(["narrator", "--recorded", str(bad1_path), "--store", str(store),
                "--category", CAT, "--date", DATE])
    assert rc1 == 1
    out1 = capsys.readouterr().out
    assert "NARRATOR GATE FAILED" in out1.splitlines()

    # Invalid answer 2: unknown finding id (gate check 1) -- a distinct
    # violation, so the fallback log below carries two different reasons.
    bad2 = _ok(tmp_path)
    bad2.scenes[0].claimFindingIds = ["f-ghost"]
    bad2_path = tmp_path / "bad2.json"
    bad2_path.write_text(bad2.model_dump_json(), encoding="utf-8")
    rc2 = main(["narrator", "--recorded", str(bad2_path), "--store", str(store),
                "--category", CAT, "--date", DATE])
    assert rc2 == 1
    out2 = capsys.readouterr().out
    assert "NARRATOR GATE FAILED" in out2.splitlines()

    # Neither rejected attempt wrote an artifact.
    assert not (store / CAT / "story" / f"{DATE}.json").exists()

    # The safety valve: record an honest fallback from the two rejection
    # reasons, as the orchestrator would after exhausting retries.
    reasons_path = tmp_path / "reasons.json"
    reasons_path.write_text(
        json.dumps(["banned word: momentum", "unknown finding id: f-ghost"]),
        encoding="utf-8")
    rc_fb = main(["narrator", "--record-fallback", "--reasons", str(reasons_path),
                  "--store", str(store), "--category", CAT, "--date", DATE])
    assert rc_fb == 0

    _fill_scorecards_for_dashboard(store)

    summary = build_site(CAT, str(store / CAT), work_dir="work-nonexistent",
                          plain_path=None, out_dir=str(tmp_path / "site"),
                          today=DATE_OBJ)
    assert summary["story_lint"] == []

    # F110 Task 12: the category index.html is the compiled dashboard app now,
    # a committed build input. The story page this test is about is still
    # assembled on every build (it feeds the copy lint, and its scene renderer
    # is the one the story permalinks use) -- assert against that.
    html = story_front_html(store / CAT, DATE_OBJ)
    # The Phase A assembler headline renders -- not the narrated one, which
    # never made it past the gate.
    assert "The GPU shortage got worse this month." in html
    assert lint_story_copy(html) == []
