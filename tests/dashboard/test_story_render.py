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
    # vbscript: and any other scheme do not produce a link at all.
    guarded = re.search(
        r"if\(d\.explore&&\("
        r"/\^https\?:/i\.test\(d\.explore\)\|\|"
        r"!/\^\[a-zA-Z\]\[a-zA-Z0-9\+\.\-\]\*:/\.test\(d\.explore\)"
        r"\)\)\{"
        r"var ex=el\('a','ev-explore','see everything we have →'\);\s*"
        r"ex\.href=encodeURI\(d\.explore\);",
        js,
    )
    assert guarded, "explore link href must be textually inside the scheme guard"
    assert js.count("ex.href=encodeURI(d.explore)") == 1

    # Belt-and-suspenders: the guard regex itself, applied in Python, must
    # accept relative paths and http(s) URLs and reject javascript:/data:/
    # vbscript: schemes. This mirrors (without executing) the JS logic.
    def guard_allows(value: str) -> bool:
        return bool(re.match(r"^https?:", value, re.I)) or not re.match(
            r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value
        )

    assert guard_allows("appendix.html")
    assert guard_allows("https://s.example/appendix.html")
    assert guard_allows("http://s.example/appendix.html")
    assert not guard_allows("javascript:alert(1)")
    assert not guard_allows("data:text/html,<script>alert(1)</script>")
    assert not guard_allows("vbscript:msgbox(1)")
