import re

from gpu_agent.dashboard.site_model import build_site_model
from gpu_agent.dashboard.site_render import (
    DISCLAIMER, HOW_LINKS, SITE_CSS, page, render_category_page,
    render_index_redirect,
)
from gpu_agent.reader import lint_acronyms

FIX = "tests/dashboard/fixtures"
CAT = "chips.merchant-gpu"


def _model():
    return build_site_model(CAT, FIX, work_dir="work-nonexistent",
                            plain_path=f"{FIX}/plain-2026-07-06.json",
                            price_fn=lambda d: {"H100": 2.31})


def _text_above_appendix(html):
    cut = html.split('id="appendix-links"')[0]
    return re.sub(r"<[^>]+>", " ", cut)


def test_category_page_structure_and_links():
    html = render_category_page(_model())
    assert html.startswith("<!doctype html>")
    for href in HOW_LINKS.values():
        assert f'href="{href}"' in html
    assert 'id="appendix-links"' in html
    assert "Why it reads this way" in html
    assert "MERCHANT GPU" in html
    assert "2026-07-06" in html


def test_featured_tile_renders_value_and_reason_link():
    html = render_category_page(_model())
    assert "$2.31/GPU-hr" in html
    assert 'href="how/featured.html"' in html


def test_no_featured_drops_tile_and_link():
    m = _model()
    m["featured"] = None
    m["why"] = [w for w in m["why"] if w["topic"] != "featured"]
    html = render_category_page(m)
    assert 'href="how/featured.html"' not in html


def test_implication_section_conditional():
    m = _model()
    assert "For TSMC" not in render_category_page(m)
    m["implication"] = {"lines": ["Watch CoWoS allocation notes."]}
    html = render_category_page(m)
    assert "For TSMC" in html and "Watch CoWoS allocation notes." in html


def test_above_fold_text_passes_acronym_lint_and_no_slop():
    html = render_category_page(_model())
    text = _text_above_appendix(html)
    assert lint_acronyms(text) == []
    for slop in ("delve", "leverage", "seamless", "tapestry"):
        assert slop not in text.lower()


def test_render_is_deterministic_and_clockless():
    m = _model()
    assert render_category_page(m) == render_category_page(m)
    import gpu_agent.dashboard.site_render as sr
    import inspect
    src = inspect.getsource(sr)
    assert "datetime.now" not in src and "date.today" not in src


def test_index_redirect_points_at_category():
    html = render_index_redirect("chips.merchant-gpu/index.html", "Merchant GPU")
    assert 'http-equiv="refresh"' in html and "chips.merchant-gpu/index.html" in html


def test_populated_calls_render_top5_names_oneliners_and_breaks_if(tmp_path):
    # Every other test uses work_dir="work-nonexistent" (calls=[]); this one pins the
    # populated branch of _calls(): the top-5 cap, real call names (the `name` key from
    # parse_calls), the one-liner rest list, and a breaks-if line.
    work = tmp_path / "work" / "daily-2026-07-06"
    work.mkdir(parents=True)
    with open(f"{FIX}/report-2026-07-06.txt", encoding="utf-8", errors="replace") as fh:
        (work / "report.txt").write_text(fh.read(), encoding="utf-8")
    m = build_site_model(CAT, FIX, work_dir=str(tmp_path / "work"),
                         plain_path=f"{FIX}/plain-2026-07-06.json",
                         price_fn=lambda d: {"H100": 2.31})
    html = render_category_page(m)
    assert "The top calls (5 of 14)" in html      # fixture report carries 14 calls
    assert "NVDA demand durability" in html       # a known call name from the fixture
    assert 'class="callmore"' in html             # calls 6..14 render as one-liners
    assert "breaks if:" in html


from gpu_agent.dashboard.site_render import (
    render_appendix, render_how_alert, render_how_featured, render_how_tile,
)


def test_how_alert_names_the_ladder_and_todays_state():
    m = _model()
    html = render_how_alert(m)
    for word in ("GREEN", "YELLOW", "ORANGE", "RED"):
        assert word in html
    assert m["alert"]["color"].upper() in html
    assert 'href="../style.css"' in html


def test_how_demand_shows_weights_findings_and_evidence_links():
    m = _model()
    html = render_how_tile(m, "demand")
    rows = [r for r in m["contributions"] if r["demand_contribution"] != 0]
    assert rows, "fixture must have demand-side rows"
    top = rows[0]
    assert top["label"] in html
    assert f'{top["weight"]:g}' in html
    assert "<details>" in html
    ev_urls = [e["url"] for r in rows for e in r["evidence"] if e["url"]]
    if ev_urls:
        assert f'href="{ev_urls[0]}"' in html


def test_how_demand_states_the_rows_total_and_why_it_can_differ():
    # F95 item 1 (label honestly): the drill-down rows must state their own total in
    # plain language, distinct from the blended headline score, and say why they differ.
    m = _model()
    total = sum(r["demand_contribution"] for r in m["contributions"])
    html = render_how_tile(m, "demand")
    assert f"{total:+.3f}" in html
    assert "The tile above blends this with longer-horizon signals" in html


def test_contrib_table_drops_non_http_scheme_links():
    from gpu_agent.dashboard.site_render import _contrib_table
    rows = [{
        "label": "Synthetic indicator", "entity": "nvidia", "statement": "a statement",
        "weight": 0.1, "magnitude": 2, "demand_contribution": 0.05,
        "supply_contribution": 0.0,
        "evidence": [
            {"source": "Evil Source", "url": "javascript:alert(1)",
             "date": "2026-07-01", "tier": "secondary"},
            {"source": "Good Source", "url": "https://example.com/report",
             "date": "2026-07-01", "tier": "primary"},
            {"source": "No URL Source", "url": "", "date": "2026-07-01", "tier": "secondary"},
        ],
    }]
    html = _contrib_table(rows, "demand_contribution")
    assert "javascript:alert(1)" not in html
    assert 'href="https://example.com/report">link</a>' in html
    assert "Evil Source" in html and "No URL Source" in html


def test_how_gap_shows_the_equation_and_cross_links():
    m = _model()
    html = render_how_tile(m, "gap")
    ds = m["demand_supply"]
    assert f'{ds["sdgi"]:+.2f}' in html
    assert 'href="demand.html"' in html and 'href="supply.html"' in html


def test_how_featured_shows_selection_trace():
    m = _model()
    html = render_how_featured(m)
    assert m["featured"]["reason_text"] in html
    assert m["featured"]["display"] in html


def test_appendix_has_raw_scores_findings_and_runs():
    m = _model()
    html = render_appendix(m)
    assert "Raw scores" in html
    for d in m["trend"]["dates"]:
        assert d in html
    assert str(len(m["runs"])) in html or m["runs"][0]["date"] in html


# --- F124: the standing independence disclaimer -----------------------------
# docs/publishing-posture.md section 4, decided with the user 2026-08-22. The
# wording is APPROVED VERBATIM, so these tests pin it character for character:
# a reword is a copy change and needs the user, not a test edit.

APPROVED_DISCLAIMER = (
    "Independent personal project. The analysis here is one individual's own "
    "work, produced from public sources. It is not affiliated with, endorsed "
    "by, or representative of any employer, and it is not investment advice."
)


def test_disclaimer_is_the_approved_wording_character_for_character():
    assert DISCLAIMER == APPROVED_DISCLAIMER


def test_every_shell_page_carries_the_disclaimer_in_its_footer():
    html = page("Any page", "<p>body</p>")
    assert '<footer class="disclaimer">' in html
    assert APPROVED_DISCLAIMER in html
    # In the footer -- last thing in the body, not floating in the head.
    assert html.index('<footer class="disclaimer">') > html.index("<body>")
    assert html.index(APPROVED_DISCLAIMER) < html.index("</body>")


def test_the_disclaimer_is_styled_rather_than_left_as_bare_text():
    assert ".disclaimer" in SITE_CSS


# --- F137: the alert-rule featured reason is reachable again ---------------------------
#
# Before F137 the only two rules tagged in registry/featured-metrics.json were
# `gap-band-changed` and `demand-reversal`, and both were structurally unable to fire
# (see tests/test_change_alert_saturation.py). So select_featured's "alert-rule" branch
# was dead code and the sentence below had never once been printed on the public page.
# These tests drive the whole chain — alert state -> featured selection -> rendered HTML —
# to prove it now renders.

_ALERT_REASON = "Shown because it tracks what set off today's alert."


def _model_with_alert(monkeypatch, color, triggers, sizes):
    from gpu_agent import change as change_mod

    def _stub(store_dir, sc, book=None):
        return change_mod.AlertState(color=color, priorColor="green", rawColor=color,
                                     triggers=list(triggers), triggerSizes=dict(sizes))

    monkeypatch.setattr(change_mod, "alert_state", _stub)
    return _model()


def test_a_fired_gap_rule_makes_the_gap_the_featured_number(monkeypatch):
    m = _model_with_alert(monkeypatch, "yellow", ["gap-moved-sharply"],
                          {"gap-moved-sharply": "0.55, about 1.7 times its usual "
                                                "run-to-run move"})
    assert m["featured"]["metric_id"] == "gap-score"
    assert m["featured"]["reason_code"] == "alert-rule"
    assert m["featured"]["reason_text"] == _ALERT_REASON


def test_the_alert_rule_reason_actually_renders_on_the_page(monkeypatch):
    m = _model_with_alert(monkeypatch, "yellow", ["gap-moved-sharply"],
                          {"gap-moved-sharply": "0.55, about 1.7 times its usual "
                                                "run-to-run move"})
    # the renderer HTML-escapes the apostrophe in "today's", so match the stable prefix
    assert "Shown because it tracks what set off today" in render_how_featured(m)


def test_the_alert_page_says_the_new_rule_in_plain_words_with_its_size(monkeypatch):
    m = _model_with_alert(monkeypatch, "yellow", ["gap-moved-sharply"],
                          {"gap-moved-sharply": "0.55, about 1.7 times its usual "
                                                "run-to-run move"})
    html = render_how_alert(m)
    assert "the demand-vs-supply gap moved much more than it usually does" in html
    assert "0.55, about 1.7 times its usual run-to-run move" in html
    assert "gap band" not in html


def test_a_fired_demand_reversal_features_demand_and_reads_plainly(monkeypatch):
    m = _model_with_alert(monkeypatch, "orange", ["demand-reversal"],
                          {"demand-reversal": "demand fell 0.57, about 2.4 times its "
                                              "usual run-to-run move"})
    assert m["featured"]["metric_id"] == "demand-momentum"
    assert m["featured"]["reason_code"] == "alert-rule"
    html = render_how_alert(m)
    assert "buyers pulled back sharply while the shortage eased at the same time" in html
    assert "demand fell 0.57" in html


def test_the_why_line_carries_the_new_wording(monkeypatch):
    m = _model_with_alert(monkeypatch, "yellow", ["gap-moved-sharply"],
                          {"gap-moved-sharply": "0.55, about 1.7 times its usual "
                                                "run-to-run move"})
    why = next(w for w in m["why"] if w["topic"] == "alert")
    assert "moved much more than it usually does" in why["text"]
    assert "1.7 times its usual run-to-run move" in why["text"]


def test_the_alert_ladder_explainer_no_longer_mentions_bands(monkeypatch):
    m = _model_with_alert(monkeypatch, "green", [], {})
    html = render_how_alert(m)
    assert "gap band" not in html and "toward glut" not in html
    assert "moved much more than it usually does" in html
