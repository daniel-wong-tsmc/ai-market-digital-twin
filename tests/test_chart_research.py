"""tests/test_chart_research.py -- F113 Task 3: candidate model + researcher
prompt + emit.

Deterministic, network-free. `emit_research` is exercised against small
synthetic store/story fixtures written to `tmp_path` (same shape the real
`store/<cat>/` tree uses), not the real registry/store data -- so these
tests never depend on, or drift with, the live curated chart-series
registry or any real cycle's findings.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gpu_agent.chartdata.research import CandidatePoint, CandidateSeries, emit_research
from gpu_agent.chartdata.research_prompt import build_research_prompt
from gpu_agent.cli import main


# ---------------------------------------------------------------------------
# CandidateSeries / CandidatePoint model
# ---------------------------------------------------------------------------

def _point(label="Q1", value=1.0, url="https://example.test/a", published="2026-08-01"):
    return CandidatePoint(label=label, value=value, sourceUrl=url, publishedAt=published)


def test_candidate_point_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CandidatePoint(label="Q1", value=1.0, sourceUrl="https://example.test/a",
                        publishedAt="2026-08-01", extraField="nope")


def test_candidate_series_accepts_three_points():
    series = CandidateSeries(
        seriesName="Widget demand", unit="units", form="line",
        sourceName="Example Outlet",
        points=[_point("Q1"), _point("Q2"), _point("Q3")],
    )
    assert len(series.points) == 3
    assert series.pair is False
    assert series.bulletIndex is None


def test_candidate_series_rejects_two_points_when_not_pair():
    with pytest.raises(ValidationError):
        CandidateSeries(
            seriesName="Widget demand", unit="units", form="line",
            sourceName="Example Outlet",
            points=[_point("Q1"), _point("Q2")],
            pair=False,
        )


def test_candidate_series_allows_two_points_when_pair():
    series = CandidateSeries(
        seriesName="Supply vs demand", unit="units", form="bars",
        sourceName="Example Outlet",
        points=[_point("Supply"), _point("Demand")],
        pair=True,
    )
    assert len(series.points) == 2


def test_candidate_series_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CandidateSeries(
            seriesName="Widget demand", unit="units", form="line",
            sourceName="Example Outlet",
            points=[_point("Q1"), _point("Q2"), _point("Q3")],
            somethingElse=True,
        )


def test_candidate_series_bulletIndex_settable_and_forbid_still_holds():
    # Task 5 dependency: bulletIndex exists on the model NOW so the
    # verifier (Task 4) can stamp it onto the quarantine record without
    # ever needing extra="forbid" relaxed.
    series = CandidateSeries(
        seriesName="Widget demand", unit="units", form="line",
        sourceName="Example Outlet",
        points=[_point("Q1"), _point("Q2"), _point("Q3")],
        bulletIndex=2,
    )
    assert series.bulletIndex == 2


# ---------------------------------------------------------------------------
# build_research_prompt
# ---------------------------------------------------------------------------

def test_prompt_carries_bullet_text_and_finding_url():
    bullet = {"text": "AMD delivered a record quarter on GPU demand."}
    findings = [{"statement": "AMD reported record data-center revenue.",
                 "url": "https://example.test/amd-q2"}]
    prompt = build_research_prompt(bullet, findings)
    assert "AMD delivered a record quarter on GPU demand." in prompt
    assert "https://example.test/amd-q2" in prompt
    assert "published" in prompt.lower()
    assert "NO-SERIES-FOUND" in prompt


def test_prompt_states_rules_even_with_no_findings():
    bullet = {"text": "Some bullet with no findings attached."}
    prompt = build_research_prompt(bullet, [])
    assert "Some bullet with no findings attached." in prompt
    assert "NO-SERIES-FOUND" in prompt
    assert "published" in prompt.lower()


# ---------------------------------------------------------------------------
# emit_research -- fixture store/story trees
# ---------------------------------------------------------------------------

def _write_scorecard(store_root: Path, category_id: str, findings: list[dict]) -> None:
    cat_dir = store_root / category_id
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "2026-08-v1.json").write_text(
        json.dumps({"findings": findings}), encoding="utf-8")


def _write_story(store_root: Path, category_id: str, story: dict) -> None:
    story_dir = store_root / category_id / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / f"{story['storyDate']}.json").write_text(
        json.dumps(story), encoding="utf-8")


def _finding(fid, indicator_id=None, entity=None, url="https://example.test/e",
             statement="Example outlet reported a specific number here."):
    f = {"id": fid, "statement": statement,
         "evidence": [{"source": "Example outlet", "url": url,
                       "date": "2026-08-01", "tier": "primary"}]}
    if indicator_id:
        f["indicatorId"] = indicator_id
    if entity:
        f["entity"] = entity
    return f


def _write_indicator_rows(store_root: Path, indicator_id: str) -> None:
    series_dir = store_root / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for month, val in (("2026-05", 10.0), ("2026-06", 11.0), ("2026-07", 12.0),
                        ("2026-08", 13.0), ("2026-08", 14.0), ("2026-08", 15.0)):
        rows.append({
            "indicatorId": indicator_id, "period": month, "value": val, "unit": "USD_B",
            "publishedAt": f"{month}-15", "capturedAt": "2026-08-05",
            "source": {"url": "https://example.test/src", "title": "Example source"},
            "estimateGrade": False,
        })
    series_dir.joinpath(f"{indicator_id}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_emit_writes_one_prompt_per_chartless_bullet(tmp_path):
    store_root = tmp_path / "store"
    category_id = "chips.test-category"
    findings = [
        _finding("f1", url="https://example.test/f1"),
        _finding("f2", url="https://example.test/f2"),
        _finding("f3", url="https://example.test/f3"),
    ]
    _write_scorecard(store_root, category_id, findings)
    story = {
        "storyDate": "2026-08-06",
        "scenes": [],
        "bullets": [
            {"text": "Bullet one about topic A.", "claimFindingIds": ["f1"]},
            {"text": "Bullet two about topic B.", "claimFindingIds": ["f2"]},
            {"text": "Bullet three about topic C.", "claimFindingIds": ["f3"]},
        ],
    }
    _write_story(store_root, category_id, story)

    work_dir = tmp_path / "work" / "daily-2026-08-06"
    paths = emit_research(category_id, str(store_root), str(work_dir))

    assert len(paths) == 3
    for i, path in enumerate(sorted(paths), start=1):
        assert path == work_dir / "chart-research" / f"bullet-{i}-prompt.txt"
        text = path.read_text(encoding="utf-8")
        assert f"topic {chr(ord('A') + i - 1)}" in text
        assert "NO-SERIES-FOUND" in text


def test_emit_prompt_carries_the_finding_s_own_statement_not_just_attribution(tmp_path):
    # Round-2 review fix: the earlier version built prompt context from the
    # bullet's already-resolved `sources` refs, whose "title" is only an
    # ATTRIBUTION string (an outlet name), never the concrete numeric claim.
    # This asserts the real claim text -- something only the scorecard
    # finding's own `statement` field carries -- actually reaches the
    # prompt; a check that only looked for the URL or the outlet name would
    # have passed under the old, wrong behaviour too.
    store_root = tmp_path / "store"
    category_id = "chips.test-category"
    distinctive_statement = ("Intel Data Center and AI revenue was $5.1 billion in "
                              "Q1 2026, up 22% year over year.")
    findings = [
        _finding("f1", url="https://example.test/f1", statement=distinctive_statement),
        _finding("f2", url="https://example.test/f2"),
        _finding("f3", url="https://example.test/f3"),
    ]
    _write_scorecard(store_root, category_id, findings)
    story = {
        "storyDate": "2026-08-06",
        "scenes": [],
        "bullets": [
            {"text": "Bullet one about topic A.", "claimFindingIds": ["f1"]},
            {"text": "Bullet two about topic B.", "claimFindingIds": ["f2"]},
            {"text": "Bullet three about topic C.", "claimFindingIds": ["f3"]},
        ],
    }
    _write_story(store_root, category_id, story)

    work_dir = tmp_path / "work" / "daily-2026-08-06"
    paths = emit_research(category_id, str(store_root), str(work_dir))

    bullet_one_prompt = (work_dir / "chart-research" / "bullet-1-prompt.txt").read_text(encoding="utf-8")
    assert distinctive_statement in bullet_one_prompt
    assert "https://example.test/f1" in bullet_one_prompt


def test_emit_skips_bullet_that_already_has_a_chart(tmp_path):
    store_root = tmp_path / "store"
    category_id = "chips.test-category"
    findings = [
        _finding("f1", indicator_id="chartedIndicator", entity="acme",
                 url="https://example.test/f1"),
        _finding("f2", url="https://example.test/f2"),
        _finding("f3", url="https://example.test/f3"),
    ]
    _write_scorecard(store_root, category_id, findings)
    _write_indicator_rows(store_root, "chartedIndicator")
    story = {
        "storyDate": "2026-08-06",
        "scenes": [
            {"n": 1, "title": "s", "paragraphs": ["x"], "claimFindingIds": [],
             "visual": {"seriesId": "chartedIndicator", "label": "Acme demand"}},
        ],
        "bullets": [
            {"text": "Bullet one has a chart already.", "claimFindingIds": ["f1"]},
            {"text": "Bullet two about topic B.", "claimFindingIds": ["f2"]},
            {"text": "Bullet three about topic C.", "claimFindingIds": ["f3"]},
        ],
    }
    _write_story(store_root, category_id, story)

    work_dir = tmp_path / "work" / "daily-2026-08-06"
    paths = emit_research(category_id, str(store_root), str(work_dir))

    names = sorted(p.name for p in paths)
    assert names == ["bullet-2-prompt.txt", "bullet-3-prompt.txt"]
    assert not (work_dir / "chart-research" / "bullet-1-prompt.txt").exists()


# ---------------------------------------------------------------------------
# CLI: `gpu-agent chart-research emit`
# ---------------------------------------------------------------------------

def test_cli_chart_research_emit_prints_paths_as_json(tmp_path, capsys):
    store_root = tmp_path / "store"
    category_id = "chips.test-category"
    findings = [
        _finding("f1", url="https://example.test/f1"),
        _finding("f2", url="https://example.test/f2"),
        _finding("f3", url="https://example.test/f3"),
    ]
    _write_scorecard(store_root, category_id, findings)
    story = {
        "storyDate": "2026-08-06",
        "scenes": [],
        "bullets": [
            {"text": "Bullet one about topic A.", "claimFindingIds": ["f1"]},
            {"text": "Bullet two about topic B.", "claimFindingIds": ["f2"]},
            {"text": "Bullet three about topic C.", "claimFindingIds": ["f3"]},
        ],
    }
    _write_story(store_root, category_id, story)
    work_dir = tmp_path / "work" / "daily-2026-08-06"

    rc = main(["chart-research", "emit", "--category", category_id,
               "--store", str(store_root), "--work", str(work_dir)])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 3
    for p in out:
        assert Path(p).exists()


def test_cli_chart_research_emit_exits_nonzero_on_missing_store(tmp_path, capsys):
    rc = main(["chart-research", "emit", "--category", "chips.does-not-exist",
               "--store", str(tmp_path / "store"), "--work", str(tmp_path / "work")])

    assert rc == 1
    assert "error" in capsys.readouterr().err
