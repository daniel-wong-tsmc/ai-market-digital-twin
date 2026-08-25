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


def test_prompt_states_the_same_site_rule_the_verifier_enforces():
    """The verifier rejects a candidate whose points span more than one site,
    because the chart is captioned as resting on one source. The researcher
    has to be TOLD that: a gate enforcing a rule its own prompt never stated
    just burns dispatches on candidates that get thrown away. This test is
    what stops the instruction and the enforcement drifting apart again."""
    from gpu_agent.chartdata.verify import verify_candidate

    prompt = build_research_prompt({"text": "Any bullet."}, []).lower()
    assert "same site" in prompt
    assert "rejected" in prompt

    # ...and the rule really is enforced, so the prompt is not promising
    # something the gate does not do.
    cand = CandidateSeries(
        seriesName="Two publishers", unit="units", form="line",
        sourceName="Example Outlet",
        points=[_point(url="https://example.test/a"),
                _point(url="https://other.test/b"),
                _point(url="https://example.test/c")],
    )
    ok, failures = verify_candidate(cand, lambda url: "1.0")
    assert ok is False
    assert "ONE source" in failures[0]


def test_prompt_states_the_publicly_reachable_source_rule():
    """Same pairing for the other new gate: the verifier refuses local,
    private and internal addresses, so the prompt says not to cite one."""
    from gpu_agent.chartdata.verify import verify_candidate

    prompt = build_research_prompt({"text": "Any bullet."}, []).lower()
    assert "public web" in prompt
    assert "local address" in prompt

    cand = CandidateSeries(
        seriesName="Local page", unit="units", form="line",
        sourceName="Example Outlet",
        points=[_point(url="http://localhost:8080/series"),
                _point(url="http://localhost:8080/series"),
                _point(url="http://localhost:8080/series")],
    )
    ok, failures = verify_candidate(cand, lambda url: "1.0")
    assert ok is False
    assert "point 1" in failures[0]


# Three consecutive live cycles (2026-08-10, -11 twice) rejected every
# researched series for reasons the brief never stated: values came back as
# prose ("$35.6 billion", "over $1.3 trillion", "close to 80%") where the
# schema wants a bare number, and one series cited a publisher that answers
# automated readers with HTTP 403, which the re-fetch verifier can never pass.
# Same doctrine as the two tests above: instruction and enforcement stated
# together and tested together.

def test_prompt_says_value_must_be_a_bare_number():
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "bare number" in prompt.lower()
    # ...and the schema really does refuse prose, so the warning is earned.
    with pytest.raises(ValidationError):
        CandidatePoint(label="Q1", value="$35.6 billion",
                       sourceUrl="https://example.test/q1", publishedAt="2026-01-01")


def test_prompt_says_hedged_text_is_not_a_number():
    """The 2026-08-10 candidate handed back 'below 60%' / 'close to 80%'
    with an honest note that the source only gave ranges. The brief must
    say what to do with that: skip the point (or give up), never turn the
    hedge into a made-up figure and never send the words as the value."""
    prompt = build_research_prompt({"text": "Any bullet."}, []).lower()
    assert "close to" in prompt or "about" in prompt
    assert "range" in prompt


def test_prompt_warns_that_licensed_and_bot_blocking_sites_fail_verification():
    """The verifier re-fetches every cited page with a plain automated
    reader. A site that blocks such readers (TrendForce returned 403 to all
    five points on 2026-08-11) can never verify, so the researcher is told
    up front -- and told which registered licensed publishers to avoid,
    read from `registry/licensed-sources.json`, not hard-coded."""
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "trendforce.com" in prompt
    assert "semianalysis.com" in prompt
    lowered = prompt.lower()
    assert "verif" in lowered
    assert "automated" in lowered or "robot" in lowered


def test_prompt_survives_a_missing_licensed_registry(tmp_path, monkeypatch):
    """The prompt builder is called from a worktree or an odd cwd too; no
    registry file must mean a generic warning, never a crash."""
    monkeypatch.chdir(tmp_path)
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "trendforce.com" not in prompt
    assert "verif" in prompt.lower()
    assert "NO-SERIES-FOUND" in prompt


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


# ---------------------------------------------------------------------------
# F113 Task 7 Step 2: registry trust proof
# ---------------------------------------------------------------------------
#
# The whole F113 trust model rests on ONE property: a researched series never
# enters the human-curated `registry/chart-series.json`. Promotion is a human
# edit, always. This test is the belt-and-suspenders mechanical guard: it scans
# every .py file shipped in the package for `chart-series.json` appearing
# anywhere near a write operation, and fails loudly if one ever shows up.

_REGISTRY_FILENAME = "chart-series.json"

# Any of these on a line means "this line can put bytes on disk".
_WRITE_MARKERS = (
    'open(',          # paired with a mode check below
    '.write_text(',
    '.write_bytes(',
    'json.dump(',
    '.write(',
    '.writelines(',
    'shutil.copy',
    'shutil.move',
    'os.replace(',
    'os.rename(',
    '.rename(',
    '.replace(',
    '.touch(',
    '.unlink(',
    'os.remove(',
)

# How far from the registry filename a write op still counts as "near".
_PROXIMITY_LINES = 6


def _package_python_files():
    pkg_root = Path(__file__).resolve().parents[1] / "gpu_agent"
    return sorted(p for p in pkg_root.rglob("*.py") if "__pycache__" not in p.parts)


def _is_write_line(line: str) -> bool:
    """True if `line` looks like it writes/mutates a file on disk.

    `open(...)` only counts when it carries a write-ish mode, so the many
    legitimate read-only `open(path)` loaders don't trip the guard.
    """
    stripped = line.strip()
    # Ignore pure comment lines -- F113 deliberately documents the rule in
    # prose right next to the code, and prose is not a writer.
    if stripped.startswith("#"):
        return False
    for marker in _WRITE_MARKERS:
        if marker not in line:
            continue
        if marker == 'open(':
            # only a write mode counts
            tail = line.split('open(', 1)[1]
            if any(m in tail for m in ('"w', "'w", '"a', "'a", '"x', "'x", '"r+', "'r+")):
                return True
            continue
        return True
    return False


def test_no_registry_writers():
    """No module in gpu_agent/ may write to registry/chart-series.json.

    Researched series live in the quarantine store; promotion into the curated
    registry is a human edit. If this test goes red, something in the package
    grew the ability to edit the registry -- that is a trust-model break, not a
    test to be relaxed.
    """
    offenders = []
    for path in _package_python_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        registry_lines = [
            i for i, line in enumerate(lines) if _REGISTRY_FILENAME in line
        ]
        if not registry_lines:
            continue
        for i in registry_lines:
            lo = max(0, i - _PROXIMITY_LINES)
            hi = min(len(lines), i + _PROXIMITY_LINES + 1)
            for j in range(lo, hi):
                if _is_write_line(lines[j]):
                    offenders.append(
                        f"{path.name}:{j + 1}: {lines[j].strip()!r} "
                        f"(near {_REGISTRY_FILENAME} on line {i + 1})"
                    )

    assert not offenders, (
        "A writer to the human-curated chart registry appeared. Researched "
        "series must NEVER enter registry/chart-series.json -- promotion is a "
        "human edit. Offending lines:\n  " + "\n  ".join(offenders)
    )


def test_no_registry_writers_guard_is_not_decorative():
    """The guard above must actually detect a writer, not just always pass.

    Proves `_is_write_line` fires on the write shapes we care about and stays
    quiet on the read-only and comment shapes that legitimately appear in the
    package today.
    """
    should_fire = [
        'with open(path, "w", encoding="utf-8") as fh:',
        'Path("registry/chart-series.json").write_text(payload)',
        'json.dump(entries, fh)',
        "fh.write(json.dumps(entries))",
        'p.write_bytes(b"{}")',
        "os.replace(tmp, dest)",
    ]
    for line in should_fire:
        assert _is_write_line(line), f"guard failed to flag a writer: {line!r}"

    should_not_fire = [
        'with open(Path(path), encoding="utf-8") as fh:',
        'DEFAULT_REGISTRY_PATH = "registry/chart-series.json"',
        "# NOT `registry/chart-series.json` -- that registry stays human-curated",
        "entries = json.load(fh)",
    ]
    for line in should_not_fire:
        assert not _is_write_line(line), f"guard false-positived on: {line!r}"


# ---------------------------------------------------------------------------
# F117: rule 8's real finding. On 2026-08-19 the researcher's own reader opened
# counterpointresearch.com cleanly three times while the verifier's plain
# reader got HTTP 403 five times. Naming domains will always lag; telling the
# researcher that its own fetch proves nothing will not.
# ---------------------------------------------------------------------------

def test_rule_8_says_the_researchers_own_fetch_proves_nothing():
    prompt = build_research_prompt({"text": "Any bullet."}, []).lower()
    assert "different" in prompt and "reader" in prompt
    assert "proves nothing" in prompt


def test_rule_8_names_the_blocked_domains_from_the_shipped_registry():
    """The seeded blocks-plain-readers domain is read from
    registry/do-not-fetch.json, not hard-coded, so the list the researcher is
    warned about and the list the verifier learns into cannot drift apart."""
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "counterpointresearch.com" in prompt
    lowered = prompt.lower()
    assert "turn the plain reader away" in lowered
    assert "unavailable" in lowered
    # the licensed-publisher list is still there
    assert "trendforce.com" in prompt


def test_rule_8_lists_a_publisher_objection_when_one_exists(tmp_path, monkeypatch):
    """No publisher has ever objected, so the shipped list is empty -- but the
    brief must name one the day it is not."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "do-not-fetch.json").write_text(
        json.dumps({"version": 1, "entries": [
            {"domain": "objector.test", "kind": "publisher-objection",
             "since": "2026-08-25", "why": "asked us not to"}]}, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "objector.test" in prompt
    assert "never cite" in prompt.lower()


def test_rule_8_survives_a_missing_do_not_fetch_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = build_research_prompt({"text": "Any bullet."}, [])
    assert "counterpointresearch.com" not in prompt
    assert "proves nothing" in prompt.lower()
    assert "NO-SERIES-FOUND" in prompt


def test_build_research_prompt_reads_the_registry_it_is_pointed_at(tmp_path):
    """Review finding: `--do-not-fetch` was accepted by `chart-research emit`
    and then ignored, so the brief was built from a file nobody named."""
    reg = tmp_path / "elsewhere.json"
    reg.write_text(json.dumps({"version": 1, "entries": [
        {"domain": "namedfile.test", "kind": "blocks-plain-readers",
         "since": "2026-08-25", "why": "403s the reader"}]}, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    prompt = build_research_prompt({"text": "Any bullet."}, [],
                                   do_not_fetch_path=reg)

    assert "namedfile.test" in prompt
    # and NOT the repo default's seeded domain
    assert "counterpointresearch.com" not in prompt
