# F112(a) AMD Quarterly-Fetch Staleness Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last silent-wrong-data path from F110: refuse to append chart-series
data when the discovered/parsed newest quarter is strictly OLDER than the newest quarter
already stored, reporting it as a loud per-series failure instead of a quiet success.

**Architecture:** One new exception (`StalenessViolation`) and one small guard in
`run_fetch`'s per-series loop in `gpu_agent/chartdata/fetch.py`, between `parse()` and
`_append_points()`. The AMD fetcher itself stays pure (string in, data out — it never sees
the store, so it cannot host the check). `run_fetch`'s never-raises contract is untouched:
the violation is raised inside the loop and caught by the existing per-series `except`,
becoming a `failed` entry; the store file is never written.

**Tech Stack:** Python stdlib only (matches the module). Tests: pytest, existing fixtures
`fixtures/chartdata/amd-ir-quarterly-results-landing.html` + `amd-ir-q2-2026.html` whose
newest parsed quarter is `2026-Q2`.

**Spec:** none (bounded path — brainstorm ran in chat; design decisions and provenance are
recorded in this plan's Decision Provenance section below).

## Decision Provenance

All four forks below were question-stopped per the 2026-07-12 rule
(`.superpowers/handoffs/f112a-amd-staleness-QUESTIONS.md`) and answered by the user
interactively, **user-approved 2026-08-20** (relayed by the orchestrator):

1. **Violation behavior: LOG-AND-SKIP.** Dedicated exception inside `run_fetch`'s
   per-series loop; loud `failed` entry in the fetch summary/cycle log; store untouched;
   run continues; `run_fetch`'s never-raises contract preserved.
2. **Equal quarter: ALLOW SAME-OR-NEWER.** Only a strictly-older newest parsed quarter
   trips the check. Same-week re-run idempotence stays.
3. **First-ever fetch / empty or missing store file: check passes vacuously**, normal append.
4. **Placement: GENERIC** — in `gpu_agent/chartdata/fetch.py` `run_fetch`, guarding every
   quarterly series that reaches the loop (all due series are quarterly by construction of
   `due_series`), not AMD-only.

Mechanical choices made by the lane (no design weight):
- Periods are `YYYY-Qn` strings; `max()`/`<` string comparison is correct for 4-digit years
  and is exactly how `_append_points` already sorts (`merged.sort(key=... r["period"])`).
- The guard re-reads the store file via the existing `_read_jsonl`; `_append_points` reads
  it again. Files are tiny (a handful of quarterly rows); clarity beats caching.
- `StalenessViolation` subclasses `Exception` directly (not `ParseFailed` — the page parsed
  fine; the problem is what it parsed relative to the store).

## Global Constraints

- Never touch: run-cycle SKILL.md; pin tests (`tests/test_evals_baseline_pin.py`,
  `tests/test_run_cycle_conformance.py`, `tests/narrator/test_prompt_pin.py`,
  `tests/test_scoring_v1_replay_pin.py`); `store/`; `site/`; `web/`. F112(b)–(f) stay in
  the backlog untouched.
- Python: `../../.venv/Scripts/python` from the worktree root
  (`C:\Users\danie\random_for_fun\.worktrees\f112a-amd-staleness`). Never create a venv.
- Full suite must be green before DONE: `../../.venv/Scripts/python -m pytest -q` —
  expect ~2547 passed, 6 skipped in a worktree.
- `git log --oneline -1` immediately before every commit (concurrent-instance guard).
- Commit per task on branch `f112a-amd-staleness`; STOP before merge.

---

### Task 1: StalenessViolation guard in run_fetch (RED → GREEN)

**Files:**
- Modify: `gpu_agent/chartdata/fetch.py` (new exception near `ParseFailed` ~line 31; new
  helper near `_read_jsonl` ~line 87; guard inside `run_fetch`'s per-series loop between
  `points = fetcher(html_text)` and `n_new = _append_points(...)` ~line 210)
- Test: `tests/test_chartdata_fetch.py` (new section at end of file)

**Interfaces:**
- Consumes: existing `run_fetch(series, as_of_date, earnings_dates, store_dir, fetch_html)`,
  `_read_jsonl(path) -> list[dict]`, test helpers `_series_fixture()`, `_stub_fetch_html()`
  from `tests/test_chartdata_fetch.py`.
- Produces: `StalenessViolation(Exception)` exported from `gpu_agent.chartdata.fetch`;
  helper `_newest_stored_period(store_dir: str, cs: ChartSeries) -> str | None`. Task 2's
  tests rely on the guard's semantics (strictly-older only).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chartdata_fetch.py` (the fixture's newest parsed quarter is
`2026-Q2`; seeding the store with a `2026-Q3` row makes the fetch strictly stale):

```python
# ── F112(a): staleness guard -- a strictly-older newest parsed quarter must
#    become a loud 'failed' entry, never a quiet success (user-approved
#    2026-08-20: log-and-skip; same-or-newer allowed; empty store vacuous). ──

def _seed_store_row(tmp_path, period: str) -> Path:
    """Write a single minimal series row for amdDataCenterRevenue so the
    store's newest period is `period`. Shape mirrors _row()'s output."""
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    row = {
        "indicatorId": "amdDataCenterRevenue",
        "period": period,
        "value": 9.999,
        "unit": "US$ billions",
        "publishedAt": "2026-11-03",
        "capturedAt": "2026-11-03",
        "source": {"url": "https://example.test", "title": "seed"},
        "estimateGrade": False,
        "note": "seed row for staleness tests",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_run_fetch_fails_loudly_when_parsed_quarter_is_older_than_stored(tmp_path):
    series = _series_fixture()
    _seed_store_row(tmp_path, "2026-Q3")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["fetched"] == []
    assert len(result["failed"]) == 1
    failure = result["failed"][0]
    assert failure["id"] == "amdDataCenterRevenue"
    assert "StalenessViolation" in failure["error"]
    # the loud line must name both quarters so the cycle log is diagnosable
    assert "2026-Q2" in failure["error"]
    assert "2026-Q3" in failure["error"]


def test_staleness_violation_leaves_the_store_file_byte_identical(tmp_path):
    series = _series_fixture()
    path = _seed_store_row(tmp_path, "2026-Q3")
    before = path.read_text(encoding="utf-8")

    run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
              fetch_html=_stub_fetch_html())

    assert path.read_text(encoding="utf-8") == before
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run (from the worktree root):
`../../.venv/Scripts/python -m pytest tests/test_chartdata_fetch.py -k "staleness or fails_loudly" -v`

Expected: both FAIL — today the stale fetch succeeds (`fetched` non-empty, older periods
appended, file changed). If they PASS, stop: the premise is wrong.

- [ ] **Step 3: Write the minimal implementation**

In `gpu_agent/chartdata/fetch.py`, add below `ParseFailed`:

```python
class StalenessViolation(Exception):
    """F112(a): raised inside run_fetch's per-series loop when the newest
    period a fetcher parsed is strictly OLDER than the newest period already
    stored for that series -- i.e. link discovery landed on an old release.
    Caught by the same per-series except as every other failure and turned
    into a loud 'failed' entry (user-approved 2026-08-20: log-and-skip);
    same-or-newer passes, and an empty/missing store file passes vacuously."""
```

Add below `_read_jsonl`:

```python
def _newest_stored_period(store_dir: str, cs: ChartSeries) -> str | None:
    """Newest 'period' already on disk for this series, or None when the
    file is missing/empty (first-ever fetch -- staleness check is vacuous).
    Period labels are 'YYYY-Qn' strings, so max()/< compare correctly."""
    rows = _read_jsonl(Path(store_dir) / f"{cs.id}.jsonl")
    periods = [str(r["period"]) for r in rows if r.get("period")]
    return max(periods) if periods else None
```

In `run_fetch`'s per-series loop, between `points = fetcher(html_text)` and
`n_new = _append_points(store_dir, cs, points, as_of_date)`:

```python
                points = fetcher(html_text)
                # F112(a) staleness guard: if the newest quarter we just
                # parsed is strictly older than the newest quarter already
                # stored, link discovery found an OLD release -- appending
                # nothing new would otherwise look like a quiet success.
                newest_stored = _newest_stored_period(store_dir, cs)
                if newest_stored is not None and points:
                    newest_parsed = max(str(p.get("period", "")) for p in points)
                    if newest_parsed < newest_stored:
                        raise StalenessViolation(
                            f"discovered newest quarter {newest_parsed} is older "
                            f"than newest stored {newest_stored} -- refusing "
                            "stale data (link discovery may have found an old "
                            "release)")
                n_new = _append_points(store_dir, cs, points, as_of_date)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_chartdata_fetch.py -v`
Expected: entire file PASSES (the pre-existing idempotence and end-to-end tests prove
same-quarter re-runs and first-ever fetches still succeed).

- [ ] **Step 5: Commit**

`git log --oneline -1` first (HEAD must be your own last commit), then:

```bash
git add gpu_agent/chartdata/fetch.py tests/test_chartdata_fetch.py
git commit -m "feat(chartdata): F112(a) staleness guard -- refuse strictly-older parsed quarter"
```

---

### Task 2: Edge-case regression tests + full suite

Pins down the two user-approved edge cases explicitly (equal quarter allowed; first-ever
fetch vacuous) so a future change can't silently tighten the guard to `<=`, then proves
the whole suite green. These are regression tests expected to PASS immediately — the RED
phase for the feature happened in Task 1.

**Files:**
- Test: `tests/test_chartdata_fetch.py` (same new section)

**Interfaces:**
- Consumes: `_seed_store_row` from Task 1, `run_fetch`, `_series_fixture()`,
  `_stub_fetch_html()`.
- Produces: nothing new — verification only.

- [ ] **Step 1: Write the edge-case tests**

```python
def test_equal_newest_quarter_is_allowed_and_backfills_older_periods(tmp_path):
    """Store's newest == parse's newest (2026-Q2): NOT a violation
    (user-approved 2026-08-20: same-or-newer allowed). The fetch succeeds
    and the two older parsed periods backfill as new rows."""
    series = _series_fixture()
    _seed_store_row(tmp_path, "2026-Q2")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 2}]


def test_first_ever_fetch_with_no_store_file_passes_the_staleness_check(tmp_path):
    """Missing store file: staleness check is vacuous (user-approved
    2026-08-20); the fetch appends all parsed periods normally."""
    series = _series_fixture()

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 3}]
```

- [ ] **Step 2: Run the file, then the full suite**

Run: `../../.venv/Scripts/python -m pytest tests/test_chartdata_fetch.py -v`
Expected: all PASS. If `test_equal_newest_quarter...` fails on `newPoints: 2` or
`test_first_ever_fetch...` on `newPoints: 3`, check the fixture's parsed period count
(the detail fixture yields 3 three-months-ended columns) before touching the guard.

Then: `../../.venv/Scripts/python -m pytest -q`
Expected: ~2547 passed, 6 skipped (test_change_pricefeed skips outside the root
checkout). ANY pin test red → STOP, question-stop; never re-record a pin.

- [ ] **Step 3: Commit**

`git log --oneline -1` first, then:

```bash
git add tests/test_chartdata_fetch.py
git commit -m "test(chartdata): F112(a) edge-case pins -- equal quarter allowed, empty store vacuous"
```

---

### Task 3: Backlog tick + code review + DONE sentinel

**Files:**
- Modify: `docs/fix-backlog.md` (F112 item: mark sub-item (a) done with date + one-line
  outcome; leave (b)–(f) untouched)
- Create: `.superpowers/handoffs/f112a-amd-staleness-DONE.md` (in the ROOT checkout's
  `.superpowers/handoffs/`, where the orchestrator watches)

- [ ] **Step 1: Update the backlog line for F112(a) only**

Edit the `(a)` sentence inside the F112 item to record completion, e.g. append:
`— DONE 2026-08-20 (lane f112a-amd-staleness): generic staleness guard in
chartdata/fetch.py run_fetch; strictly-older parsed quarter -> loud 'failed' entry,
store untouched; same-or-newer + first-fetch pass (user-approved decisions).`
Do not renumber or touch (b)–(f).

- [ ] **Step 2: Request code review**

Invoke superpowers:requesting-code-review on the branch diff (`git diff main...HEAD`).
Address findings via superpowers:receiving-code-review; re-run the full suite after any
change.

- [ ] **Step 3: Verification before completion**

Invoke superpowers:verification-before-completion: re-run
`../../.venv/Scripts/python -m pytest -q` and paste the actual tail line into the DONE
sentinel. No green claim without fresh output.

- [ ] **Step 4: Commit backlog tick, write DONE sentinel**

```bash
git add docs/fix-backlog.md docs/superpowers/plans/2026-08-20-f112a-amd-staleness.md
git commit -m "docs: tick F112(a) in backlog; add f112a lane plan"
```

Then write `.superpowers/handoffs/f112a-amd-staleness-DONE.md` (root checkout) with:
branch name, commit hashes, suite tail line, decision provenance recap, and the explicit
note that merge is left to the user. STOP — no merge, no push unless the user says so.
