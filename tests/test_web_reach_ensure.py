import json
import subprocess
import sys
import types
import pytest
from gpu_agent import web_reach_ensure as wre


def test_module_imports_and_runs_without_pydantic():
    # F106 finding 4: gpu_agent/web_reach_ensure.py's own header says "STDLIB
    # ONLY. Must run on a bare clone (no .venv, no pydantic)." Proving that by
    # deleting pydantic from sys.modules in *this* process is unreliable (an
    # already-imported submodule can leave partial state, and other tests in
    # this session have already imported pydantic-dependent modules). Instead
    # spawn a genuinely fresh interpreter, install an import hook that raises
    # ImportError for "pydantic" (and anything under it) before gpu_agent is
    # ever touched, then import gpu_agent.web_reach_ensure and exercise the
    # exact call path that broke before the fix: ensure_tool() on a tool that
    # declares `secretName` (which used to reach into
    # gpu_agent.gathering.webreach -> pydantic). A bare clone with no
    # third-party packages installed is exactly this scenario -- the POSIX
    # launcher (scripts/web-reach-ensure) deliberately falls back to system
    # python3 there.
    script = (
        "import builtins, sys\n"
        "_real_import = builtins.__import__\n"
        "def _blocking_import(name, *a, **k):\n"
        "    if name == 'pydantic' or name.startswith('pydantic.'):\n"
        "        raise ImportError('pydantic is not available on a bare clone')\n"
        "    return _real_import(name, *a, **k)\n"
        "builtins.__import__ = _blocking_import\n"
        "from gpu_agent import web_reach_ensure as wre\n"
        "assert 'pydantic' not in sys.modules\n"
        "tool = {'id': 'huggingnews', 'secretName': 'HN_FAKE_TEST_KEY',\n"
        "        'healthCmd': {'linux': 'nonexistent-cmd-xyz', 'windows': 'nonexistent-cmd-xyz',\n"
        "                      'macos': 'nonexistent-cmd-xyz'}}\n"
        "result = wre.ensure_tool(tool, wre.detect_os(), check_only=True, log=lambda m: None)\n"
        "assert result['tool'] == 'huggingnews'\n"
        "assert result['keyed'] is False\n"
        "assert 'pydantic' not in sys.modules\n"
        "print('OK')\n"
    )
    import pathlib
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                        cwd=repo_root, timeout=60)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "OK" in r.stdout


def test_run_survives_non_ascii_output():
    # Real (un-mocked) _run: a command whose output carries bytes that are
    # undecodable under Windows' cp1252 default (0x81/0x8f) must NOT crash the
    # subprocess reader thread — the returncode has to survive. Regression guard
    # for the utf-8/errors=replace fix (agent-reach's localized install output
    # previously raised UnicodeDecodeError and dropped the status).
    cmd = f'"{sys.executable}" -c "import sys; sys.stdout.buffer.write(bytes([0x81,0x8f,0xff]))"'
    r = wre._run(cmd, 30)
    assert r.returncode == 0
    assert isinstance(r.stdout, str)  # decoded in text mode, not bytes


def test_run_child_encodes_emoji_output_on_a_cp1252_machine(monkeypatch):
    # F132 companion guard. The test above covers OUR decoding; this covers the
    # child's own ENCODING, which is the half that killed the 2026-08-31 crawl4ai
    # fetch. PYTHONIOENCODING=cp1252 in the parent simulates the user's Windows box
    # (a child inherits it when no env is passed), so this fails on the pre-fix
    # code even on a UTF-8 CI host.
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    cmd = f'"{sys.executable}" -c "print(chr(0x1f92f))"'
    r = wre._run(cmd, 30)
    assert r.returncode == 0, f"child died under cp1252: {r.stderr!r}"
    assert chr(0x1f92f) in r.stdout


def test_run_env_still_inherits_the_ambient_environment(monkeypatch):
    # The UTF-8 switches must be ADDED to os.environ, never replace it: the health
    # and install commands need PATH, and keyed tools need their credential vars.
    monkeypatch.setenv("F132_CANARY", "still-here")
    cmd = (f'"{sys.executable}" -c '
           f'"import os, sys; sys.stdout.write(os.environ.get(\'F132_CANARY\', \'MISSING\'))"')
    r = wre._run(cmd, 30)
    assert r.returncode == 0
    assert r.stdout.strip() == "still-here"


def test_augment_path_prepends_local_bin_and_is_idempotent(monkeypatch):
    import os
    expanded = os.path.expanduser(os.path.join("~", ".local", "bin"))
    base = os.pathsep.join(["/usr/bin", "/bin"])
    monkeypatch.setenv("PATH", base)
    wre._augment_path()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[0] == expanded
    assert parts[1:] == base.split(os.pathsep)
    # calling again must not duplicate the entry
    wre._augment_path()
    assert os.environ["PATH"].split(os.pathsep).count(expanded) == 1


def _reg():
    return {"tools": [
        {"id": "toolA", "enabled": True,
         "healthCmd": {"windows": "hc-A", "macos": "hc-A", "linux": "hc-A"},
         "install": {"windows": ["i-A"], "macos": ["i-A"], "linux": ["i-A"]}},
        {"id": "toolB", "enabled": True,
         "healthCmd": {"windows": "hc-B", "macos": "hc-B", "linux": "hc-B"},
         "install": {"windows": ["i-B1", "i-B2"], "macos": ["i-B"], "linux": ["i-B"]}},
        {"id": "off", "enabled": False,
         "healthCmd": {"windows": "x", "macos": "x", "linux": "x"},
         "install": {"windows": ["x"], "macos": ["x"], "linux": ["x"]}},
    ]}


def _cp(returncode, stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)


def test_healthy_tool_is_not_installed(monkeypatch):
    calls = []
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: (calls.append(cmd), _cp(0))[1])
    res = wre.ensure_tool(_reg()["tools"][0], "linux", log=lambda m: None)
    assert res == {"tool": "toolA", "status": "ok"}
    assert calls == ["hc-A"]  # only the health check ran, no install


def test_missing_tool_runs_install_cmds_in_order_then_rechecks(monkeypatch):
    calls = []
    # health fails first, install cmds succeed, health passes on recheck
    seq = {"hc-B": [1, 0]}
    def fake_run(cmd, timeout):
        calls.append(cmd)
        if cmd in seq:
            return _cp(seq[cmd].pop(0))
        return _cp(0)
    monkeypatch.setattr(wre, "_run", fake_run)
    res = wre.ensure_tool(_reg()["tools"][1], "windows", log=lambda m: None)
    assert res == {"tool": "toolB", "status": "installed-ok"}
    assert calls == ["hc-B", "i-B1", "i-B2", "hc-B"]  # health, both installs in order, recheck


def test_check_only_never_installs(monkeypatch):
    calls = []
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: (calls.append(cmd), _cp(1))[1])
    res = wre.ensure_tool(_reg()["tools"][0], "macos", check_only=True, log=lambda m: None)
    assert res == {"tool": "toolA", "status": "missing"}
    assert calls == ["hc-A"]  # no install attempted


def test_failed_install_reports_failed(monkeypatch):
    # health always fails AND the install command always fails -> status "failed"
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _cp(1))
    res = wre.ensure_tool(_reg()["tools"][0], "linux", log=lambda m: None)
    assert res["tool"] == "toolA" and res["status"] == "failed"
    assert "detail" in res


def test_ensure_all_skips_disabled_and_uses_os(monkeypatch):
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _cp(0))
    out = wre.ensure_all(_reg(), "linux", log=lambda m: None)
    assert [r["tool"] for r in out] == ["toolA", "toolB"]  # "off" skipped
    assert all(r["status"] == "ok" for r in out)


def test_detect_os_maps_platform(monkeypatch):
    monkeypatch.setattr(wre.platform, "system", lambda: "Windows")
    assert wre.detect_os() == "windows"
    monkeypatch.setattr(wre.platform, "system", lambda: "Darwin")
    assert wre.detect_os() == "macos"
    monkeypatch.setattr(wre.platform, "system", lambda: "Linux")
    assert wre.detect_os() == "linux"


def test_main_check_only_json_exit_code(monkeypatch, capsys, tmp_path):
    reg_file = tmp_path / "reg.json"
    reg_file.write_text(json.dumps(_reg()), encoding="utf-8")
    monkeypatch.setattr(wre, "REGISTRY_PATH", reg_file)
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _cp(0))
    rc = wre.main(["--check-only", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(out["webReach"].keys()) == {"toolA", "toolB"}
    assert out["webReach"]["toolA"]["status"] == "ok"


def test_cli_subcommand_delegates(monkeypatch, capsys, tmp_path):
    from gpu_agent import cli, web_reach_ensure as w
    reg_file = tmp_path / "reg.json"
    reg_file.write_text(json.dumps(_reg()), encoding="utf-8")
    monkeypatch.setattr(w, "REGISTRY_PATH", reg_file)
    monkeypatch.setattr(w, "_run", lambda cmd, timeout: _cp(0))
    rc = cli.main(["web-reach-ensure", "--check-only", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(out["webReach"].keys()) == {"toolA", "toolB"}


# --- Task 5: version_of + unattended-never-installs + drift reporting ---


def _vp(stdout, returncode=0, stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_version_of_extracts_semver_from_agent_reach_style_output(monkeypatch):
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _vp("Agent Reach v1.5.0\n"))
    tool = {"id": "agent-reach", "pin": "1.5.0", "versionCmd": {"linux": "agent-reach --version"}}
    assert wre.version_of(tool, "linux") == "1.5.0"


def test_version_of_extracts_semver_from_pip_show_style_output(monkeypatch):
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _vp("Name: crawl4ai\nVersion: 0.9.0\n"))
    tool = {"id": "crawl4ai", "pin": "0.9.0",
            "versionCmd": {"linux": "pipx runpip crawl4ai show crawl4ai"}}
    assert wre.version_of(tool, "linux") == "0.9.0"


def test_version_of_falls_back_to_pin_when_no_versioncmd():
    tool = {"id": "last30days", "pin": "skill-present"}
    assert wre.version_of(tool, "linux") == "skill-present"


def test_version_of_returns_unknown_when_no_versioncmd_and_no_pin():
    tool = {"id": "mystery"}
    assert wre.version_of(tool, "linux") == "unknown"


def test_version_of_falls_back_to_first_nonempty_line_when_no_semver(monkeypatch):
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _vp("\n  dev-build  \n"))
    tool = {"id": "agent-reach", "pin": "1.5.0", "versionCmd": {"linux": "agent-reach --version"}}
    assert wre.version_of(tool, "linux") == "dev-build"


def test_version_of_returns_unknown_when_stdout_empty(monkeypatch):
    monkeypatch.setattr(wre, "_run", lambda cmd, timeout: _vp(""))
    tool = {"id": "agent-reach", "versionCmd": {"linux": "agent-reach --version"}}
    assert wre.version_of(tool, "linux") == "unknown"


def test_version_of_returns_unknown_on_oserror(monkeypatch):
    def boom(cmd, timeout):
        raise OSError("nope")
    monkeypatch.setattr(wre, "_run", boom)
    tool = {"id": "agent-reach", "pin": "1.5.0", "versionCmd": {"linux": "agent-reach --version"}}
    assert wre.version_of(tool, "linux") == "unknown"


def test_version_of_returns_unknown_on_timeout(monkeypatch):
    def boom(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(wre, "_run", boom)
    tool = {"id": "agent-reach", "pin": "1.5.0", "versionCmd": {"linux": "agent-reach --version"}}
    assert wre.version_of(tool, "linux") == "unknown"


def test_unattended_never_installs_and_carries_version_pin_drift(monkeypatch):
    calls = []
    reg = {"tools": [
        {"id": "toolX", "enabled": True, "pin": "1.5.0",
         "healthCmd": {"linux": "hc-X"},
         "versionCmd": {"linux": "vc-X"},
         "install": {"linux": ["INSTALL-SHOULD-NOT-RUN"]}},
    ]}
    monkeypatch.setattr(wre, "health_ok", lambda tool, os_key, timeout=60: False)

    def fake_run(cmd, timeout):
        calls.append(cmd)
        return _vp("1.5.0")
    monkeypatch.setattr(wre, "_run", fake_run)

    out = wre.ensure_all(reg, "linux", unattended=True, log=lambda m: None)

    assert "INSTALL-SHOULD-NOT-RUN" not in calls
    assert out[0]["status"] == "missing"
    assert out[0]["version"] == "1.5.0"
    assert out[0]["pin"] == "1.5.0"
    assert out[0]["drift"] is False


def test_ensure_all_reports_drift_and_logs_it(monkeypatch):
    logs = []
    reg = {"tools": [
        {"id": "agent-reach", "enabled": True, "pin": "1.5.0",
         "healthCmd": {"linux": "hc"}, "versionCmd": {"linux": "vc"},
         "install": {"linux": ["i"]}},
    ]}

    def fake_run(cmd, timeout):
        if cmd == "hc":
            return _cp(0)  # healthy -> ensure_tool short-circuits to "ok"
        if cmd == "vc":
            return _vp("1.6.0")
        return _cp(0)
    monkeypatch.setattr(wre, "_run", fake_run)

    out = wre.ensure_all(reg, "linux", log=logs.append)

    assert out[0]["status"] == "ok"
    assert out[0]["version"] == "1.6.0"
    assert out[0]["pin"] == "1.5.0"
    assert out[0]["drift"] is True
    assert any("VERSION DRIFT" in m and "agent-reach" in m for m in logs)


def test_cli_unattended_flag_threads_through(monkeypatch, capsys, tmp_path):
    from gpu_agent import cli, web_reach_ensure as w
    reg_file = tmp_path / "reg.json"
    reg_file.write_text(json.dumps(_reg()), encoding="utf-8")
    monkeypatch.setattr(w, "REGISTRY_PATH", reg_file)
    monkeypatch.setattr(w, "health_ok", lambda tool, os_key, timeout=60: False)
    calls = []
    monkeypatch.setattr(w, "_run", lambda cmd, timeout: (calls.append(cmd), _cp(1))[1])
    rc = cli.main(["web-reach-ensure", "--unattended", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1  # tools are "missing" -> non-ok status -> exit 1
    assert all("i-A" not in c and "i-B" not in c for c in calls)  # no install cmds ran
    assert out["webReach"]["toolA"]["status"] == "missing"
