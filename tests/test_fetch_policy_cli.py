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


def test_both_commands_default_to_the_repo_registry_path():
    """The default has to be the repo-relative path: an unattended cycle picks
    the list up without the run-cycle skill having to pass a flag."""
    import gpu_agent.cli as cli
    text = Path(cli.__file__).read_text(encoding="utf-8")
    assert text.count('"--do-not-fetch"') == 2
    assert text.count(f'default="{DEFAULT_REGISTRY_PATH}"') == 2
