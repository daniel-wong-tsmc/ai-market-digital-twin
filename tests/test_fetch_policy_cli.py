"""F117/F126: the CLI hands the do-not-fetch registry to the commands that fetch.

Network-free. `webreach-fetch` is driven against an in-process fake tool (the
same trick tests/test_webreach_runner.py uses), and `chart-research accept`
never reaches the network because the request is refused before any fetch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from gpu_agent.cli import main
from gpu_agent.fetch_policy import KIND_BLOCKS_READERS, KIND_OBJECTION

DEFAULT_REGISTRY_PATH = "registry/do-not-fetch.json"


def _fake_tools(tmp_path: Path) -> Path:
    """A tools registry whose one verb is an in-process python call."""
    p = tmp_path / "tools.json"
    p.write_text(json.dumps({"tools": [{
        "id": "fake-fetch", "enabled": True, "role": "fetch",
        "fetchVerbs": {"read": {
            "argv": [sys.executable, "-c",
                     "import sys; print('FETCHED ' + sys.argv[1])", "{target}"],
            "kind": "url"}},
    }]}), encoding="utf-8")
    return p


def _do_not_fetch(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "do-not-fetch.json"
    p.write_text(json.dumps({"version": 1, "entries": entries}, indent=2) + "\n",
                 encoding="utf-8", newline="\n")
    return p


def test_webreach_fetch_refuses_a_publisher_who_objected(tmp_path):
    dnf = _do_not_fetch(tmp_path, [
        {"domain": "objector.test", "kind": KIND_OBJECTION,
         "since": "2026-08-25", "why": "asked us not to"}])
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([
        {"toolId": "fake-fetch", "verb": "read", "target": "https://objector.test/a"},
        {"toolId": "fake-fetch", "verb": "read", "target": "https://example.com/b"},
    ]), encoding="utf-8")
    out = tmp_path / "out"

    rc = main(["webreach-fetch", "--requests", str(reqs), "--out-dir", str(out),
               "--registry", str(_fake_tools(tmp_path)), "--do-not-fetch", str(dnf)])

    assert rc == 0
    rows = json.loads((out / "fetch-manifest.json").read_text("utf-8"))["results"]
    assert rows[0]["refused"] == "refused: publisher objection (objector.test)"
    assert rows[0]["path"] is None
    assert rows[1]["refused"] is None, "the rest of the batch still runs"


def test_webreach_fetch_does_not_refuse_a_site_that_only_blocks_the_plain_reader(tmp_path):
    """Gatherers still read those pages for claims; only the chart verifier
    cares that the plain reader is turned away."""
    dnf = _do_not_fetch(tmp_path, [
        {"domain": "blocker.test", "kind": KIND_BLOCKS_READERS,
         "since": "2026-08-19", "why": "403s the plain reader"}])
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([
        {"toolId": "fake-fetch", "verb": "read", "target": "https://blocker.test/a"}]),
        encoding="utf-8")
    out = tmp_path / "out"

    rc = main(["webreach-fetch", "--requests", str(reqs), "--out-dir", str(out),
               "--registry", str(_fake_tools(tmp_path)), "--do-not-fetch", str(dnf)])

    assert rc == 0
    row = json.loads((out / "fetch-manifest.json").read_text("utf-8"))["results"][0]
    assert row["refused"] is None
    assert row["exitCode"] == 0


def test_a_missing_do_not_fetch_file_is_not_a_usage_error(tmp_path):
    """An unattended cycle must never fail because the list is not there."""
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([
        {"toolId": "fake-fetch", "verb": "read", "target": "https://example.com/a"}]),
        encoding="utf-8")
    out = tmp_path / "out"

    rc = main(["webreach-fetch", "--requests", str(reqs), "--out-dir", str(out),
               "--registry", str(_fake_tools(tmp_path)),
               "--do-not-fetch", str(tmp_path / "nope" / "missing.json")])

    assert rc == 0


def test_chart_research_accept_rejects_an_objected_publisher_and_never_fetches(tmp_path, capsys):
    category = "chips.test-category"
    story_date = "2026-08-06"
    store = tmp_path / "store"
    (store / category / "story").mkdir(parents=True)
    (store / category / "story" / f"{story_date}.json").write_text(
        json.dumps({"storyDate": story_date, "scenes": [], "bullets": []}),
        encoding="utf-8")
    work = tmp_path / "work"
    (work / "chart-research").mkdir(parents=True)
    (work / "chart-research" / "bullet-1.json").write_text(json.dumps({
        "seriesName": "Foundry share", "unit": "percent", "form": "columns",
        "sourceName": "Objector", "pair": False,
        "points": [{"label": f"Q{i}", "value": float(i),
                    "sourceUrl": "https://objector.test/report",
                    "publishedAt": "2026-01-01"} for i in (1, 2, 3)],
    }), encoding="utf-8")
    dnf = _do_not_fetch(tmp_path, [
        {"domain": "objector.test", "kind": KIND_OBJECTION,
         "since": "2026-08-25", "why": "asked us not to"}])

    rc = main(["chart-research", "accept", "--category", category,
               "--store", str(store), "--work", str(work),
               "--do-not-fetch", str(dnf)])

    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["accepted"] == []
    assert "publisher objection" in result["rejected"][0]["failures"][0]


def _repo_registry_stubs(root: Path) -> None:
    """The other repo-relative registries the two commands read by default,
    copied from the real repo so a chdir test exercises the DEFAULT paths
    rather than a hand-made shape."""
    src = Path(__file__).resolve().parents[1] / "registry"
    dst = root / "registry"
    dst.mkdir(exist_ok=True)
    for name in ("licensed-sources.json", "chart-series.json"):
        (dst / name).write_text((src / name).read_text(encoding="utf-8"),
                                encoding="utf-8", newline="\n")


def _emit_store(root: Path, category: str) -> Path:
    """The smallest store `emit` will actually run against: a monthly
    scorecard with findings, plus a story whose bullets carry no chart. Same
    shape tests/test_chart_research.py builds for its emit tests."""
    store = root / "store"
    cat = store / category
    cat.mkdir(parents=True, exist_ok=True)
    findings = [{"id": f"f{i}",
                 "statement": "Example outlet reported a specific number here.",
                 "evidence": [{"source": "Example outlet",
                               "url": f"https://example.test/f{i}",
                               "date": "2026-08-01", "tier": "primary"}]}
                for i in (1, 2, 3)]
    (cat / "2026-08-v1.json").write_text(json.dumps({"findings": findings}),
                                         encoding="utf-8")
    story_dir = cat / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "2026-08-06.json").write_text(json.dumps({
        "storyDate": "2026-08-06",
        "scenes": [],
        "bullets": [{"text": f"Bullet {i} about a topic.",
                     "claimFindingIds": [f"f{i}"]} for i in (1, 2, 3)],
    }), encoding="utf-8")
    return store


def _briefs(work: Path) -> list[Path]:
    return sorted((work / "chart-research").glob("bullet-*-prompt.txt"))


def test_chart_research_emit_honours_the_registry_it_is_given(tmp_path):
    """The flag used to be accepted by `emit` and then ignored, so the brief
    was built from a file nobody named."""
    category = "chips.test-category"
    store = _emit_store(tmp_path, category)
    work = tmp_path / "work"
    dnf = _do_not_fetch(tmp_path, [
        {"domain": "namedfile.test", "kind": KIND_BLOCKS_READERS,
         "since": "2026-08-25", "why": "403s the reader"}])

    rc = main(["chart-research", "emit", "--category", category,
               "--store", str(store), "--work", str(work),
               "--do-not-fetch", str(dnf)])

    assert rc == 0
    briefs = _briefs(work)
    assert briefs, "emit wrote no brief to check"
    text = briefs[0].read_text(encoding="utf-8")
    assert "namedfile.test" in text
    assert "counterpointresearch.com" not in text, (
        "the brief must come from the named file, not the repo default")


def test_webreach_fetch_picks_the_list_up_with_no_flag_at_all(tmp_path, monkeypatch):
    """The default is the repo-relative path, so an unattended cycle enforces
    an objection without the run-cycle skill passing anything. Proven by
    behaviour -- an actual refusal -- not by reading the source for a
    `default=` string, which would pass even with the flag wired to the wrong
    handler."""
    tools = _fake_tools(tmp_path)
    monkeypatch.chdir(tmp_path)
    _repo_registry_stubs(tmp_path)
    (tmp_path / "registry" / "do-not-fetch.json").write_text(
        json.dumps({"version": 1, "entries": [
            {"domain": "objector.test", "kind": KIND_OBJECTION,
             "since": "2026-08-25", "why": "asked us not to"}]}, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([
        {"toolId": "fake-fetch", "verb": "read", "target": "https://objector.test/a"}]),
        encoding="utf-8")

    rc = main(["webreach-fetch", "--requests", str(reqs), "--out-dir", "out",
               "--registry", str(tools)])

    assert rc == 0
    row = json.loads((tmp_path / "out" / "fetch-manifest.json")
                     .read_text("utf-8"))["results"][0]
    assert row["refused"] == "refused: publisher objection (objector.test)"


def test_chart_research_emit_picks_the_list_up_with_no_flag_at_all(tmp_path, monkeypatch):
    category = "chips.test-category"
    store = _emit_store(tmp_path, category)
    monkeypatch.chdir(tmp_path)
    _repo_registry_stubs(tmp_path)
    (tmp_path / "registry" / "do-not-fetch.json").write_text(
        json.dumps({"version": 1, "entries": [
            {"domain": "defaultfile.test", "kind": KIND_BLOCKS_READERS,
             "since": "2026-08-25", "why": "403s the reader"}]}, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    rc = main(["chart-research", "emit", "--category", category,
               "--store", str(store), "--work", "work"])

    assert rc == 0
    briefs = _briefs(tmp_path / "work")
    assert briefs, "emit wrote no brief to check"
    assert "defaultfile.test" in briefs[0].read_text(encoding="utf-8")
