import datetime as dt

import pytest

from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import NarratorAnswer, RelatedDoc
from gpu_agent.narrator.inputs import build_narrator_inputs
from tests.narrator.test_schema import _answer, _scene
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store


_inp_cache: dict = {}


def _inp(tmp_path):
    # Several tests below call _inp(tmp_path) more than once with the same
    # tmp_path (to check two answers against the same fixture inputs), but
    # tests/dashboard/test_story_model._store() creates its directory tree
    # with mkdir(parents=True) and no exist_ok=True, so a second call on the
    # same tmp_path raises FileExistsError. Cache by tmp_path so the store is
    # only built once per test; pytest's tmp_path is unique per test function,
    # so this cannot leak fixture state between tests.
    key = str(tmp_path)
    if key not in _inp_cache:
        _inp_cache[key] = build_narrator_inputs(
            CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    return _inp_cache[key]


def _ok(tmp_path):
    # an answer aligned with the fixture store: finding f-1, series pool ids, month keys
    #
    # scene 2's only cited finding (f-2) has a single evidence date of
    # 2026-06-10 against the fixture store's storyDate of 2026-07-23 -- 43
    # days into the "news" half life's decay curve, deep under
    # AGING_THRESHOLD. Check 7 (F103 Task 4) requires a scene that leans
    # only on aged evidence to date its claims in prose, so scene 2's
    # paragraph carries a month/year token here to stay gate-clean.
    return NarratorAnswer.model_validate(_answer(
        scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                _scene(n=2, title="What would close the gap",
                       claimFindingIds=["f-2"], relatedDocs=[],
                       paragraphs=["Cut back on output in June 2026."])],
        kpiPicks=[{"indicatorId": "hbmSupplyCapex", "whyCaption": "relief lever",
                    "scene": 1}],
        calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                         "scene": 1}]))


def test_clean_answer_passes(tmp_path):
    assert gate_narrator(_ok(tmp_path), _inp(tmp_path)) == []


def test_unknown_finding_id_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-ghost"]
    assert any("f-ghost" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_sourceless_scene_needs_exact_wording(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = []
    a.scenes[0].sourceLine = "Source: trust me"
    assert any("Source: trust me" in v for v in gate_narrator(a, _inp(tmp_path)))
    a.scenes[0].sourceLine = "No new sourced evidence today."
    assert gate_narrator(a, _inp(tmp_path)) == []


def test_related_doc_outside_pool_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].relatedDocs = [RelatedDoc(url="https://elsewhere.example/x",
                                          title="t", outlet="o", date="d")]
    assert any("elsewhere" in v for v in gate_narrator(a, _inp(tmp_path)))


def _inp_with_docpool(tmp_path, docs):
    # _inp(tmp_path) is built with run_dir=None, so its own docPool is always
    # empty (see build_narrator_inputs's `if run_dir is not None:` guard).
    # The outlet-match check (Important 2b) needs a real pooled doc to check
    # against, so tests exercising it build inputs by hand rather than going
    # through build_narrator_inputs's run_dir/blobs.json plumbing.
    return {**_inp(tmp_path), "docPool": docs}


def test_related_doc_outlet_must_match_pooled_source(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].relatedDocs = [RelatedDoc(url="https://x.example/hbm",
                                          title="t", outlet="CNBC", date="d")]
    inp = _inp_with_docpool(tmp_path, [
        {"url": "https://x.example/hbm", "source": "Reuters", "date": "2026-07-22"}])
    violations = gate_narrator(a, inp)
    assert any("CNBC" in v and "https://x.example/hbm" in v for v in violations)

    # Same url, matching outlet -- must not be rejected by the outlet check.
    a2 = _ok(tmp_path)
    a2.scenes[0].relatedDocs = [RelatedDoc(url="https://x.example/hbm",
                                           title="t", outlet="Reuters", date="d")]
    assert not any("outlet" in v for v in gate_narrator(a2, inp))


def test_visual_series_id_must_be_known(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].visual.seriesId = "notASeries"
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("notASeries" in v for v in violations)


def test_banned_word_rejected(tmp_path):
    a = _ok(tmp_path)
    a.deck = "Demand momentum is strengthening."
    assert len(gate_narrator(a, _inp(tmp_path))) >= 1


def test_scene_bounds_and_forward_close(tmp_path):
    a = _ok(tmp_path)
    a.scenes = a.scenes[:1]                       # only 1 scene
    a.scenes[0].title = "What to watch"           # forward-looking, so only
                                                   # the count check can fire
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("between 2 and 5" in v and "1" in v for v in violations)
    assert not any("forward-looking" in v for v in violations)

    b = _ok(tmp_path)
    b.scenes[-1].title = "Another grim chapter"   # not forward-looking
    violations_b = gate_narrator(b, _inp(tmp_path))
    assert any("forward-looking" in v and "Another grim chapter" in v
               for v in violations_b)


def test_scene_bounds_upper_limit(tmp_path):
    scenes = [
        _scene(n=1, title="What tightened", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=2, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=3, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=4, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=5, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=6, title="What to watch", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
    ]
    a = NarratorAnswer.model_validate(_answer(
        scenes=scenes, kpiPicks=[], calloutMonths=[]))
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("between 2 and 5" in v and "6" in v for v in violations)


def test_kpi_pick_cannot_be_the_anchored_indicator(tmp_path):
    # The page always shows gpuRentalOnDemand as its own anchored chip
    # (story_model._base_model); a kpiPick naming that same indicator would
    # render the exact same chip a second time. The gate must reject it and
    # name the offending id so the brain can correct itself.
    a = _ok(tmp_path)
    a.kpiPicks[0].indicatorId = "gpuRentalOnDemand"
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("gpuRentalOnDemand" in v for v in violations)


def test_kpi_and_callout_membership(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].indicatorId = "notASeries"
    assert any("notASeries" in v for v in gate_narrator(a, _inp(tmp_path)))
    b = _ok(tmp_path)
    b.calloutMonths[0].monthKey = "1999-01"
    assert any("1999-01" in v for v in gate_narrator(b, _inp(tmp_path)))


# Supplementary coverage for the two sub-parts of check 6 that the brief's
# test_kpi_and_callout_membership doesn't exercise on its own: a kpiPick
# pointing at a scene number that doesn't exist, and two kpiPicks sharing a
# scene.
def test_kpi_pick_scene_must_exist(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].scene = 99
    assert any("99" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_kpi_pick_scenes_must_be_unique(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks.append(a.kpiPicks[0].model_copy())
    assert any("unique" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_scene_n_values_must_be_contiguous(tmp_path):
    a = _ok(tmp_path)
    a.scenes[-1].n = 7                    # not 1..2 contiguous any more
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("[1, 7]" in v or ("1" in v and "7" in v and "contiguous" in v)
               for v in violations)

    b = _ok(tmp_path)
    b.scenes[0].n, b.scenes[1].n = 2, 1   # right set of values, wrong order
    violations_b = gate_narrator(b, _inp(tmp_path))
    assert any("[2, 1]" in v and "contiguous" in v for v in violations_b)


def test_scene_source_line_must_not_be_empty(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-1"]  # keep a claim so check 2's exact-
                                           # wording rule doesn't also fire
    a.scenes[0].sourceLine = "   "
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("sourceLine must not be empty" in v and "1" in v
               for v in violations)


_BANNED_WORD = "momentum"


@pytest.mark.parametrize("field", [
    "headline", "deck", "scene_title", "scene_paragraph", "scene_sourceLine",
    "kpi_whyCaption", "callout_text",
    "visual_label", "related_title", "related_outlet", "related_date",
])
def test_prose_sweep_covers_every_location(tmp_path, field):
    a = _ok(tmp_path)
    if field == "headline":
        a.headline = f"The {_BANNED_WORD} shifted."
    elif field == "deck":
        a.deck = f"Demand {_BANNED_WORD} is building."
    elif field == "scene_title":
        a.scenes[0].title = f"The {_BANNED_WORD} shift"
    elif field == "scene_paragraph":
        a.scenes[0].paragraphs = [f"Buyers felt {_BANNED_WORD} building."]
    elif field == "scene_sourceLine":
        a.scenes[0].claimFindingIds = ["f-1"]
        a.scenes[0].sourceLine = f"Source: {_BANNED_WORD} tracker"
    elif field == "kpi_whyCaption":
        a.kpiPicks[0].whyCaption = f"the {_BANNED_WORD} lever"
    elif field == "callout_text":
        a.calloutMonths[0].text = f"Jul: {_BANNED_WORD} shift"
    elif field == "visual_label":
        # CRITICAL 1: scene.visual.label renders as visible page text
        # (story_render._scene_html's `st-lab` span) but was never part of
        # the gate's banned-word sweep before this fix.
        a.scenes[0].visual.label = f"{_BANNED_WORD} tracker"
    elif field == "related_title":
        # CRITICAL 1: each relatedDocs.title renders as visible page text
        # too (story_render._scene_html's "Related coverage:" links).
        a.scenes[0].relatedDocs = [RelatedDoc(
            url="https://x.example/a", title=f"{_BANNED_WORD} builds",
            outlet="Reuters", date="d")]
    elif field == "related_outlet":
        # CRITICAL 1: same for relatedDocs.outlet.
        a.scenes[0].relatedDocs = [RelatedDoc(
            url="https://x.example/a", title="t",
            outlet=f"{_BANNED_WORD} Wire", date="d")]
    elif field == "related_date":
        # Divergence 1: relatedDocs.date is brain-authored freeform text
        # (the schema places no validation on it) but story_render._scene_html
        # renders it as visible page text too, in the same
        # "outlet · title · date" related-coverage link as title/outlet.
        a.scenes[0].relatedDocs = [RelatedDoc(
            url="https://x.example/a", title="t", outlet="Reuters",
            date=f"{_BANNED_WORD} 2026")]
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("momentum" in v for v in violations)


def test_headline_single_index_now_rejected(tmp_path):
    # Divergence 2: the headline renders TWICE on the page (site_render.page's
    # <title>Merchant GPU — {headline}</title> and story_render._headline_block's
    # <h1>{headline}</h1>). A headline with "index" exactly once therefore
    # shows up as "index" TWICE on the real page, which trips build-time
    # lint_story_copy's "index/indexed appears at most once" rule. Before this
    # fix, gate_narrator counted the headline only once and passed this
    # answer -- confirmed reproducible: gate-pass, build-crash.
    a = _ok(tmp_path)
    a.headline = "The index rose last week"
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("index" in v.lower() for v in violations)


def test_index_once_with_gap_chart_now_rejected(tmp_path):
    # Divergence 3 (certified): story_render.lint_story_copy scans the WHOLE
    # rendered page, and whenever inputs.gapMonths is non-empty (the normal
    # live state) gap_chart.py renders a fixed axis label containing
    # "indexed" ("orders vs. chips shipped, indexed"). That fixed chrome
    # occurrence already spends the page's entire "index/indexed appears at
    # most once" budget, so the narrator's own budget is zero. The fixture
    # used throughout this file (_inp(tmp_path)) has a non-empty gapMonths,
    # so a single "index" in narrator prose here must now be REJECTED --
    # before the fix, gate_narrator counted only narrator prose (0 there + 1
    # here = 1, "at most once" satisfied) and returned [], while the real
    # page had chrome's 1 + narrator's 1 = 2 and crashed build_site.
    a = _ok(tmp_path)
    a.scenes[0].paragraphs = ["The index rose modestly this week."]
    assert _inp(tmp_path)["gapMonths"]  # sanity: fixture really has gap months
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("index" in v.lower() for v in violations)


def test_index_once_without_gap_chart_still_passes(tmp_path):
    # Companion to the above: with gapMonths EMPTY, no gap chart renders, so
    # there is no fixed "indexed" chrome eating the page's budget. The plan's
    # original "once max" rule is then the correct (and only) check, and a
    # single narrator "index" occurrence must still pass.
    inp = {**_inp(tmp_path), "gapMonths": []}
    a = _ok(tmp_path)
    a.scenes[0].paragraphs = ["The index rose modestly this week."]
    a.calloutMonths = []  # no gapMonths left for the fixture's callout to reference
    assert gate_narrator(a, inp) == []


def test_prose_sweep_catches_banned_word_hidden_by_angle_bracket_noise(tmp_path):
    # Unescaped prose containing a literal "<script>...</script>" span would
    # be stripped entirely by lint_story_copy's script-tag remover before the
    # banned-word scan runs, hiding the word inside. Escaping the model's
    # prose before wrapping it in "<p>...</p>" turns those angle brackets
    # into harmless entities so the word is still scanned and caught.
    a = _ok(tmp_path)
    a.deck = "Before. <script>the outlook shows momentum</script> After."
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("momentum" in v for v in violations)


def test_callout_months_cap_at_two(tmp_path):
    a = _ok(tmp_path)
    a.calloutMonths = [
        a.calloutMonths[0].model_copy(),
        a.calloutMonths[0].model_copy(),
        a.calloutMonths[0].model_copy(),
    ]
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("at most 2" in v and "3" in v for v in violations)


def test_callout_scene_must_exist(tmp_path):
    a = _ok(tmp_path)
    a.calloutMonths[0].scene = 99
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("calloutMonths" in v and "99" in v for v in violations)


def _inp_with_findings_and_date(tmp_path, findings, story_date):
    # Check 7 tests need full control over finding evidence dates and the
    # story's reference date, independent of whatever the fixture store
    # happens to contain -- override both on top of the normal fixture
    # inputs (which still supplies seriesPool/gapMonths/docPool so the
    # earlier checks don't spuriously fire).
    return {**_inp(tmp_path), "findings": findings, "storyDate": story_date}


_AGED_FINDING = {
    "id": "f-aged", "statement": "SK Hynix shifted HBM output",
    "evidence": [{"source": "s", "url": "https://x.example/aged",
                  "date": "2026-05-24", "tier": "primary"}],
}
_FRESH_FINDING = {
    "id": "f-fresh", "statement": "Oracle capex up 162%",
    "evidence": [{"source": "s", "url": "https://x.example/fresh",
                  "date": "2026-07-24", "tier": "primary"}],
}


def test_check7_aged_only_scene_without_date_token_flagged(tmp_path):
    # Evidence dated 2026-05-24 against a storyDate two months later is deep
    # into the "news" half life's decay curve -- well under AGING_THRESHOLD.
    inp = _inp_with_findings_and_date(tmp_path, [_AGED_FINDING], "2026-07-24")
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-aged"]
    a.scenes[0].paragraphs = ["Supply stayed tight across the board."]
    violations = gate_narrator(a, inp)
    assert ("scene 1 leans only on aged evidence and must date its claims "
            "in prose") in violations


def test_check7_aged_scene_passes_when_dated_in_prose(tmp_path):
    inp = _inp_with_findings_and_date(tmp_path, [_AGED_FINDING], "2026-07-24")
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-aged"]
    a.scenes[0].paragraphs = ["Supply stayed tight in late May 2026."]
    violations = gate_narrator(a, inp)
    assert not any("leans only on aged evidence" in v for v in violations)


def test_check7_scene_with_fresh_finding_not_flagged(tmp_path):
    inp = _inp_with_findings_and_date(
        tmp_path, [_AGED_FINDING, _FRESH_FINDING], "2026-07-24")
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-aged", "f-fresh"]
    a.scenes[0].paragraphs = ["Supply stayed tight across the board."]
    violations = gate_narrator(a, inp)
    assert not any("leans only on aged evidence" in v for v in violations)


def test_check7_skipped_when_story_date_missing_or_garbage(tmp_path):
    inp = _inp_with_findings_and_date(
        tmp_path, [_AGED_FINDING], "not-a-date")
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-aged"]
    a.scenes[0].paragraphs = ["Supply stayed tight across the board."]
    violations = gate_narrator(a, inp)
    assert not any("leans only on aged evidence" in v for v in violations)


def test_missing_inputs_keys_fail_closed_instead_of_raising(tmp_path):
    a = _ok(tmp_path)
    violations = gate_narrator(a, {})
    assert violations


def test_content_free_answer_with_empty_inputs_is_still_rejected():
    # A structurally legal but content-free answer -- no claim ids (using the
    # exact no-source sentence), no relatedDocs, no kpiPicks, no
    # calloutMonths -- references nothing in `inputs`, so checks 2/3/6 stay
    # silent no matter what `inputs` contains. Before the missing-keys check,
    # gate_narrator(a, {}) returned [] (a silent pass) instead of failing
    # closed on the fact that `inputs` itself is empty.
    a = NarratorAnswer.model_validate(_answer(
        scenes=[_scene(claimFindingIds=[],
                       sourceLine="No new sourced evidence today.",
                       relatedDocs=[]),
                _scene(n=2, title="What would close the gap",
                       claimFindingIds=[],
                       sourceLine="No new sourced evidence today.",
                       relatedDocs=[])],
        kpiPicks=[], calloutMonths=[]))
    violations = gate_narrator(a, {})
    assert violations
    for k in ("findings", "docPool", "seriesPool", "gapMonths"):
        assert any(k in v for v in violations)
