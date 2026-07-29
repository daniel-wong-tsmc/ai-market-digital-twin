"""F66 Task 3: the `gpu-agent audit-citations` verb.

NOTE: tests/ is not a package in this repo -- never import from another test
module; each test file carries its own helpers.
"""
import json
import pathlib

from gpu_agent.cli import main
from gpu_agent.narrator.schema import NarratorMeta, StoryArtifact, StoryScene
from gpu_agent.narrator.store import StoryStore

CAT = "chips.merchant-gpu"
DATE = "2026-07-27"


def _finding(fid, statement="rates held flat", number=None):
    d = {
        "id": fid, "statement": statement, "kind": "observed", "trend": "flat",
        "why": "because",
        "impact": {"targets": ["tsmc"], "direction": "mixed", "mechanism": "m"},
        "evidence": [{"source": "src", "url": "https://example.com/a",
                      "date": "2026-07-23", "excerpt": "an excerpt",
                      "tier": "secondary"}],
        "confidence": {"level": "medium", "basis": "b"},
        "asOf": "2026-07", "indicatorId": "gpuSpotPrice", "side": "price",
        "polarityDemand": 0, "polaritySupply": 0, "magnitude": 2,
        "entity": "nvidia", "observedAt": "2026-07-23",
        "capturedAt": "2026-07-23T00:00:00Z",
    }
    if number is not None:
        d["value"] = {"number": number, "unit": "USD_B"}
    return d


def _seed(root, paragraphs, finding_ids=("f-a",), statement="rates held flat"):
    fd = root / "findings"
    fd.mkdir(parents=True, exist_ok=True)
    for fid in finding_ids:
        (fd / f"{fid}.json").write_text(
            json.dumps(_finding(fid, statement=statement), indent=2), encoding="utf-8")
    scene = StoryScene(n=1, title="A scene", paragraphs=paragraphs, visual=None,
                       claimFindingIds=list(finding_ids),
                       sourceLine="Sources: example.com", relatedDocs=[])
    StoryStore(root).write(StoryArtifact(
        schemaVersion=1, categoryId=CAT, storyDate=DATE, headline="H", deck="D",
        scenes=[scene], kpiPicks=[], calloutMonths=[],
        narratorMeta=NarratorMeta(model="m", promptHash="h", retries=0,
                                  fellBack=False, wroteAt="2026-07-27T00:00:00Z")))


def _argv(root):
    return ["audit-citations", "--store", str(root), "--category", CAT, "--date", DATE]


def test_clean_run_exits_zero_and_writes_artifact(tmp_path, capsys):
    _seed(tmp_path, ["Nothing numeric here at all."])
    rc = main(_argv(tmp_path))
    assert rc == 0
    art = json.loads((tmp_path / CAT / "audit" / f"{DATE}.json").read_text("utf-8"))
    assert art["summary"] == {"claimsAudited": 1, "flagged": 0, "skipped": 0}
    assert art["schemaVersion"] == 1
    assert art["categoryId"] == CAT and art["asOf"] == DATE


def test_flagged_run_exits_one_and_still_writes_artifact(tmp_path, capsys):
    # The audit record is EVIDENCE: a cycle that flagged something must leave a
    # trace. This deliberately differs from the gates that write nothing on
    # rejection.
    _seed(tmp_path, ["Rates ran to $9.99 an hour."])
    rc = main(_argv(tmp_path))
    assert rc == 1
    art = json.loads((tmp_path / CAT / "audit" / f"{DATE}.json").read_text("utf-8"))
    assert art["summary"]["flagged"] == 1
    assert art["claims"][0]["flaggedTokens"] == ["9.99"]


def test_stderr_names_the_claim_and_the_token(tmp_path, capsys):
    _seed(tmp_path, ["Rates ran to $9.99 an hour."])
    rc = main(_argv(tmp_path))
    assert rc == 1
    err = capsys.readouterr().err
    assert "CITATION AUDIT FAILED" in err
    # wording deliberately echoes the F14 wiki gate's "uncited number"
    assert "scene:1: uncited number 9.99" in err


def test_stderr_names_an_unresolved_finding(tmp_path, capsys):
    _seed(tmp_path, ["Nothing numeric here."], finding_ids=("f-a",))
    # add a citation to an id with no file
    p = tmp_path / CAT / "story" / f"{DATE}.json"
    art = json.loads(p.read_text("utf-8"))
    art["scenes"][0]["claimFindingIds"].append("f-missing")
    p.write_text(json.dumps(art), encoding="utf-8")
    rc = main(_argv(tmp_path))
    assert rc == 1
    err = capsys.readouterr().err
    assert "scene:1: unresolved finding f-missing" in err


def test_missing_story_artifact_exits_zero_with_empty_audit(tmp_path, capsys):
    (tmp_path / "findings").mkdir(parents=True, exist_ok=True)
    rc = main(_argv(tmp_path))
    assert rc == 0
    art = json.loads((tmp_path / CAT / "audit" / f"{DATE}.json").read_text("utf-8"))
    assert art["claims"] == []
    assert art["summary"] == {"claimsAudited": 0, "flagged": 0, "skipped": 0}


def test_out_flag_redirects_the_artifact(tmp_path, capsys):
    _seed(tmp_path, ["Nothing numeric here."])
    out = tmp_path / "elsewhere" / "audit.json"
    rc = main(_argv(tmp_path) + ["--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text("utf-8"))["categoryId"] == CAT
    assert not (tmp_path / CAT / "audit").exists()


def test_series_values_are_supported_via_the_cli(tmp_path, capsys):
    """D5b sourcing option (a), user-approved: the CLI reads store/series/ and
    hands the values to the audit, so the page is not flagged for quoting
    arithmetic we computed ourselves. Without this the same prose flags."""
    _seed(tmp_path, ["A median of $18.77 per chip-hour."])
    assert main(_argv(tmp_path)) == 1              # no series data yet

    sd = tmp_path / "series"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "gpuSpotPrice.jsonl").write_text(
        json.dumps({"period": "2026-07", "value": 18.77, "unit": "USD_per_hr"}) + "\n",
        encoding="utf-8")
    assert main(_argv(tmp_path)) == 0
