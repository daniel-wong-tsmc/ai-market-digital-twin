import datetime as dt
import json, os
from gpu_agent.dashboard.build import build_dashboard
from gpu_agent.dashboard.site_build import build_site

FIX = "tests/dashboard/fixtures"

def test_end_to_end_writes_html_and_summary(tmp_path):
    # Arrange a mini work dir containing the fixture report.
    work = tmp_path / "work" / "daily-2026-07-06"
    work.mkdir(parents=True)
    with open(f"{FIX}/report-2026-07-06.txt", encoding="utf-8", errors="replace") as fh:
        (work / "report.txt").write_text(fh.read(), encoding="utf-8")
    out = tmp_path / "dashboard.html"
    summary = build_dashboard(
        category_id="chips.merchant-gpu", store_dir=FIX,
        work_dir=str(tmp_path / "work"), plain_path=f"{FIX}/plain-2026-07-06.json",
        out_path=str(out), generated_at="2026-07-06 09:20")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert 'id="calls"' in html and 'id="top-signals"' in html
    assert summary["runs"] == 4
    assert summary["claims"] == 14
    assert summary["auto_simplified"] >= 1   # most sentences have no fixture rewrite

def test_generated_html_has_no_slop_or_raw_cowos(tmp_path):
    work = tmp_path / "work" / "daily-2026-07-06"
    work.mkdir(parents=True)
    with open(f"{FIX}/report-2026-07-06.txt", encoding="utf-8", errors="replace") as fh:
        (work / "report.txt").write_text(fh.read(), encoding="utf-8")
    out = tmp_path / "dashboard.html"
    build_dashboard(category_id="chips.merchant-gpu", store_dir=FIX,
                    work_dir=str(tmp_path / "work"), plain_path=f"{FIX}/plain-2026-07-06.json",
                    out_path=str(out), generated_at="2026-07-06 09:20")
    html = out.read_text(encoding="utf-8")
    for w in ["delve", "leverage", "seamless", "boasts"]:
        assert w not in html.lower()
    # Scope to the "Key claims" section (which contains the breaks_if expanders);
    # the Plain-language guide table intentionally lists raw terms like "CoWoS".
    calls_html = html[html.index('id="calls"'):html.index('id="demand-supply"')]
    assert "CoWoS" not in calls_html                      # breaks_if jargon must be term-swapped
    assert "advanced chip packaging" in calls_html        # proof it was swapped in place

def test_build_model_change_parity_sees_fixture_history(tmp_path):
    # F78 Task 11 review fix: store-root detection must honor BOTH layouts. FIX is the
    # dashboard's flat category dir AND (via the chips.merchant-gpu/ scorecard copies
    # added alongside) a change-engine store root; with 4 real day-grain runs the change
    # engine must SEE that history — never report a false first run (alert prior None /
    # every horizon "no run yet"), which is what naive parent-derivation produced here.
    from gpu_agent.dashboard.build import build_model
    work = tmp_path / "work" / "daily-2026-07-06"
    work.mkdir(parents=True)
    with open(f"{FIX}/report-2026-07-06.txt", encoding="utf-8", errors="replace") as fh:
        (work / "report.txt").write_text(fh.read(), encoding="utf-8")
    m, _ = build_model("chips.merchant-gpu", FIX, str(tmp_path / "work"),
                       f"{FIX}/plain-2026-07-06.json", "2026-07-06 09:20")
    assert m["alert"]["prior"] is not None                # 4 runs of history -> a prior color
    assert any("no run yet" not in w["text"] for w in m["what_changed"])

def test_e2e_index_has_panel_and_no_folded_headers(tmp_path):
    # F100 Task 12, retargeted per Task 8 Decision A item 1: the category
    # index.html is now the F101 story page (built via build_site, mirroring
    # test_site_build.py's _build helper), not the executive brief -- the old
    # deep-dive drawer ("dd-drawer") is by design no longer on index.html. This
    # keeps the test's original intent: the index page carries a working
    # evidence panel (the story page's own equivalent: the "ev-panel" shell and
    # its "ev-data" JSON blob) and does not carry the folded headers it was
    # written to forbid ("Standing calls" was the brief's folded section; the
    # story page must not regress into showing it either).
    # F110 Task 12 retarget: the category index.html is now the compiled
    # dashboard app -- a committed build input the Python builder leaves alone.
    # The evidence panel this test guards still ships on the story page
    # build_site assembles (and, through the same renderer, on every story
    # permalink), so assert against that page rather than a file build_site no
    # longer writes. See tests/dashboard/test_site_build.py::story_front_html.
    from tests.dashboard.test_site_build import story_front_html

    build_site("chips.merchant-gpu", FIX, work_dir="work-nonexistent",
               plain_path=f"{FIX}/plain-2026-07-06.json",
               out_dir=str(tmp_path / "site"), price_fn=lambda d: {"H100": 2.31})
    html = story_front_html(FIX)
    assert 'id="ev-data"' in html
    assert "window.openEV" in html and "ev-panel" in html
    assert "<h2>Standing calls</h2>" not in html
