"""F135 — the per-run notebook watermark.

Why this exists. Every notebook (wiki) event is stamped with the scorecard's period label,
and that label is the MONTH. The report used to build WHAT MOVED by asking the notebook for
"everything stamped after <the prior run's label>, up to <this run's label>" — two identical
strings on every run but the month's first, so the window was empty by construction and the
section printed "nothing new cleared the materiality bar" however much had landed.

The fix (user-decided 2026-08-31, Q1 option A): each run records the notebook's sequence
number in this small append-only ledger, one line per run, and WHAT MOVED asks for
"everything added since sequence N" instead.

Shape and guarantees:

- One file per category: ``<store>/<categoryId>/run-markers.jsonl``. Append-only — lines are
  never rewritten, reordered or deleted, matching the store's history discipline.
- Recording is idempotent by ``(asOf, version)``: re-rendering the same scorecard appends
  nothing and changes nothing, so a $0 replay of the report stays a replay.
- Reads are forgiving. A line that will not parse is skipped with a warning rather than
  sinking the brief — a damaged watermark must never cost the executive the report.
- A missing marker widens the window, it never empties it: the caller falls back to the
  honest-restart state, not to a silently blank list.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

from pydantic import BaseModel


class RunMarker(BaseModel):
    """One run's watermark: where the notebook stood when that run rendered its report."""

    categoryId: str
    asOf: str
    version: int
    # The notebook's event count at record time — equivalently, the sequence number the next
    # event will be given. The window question is therefore "seq >= wikiSeq".
    wikiSeq: int
    # The cycle's calendar date, when the caller knows it. Display only: it lets the report
    # name the run it is comparing against instead of the misleading month label.
    storyDate: Optional[str] = None


class RunMarkerLedger:
    """Append-only per-category ledger of :class:`RunMarker` rows.

    SINGLE WRITER ASSUMED. Unlike the wiki log this takes no lock: it is written once per
    category per cycle, by the report step, and a cycle renders its categories in sequence.
    Two `report` runs racing on the same category could both pass the idempotency check and
    append the same `(asOf, version)` twice. That is survivable rather than corrupting —
    `open("a")` is O_APPEND so the lines cannot interleave, and `previous()` excludes the
    current key and resolves ties to the first line — but it is an assumption, not a
    guarantee. Add a lock here if the report ever runs concurrently per category.
    """

    def __init__(self, store_root, category_id: str):
        self.root = pathlib.Path(store_root)
        self.categoryId = category_id
        self.path = self.root / category_id / "run-markers.jsonl"
        self._warned: set[int] = set()   # line numbers already reported as unreadable

    def read(self) -> list[RunMarker]:
        """Every marker on disk, in file (append) order. Unparseable lines are skipped
        with a warning — never raised — so a damaged ledger cannot cost us the report. One
        run reads the ledger two or three times, so each bad line is reported only once."""
        if not self.path.exists():
            return []
        out: list[RunMarker] = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                out.append(RunMarker.model_validate_json(line))
            except Exception as e:  # noqa: BLE001 — skip the bad line, keep the good ones
                if n not in self._warned:
                    self._warned.add(n)
                    print(f"gpu-agent: warning: run-marker ledger {self.path} line {n} is "
                          f"unreadable ({type(e).__name__}); skipping it", file=sys.stderr)
        return out

    def latest(self) -> Optional[RunMarker]:
        rows = self.read()
        return rows[-1] if rows else None

    def previous(self, *, as_of: str, version: int) -> Optional[RunMarker]:
        """The newest marker recorded by a run STRICTLY EARLIER than ``(as_of, version)``.

        Ordering is by the same key the scorecard chain uses — period label first, then
        version — so this is "the run before this one", whether or not this run has a
        marker of its own yet."""
        here = (as_of, version)
        earlier = [m for m in self.read() if (m.asOf, m.version) < here]
        if not earlier:
            return None
        return max(earlier, key=lambda m: (m.asOf, m.version))

    def has(self, *, as_of: str, version: int) -> bool:
        return any((m.asOf, m.version) == (as_of, version) for m in self.read())

    def record(self, marker: RunMarker) -> bool:
        """Append ``marker``. Returns True if a line was written, False if this run already
        had a marker (idempotent by ``(asOf, version)``) — the first recording always wins,
        and nothing already on disk is ever touched."""
        if self.has(as_of=marker.asOf, version=marker.version):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(marker.model_dump(), separators=(",", ":"), sort_keys=False)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
        return True
