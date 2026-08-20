# F83 scheduler fix (user-approved 2026-08-20): session-start banner saying how stale the
# newest completed cycle is, so a silent scheduler gap is visible within one glance.
# scripts/cycle_gap.py is run by scripts/session-orient; it must NEVER break orientation,
# so every failure mode is silence + exit 0.
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "cycle_gap.py"


def run_gap(tmp_path, cycle_log, today):
    args = [sys.executable, str(SCRIPT), "--today", today]
    if cycle_log is not None:
        log_path = tmp_path / "cycle-log.json"
        log_path.write_text(json.dumps(cycle_log), encoding="utf-8")
        args += ["--cycle-log", str(log_path)]
    else:
        args += ["--cycle-log", str(tmp_path / "does-not-exist.json")]
    return subprocess.run(args, capture_output=True, text=True, cwd=str(REPO_ROOT))


def entry(captured_at):
    return {"asOf": "2026-08", "capturedAt": captured_at, "mode": "daily",
            "runDir": "work/daily-x", "entries": [{"status": "done"}]}


def test_cycle_completed_today_is_calm():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = run_gap(pathlib.Path(d), entry("2026-08-20T00:00:00Z"), "2026-08-20")
    assert r.returncode == 0
    assert "last completed cycle: today (2026-08-20)" in r.stdout
    assert "WARNING" not in r.stdout


def test_cycle_completed_yesterday_is_calm():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = run_gap(pathlib.Path(d), entry("2026-08-19T00:00:00Z"), "2026-08-20")
    assert r.returncode == 0
    assert "last completed cycle: yesterday (2026-08-19)" in r.stdout
    assert "WARNING" not in r.stdout


def test_two_plus_day_gap_warns_with_day_count():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = run_gap(pathlib.Path(d), entry("2026-08-15T00:00:00Z"), "2026-08-20")
    assert r.returncode == 0
    assert "WARNING: last completed cycle was 5 days ago (2026-08-15)" in r.stdout


def test_missing_file_is_silent_and_exit_zero():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = run_gap(pathlib.Path(d), None, "2026-08-20")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_garbage_file_is_silent_and_exit_zero(tmp_path):
    bad = tmp_path / "cycle-log.json"
    bad.write_text("{not json", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--today", "2026-08-20", "--cycle-log", str(bad)],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_missing_captured_at_is_silent(tmp_path):
    log = tmp_path / "cycle-log.json"
    log.write_text(json.dumps({"entries": []}), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--today", "2026-08-20", "--cycle-log", str(log)],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_default_cycle_log_is_repo_store(tmp_path):
    # No --cycle-log: reads store/cycle-log.json relative to the repo the script lives in.
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--today", "2099-01-01"],
        capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0
    # The real store log exists in this repo, so a line must be printed
    # regardless of the cwd the hook happens to run from.
    assert "last completed cycle" in r.stdout
