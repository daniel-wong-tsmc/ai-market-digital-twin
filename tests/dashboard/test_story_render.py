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
from gpu_agent.dashboard.story_render import (_chart_block, _headline_block,
                                              _kpi_band, STORY_CSS,
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


def test_lint_catches_banned_words_outside_scripts():
    bad = "<p>Demand momentum is strengthening.</p><script>var momentum=1;</script>"
    hits = lint_story_copy(bad)
    assert any("momentum" in h for h in hits)
    assert any("strengthening" in h for h in hits)
    assert lint_story_copy("<script>var momentum=1;</script>") == []


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
    assert "Related coverage" in html
    assert "<a href" not in html
    assert "evil.example" not in html


def test_lint_survives_script_containing_literal_closing_tag_text():
    # A script body that contains the literal text of a closing </script>
    # tag inside a JS string used to truncate the non-greedy strip early,
    # leaving the rest of the script scanned as if it were page prose.
    html = ("<script>var x='</script>'; var leverage=1;</script>"
            "<p>ok copy.</p>")
    assert lint_story_copy(html) == []
