import re
from gpu_agent.dashboard.brief_render import (
    BRIEF_CSS, DASHBOARD_CSS, lint_exec_copy, lint_tile_labels, render_brief,
    _verdict, _kpi_cards, _chart, _dims_list)

MODEL = {
    "category_id": "chips.merchant-gpu", "category_label": "Merchant GPU",
    "month_label": "July 2026", "revision": 8, "narrative": "The <story>.",
    "brief_two": "The <story>. Second sentence.",
    "status": {"rating": "Strong", "direction": "steady",
               "reason": "Supply caps it.", "constraint": "HBM supply"},
    "attention": {"word": "elevated", "css": "elevated", "raw_word": "calm",
                  "lagging": True},
    "last_check": "2026-07-15", "stale": False,
    "agenda": [{"slot_label": "Demand durability", "metric_label": "D2",
                "display": "$75.2B", "trend_word": "rising",
                "as_of": "2026-07-01", "source": "NVIDIA IR", "was": None,
                "delta_line": ""},
               {"slot_label": "Binding constraint", "metric_label": "S10",
                "display": "2027 sold out", "trend_word": "tightening",
                "as_of": "2026-07-10", "source": "TrendForce", "was": "S9",
                "delta_line": ""},
               {"slot_label": "Customer mix", "metric_label": "m",
                "display": "44.6%", "trend_word": "shifting",
                "as_of": "2026-07-02", "source": "s", "was": None,
                "delta_line": ""}],
    "tsmc": [{"text": "Wafer starts exposure.", "dims": ["momentum"],
              "thesis_ids": [], "finding_ids": ["f1"]}],
    "calls": {"rows": [{"title": "HBM binds supply", "lens": "supply",
                        "conviction": "high", "verdict": "strengthened",
                        "glyph": "▲", "streak": 1, "trigger": "gap re-widens"}],
              "total": 23, "provisional": 9},
    "strip": [{"date": "2026-07-14", "text": "CoWoS keeps narrowing.",
               "source": "TrendForce"}],
    "dimensions": [{"name": "momentum", "rating": "Very strong",
                    "direction": "improving", "confidence": "high",
                    "sentence": "Revenue set a record.", "capped": False}],
    "evidence": {"n": 86, "median": "2026-07-02", "oldest": "2026-06-12",
                 "primary": 2},
    "counterweights": {},
    "chart": {"labels": ["a", "b"], "demand": [1.0, 2.0], "supply": [-0.1, 0.1]},
}


def test_render_brief_contains_all_blocks_in_order():
    html = render_brief(MODEL)
    order = [html.index("Executive Brief"),               # masthead
             html.index("Strong / steady"),               # verdict rating-label
             html.index("Demand durability"),              # KPI card slot label
             html.index("Demand vs supply momentum"),      # chart caption
             html.index("Six dimensions"),                 # new dims list header
             html.index("signal checks")]                  # footer wording
    assert order == sorted(order)


def test_render_brief_escapes_and_details():
    html = render_brief(MODEL)
    assert "The &lt;story&gt;." in html
    assert "steps down after two calm days; today's raw read was calm" in html
    assert 'class="chip status-elevated"' in html
    assert 'id="dd-drawer"' in html
    assert 'id="dd-data"' in html


def test_status_classes_only_on_chip_and_stale_strip():
    html = render_brief(dict(MODEL, stale=True))
    hits = re.findall(r'class="([^"]*status-[a-z]+[^"]*)"', html)
    assert hits and all(("chip" in h) or ("stalestrip" in h) for h in hits)


def test_agenda_band_omitted_below_three():
    m = dict(MODEL, agenda=MODEL["agenda"][:2])
    assert "Demand durability" not in render_brief(m)


def test_lint_exec_copy_catches_banned_tokens():
    assert lint_exec_copy("x +15 more moved y")
    assert lint_exec_copy("because no alert rule fired")
    assert lint_exec_copy("since the prior run")
    assert lint_exec_copy("per F65 rules")
    assert lint_exec_copy("1.6 trillion internal settings")
    assert lint_exec_copy(render_brief(MODEL)) == []


def test_brief_css_defines_status_and_tiles():
    for cls in ("status-calm", "status-watch", "status-elevated",
                "status-critical", ".kpis", ".hero"):
        assert cls in BRIEF_CSS


def test_render_brief_escapes_category_label_uppercase_ordering():
    html = render_brief(dict(MODEL, category_label="A&B"))
    assert "A&amp;B" in html          # escaped correctly AFTER uppercasing
    assert "&AMP;" not in html        # not the escape-then-uppercase garble


def test_render_brief_omits_empty_optional_blocks():
    m = dict(MODEL, tsmc=[], strip=[],
             calls={"rows": [], "total": 0, "provisional": 0})
    html = render_brief(m)
    assert "<h2>What this means for TSMC</h2>" not in html   # now always true (folded away)
    assert "Latest signal" not in html              # empty strip omitted
    assert 'id="dd-drawer"' in html                 # panel present even when optional blocks are empty


def test_agenda_and_dimension_tiles_disjoint():
    # C tiles are metric labels; G tiles are the six dimension names.
    dims = {"momentum", "unitEconomics", "bottleneck", "competitiveStructure",
            "moat", "strategicRisk"}
    for o in MODEL["agenda"]:
        assert o["metric_label"] not in dims


def test_kpi_card_renders_trend_delta():
    m = dict(MODEL)
    m["agenda"] = [dict(MODEL["agenda"][0], trend_word="surging")] + \
        MODEL["agenda"][1:]
    assert "surging" in render_brief(m)


def test_lint_tile_labels_flags_raw_codes():
    assert lint_tile_labels({"agenda": [{"metric_label": "D2"}]})
    assert lint_tile_labels({"agenda": [{"metric_label": "DC revenue structure"}]}) == []


def test_dashboard_css_covers_core_classes():
    for sel in [".kcard", ".dd-drawer", ".dd-scrim", ".dimrow", ".ddchart", ".brief-two"]:
        assert sel in DASHBOARD_CSS


def test_verdict_uses_two_sentence_and_rating():
    m = {"status": {"rating": "Strong", "direction": "improving"}, "brief_two": "One. Two."}
    h = _verdict(m)
    assert "Strong" in h and "One. Two." in h and "brief-two" in h


def test_kpi_cards_clickable_to_dimension():
    card = {"slot_label": "Binding constraint", "metric_label": "Lead times",
            "display": "40 wk", "trend_word": "rising", "as_of": "2026-07-16",
            "source": "TechTimes", "was": "", "delta_line": ""}
    m = {"agenda": [card] * 3}
    h = _kpi_cards(m)
    assert "openDD('bottleneck')" in h and "40 wk" in h and "Lead times" in h


def test_chart_draws_two_polylines():
    m = {"chart": {"labels": ["a", "b"], "demand": [1.0, 2.0], "supply": [-0.1, 0.1]}}
    h = _chart(m)
    assert h.count("<polyline") >= 2 and "ddchart" in h


def test_dims_list_rows_clickable():
    m = {"dimensions": [{"name": "bottleneck", "rating": "Weak", "direction": "improving",
                         "confidence": "medium", "sentence": "s", "capped": True}]}
    h = _dims_list(m)
    assert "openDD('bottleneck')" in h and "Weak" in h


def _model():
    return {
      "category_label": "Merchant GPU", "month_label": "July 2026", "revision": 12,
      "last_check": "2026-07-20", "stale": False,
      "attention": {"word": "elevated", "css": "elevated", "raw_word": "elevated", "lagging": False},
      "status": {"rating": "Strong", "direction": "improving", "reason": "r.", "constraint": ""},
      "brief_two": "One. Two.",
      "agenda": [{"slot_label": "Binding constraint", "metric_label": "Lead times",
                  "display": "40 wk", "trend_word": "rising", "as_of": "2026-07-16",
                  "source": "TechTimes", "was": "", "delta_line": ""}] * 3,
      "chart": {"labels": ["a", "b"], "demand": [1.0, 2.0], "supply": [-0.1, 0.1]},
      "dimensions": [{"name": "bottleneck", "rating": "Weak", "direction": "improving",
                      "confidence": "medium", "sentence": "s", "capped": True}],
      "strip": [], "tsmc": [], "calls": {"rows": [], "total": 0, "provisional": 0},
      "evidence": {"n": 1, "median": "2026-07-01", "oldest": "2026-06-01", "primary": 1},
      "deepdive": {"bottleneck": {"eyebrow": "Dimension", "title": "bottleneck — Weak, improving",
                   "badges": [], "why": "w", "trend": [0, 2], "trend_good": True,
                   "evidence": [], "confidence": "3/3 Weak", "change": "x", "tsmc": [], "calls": []}},
    }


def test_render_brief_dashboard_shape():
    h = render_brief(_model())
    assert 'id="dd-data"' in h and 'id="dd-drawer"' in h        # panel wired
    assert "kcards" in h and "ddchart" in h and "dimlist" in h  # new sections
    assert "<h2>What this means for TSMC</h2>" not in h         # folded away
    assert "<h2>Standing calls</h2>" not in h                   # folded away
    assert '"bottleneck"' in h                                  # payload embedded
