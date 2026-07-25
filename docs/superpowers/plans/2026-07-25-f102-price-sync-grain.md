# F102 — price-sync Month-Grain Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `price-sync` accepts month-grain `--as-of` (resolved to month-end) and degrades any malformed as-of to the documented warning path — no traceback can escape `sync_series` on bad time input.

**Architecture:** One new parser `_parse_as_of` in `gpu_agent/price_local.py`, used by `sync_series`; the CLI verb keeps exit-0-with-warning semantics. Tests beside the existing price tests.

**Tech Stack:** Python 3 (`.venv/Scripts/python`; worktree `../../.venv/Scripts/python`), stdlib, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-f102-price-sync-grain-design.md`. ONLY `gpu_agent/price_local.py` + its tests + (if needed for exit semantics) the `price-sync` handler in `gpu_agent/cli.py` change. Frozen core, brains, prompts, registries, eval + narrator fixtures byte-untouched; all four pins green; `git diff --stat fixtures/ registry/ gpu_agent/evals gpu_agent/narrator gpu_agent/dashboard` EMPTY at every commit.
- Day-grain behavior byte-identical (existing tests must pass untouched; any that fail = question-stop).
- No `date.today()` — `as_of` stays the only time input.
- Worktree `.worktrees/f102-price-grain`, branch `f102-price-grain`. Never touch root `store/`.

**Verified facts (2026-07-25):** the crash: `sync_series` @price_local.py:282-285 slices `as_of[2:4]+as_of[5:7]+as_of[8:10]` → `_yymmdd_date` @:206 does `int("")` on month-grain input. `_month_end_yymmdd(period: "YYYY-MM") -> str` exists in the same module (true calendar month-end, already short-month-safe). `sync_series(data_dir, series_dir, as_of, benchmarks=None)` returns warnings (read the exact return shape + the existing warning-append pattern in Step 0 — the staleness warning @:292-297 shows it). CLI verb `price-sync --as-of <asOf>` (run-cycle SKILL.md:367); handler in `cli.py` (locate in Step 0).

---

### Task 1: The parser + graceful degradation

**Files:**
- Modify: `gpu_agent/price_local.py` (+ `gpu_agent/cli.py` ONLY if the handler lets exceptions escape)
- Test: `tests/test_price_local.py` (append; if price tests live under another name, Step 0 finds it and the task report says so)

**Interfaces:**
- `_parse_as_of(as_of: str) -> str | None` — returns YYMMDD: `YYYY-MM-DD` → direct (validated: `datetime.date` round-trip, not slicing); `YYYY-MM` → `_month_end_yymmdd(as_of)`; anything else → `None` (never raises).
- `sync_series` calls it first; `None` → append warning `f"price-sync: unusable as-of {as_of!r} — skipped (no rows written)"` to the existing warning channel and return WITHOUT touching `series_dir`.
- CLI: verify the handler prints warnings and exits 0 on the skip path (it should already, per the never-fatal contract; if it re-raises, wrap per the existing warning-print pattern).

- [ ] **Step 0:** read the exact `sync_series` return shape + warning pattern, the CLI handler, and the price test file's name/style.
- [ ] **Step 1: Write the failing tests**

```python
# appended to the price tests file (adjust helper names to the file's own fixtures)
import datetime as dt
from gpu_agent.price_local import _parse_as_of


def test_parse_as_of_day_grain():
    assert _parse_as_of("2026-07-17") == "260717"


def test_parse_as_of_month_grain_true_month_end():
    assert _parse_as_of("2026-07") == "260731"
    assert _parse_as_of("2026-02") == "260228"
    assert _parse_as_of("2028-02") == "280229"      # leap year


def test_parse_as_of_rejects_garbage_without_raising():
    for bad in ("", "garbage", "2026", "2026-7", "2026-07-99", "26-07-01"):
        assert _parse_as_of(bad) is None


def test_sync_series_month_grain_completes(tmp_path):
    # the four-sighting reproduction (v11/v14/v15/v17): month-grain as-of must
    # sync cleanly. Arrange a minimal data_dir using THIS test file's existing
    # fixture helpers (Step 0); then:
    #   result = sync_series(data_dir, tmp_path / "series", as_of="2026-07")
    # assert: at least one series file written; no date-related warning in result.
    ...


def test_sync_series_bad_as_of_warns_and_writes_nothing(tmp_path):
    # result = sync_series(data_dir, series_dir, as_of="garbage")
    # assert: the "unusable as-of" warning present; series_dir contents byte-identical
    # (snapshot dir listing + file bytes before/after).
    ...
```

Write the two `sync_series` bodies fully against the real fixtures found in Step 0.

- [ ] **Step 2:** run → FAIL (`_parse_as_of` not defined; month-grain path crashes with ValueError — capture that traceback in the task report as the bug's last appearance).
- [ ] **Step 3:** implement per Interfaces.
- [ ] **Step 4:** run the price test file → all green INCLUDING pre-existing day-grain tests untouched. CLI check: `../../.venv/Scripts/python -m gpu_agent.cli price-sync --as-of garbage --data <fixture> --series <tmp>` (flags per the real handler) exits 0 with the warning printed.
- [ ] **Step 5:** commit `fix(f102): price-sync accepts month-grain as-of; malformed input degrades to warning`.

---

### Task 2: Close-out — suite, pins, backlog, sentinel

- [ ] **Step 1:** full suite → green; forbidden-diff EMPTY; four pins green (named in the report).
- [ ] **Step 2:** `docs/fix-backlog.md` F102 entry: append "FIXED <date> — `_parse_as_of` (day + month grain, month-end anchor), graceful skip on malformed input (spec/plan refs). Live criterion: next cycle's price-sync refreshes store/series and the front-page rent gauge drops its aging mark."
- [ ] **Step 3:** sentinel `.superpowers/handoffs/f102-price-grain-DONE.md` ("STOP before merge — only the user merges").
- [ ] **Step 4:** final commit, explicit paths.

---

## Self-Review

1. **Spec coverage:** §2.1 parser → T1 (both grains, month-end via the existing helper, validated not sliced); §2.2 degradation → T1 (warning path, no partial writes, CLI exit 0); §4 tests → T1 (units incl. leap-year, reproduction, no-write guard, CLI) + T2 (suite/pins); §4 live criterion → T2 backlog note, post-merge. §3 constraints → Global Constraints (single-file scope, day-grain untouched, no today()).
2. **Placeholders:** the two `sync_series` test bodies are comment-structured with explicit asserts enumerated and a binding instruction to the real fixtures located in Step 0 — same justification as F96 Task 2; everything else is complete.
3. **Type consistency:** `_parse_as_of(as_of) -> str | None` used consistently; warning text string identical in T1 interface and test; branch/sentinel names consistent (`f102-price-grain`).
