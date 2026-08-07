"""F114 Task 5 regression pin: the MECHANICAL bullet path must never drift.

F114 makes the dashboard prefer the narrator's own bullets when the story
artifact carries them. The old mechanical condenser (scene title + first
sentence, plus its chart matching) stays on as the fallback for pre-F114
artifacts and for days the narrator fell back.

This file freezes today's mechanical output for the 2026-08-05 story
fixture, byte for byte, BEFORE the preference switch is implemented. If a
later change to `build_bullets` alters what the fallback produces -- text,
sources, charts, or no-chart wording -- these tests go red.

Both cases are hermetic: the series directory is built by the test, never
read from the live `store/series/` tree (which changes every cycle), so the
golden depends only on the two committed fixtures.
"""
import json
from pathlib import Path

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.bullets import build_bullets

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
GOLDEN = json.loads(
    Path("fixtures/dashboard/golden-bullets-mechanical.json").read_text(encoding="utf-8"))


def _row(indicator_id, period, value, *, unit="USD", estimate_grade=False,
         url="https://example.test/src", title="Example source"):
    return {
        "indicatorId": indicator_id, "period": period, "value": value, "unit": unit,
        "publishedAt": f"{period}-15", "capturedAt": "2026-08-05",
        "source": {"url": url, "title": title},
        "estimateGrade": estimate_grade,
        "note": "golden pin row",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _curated_registry() -> dict[str, ChartSeries]:
    """One curated series whose topicTags hit scene 1's 'amd' tag."""
    return {
        "amdDataCenterRevenue": ChartSeries(
            id="amdDataCenterRevenue", name="AMD data centre revenue",
            sourceName="AMD Investor Relations",
            sourceUrl="https://ir.amd.com/",
            cadence="quarterly", quality="hard-fact", topicTags=("amd",),
            form="columns", unit="US$ billions", fetcher=None,
        ),
    }


def _populated_series_dir(tmp_path: Path) -> Path:
    """A deterministic series tree that exercises all three chart outcomes
    against the real fixture story: bullet 1 gets a curated chart, bullet 2
    gets the rule-3 fallback chart (scene 2's own visual names
    hyperscalerCapexRevision, and here that series has a plain 'USD' unit),
    bullet 3 gets an honest no-chart reason."""
    _write_jsonl(tmp_path / "amdDataCenterRevenue.jsonl",
                 [_row("amdDataCenterRevenue", f"2025-{m:02d}", 1.0 + m, unit="USD_B")
                  for m in range(1, 9)])
    _write_jsonl(tmp_path / "hyperscalerCapexRevision.jsonl",
                 [_row("hyperscalerCapexRevision", f"2025-{m:02d}", float(m))
                  for m in range(1, 9)])
    return tmp_path


def test_mechanical_bullets_golden_with_no_series_data_on_disk(tmp_path):
    """Nothing chartable anywhere: pins the text, sources, storyHref and the
    exact honest no-chart wording for all three bullets."""
    bullets = build_bullets(STORY, SCORECARD, {}, str(tmp_path))
    assert bullets == GOLDEN["noSeriesData"]


def test_mechanical_bullets_golden_with_curated_and_fallback_charts(tmp_path):
    """Pins the chart-matching half of the mechanical path: curated series
    match, rule-3 fallback match, and the no-chart reason, all on the same
    real fixture story."""
    series_dir = _populated_series_dir(tmp_path)
    bullets = build_bullets(STORY, SCORECARD, _curated_registry(), str(series_dir))
    assert bullets == GOLDEN["withSeriesData"]


def test_golden_covers_all_three_chart_outcomes():
    """Guards the pin itself: if a future edit quietly flattened the golden
    so every bullet fell to a no-chart reason, the two tests above would
    still pass while covering almost nothing."""
    charted = GOLDEN["withSeriesData"]
    assert charted[0]["chart"] is not None and charted[0]["chart"]["source"].get("assessment") is None
    assert charted[1]["chart"] is not None and charted[1]["chart"]["source"]["assessment"] is True
    assert charted[2]["chart"] is None and charted[2]["noChartReason"] is not None
    assert all(b["chart"] is None for b in GOLDEN["noSeriesData"])
