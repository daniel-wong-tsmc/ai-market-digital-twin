import json
import pathlib
import pytest
from gpu_agent.gathering.webreach import FetchRequest, build_argv, validate_request

REGISTRY = json.loads(pathlib.Path("registry/web-reach-tools.json").read_text("utf-8"))

# Built from parts rather than spelled outright, so this file never contains
# the literal key-prefix string itself -- keeps a branch-wide leak scan for
# that prefix a true zero even though this test asserts the prefix is absent.
KEY_PREFIX = "a" + "k_"

def _tool():
    t = next((t for t in REGISTRY["tools"] if t["id"] == "huggingnews"), None)
    assert t is not None, "registry must contain the huggingnews tool"
    return t

def test_entry_has_install_not_needed_flag_with_empty_install_lists():
    t = _tool()
    assert t["installNotNeeded"] is True
    assert t["install"] == {"windows": [], "macos": [], "linux": []}

def test_entry_shape_and_verbs():
    t = _tool()
    assert t["enabled"] is True
    assert t["secretName"] == "HUGGINGNEWS_API_KEY"
    assert set(t["fetchVerbs"]) == {"latest", "search", "detail"}
    for verb in t["fetchVerbs"].values():
        assert verb["auth"]["secretName"] == "HUGGINGNEWS_API_KEY"
        assert "{secret}" in " ".join(verb["auth"]["argv"])
        assert not any(KEY_PREFIX in slot for slot in verb["argv"])   # no key material, ever

def test_verbs_validate_and_render(monkeypatch):
    monkeypatch.delenv("HUGGINGNEWS_API_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR",
                        pathlib.Path("no-such-dir"))
    cases = {"latest": "ai-compute-chips,ai-model-releases",
             "search": "GPU supply", "detail": "some-story-slug-1a2b3c4d"}
    for verb, target in cases.items():
        req = FetchRequest(toolId="huggingnews", verb=verb, target=target)
        assert validate_request(req, REGISTRY, set()) is None
        argv = build_argv(_tool(), req)
        assert argv[0] == "curl" and "api.huggingnews.com/api/stories" in " ".join(argv)
        assert "-H" not in argv                     # anonymous render without a key

def test_detail_verb_hits_slug_path(monkeypatch):
    monkeypatch.delenv("HUGGINGNEWS_API_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR",
                        pathlib.Path("no-such-dir"))
    req = FetchRequest(toolId="huggingnews", verb="detail", target="a-slug-1234")
    assert any(a.endswith("/api/stories/a-slug-1234") for a in build_argv(_tool(), req))

def test_ensure_reports_keyed_status(monkeypatch, capsys):
    from gpu_agent.web_reach_ensure import load_registry, ensure_all, detect_os
    monkeypatch.setenv("HUGGINGNEWS_API_KEY", "sk-test-fake-not-a-real-key")
    # check_only with a stubbed health probe: we only assert the SUFFIX logic here
    monkeypatch.setattr("gpu_agent.web_reach_ensure.health_ok", lambda tool, os_key, **k: True)
    ensure_all(load_registry(), detect_os(), check_only=True)
    out = capsys.readouterr().out
    assert "(keyed)" in out and "sk-test-fake" not in out


def _huggingnews_result(monkeypatch, *, keyed: bool) -> dict:
    """Run ensure_tool for the real huggingnews registry entry and return its
    result dict, as `--json` mode would emit it (F106 finding 3: the keyed
    state must reach the machine-readable result, not just the log line)."""
    from gpu_agent.web_reach_ensure import load_registry, ensure_tool, detect_os
    if keyed:
        monkeypatch.setenv("HUGGINGNEWS_API_KEY", "sk-test-fake-not-a-real-key")
    else:
        monkeypatch.delenv("HUGGINGNEWS_API_KEY", raising=False)
        monkeypatch.setattr("gpu_agent.web_reach_ensure.SECRETS_DIR", pathlib.Path("no-such-dir"))
    monkeypatch.setattr("gpu_agent.web_reach_ensure.health_ok", lambda tool, os_key, **k: True)
    tool = _tool()
    return ensure_tool(tool, detect_os(), check_only=True, log=lambda m: None)


def test_json_result_carries_keyed_true_when_secret_present(monkeypatch):
    result = _huggingnews_result(monkeypatch, keyed=True)
    assert result["keyed"] is True


def test_json_result_carries_keyed_false_when_secret_absent(monkeypatch):
    result = _huggingnews_result(monkeypatch, keyed=False)
    assert result["keyed"] is False


def test_json_result_omits_keyed_for_tool_without_secret_name(monkeypatch):
    from gpu_agent.web_reach_ensure import ensure_tool
    monkeypatch.setattr("gpu_agent.web_reach_ensure.health_ok", lambda tool, os_key, **k: True)
    tool = {"id": "no-key-tool", "healthCmd": {"linux": "true"}}
    result = ensure_tool(tool, "linux", check_only=True, log=lambda m: None)
    assert "keyed" not in result
