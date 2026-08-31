"""Idempotent, cross-platform ensure-installed for the web-reach tools.

STDLIB ONLY. Must run on a bare clone (no .venv, no pydantic). Do NOT import
gpu_agent.cli or any third-party package here.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import platform
import re
import subprocess

REGISTRY_PATH = pathlib.Path("registry/web-reach-tools.json")

# Machine-local, gitignored secrets directory (env var wins over this; see
# resolve_secret). Lives here — not in gpu_agent/gathering/webreach.py — because
# this module is STDLIB ONLY and must be importable/callable on a bare clone
# with no .venv/pydantic (see module docstring). webreach.py imports this
# module at load time already, so resolve_secret/SECRETS_DIR flow from here
# outward, never the reverse (F106 finding 4).
SECRETS_DIR = pathlib.Path(".superpowers/secrets")

_HEALTH_TIMEOUT = 60  # health checks are cheap; cap them low

_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")


def _augment_path() -> None:
    # pipx installs its shims into ~/.local/bin, which is NOT on PATH on a pristine
    # machine. Prepend it to this process's PATH so subsequent same-run subprocess
    # calls (install recipes, recheck healthCmd) can find a just-installed shim
    # (e.g. `agent-reach`) even before the shell/profile has picked up `pipx ensurepath`.
    import os
    extra = os.path.expanduser(os.path.join("~", ".local", "bin"))
    cur = os.environ.get("PATH", "")
    parts = cur.split(os.pathsep)
    if extra and extra not in parts:
        os.environ["PATH"] = extra + os.pathsep + cur


def detect_os() -> str:
    s = platform.system().lower()
    if s.startswith("win"):
        return "windows"
    if s == "darwin":
        return "macos"
    return "linux"


def load_registry(path: pathlib.Path = REGISTRY_PATH) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def utf8_env() -> dict[str, str]:
    """F132: the ambient environment plus the two switches that make a Python child
    process speak UTF-8 on its stdout/stderr (and for its own file I/O), regardless
    of the machine's locale. THE one home for this -- `gpu_agent.gathering.webreach`
    imports it from here rather than keeping a second copy, the same way it already
    imports `resolve_secret`/`detect_os` (F106 finding 4: this module is the
    stdlib-only half that must stay importable on a bare clone with no pydantic).

    Why it exists: `subprocess.run(encoding="utf-8")` only says how WE DECODE what
    the child sends. It says nothing about how the child ENCODES. On Windows a Python
    child whose stdout is a pipe falls back to the ANSI code page (cp1252 here), so
    the first astral-plane character in a fetched page kills the child before a byte
    reaches us. Observed live 2026-08-31 (v17): `crwl crawl <tomshardware url>` exited
    1 with "'charmap' codec can't encode character '\\U0001f92f'" and the fetch was
    lost. `PYTHONIOENCODING=utf-8:replace` fixes the child's streams (the `:replace`
    half means it can never die over one unencodable character either); `PYTHONUTF8=1`
    puts it in UTF-8 mode so any file it writes matches.

    This ADDS to `os.environ` rather than replacing it -- children still need PATH
    (including `_augment_path`'s fix-up, which is why this is built per call), HOME,
    proxy settings and any credential env vars. Non-Python tools ignore both variables
    harmlessly; a non-Python tool emitting legacy bytes is not fixed by this, but the
    caller's `errors="replace"` decode turns that into mojibake, not a lost fetch.
    Nothing here touches argv or the shell, so the F88 injection wall (shell=False
    argv, scheme/tool/verb validation) is untouched."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PYTHONUTF8"] = "1"
    return env


def _run(cmd: str, timeout: int) -> subprocess.CompletedProcess:
    # shell=True: registry commands may use the OS shell (cmd.exe on Windows,
    # /bin/sh on POSIX). Each OS's recipe is authored for its own shell.
    # encoding+errors: tool output can carry non-ASCII bytes (e.g. agent-reach's
    # localized doctor text); decode as UTF-8 and never crash on undecodable
    # bytes, so the reader thread can't die and drop the returncode (the Windows
    # cp1252 default raised UnicodeDecodeError on real install output).
    # env (F132): see utf8_env below -- the settings above only control how WE
    # decode the child; utf8_env controls how the child ENCODES in the first place.
    # Built at call time so _augment_path()'s PATH fix-up still reaches the child.
    return subprocess.run(cmd, shell=True, timeout=timeout,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=utf8_env())


def health_ok(tool: dict, os_key: str, timeout: int = _HEALTH_TIMEOUT) -> bool:
    cmd = (tool.get("healthCmd") or {}).get(os_key)
    if not cmd:
        return False
    try:
        return _run(cmd, timeout).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def version_of(tool: dict, os_key: str, timeout: int = _HEALTH_TIMEOUT) -> str:
    """Best-effort installed-version probe for drift reporting. Never raises.

    Runs the tool's versionCmd for os_key and pulls the first semver-shaped
    substring (X.Y or X.Y.Z) out of stdout. Falls back to the stripped first
    non-empty stdout line if no such substring is found. If the tool has no
    versionCmd (e.g. last30days, a versionless skill-dir marker), returns its
    registry `pin` instead (so a present-but-unversioned tool still reports
    something meaningful for the cycle log) -- or "unknown" if there's no pin
    either. A command that times out or can't be launched also yields
    "unknown"; this is a reporting probe, not a gate, so it must never blow up
    ensure_all.
    """
    cmd = (tool.get("versionCmd") or {}).get(os_key)
    if not cmd:
        return tool.get("pin", "unknown")
    try:
        r = _run(cmd, timeout)
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"
    stdout = r.stdout or ""
    m = _VERSION_RE.search(stdout)
    if m:
        return m.group(0)
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            return line
    return "unknown"


def resolve_secret(name: str, *, secrets_dir: pathlib.Path | None = None) -> str | None:
    """Env var wins; else the machine-local gitignored secrets file; else None.
    The value must NEVER be written to any committed file, manifest, or log.

    Canonical (stdlib-only) home for this lookup -- see module docstring and
    F106 finding 4. `gpu_agent.gathering.webreach` re-exports `SECRETS_DIR` and
    wraps this function so `from gpu_agent.gathering.webreach import
    resolve_secret` keeps working, and its own `SECRETS_DIR` stays the name
    existing tests monkeypatch."""
    val = os.environ.get(name)
    if val:
        return val
    path = (secrets_dir if secrets_dir is not None else SECRETS_DIR) / name
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _keyed_state(tool: dict) -> bool | None:
    """True/False if `tool` declares a `secretName` (whether or not it resolves
    locally right now); None if the tool has no key concept at all -- callers
    use None to mean "omit the field", never a misleading False."""
    secret_name = tool.get("secretName")
    if not secret_name:
        return None
    return bool(resolve_secret(secret_name))


def _keyed_suffix(tool: dict) -> str:
    """For a tool with a `secretName`, report whether that secret resolves
    locally (env var or the gitignored secrets file) -- a LOCAL check only,
    never a network call."""
    state = _keyed_state(tool)
    if state is None:
        return ""
    return " (keyed)" if state else " (anonymous-only)"


def ensure_tool(tool: dict, os_key: str, *, check_only: bool = False,
                timeout: int = 600, log=print) -> dict:
    tid = tool["id"]
    suffix = _keyed_suffix(tool)
    keyed = _keyed_state(tool)

    def _result(status: str, **extra) -> dict:
        # Machine-readable twin of the `suffix` log-line text above: any tool
        # declaring a `secretName` carries a `keyed` bool in the RETURNED dict
        # too, so `--json` mode (the only path the daily/live cycle actually
        # reads -- see F106 finding 3) surfaces keyed-vs-anonymous, not just
        # the human log line. Tools with no key concept get no field at all
        # (never a misleading False).
        d = {"tool": tid, "status": status, **extra}
        if keyed is not None:
            d["keyed"] = keyed
        return d

    if health_ok(tool, os_key):
        log(f"web-reach: {tid} ok{suffix}")
        return _result("ok")
    if check_only:
        log(f"web-reach: {tid} missing (check-only; not installing){suffix}")
        return _result("missing")
    cmds = (tool.get("install") or {}).get(os_key) or []
    if not cmds:
        log(f"web-reach: {tid} missing and no install recipe for {os_key}")
        return _result("failed", detail=f"no install recipe for {os_key}")
    for c in cmds:
        log(f"web-reach: {tid} installing -> {c}")
        try:
            r = _run(c, timeout)
        except subprocess.TimeoutExpired:
            return _result("failed", detail=f"timeout: {c}")
        except OSError as e:
            return _result("failed", detail=f"{c}: {e}")
        if r.returncode != 0:
            tail = (r.stderr or "")[-500:]
            return _result("failed", detail=f"install cmd failed ({r.returncode}): {c}\n{tail}")
    if health_ok(tool, os_key):
        log(f"web-reach: {tid} installed-ok{suffix}")
        return _result("installed-ok")
    return _result("failed", detail="healthCmd still failing after install")


def ensure_all(registry: dict, os_key: str | None = None, *, check_only: bool = False,
               unattended: bool = False, timeout: int = 600, log=print) -> list[dict]:
    # unattended is a supply-chain freeze: an unattended (scheduled/unwatched) run must
    # NEVER install or upgrade anything, so it behaves like check_only for the install
    # decision -- reusing check_only's "never call ensure_tool's install path" behavior
    # rather than adding a second install-suppression code path to keep in sync.
    _augment_path()
    os_key = os_key or detect_os()
    effective_check_only = check_only or unattended
    results = []
    for tool in registry.get("tools", []):
        if not tool.get("enabled"):
            continue
        result = ensure_tool(tool, os_key, check_only=effective_check_only,
                              timeout=timeout, log=log)
        # Drift is reported, not enforced: health_ok is NOT made to fail on pin
        # mismatch (that would make interactive ensure_tool try to reinstall on
        # drift, and agent-reach's archive/main.zip install can't converge to a
        # semver pin). Instead every result carries version/pin/drift so the
        # cycle log and CLI --json output surface drift loudly without touching
        # install/health control flow.
        pin = tool.get("pin")
        version = version_of(tool, os_key, timeout=timeout)
        drift = bool(pin) and version != "unknown" and version != pin
        result["version"] = version
        result["pin"] = pin
        result["drift"] = drift
        if drift:
            log(f"web-reach: {tool['id']} VERSION DRIFT installed={version} pinned={pin}")
        results.append(result)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="web-reach-ensure",
                                 description="Idempotently ensure web-reach tools are installed.")
    ap.add_argument("--check-only", action="store_true", help="health-check only; never install")
    ap.add_argument("--unattended", action="store_true",
                    help="scheduled/unwatched run: never install or upgrade (supply-chain "
                         "freeze); report version/pin/drift instead")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable webReach block")
    ap.add_argument("--timeout", type=int, default=600, help="per-install-command timeout (s)")
    args = ap.parse_args(argv)

    registry = load_registry(REGISTRY_PATH)
    log = (lambda m: None) if args.json else print
    results = ensure_all(registry, check_only=args.check_only, unattended=args.unattended,
                          timeout=args.timeout, log=log)
    if args.json:
        print(json.dumps({"webReach": {r["tool"]: r for r in results}}, indent=2))
    return 0 if all(r["status"] in ("ok", "installed-ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
