import json
import re

from gpu_agent.dashboard.story_render import evidence_json, render_evidence_panel


def test_evidence_json_blob_escapes_lt():
    blob = evidence_json({"k": {"title": "<script>alert(1)</script>"}})
    assert 'id="ev-data"' in blob
    body = blob.split(">", 1)[1].rsplit("<", 1)[0]
    # Structural guard: the blob escaper must turn a literal "<" into the
    # JSON-safe "<" sequence, so a claim/finding value can never
    # prematurely close the surrounding <script> tag. Asserting the escape
    # sequence itself (not just the end-to-end absence of "<script>alert")
    # means this fails if the `.replace("<", ...)` call is deleted, even if
    # some other coincidence still hid the raw substring.
    assert "\\u003c" in body
    assert "<script>alert" not in body
    assert json.loads(body)["k"]["title"] == "<script>alert(1)</script>"


def test_panel_script_contract():
    js = render_evidence_panel()
    assert "window.openEV" in js and "window.closeEV" in js
    assert "encodeURI(" in js               # F100 XSS regression carry-over
    assert "data-ev" in js                  # delegated trigger
    assert "Escape" in js                   # keyboard close
    assert js.count("<script>") == 1 and js.count("</script>") == 1


def test_panel_script_shows_honest_empty_state_for_no_findings():
    # A claim with no linked evidence must show a plain, honest message --
    # never silently render nothing (which reads as broken) and never a
    # borrowed source from another claim.
    js = render_evidence_panel()
    assert "No linked sources for this yet." in js
    assert "finds.length" in js and "ev-empty" in js


# NOTE on the two tests below: we have no JS engine here (stdlib-only, no
# browser), so we cannot execute openEV() and observe a real DOM. Instead we
# pin the *source structure* of each guard: the regex requires the href
# assignment to appear textually immediately after its guard condition, with
# nothing else in between. If someone deletes the guard, weakens the regex,
# or moves the assignment outside the `if`, the exact-structure match breaks
# and the test fails. This is a stand-in for a browser-level regression test
# (e.g. a headless-browser check that javascript:/data: URLs never produce a
# clickable href), which is out of scope for this stdlib-only test suite.


def test_finding_link_href_only_inside_http_https_guard():
    js = render_evidence_panel()
    guarded = re.search(
        r"if\(f\.url&&/\^https\?:/\.test\(f\.url\)\)\{"
        r"var a=el\('a','ev-link','↗'\);\s*"
        r"a\.href=encodeURI\(f\.url\);",
        js,
    )
    assert guarded, "finding link href must be textually inside the /^https?:/ guard"
    # The href assignment must not appear anywhere else (i.e. not duplicated
    # outside the guarded block).
    assert js.count("a.href=encodeURI(f.url)") == 1


def test_explore_link_href_only_inside_scheme_guard():
    js = render_evidence_panel()
    # encodeURI() does not neutralise dangerous schemes (encodeURI these
    # javascript:alert(1) comes back unchanged), so the explore link — whose
    # value is normally a relative path like "appendix.html" — must be gated
    # so relative paths and http(s) URLs render, while javascript:, data:,
    # vbscript: and any other scheme and protocol-relative URLs do not produce a link at all.
    guarded = re.search(
        r"if\(d\.explore&&\("
        r"/\^https\?:/i\.test\(d\.explore\)\|\|"
        r"!/\^\[a-zA-Z\]\[a-zA-Z0-9\+\.\-\]\*:/\.test\(d\.explore\)"
        r"\)&&"
        + r"!/\^" + r"\\" + r"/\\" + r"//"
        + r"\.test\(d\.explore\)\)\{"
        r"var ex=el\('a','ev-explore','see everything we have →'\);\s*"
        r"ex\.href=encodeURI\(d\.explore\);",
        js,
    )
    assert guarded, "explore link href must be textually inside the scheme guard"
    assert js.count("ex.href=encodeURI(d.explore)") == 1

    # Belt-and-suspenders: the guard regex itself, applied in Python, must
    # accept relative paths and http(s) URLs and reject javascript:/data:/
    # vbscript: schemes and protocol-relative URLs. This mirrors (without executing) the JS logic.
    def guard_allows(value: str) -> bool:
        return (bool(re.match(r"^https?:", value, re.I)) or not re.match(
            r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value
        )) and not re.match(r"^//", value)

    assert guard_allows("appendix.html")
    assert guard_allows("https://s.example/appendix.html")
    assert guard_allows("http://s.example/appendix.html")
    assert not guard_allows("javascript:alert(1)")
    assert not guard_allows("data:text/html,<script>alert(1)</script>")
    assert not guard_allows("vbscript:msgbox(1)")
    assert not guard_allows("//evil.example")
    assert not guard_allows("//evil.example/path")


import datetime as dt
from tests.dashboard.test_story_model import _store, CAT
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import (_chart_block, _chip_html,
                                              _headline_block, _kpi_band,
                                              STORY_CSS,
                                              render_condense_script)


def _model(tmp_path):
    return build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))


def test_headline_block(tmp_path):
    h = _headline_block(_model(tmp_path))
    assert "The GPU shortage got worse this month." in h
    assert "updated with each run" in h
    assert 'class="st-head"' in h


def test_chart_block_has_svg_and_source_line(tmp_path):
    c = _chart_block(_model(tmp_path))
    assert "<svg" in c and "the gap, this week" in c
    assert "Source: agent-tracked orders and shipment data" in c


def test_kpi_band_chips(tmp_path):
    band = _kpi_band(_model(tmp_path))
    assert 'data-ev="kpi:gpuRentalOnDemand"' in band
    assert "price of scarcity" in band
    assert 'class="st-tip"' in band          # hover tooltip content present
    assert 'class="st-pin"' in band          # anchored marker
    assert "st-dot" in band                  # scene dots on picks
    assert band.count("st-chip") >= 3


def test_chip_html_omits_arrow_without_stray_spacing():
    # A categorical chip (arrow == "") must not leave a trailing space
    # after the value where the arrow used to sit.
    chip = {"claim": "kpi:x", "label": "Big buyers' spending plans",
            "value": "raised again", "arrow": "", "spark": [1.0, 2.0],
            "caption": "", "tip": "tip text"}
    html = _chip_html(chip)
    assert "<span class=\"st-val\">raised again</span>" in html
    assert "raised again </span>" not in html
    assert "raised again  " not in html

    numeric_chip = {**chip, "value": "$14.62/hr", "arrow": "▼"}
    numeric_html = _chip_html(numeric_chip)
    assert "<span class=\"st-val\">$14.62/hr ▼</span>" in numeric_html


def test_sparkline_locked_to_intended_size_inside_chip():
    # The sparkline is a flex item inside .st-chip (flex-direction:column);
    # without an explicit rule it stretches to the chip's full width.
    assert ".st-chip .spark{align-self:flex-start}" in STORY_CSS


def test_css_and_condense_script():
    assert ".st-chip:hover .st-tip" in STORY_CSS
    assert "overflow:visible" in STORY_CSS.replace(" ", "")
    assert "@media" in STORY_CSS
    js = render_condense_script()
    assert "condensed" in js and js.count("<script>") == 1


def test_chip_stacking_rule():
    # KPI chip fields (value, label, sparkline, caption, tooltip) must stack
    # vertically instead of flowing on one line. Verify the stacking rule is
    # present in .st-chip by checking for flex-direction:column, which makes
    # direct children stack into a column. This is added to .st-chip which is
    # already a flex item; the new rule makes it also a flex container.
    assert "flex-direction:column" in STORY_CSS
    # Absolutely positioned .st-tip must stay out of flex flow and hidden until
    # hover/focus; verify its rules are still present and unchanged.
    assert ".st-chip:hover .st-tip" in STORY_CSS
    assert ".st-chip:focus .st-tip" in STORY_CSS


from gpu_agent.dashboard.story_render import (render_story_page,
                                              lint_story_copy)


def test_render_story_page_end_to_end(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert "The GPU shortage got worse this month." in html
    assert "the gap, this week" in html
    assert 'data-ev="kpi:gpuRentalOnDemand"' in html
    assert "What tightened" in html and "What would close the gap" in html
    assert "Related coverage" in html and "CNBC" in html
    assert html.count("Source: ") >= 2       # chart + at least one scene
    assert "Tomorrow" in html
    assert "Entities" in html and "Findings" in html
    assert 'id="ev-data"' in html and "window.openEV" in html
    assert "revision" in html.lower()


def test_page_passes_its_own_lint(tmp_path):
    assert lint_story_copy(render_story_page(_model(tmp_path))) == []


def test_render_story_page_links_sibling_stylesheet(tmp_path):
    # The page sits at site/<category>/index.html; its sibling appendix.html
    # correctly links style.css at depth 0. This page must too -- depth=1
    # emits "../style.css", which resolves to the wrong file (only masked
    # in the build because two identical copies of the stylesheet get
    # written).
    html = render_story_page(_model(tmp_path))
    assert 'href="style.css"' in html
    assert 'href="../style.css"' not in html


def _empty_model():
    return {"category_id": CAT, "as_of": None, "revision": 0,
            "headline": "The state of the GPU market.", "deck": "",
            "dateline": "Wednesday, July 22, 2026 · updated with each run",
            "gap": None, "callouts": [], "kpis": {"anchored": None, "picks": []},
            "evidence": {}, "scenes": [], "archive": [],
            "explore": {"entities": 0, "findings": 0, "series": 0, "history": 0}}


def test_kpi_band_suppressed_when_no_chips():
    assert _kpi_band(_empty_model()) == ""


def test_chart_block_says_so_plainly_when_no_gap_data():
    block = _chart_block(_empty_model())
    assert "<svg" not in block
    assert "Not enough" in block and "history" in block


def test_chart_block_span_carries_both_years_across_new_year():
    model = {"gap": {
        "months": [{"key": "2026-11", "label": "Nov"},
                   {"key": "2026-12", "label": "Dec"},
                   {"key": "2027-01", "label": "Jan"},
                   {"key": "2027-02", "label": "Feb"}],
        "demand": [100, 101, 102, 103], "supply": [100, 99, 98, 97],
        "gap_now": 6, "gap_prev": 4, "gap_word": "widened"}, "callouts": []}
    block = _chart_block(model)
    assert "Nov 2026" in block and "Feb 2027" in block
    assert "Nov–Feb 2027" not in block   # the mislabelling this fixes


def test_render_story_page_degrades_gracefully_with_no_chips_or_scenes():
    html = render_story_page(_empty_model())
    # No empty band-with-caption shell, no empty story section, no <svg>
    # chart -- and no crash.
    assert "says who?" not in html
    assert "The story, step by step" not in html
    assert "<svg" not in html
    assert "Not enough" in html
    assert lint_story_copy(html) == []


def test_lint_catches_banned_words_outside_scripts():
    bad = "<p>Demand momentum is strengthening.</p><script>var momentum=1;</script>"
    hits = lint_story_copy(bad)
    assert any("momentum" in h for h in hits)
    assert any("strengthening" in h for h in hits)
    assert lint_story_copy("<script>var momentum=1;</script>") == []


def test_lint_flags_bare_word_index_appearing_twice():
    # \bindexed?\b reads as "indexe" + optional "d", so it matches "indexed"
    # but never the bare word "index" -- the "index/indexed may appear once
    # at most" rule was only half-enforced. "index" twice must now trip it,
    # while a single occurrence is still fine.
    hits = lint_story_copy("<p>The index rose. Another index move today.</p>")
    assert any("index" in h for h in hits)
    assert lint_story_copy("<p>The index rose today.</p>") == []


def test_scene_first_paragraph_is_evidence_trigger(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert 'data-ev="scene:1"' in html


from gpu_agent.dashboard.story_render import _scene_html


def test_scene_related_link_rejects_non_http_scheme():
    # "httpjavascript://..." passes a naive str.startswith("http") check but
    # is not an http(s) URL at all — it must not become a clickable link.
    scene = {
        "n": 1, "accent": "amber", "title": "Test scene",
        "paragraphs": ["Some plain words making up the scene body text."],
        "visual": {"series": [], "label": ""},
        "source_line": "Source: test data",
        "related": [
            {"url": "httpjavascript://evil.example/x", "outlet": "Evil",
             "title": "Bad link", "date": "2026-01-01"},
        ],
    }
    html = _scene_html(scene)
    # Every candidate link fails the http/https check, so the row must not
    # render at all -- a dangling "Related coverage:" label with nothing
    # after it is dishonest, not just cosmetic.
    assert "Related coverage" not in html
    assert "<a href" not in html
    assert "evil.example" not in html


def test_panel_js_dim_contract():
    # F103 Task 2: the evidence-panel row renderer must dim aging rows and
    # always show a date (falling back to "undated"), keyed off a computed
    # weight the model now supplies per row.
    js = render_evidence_panel()
    assert "ev-aging" in js
    assert "undated" in js
    assert "f.weight" in js


def test_scene_related_aging_class(tmp_path):
    # F103 Task 2: a scene's "related coverage" links must carry a
    # server-side st-aging class when the row's computed weight decays
    # below AGING_THRESHOLD -- the CNBC row in the fixture (2026-06-10,
    # "news" kind, 42 days old by "today") is well past that threshold.
    from gpu_agent.freshness import AGING_THRESHOLD
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    demand_scene = next(s for s in m["scenes"] if s["title"] == "Demand kept climbing")
    cnbc_row = next(r for r in demand_scene["related"] if r["outlet"] == "CNBC")
    assert cnbc_row["weight"] < AGING_THRESHOLD
    html = _scene_html(demand_scene)
    assert 'class="st-aging"' in html
    assert "CNBC" in html


def test_lint_survives_script_containing_literal_closing_tag_text():
    # A script body that contains the literal text of a closing </script>
    # tag inside a JS string used to truncate the non-greedy strip early,
    # leaving the rest of the script scanned as if it were page prose.
    html = ("<script>var x='</script>'; var leverage=1;</script>"
            "<p>ok copy.</p>")
    assert lint_story_copy(html) == []


# ── F61: the honesty line under the dateline ────────────────────────────────

from gpu_agent.dashboard.story_render import _honesty_line, _human_date
from gpu_agent.dashboard.story_render import lint_story_copy as _lint


def _h(**kw):
    base = {"median": "2026-06-24", "oldest": "2026-05-28", "stale_pct": 31,
            "level": "high", "votes": 3}
    base.update(kw)
    return {"honesty": base}


def test_human_date_handles_every_grain():
    assert _human_date("2026-05-12") == "May 12, 2026"
    assert _human_date("2026-06") == "June 2026"
    assert _human_date("2026") == "2026"
    # Never raises, never invents: anything unparseable comes back untouched.
    assert _human_date("last spring") == "last spring"
    assert _human_date("2026-13-40") == "2026-13-40"
    assert _human_date("") == ""


def test_honesty_line_full_form():
    out = _honesty_line(_h())
    assert "How current this is" in out
    assert "typically dated June 24, 2026" in out
    assert "oldest piece is from May 28, 2026" in out
    assert "about 31 percent of it is more than six weeks old" in out
    assert "Confidence in today's reading is high" in out
    assert "how much 3 separate reads of the same evidence agreed" in out
    assert "not how fresh the evidence is" in out
    assert 'class="st-honest"' in out


def test_honesty_line_says_none_at_zero_stale_share():
    out = _honesty_line(_h(stale_pct=0))
    assert "none of it is more than six weeks old" in out
    assert "0 percent" not in out


def test_honesty_line_drops_vote_count_when_unknown():
    out = _honesty_line(_h(votes=None))
    assert "how much separate reads of the same evidence agreed" in out
    assert " 3 " not in out


def test_honesty_line_does_not_claim_the_reads_agreed():
    """The label is medium and low as often as high -- the sentence must say
    how much the reads agreed, never that they agreed."""
    for level in ("high", "medium", "low"):
        out = _honesty_line(_h(level=level))
        assert f"reading is {level} " in out
        assert "that agreed" not in out
        assert "reads agreeing" not in out


def test_honesty_line_each_half_stands_alone():
    vintage_only = _honesty_line(_h(level=None, votes=None))
    assert "How current this is" in vintage_only
    assert "Confidence" not in vintage_only
    conf_only = _honesty_line(_h(median=None, oldest=None, stale_pct=None))
    assert "Confidence in today's reading is high" in conf_only
    assert "six weeks" not in conf_only


def test_honesty_line_absent_renders_nothing():
    assert _honesty_line({"honesty": None}) == ""
    assert _honesty_line({}) == ""


def test_honesty_line_escapes_stored_values():
    out = _honesty_line(_h(level="<b>high</b>"))
    assert "<b>high</b>" not in out and "&lt;b&gt;high&lt;/b&gt;" in out


def test_honesty_line_passes_the_story_copy_lint():
    # The page's one "index/indexed" token is already spent by the gap chart's
    # axis label, so this line must not add another -- nor any banned word.
    assert _lint(_honesty_line(_h())) == []
    assert "index" not in _honesty_line(_h()).lower()


def test_headline_block_carries_the_honesty_line_under_the_dateline(tmp_path):
    m = _model(tmp_path)
    m["honesty"] = _h()["honesty"]
    h = _headline_block(m)
    assert 'class="st-honest"' in h
    assert h.index("st-date") < h.index("st-honest")
    assert h.rstrip().endswith("</header>")


def test_headline_block_unchanged_when_no_honesty(tmp_path):
    m = _model(tmp_path)
    with_key = _headline_block({**m, "honesty": None})
    m.pop("honesty", None)
    assert with_key == _headline_block(m)
    assert "st-honest" not in with_key


def test_story_page_with_honesty_line_still_passes_lint(tmp_path):
    m = _model(tmp_path)
    m["honesty"] = _h()["honesty"]
    html = render_story_page(m)
    assert lint_story_copy(html) == []
    assert "How current this is" in html
    assert ".st-honest" in STORY_CSS
