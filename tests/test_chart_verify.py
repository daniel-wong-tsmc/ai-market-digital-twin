"""tests/test_chart_verify.py -- F113 Task 4: the deterministic verifier and
the quarantine store.

This is the trust gate of F113: nothing a research agent says is believed on
its word. Every test here is NETWORK-FREE -- `fetch_html` is injected in every
single case and reads the saved pages under `fixtures/chartdata/research/`.
There is no code path in these tests that could reach the internet.
"""
from __future__ import annotations

import json
from pathlib import Path

from gpu_agent.chartdata.research import CandidateSeries
from gpu_agent.chartdata.verify import accept_research, verify_candidate
from gpu_agent.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chartdata" / "research"

_ALL_URL = "https://example.test/widgets-all"
_MISSING_URL = "https://example.test/gadgets-missing"

_PAGES = {
    _ALL_URL: "page-all-numbers.html",
    _MISSING_URL: "page-missing-number.html",
}


def _fetch_fixture(url: str) -> str:
    """The ONLY fetcher these tests ever use: a saved page off disk."""
    name = _PAGES.get(url)
    if name is None:
        raise RuntimeError(f"test fetcher has no saved page for {url}")
    return (FIXTURES / name).read_text(encoding="utf-8")


def _boom(url: str) -> str:
    raise RuntimeError("connection reset")


def _candidate(name: str) -> CandidateSeries:
    return CandidateSeries.model_validate_json(
        (FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# verify_candidate
# ---------------------------------------------------------------------------

def test_good_candidate_verifies_against_its_saved_page():
    ok, failures = verify_candidate(_candidate("candidate-good"), _fetch_fixture)
    assert ok is True
    assert failures == []


def test_verifier_reuses_the_citation_audit_rounding_tolerance():
    # The good fixture's point 1 is 6.7 and the page prints 6.71 -- accepted
    # only because the shared F66 tolerance says a value rounds to the cited
    # precision. A stricter substring check would reject it.
    cand = _candidate("candidate-good")
    assert cand.points[0].value == 6.7
    assert "6.71" in _fetch_fixture(_ALL_URL)
    assert "6.7<" not in _fetch_fixture(_ALL_URL)
    ok, failures = verify_candidate(cand, _fetch_fixture)
    assert ok is True, failures


def test_verifier_matches_a_number_written_with_thousands_commas():
    # Point 3 is 12500.0; the page prints "12,500".
    cand = _candidate("candidate-good")
    assert cand.points[2].value == 12500.0
    assert "12,500" in _fetch_fixture(_ALL_URL)
    ok, _ = verify_candidate(cand, _fetch_fixture)
    assert ok is True


def test_one_missing_point_rejects_the_whole_candidate():
    cand = _candidate("candidate-bad")
    ok, failures = verify_candidate(cand, _fetch_fixture)
    assert ok is False
    assert len(failures) == 1
    msg = failures[0]
    assert "point 3" in msg
    assert "8.1" in msg
    assert _MISSING_URL in msg


def test_a_value_outside_tolerance_is_rejected():
    cand = CandidateSeries(
        seriesName="Off by too much", unit="million units", form="line",
        sourceName="Example Outlet",
        points=[{"label": "Q1", "value": 6.9, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"},
                {"label": "Q2", "value": 7.2, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"},
                {"label": "Q3", "value": 12500.0, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"}],
    )
    ok, failures = verify_candidate(cand, _fetch_fixture)
    assert ok is False
    assert "point 1" in failures[0]


def test_a_number_only_present_inside_a_script_tag_does_not_count():
    # The saved page carries `"buildNumber": 41.5` inside a <script> block.
    # Script/style content is not page text a reader ever sees, so it must
    # not be usable as backing for a claimed data point.
    assert "41.5" in _fetch_fixture(_ALL_URL)
    cand = CandidateSeries(
        seriesName="Script decoy", unit="million units", form="line",
        sourceName="Example Outlet",
        points=[{"label": "Q1", "value": 41.5, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"},
                {"label": "Q2", "value": 7.2, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"},
                {"label": "Q3", "value": 12500.0, "sourceUrl": _ALL_URL,
                 "publishedAt": "2026-08-01"}],
    )
    ok, failures = verify_candidate(cand, _fetch_fixture)
    assert ok is False
    assert "point 1" in failures[0]


def test_a_fetch_that_raises_is_an_unreachable_rejection_not_a_crash():
    ok, failures = verify_candidate(_candidate("candidate-good"), _boom)
    assert ok is False
    assert failures  # one entry per unreachable point, nothing raised out
    assert "unreachable" in failures[0]
    assert _ALL_URL in failures[0]


# ---------------------------------------------------------------------------
# accept_research -- store/work fixture trees
# ---------------------------------------------------------------------------

CATEGORY = "chips.test-category"
STORY_DATE = "2026-08-06"


def _make_store(tmp_path: Path) -> Path:
    store_root = tmp_path / "store"
    story_dir = store_root / CATEGORY / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / f"{STORY_DATE}.json").write_text(
        json.dumps({"storyDate": STORY_DATE, "scenes": [], "bullets": []}),
        encoding="utf-8")
    return store_root


def _answer(work_dir: Path, n: int, fixture: str) -> Path:
    d = work_dir / "chart-research"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"bullet-{n}.json"
    p.write_text((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"),
                  encoding="utf-8")
    return p


def _research_dir(store_root: Path) -> Path:
    return store_root / CATEGORY / "research-series"


def test_accept_writes_a_passing_candidate_to_the_quarantine_store(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["rejected"] == []
    assert result["missing"] == []
    assert len(result["accepted"]) == 1
    written = Path(result["accepted"][0])
    assert written == _research_dir(store_root) / "2026-08-06-widget-shipments-by-quarter.json"
    assert written.exists()


def test_quarantine_record_is_the_candidate_verbatim_with_no_wall_clock_field(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)
    record = json.loads(Path(result["accepted"][0]).read_text(encoding="utf-8"))

    source = json.loads((FIXTURES / "candidate-good.json").read_text(encoding="utf-8"))
    assert record["seriesName"] == source["seriesName"]
    assert record["unit"] == source["unit"]
    assert record["form"] == source["form"]
    assert record["sourceName"] == source["sourceName"]
    assert record["points"] == source["points"]
    assert record["notes"] == source["notes"]
    # Exactly the candidate's own fields -- no verifiedAt / capturedAt / any
    # other wall-clock stamp, so a rerun is byte-identical.
    assert set(record) == {"seriesName", "unit", "form", "sourceName",
                            "points", "pair", "notes", "bulletIndex"}


def test_written_record_carries_the_bullet_index_of_the_file_it_came_from(tmp_path):
    # HARD REQUIREMENT (carried from Task 3's review): Task 5 matches an
    # accepted candidate back to its bullet through `bulletIndex`, and a
    # wrong/None index renders EXACTLY like "no series found" -- an
    # invisible failure. So assert the CORRECT number, per source file, not
    # merely that the field is present.
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 2, "candidate-good")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)
    record = json.loads(Path(result["accepted"][0]).read_text(encoding="utf-8"))
    assert record["bulletIndex"] == 2


def test_bullet_index_tracks_a_different_source_file_number(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 3, "candidate-good")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)
    record = json.loads(Path(result["accepted"][0]).read_text(encoding="utf-8"))
    assert record["bulletIndex"] == 3


def test_a_failing_candidate_is_rejected_and_nothing_is_written(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    answer = _answer(work_dir, 1, "candidate-bad")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["accepted"] == []
    assert len(result["rejected"]) == 1
    assert Path(result["rejected"][0]["file"]) == answer
    assert any("point 3" in f for f in result["rejected"][0]["failures"])
    assert not _research_dir(store_root).exists()


def test_an_unreachable_source_rejects_the_candidate_and_the_cycle_continues(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_boom)

    assert result["accepted"] == []
    assert len(result["rejected"]) == 1
    assert any("unreachable" in f for f in result["rejected"][0]["failures"])
    assert not _research_dir(store_root).exists()


def test_accept_refuses_to_overwrite_an_existing_quarantine_file(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")

    target = _research_dir(store_root) / "2026-08-06-widget-shipments-by-quarter.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"alreadyHere": true}', encoding="utf-8")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["accepted"] == []
    assert len(result["rejected"]) == 1
    assert any("exists" in f for f in result["rejected"][0]["failures"])
    # append-only: the file on disk is untouched
    assert json.loads(target.read_text(encoding="utf-8")) == {"alreadyHere": True}


def test_no_series_found_answer_counts_as_missing_not_an_error(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    d = work_dir / "chart-research"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bullet-1.json").write_text("NO-SERIES-FOUND\n", encoding="utf-8")
    (d / "bullet-2.json").write_text('"NO-SERIES-FOUND"', encoding="utf-8")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["accepted"] == []
    assert result["rejected"] == []
    assert len(result["missing"]) == 2


def test_a_malformed_answer_file_is_a_rejection_not_a_crash(tmp_path):
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    d = work_dir / "chart-research"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bullet-1.json").write_text("{not json at all", encoding="utf-8")

    result = accept_research(CATEGORY, str(store_root), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["accepted"] == []
    assert len(result["rejected"]) == 1


def test_accept_never_raises_when_the_store_has_no_story(tmp_path):
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")

    result = accept_research(CATEGORY, str(tmp_path / "store"), str(work_dir),
                              fetch_html=_fetch_fixture)

    assert result["accepted"] == []
    assert len(result["rejected"]) == 1


def test_accept_with_no_answer_files_is_an_empty_result(tmp_path):
    store_root = _make_store(tmp_path)
    result = accept_research(CATEGORY, str(store_root),
                              str(tmp_path / "work" / "daily-2026-08-06"),
                              fetch_html=_fetch_fixture)
    assert result == {"accepted": [], "rejected": [], "missing": []}


def test_accept_writes_no_curated_registry_file(tmp_path, monkeypatch):
    # Spec section 2/8: researched series NEVER enter registry/chart-series.json.
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    _answer(work_dir, 1, "candidate-good")
    accept_research(CATEGORY, str(store_root), str(work_dir),
                     fetch_html=_fetch_fixture)
    written = [p for p in store_root.rglob("*.json")]
    assert all("chart-series" not in p.name for p in written)


# ---------------------------------------------------------------------------
# CLI: `gpu-agent chart-research accept`
# ---------------------------------------------------------------------------

def test_cli_chart_research_accept_prints_summary_and_exits_zero(tmp_path, capsys):
    # Network-free by construction: a NO-SERIES-FOUND answer and a malformed
    # answer are both decided before any point is ever fetched, so the CLI's
    # real (network) fetcher is never reached.
    store_root = _make_store(tmp_path)
    work_dir = tmp_path / "work" / "daily-2026-08-06"
    d = work_dir / "chart-research"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bullet-1.json").write_text("NO-SERIES-FOUND\n", encoding="utf-8")
    (d / "bullet-2.json").write_text("{not json at all", encoding="utf-8")

    rc = main(["chart-research", "accept", "--category", CATEGORY,
               "--store", str(store_root), "--work", str(work_dir)])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["accepted"] == []
    assert len(out["missing"]) == 1
    assert len(out["rejected"]) == 1


def test_cli_chart_research_accept_exits_zero_on_a_broken_store(tmp_path, capsys):
    # The verifier can never block or strand a cycle.
    rc = main(["chart-research", "accept", "--category", "chips.does-not-exist",
               "--store", str(tmp_path / "store"), "--work", str(tmp_path / "work")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["accepted"] == []
