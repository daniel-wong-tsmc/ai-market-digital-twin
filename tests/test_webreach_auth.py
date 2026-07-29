import json
import pathlib
import sys
import pytest
from gpu_agent.gathering.webreach import (
    FetchRequest, auth_secrets_used, build_argv, resolve_secret, run_requests)

FAKE = "sk-test-fake-not-a-real-key"

def _tool(auth=True):
    verb = {"kind": "query",
            "argv": ["curl", "-fsS", "--get", "https://api.example.com/stories",
                     "--data-urlencode", "tags={target}"]}
    if auth:
        verb["auth"] = {"secretName": "HN_TEST_KEY",
                        "argv": ["-H", "Authorization: Bearer {secret}"]}
    return {"id": "hn-test", "enabled": True, "fetchVerbs": {"latest": verb}}

def _req():
    return FetchRequest(toolId="hn-test", verb="latest", target="ai-compute-chips")

def test_resolve_secret_env_wins_over_file(tmp_path, monkeypatch):
    (tmp_path / "HN_TEST_KEY").write_text("from-file", "utf-8")
    monkeypatch.setenv("HN_TEST_KEY", "from-env")
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) == "from-env"

def test_resolve_secret_file_fallback_stripped(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    (tmp_path / "HN_TEST_KEY").write_text(FAKE + "\n", "utf-8")
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) == FAKE

def test_resolve_secret_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) is None

def test_build_argv_appends_auth_when_secret_present(monkeypatch):
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    argv = build_argv(_tool(), _req())
    assert argv[-2:] == ["-H", f"Authorization: Bearer {FAKE}"]
    assert "tags=ai-compute-chips" in argv       # {target} substitution untouched
    assert "tags={target}" not in argv

def test_build_argv_omits_auth_when_secret_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR", tmp_path)
    argv = build_argv(_tool(), _req())
    assert "-H" not in argv                      # anonymous degrade: no auth slots at all

def test_build_argv_without_auth_block_unchanged(monkeypatch):
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    assert "-H" not in build_argv(_tool(auth=False), _req())

def test_run_requests_scrubs_secret_from_error(tmp_path, monkeypatch):
    # a failing tool that echoes its argv (secret included) to stderr must not
    # leak the secret into the recorded manifest
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    tool = _tool()
    tool["fetchVerbs"]["latest"]["argv"] = [
        sys.executable, "-c",
        "import sys; sys.stderr.write(' '.join(sys.argv[1:])); sys.exit(3)",
        "tags={target}"]
    registry = {"version": 1, "tools": [tool]}
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([{"toolId": "hn-test", "verb": "latest",
                                 "target": "ai-compute-chips"}]), "utf-8")
    manifest = run_requests(reqs, tmp_path / "out", registry, set())
    text = json.dumps(manifest) + (tmp_path / "out" / "fetch-manifest.json").read_text("utf-8")
    assert FAKE not in text
    assert manifest["results"][0]["exitCode"] == 3
