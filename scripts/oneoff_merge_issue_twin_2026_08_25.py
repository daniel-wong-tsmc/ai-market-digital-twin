"""One-off, user-approved data cleanup (2026-08-25).

The known-issues register for chips.merchant-gpu held two OPEN constraint issues
for one real problem (stacked-memory / HBM supply), minted before F123 taught
`open_issues` to rename a re-worded constraint instead of duplicating it. F123
stops new twins; the pair that already existed is a data fix, which is this
script.

User decision (interactive, 2026-08-25): keep the older issue
`constraint-stacked-memory-and-server-dram`, fold the twin
`constraint-stacked-high-bandwidth-memory-supply` into it, and drop the twin.
The survivor keeps its title, trigger label and all three counters -- the two
issues were checked on the same days, so summing checkCount would double-count.
The only thing it gains is the twin's `latest.claimFindingIds`, unioned in after
its own. `history.jsonl` is deliberately NOT touched: it is the audit trail.

`constraint-hbm4-memory-allocation-per-accelerator` is a different question
(allocation per accelerator, not total supply) and is left alone.

Idempotent: a second run finds the twin already gone and its findings already
folded in, and exits 0 without writing. It refuses, loudly, if the survivor is
missing or if the register is in any other unexpected shape.

Usage (from the repo or worktree root):
    .venv/Scripts/python scripts/oneoff_merge_issue_twin_2026_08_25.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gpu_agent.issues import (  # noqa: E402
    IssueRegister,
    read_register,
    write_register,
)

CATEGORY_ID = "chips.merchant-gpu"
CAT_DIR = _REPO_ROOT / "store" / CATEGORY_ID

SURVIVOR_ID = "constraint-stacked-memory-and-server-dram"
TWIN_ID = "constraint-stacked-high-bandwidth-memory-supply"

ALREADY_MERGED = "already merged"
MERGED = "merged"


class MergeRefused(Exception):
    """The register is not in a shape this one-off knows how to merge."""


def merge_twin(register: IssueRegister) -> tuple[IssueRegister, str]:
    """Fold the twin into the survivor. Returns (register, human-readable note).

    Raises MergeRefused if the survivor is absent -- that means this is not the
    register this cleanup was written for, and guessing would be worse than
    stopping."""
    issues = list(register.issues)
    survivor_idx = next((i for i, iss in enumerate(issues)
                         if iss.id == SURVIVOR_ID), None)
    twin_idx = next((i for i, iss in enumerate(issues) if iss.id == TWIN_ID), None)

    if survivor_idx is None:
        raise MergeRefused(
            f"survivor issue {SURVIVOR_ID!r} is not in this register "
            f"(ids present: {[iss.id for iss in issues]}). Refusing to merge: "
            "this is not the register the 2026-08-25 cleanup was written for."
        )

    if twin_idx is None:
        return register, (
            f"{ALREADY_MERGED}: twin {TWIN_ID!r} is not in the register and "
            f"survivor {SURVIVOR_ID!r} is present. Nothing to do."
        )

    survivor = issues[survivor_idx]
    twin = issues[twin_idx]

    survivor_ids = list(survivor.latest.claimFindingIds) if survivor.latest else []
    twin_ids = list(twin.latest.claimFindingIds) if twin.latest else []
    union = survivor_ids + [f for f in twin_ids if f not in survivor_ids]

    if survivor.latest is not None:
        issues[survivor_idx] = survivor.model_copy(update={
            "latest": survivor.latest.model_copy(
                update={"claimFindingIds": union}),
        })
    elif twin.latest is not None:
        # The survivor has never been assessed but the twin has: carry the
        # twin's finding ids across rather than silently dropping them.
        issues[survivor_idx] = survivor.model_copy(update={"latest": twin.latest})

    del issues[twin_idx]

    return register.model_copy(update={"issues": issues}), (
        f"{MERGED}: dropped {TWIN_ID!r}; {SURVIVOR_ID!r} claimFindingIds -> {union}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    ap.add_argument("--cat-dir", default=str(CAT_DIR),
                    help="category store directory (default: chips.merchant-gpu)")
    args = ap.parse_args(argv)

    cat_dir = Path(args.cat_dir)
    register = read_register(cat_dir, CATEGORY_ID)
    before = json.dumps(register.model_dump(), sort_keys=True)

    try:
        merged, note = merge_twin(register)
    except MergeRefused as exc:
        print(f"REFUSED: {exc}")
        return 2

    after = json.dumps(merged.model_dump(), sort_keys=True)
    print(note)
    if before == after:
        print("no change -- register left untouched")
        return 0
    if args.dry_run:
        print("dry run -- register left untouched")
        return 0

    path = write_register(cat_dir, merged)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
