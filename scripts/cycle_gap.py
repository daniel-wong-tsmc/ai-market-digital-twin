"""Session-start banner: how stale is the newest completed daily cycle?

F83 scheduler fix (user-approved 2026-08-20). Run by scripts/session-orient so a
silent scheduler gap is visible the moment a session opens in this repo.

Reads the completion date (``capturedAt``) from ``store/cycle-log.json``:

* completed today / yesterday -> one calm status line
* 2+ days ago -> a WARNING line with the day count
* file missing, unreadable, or dateless -> print nothing

This runs inside session orientation, so it must never break it: every failure
mode is silence, and the exit code is always 0.
"""
import argparse
import datetime
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-log", default=str(REPO_ROOT / "store" / "cycle-log.json"))
    parser.add_argument("--today", default=None, help="override today's date (tests)")
    args = parser.parse_args(argv)

    try:
        data = json.loads(pathlib.Path(args.cycle_log).read_text(encoding="utf-8"))
        captured = str(data["capturedAt"])[:10]
        last = datetime.date.fromisoformat(captured)
        today = (datetime.date.fromisoformat(args.today) if args.today
                 else datetime.date.today())
    except Exception:
        return 0

    gap = (today - last).days
    if gap <= 0:
        print("last completed cycle: today (%s)" % captured)
    elif gap == 1:
        print("last completed cycle: yesterday (%s)" % captured)
    else:
        print("WARNING: last completed cycle was %d days ago (%s) - the scheduled "
              "daily may be failing silently; check ~/.claude/jobs/logs." % (gap, captured))
    return 0


if __name__ == "__main__":
    sys.exit(main())
