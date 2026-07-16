import re
from gpu_agent.dashboard.brief_render import BRIEF_CSS, lint_exec_copy, render_brief

MODEL = {
    "category_id": "chips.merchant-gpu", "category_label": "Merchant GPU",
    "month_label": "July 2026", "revision": 8, "narrative": "The <story>.",
    "status": {"rating": "Strong", "direction": "steady",
               "reason": "Supply caps it.", "constraint": "HBM supply"},
    "attention": {"word": "elevated", "css": "elevated", "raw_word": "calm",
                  "lagging": True},
    "last_check": "2026-07-15", "stale": False,
    "agenda": [{"slot_label": "Demand durability", "metric_label": "D2",
                "display": "$75.2B", "trend_word": "rising",
                "as_of": "2026-07-01", "source": "NVIDIA IR", "was": None},
               {"slot_label": "Binding constraint", "metric_label": "S10",
                "display": "2027 sold out", "trend_word": "tightening",
                "as_of": "2026-07-10", "source": "TrendForce", "was": "S9"},
               {"slot_label": "Customer mix", "metric_label": "m",
                "display": "44.6%", "trend_word": "shifting",
                "as_of": "2026-07-02", "source": "s", "was": None}],
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
}


def test_render_brief_contains_all_blocks_in_order():
    html = render_brief(MODEL)
    order = [html.index("Executive Brief"),            # A
             html.index("Strong / steady"),            # B hero
             html.index("Demand durability"),          # C
             html.index("What this means for TSMC"),   # D
             html.index("Standing calls"),              # E
             html.index("Latest signal"),               # F
             html.index("The six dimensions"),          # G
             html.index("signal checks")]               # H footer wording
    assert order == sorted(order)


def test_render_brief_escapes_and_details():
    html = render_brief(MODEL)
    assert "The &lt;story&gt;." in html
    assert "(was: S9)" in html                          # continuity note
    assert "strengthened ▲" in html or "▲ strengthened" in html
    assert "All 23 calls, including 9 provisional" in html
    assert "steps down after two calm days; today's raw read was calm" in html
    assert 'class="chip status-elevated"' in html


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
