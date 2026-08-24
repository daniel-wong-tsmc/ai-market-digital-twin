# F123 — Issue Identity Survives a Constraint Relabel: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `open_issues()` minting a twin issue when the brain re-words the
same binding constraint — match the new label against open constraint issues by
token overlap and rename the standing issue in place, id and history intact.

**Architecture:** Three private helpers in `gpu_agent/issues.py`
(`_label_tokens`, `_label_overlap`, `_find_rename_target`) plus a rewritten
per-trigger branch inside `open_issues`. Nothing else in the module moves; no
schema field is added; `history.jsonl` is never read or rewritten on this path.

**Tech Stack:** Python 3, pydantic v2 models, pytest. Shared root venv at
`../../.venv/Scripts/python` — never create a venv.

**Spec:** `docs/superpowers/specs/2026-08-24-f123-issue-relabel-design.md`

## Global Constraints

- Scope is `gpu_agent/issues.py` open-trigger logic and its tests only.
- `RESOLVE_STREAK = 5`; `WEAK_RATINGS = {"weak", "very weak"}` — unchanged.
- `register.json` schema unchanged (`schemaVersion: 1`, same fields).
- `history.jsonl` is append-only: a rename must not delete or rewrite a line.
- No pin may move: F6 baseline, narrator prompt pin, F83 run-cycle fingerprint,
  scoring replay pin. The narrator prompt file must be byte-untouched.
- `issues update` idempotence per story date must keep working.
- Stop words: `{and, or, the, a, an, of, for, in, on, to, with, at, by, is, its}`.
- Generic tokens: `{supply, capacity, shortage, availability, constraint,
  constraints, limits, limited}`.
- Match thresholds: `>= 2` shared tokens, `>= 1` shared non-generic token,
  overlap coefficient `>= 0.5`.
- Tests run from the worktree root: `../../.venv/Scripts/python -m pytest -q`.
- Stage files explicitly by name; run `git log --oneline -1` before every commit.

---

### Task 1: Token-overlap matching helpers

**Files:**
- Modify: `gpu_agent/issues.py` (new section after `issue_id`)
- Test: `tests/test_issues_relabel.py` (create)

**Interfaces:**
- Consumes: `_slug(text) -> str` (existing, `gpu_agent/issues.py`).
- Produces:
  - `_label_tokens(label: str) -> set[str]`
  - `_label_overlap(a: str, b: str) -> tuple[int, int, float]` returning
    `(shared_count, specific_shared_count, ratio)`
  - `_labels_match(a: str, b: str) -> bool`
  - module constants `LABEL_STOP_WORDS`, `GENERIC_LABEL_TOKENS`,
    `RENAME_MIN_SHARED_TOKENS = 2`, `RENAME_MIN_OVERLAP = 0.5`

- [ ] **Step 1: Write the failing test**

```python
"""F123: a re-worded binding constraint must rename the standing issue, not
mint a twin. Real data: the 2026-08 v8 -> v9 -> v10 relabel chain."""
import json

from gpu_agent.issues import (
    Issue,
    IssueRegister,
    IssueTrigger,
    _labels_match,
    _label_overlap,
    _label_tokens,
    append_history,
    apply_assessments,
    open_issues,
    read_history_tail,
)

CATEGORY_ID = "chips.merchant-gpu"

# The three real constraintLabel values, verbatim from
# store/chips.merchant-gpu/2026-08-v{8,9,10}.json.
V8 = "HBM stacked memory supply"
V9 = "stacked memory and server DRAM"
V10 = "Stacked high-bandwidth memory supply"


def test_label_tokens_drops_stop_words_and_lowercases():
    assert _label_tokens(V9) == {"stacked", "memory", "server", "dram"}


def test_label_tokens_empty_for_blank():
    assert _label_tokens("   ") == set()


def test_real_relabel_pairs_all_match():
    assert _labels_match(V8, V9)
    assert _labels_match(V9, V10)
    assert _labels_match(V8, V10)


def test_unrelated_constraints_do_not_match():
    assert not _labels_match(V8, "CoWoS advanced packaging capacity")
    assert not _labels_match(V8, "power and grid capacity")


def test_generic_tokens_alone_do_not_match():
    # Both end in "supply capacity" and share nothing specific.
    assert not _labels_match("wafer supply capacity", "power supply capacity")


def test_overlap_reports_shared_specific_and_ratio():
    shared, specific, ratio = _label_overlap(V8, V10)
    assert shared == 3
    assert specific == 2  # "supply" is generic
    assert ratio == 0.75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py -q`
Expected: FAIL — `ImportError: cannot import name '_label_tokens'`.

- [ ] **Step 3: Write minimal implementation**

Add to `gpu_agent/issues.py` directly after `issue_id`:

```python
LABEL_STOP_WORDS = {
    "and", "or", "the", "a", "an", "of", "for", "in", "on", "to",
    "with", "at", "by", "is", "its",
}

GENERIC_LABEL_TOKENS = {
    "supply", "capacity", "shortage", "availability",
    "constraint", "constraints", "limits", "limited",
}

RENAME_MIN_SHARED_TOKENS = 2
RENAME_MIN_OVERLAP = 0.5


def _label_tokens(label: str) -> set[str]:
    slug = _slug(label)
    if not slug:
        return set()
    return {t for t in slug.split("-") if t and t not in LABEL_STOP_WORDS}


def _label_overlap(a: str, b: str) -> tuple[int, int, float]:
    ta, tb = _label_tokens(a), _label_tokens(b)
    if not ta or not tb:
        return 0, 0, 0.0
    shared = ta & tb
    ratio = len(shared) / min(len(ta), len(tb))
    return len(shared), len(shared - GENERIC_LABEL_TOKENS), ratio


def _labels_match(a: str, b: str) -> bool:
    shared, specific, ratio = _label_overlap(a, b)
    return (shared >= RENAME_MIN_SHARED_TOKENS
            and specific >= 1
            and ratio >= RENAME_MIN_OVERLAP)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add gpu_agent/issues.py tests/test_issues_relabel.py
git commit -F <message file>
```

---

### Task 2: Rename in `open_issues` instead of minting a twin

**Files:**
- Modify: `gpu_agent/issues.py` (`open_issues`, lines ~148-194)
- Test: `tests/test_issues_relabel.py`

**Interfaces:**
- Consumes: `_labels_match`, `_label_overlap` (Task 1); `issue_id(trigger)`,
  `IssueTrigger`, `Issue`, `IssueRegister` (existing).
- Produces: `_find_rename_target(issues: list[Issue], label: str) -> int | None`
  returning the index of the open constraint issue to rename, or `None`.
  `open_issues(register, scorecard, as_of) -> tuple[IssueRegister, list[str]]`
  keeps its signature; a renamed issue's id appears in the returned list.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_issues_relabel.py`:

```python
def _scorecard(label):
    """Minimal scorecard: one binding constraint, no weak+worsening dims."""
    return {
        "categoryStatus": {
            "rating": "Strong",
            "direction": "steady",
            "bottleneck": "bottleneck",
            "reason": "...",
            "constraintLabel": label,
        },
        "dimensionRatings": {},
    }


def _empty_register():
    return IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf="", issues=[])


def test_v8_to_v9_relabel_renames_instead_of_minting_a_twin():
    reg, opened = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    assert [i.id for i in reg.issues] == ["constraint-hbm-stacked-memory-supply"]

    reg, opened = open_issues(reg, _scorecard(V9), "2026-08-21")

    assert len(reg.issues) == 1, "a relabel must not open a twin"
    issue = reg.issues[0]
    assert issue.id == "constraint-hbm-stacked-memory-supply"
    assert issue.title == V9
    assert issue.trigger.label == V9
    assert issue.openedAsOf == "2026-08-19"
    assert issue.reopenedAsOf == []
    assert opened == ["constraint-hbm-stacked-memory-supply"]


def test_three_cycle_relabel_chain_stays_one_issue():
    reg = _empty_register()
    for label, day in ((V8, "2026-08-19"), (V9, "2026-08-21"), (V10, "2026-08-22")):
        reg, _ = open_issues(reg, _scorecard(label), day)
    assert len(reg.issues) == 1
    assert reg.issues[0].id == "constraint-hbm-stacked-memory-supply"
    assert reg.issues[0].title == V10


def test_unrelated_new_constraint_still_mints_a_new_issue():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, opened = open_issues(reg, _scorecard("CoWoS advanced packaging capacity"),
                              "2026-08-21")
    assert len(reg.issues) == 2
    assert opened == ["constraint-cowos-advanced-packaging-capacity"]


def test_rerunning_open_after_a_rename_is_a_no_op():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    before = reg.model_dump()
    reg2, opened = open_issues(reg, _scorecard(V9), "2026-08-21")
    assert opened == []
    assert reg2.model_dump() == before


def test_resolved_issue_is_not_a_rename_target():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg = reg.model_copy(update={
        "issues": [reg.issues[0].model_copy(update={"state": "resolved",
                                                    "resolvedAsOf": "2026-08-20"})]
    })
    reg, opened = open_issues(reg, _scorecard(V9), "2026-08-21")
    assert len(reg.issues) == 2
    assert opened == ["constraint-stacked-memory-and-server-dram"]


def test_exact_id_hit_on_open_issue_refreshes_a_stale_label():
    # v8 -> v9 renames in place (id still derives from v8). A revert to the v8
    # wording finds the standing issue by id; its stored label must follow back,
    # or trigger_still_firing would read False against the live scorecard.
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    reg, opened = open_issues(reg, _scorecard(V8), "2026-08-22")
    assert len(reg.issues) == 1
    assert reg.issues[0].trigger.label == V8
    assert reg.issues[0].title == V8


def test_rename_target_is_deterministic_when_two_open_issues_match():
    reg = IssueRegister(
        schemaVersion=1, categoryId=CATEGORY_ID, asOf="2026-08-21",
        issues=[
            Issue(id="constraint-stacked-memory-and-server-dram",
                  title=V9, state="open", openedAsOf="2026-08-21",
                  trigger=IssueTrigger(kind="binding-constraint", label=V9)),
            Issue(id="constraint-hbm-stacked-memory-supply",
                  title=V8, state="open", openedAsOf="2026-08-19",
                  trigger=IssueTrigger(kind="binding-constraint", label=V8)),
        ],
    )
    reg2, opened = open_issues(reg, _scorecard(V10), "2026-08-22")
    # V10 overlaps V8 at 0.75 and V9 at 0.5 -> the higher ratio wins.
    assert opened == ["constraint-hbm-stacked-memory-supply"]
    assert len(reg2.issues) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py -q`
Expected: FAIL — `test_v8_to_v9_relabel_renames_instead_of_minting_a_twin`
asserts 1 issue, gets 2.

- [ ] **Step 3: Write minimal implementation**

Add above `open_issues`:

```python
def _find_rename_target(issues: list[Issue], label: str) -> Optional[int]:
    """Index of the open binding-constraint issue this re-worded label belongs
    to, or None. Deterministic: best overlap ratio, then most shared tokens,
    then earliest register position (the register really can hold two open
    constraint issues, so ties are reachable)."""
    best: Optional[tuple[float, int, int]] = None
    for idx, issue in enumerate(issues):
        if issue.state != "open" or issue.trigger.kind != "binding-constraint":
            continue
        shared, specific, ratio = _label_overlap(issue.trigger.label, label)
        if (shared < RENAME_MIN_SHARED_TOKENS or specific < 1
                or ratio < RENAME_MIN_OVERLAP):
            continue
        key = (ratio, shared, -idx)
        if best is None or key > best:
            best = key
    return None if best is None else -best[2]
```

Replace the body of the per-trigger loop in `open_issues` with:

```python
    for trig in _current_triggers(scorecard):
        iid = issue_id(trig)
        title = trig.label if trig.kind == "binding-constraint" else _title_from_dim_key(trig.label)

        idx = index_by_id.get(iid)
        if idx is None and trig.kind == "binding-constraint":
            # F123: the brain re-worded the same constraint. Rename the standing
            # issue rather than minting a twin -- a twin strands the real issue's
            # counters, and a stranded issue drifts to a false "Resolved".
            idx = _find_rename_target(issues, trig.label)

        if idx is not None:
            existing = issues[idx]
            if existing.state == "open":
                if (existing.trigger.label != trig.label
                        or existing.title != title):
                    issues[idx] = existing.model_copy(update={
                        "title": title,
                        "trigger": trig,
                    })
                    touched.append(existing.id)
                continue
            issues[idx] = existing.model_copy(update={
                "state": "open",
                "title": title,
                "trigger": trig,
                "reopenedAsOf": existing.reopenedAsOf + [as_of],
                "improvedStreak": 0,
                "worsenedCount": 0,
                "checkCount": 0,
            })
            touched.append(existing.id)
        else:
            new_issue = Issue(
                id=iid,
                title=title,
                state="open",
                openedAsOf=as_of,
                trigger=trig,
            )
            issues.append(new_issue)
            index_by_id[iid] = len(issues) - 1
            touched.append(iid)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py tests/test_issues_lifecycle.py tests/test_issues_cli.py -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add gpu_agent/issues.py tests/test_issues_relabel.py
git commit -F <message file>
```

---

### Task 3: History and counters persist through a rename

**Files:**
- Test: `tests/test_issues_relabel.py`

**Interfaces:**
- Consumes: `open_issues`, `apply_assessments`, `append_history`,
  `read_history_tail` (existing).
- Produces: nothing new — proves the append-only guarantee holds.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_issues_relabel.py`:

```python
def test_history_and_counters_survive_a_rename(tmp_path):
    cat_dir = tmp_path / CATEGORY_ID
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    iid = reg.issues[0].id

    reg, lines = apply_assessments(
        reg,
        [{"issueId": iid, "status": "worsened", "reasoning": "worse",
          "claimFindingIds": ["f-1"]}],
        _scorecard(V8), "2026-08-19",
    )
    append_history(cat_dir, lines)
    history_path = cat_dir / "issues" / "history.jsonl"
    before_bytes = history_path.read_bytes()

    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")

    issue = reg.issues[0]
    assert issue.id == iid, "the id is the thread history hangs on"
    assert issue.worsenedCount == 1
    assert issue.checkCount == 1
    assert issue.latest.reasoning == "worse"
    assert issue.openedAsOf == "2026-08-19"

    # Append-only: the rename touched no history line.
    assert history_path.read_bytes() == before_bytes
    tail = read_history_tail(cat_dir, iid, 5)
    assert [t["status"] for t in tail] == ["worsened"]


def test_renamed_issue_keeps_counting_under_the_new_label():
    """The whole point: after a relabel, an "unchanged" assessment while the
    constraint still fires must NOT count as improvement."""
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    iid = reg.issues[0].id
    reg, _ = apply_assessments(
        reg,
        [{"issueId": iid, "status": "unchanged", "reasoning": "", "claimFindingIds": []}],
        _scorecard(V9), "2026-08-21",
    )
    assert reg.issues[0].improvedStreak == 0
    assert reg.issues[0].state == "open"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py -q`
Expected: both PASS immediately if Task 2 is correct. If either fails, Task 2 is
wrong — fix `open_issues`, not the test.

- [ ] **Step 3: No implementation needed**

These are regression guards for Task 2's behaviour. Only touch
`gpu_agent/issues.py` if they fail.

- [ ] **Step 4: Run the targeted suite**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py tests/test_issues_lifecycle.py tests/test_issues_cli.py tests/narrator -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add tests/test_issues_relabel.py
git commit -F <message file>
```

---

### Task 4: Full suite, pins, and backlog tick

**Files:**
- Modify: `docs/fix-backlog.md` (the F123 checkbox line only)

**Interfaces:**
- Consumes: everything above.
- Produces: a green full suite and evidence that no pin moved.

- [ ] **Step 1: Run the full suite**

Run from the worktree root: `../../.venv/Scripts/python -m pytest -q`
Expected: ~2619 passed, small skip count (a worktree adds one expected skip for
price scrape data).

- [ ] **Step 2: Confirm no pin moved**

Run: `git status --short` and `git diff --stat`
Expected: only `gpu_agent/issues.py`, `tests/test_issues_relabel.py`,
`docs/fix-backlog.md` and the new docs. No narrator prompt file, no baseline or
fingerprint file. If a pin file appears, STOP and record a blocker.

- [ ] **Step 3: Tick the F123 checkbox**

Change only the F123 line in `docs/fix-backlog.md` from `- [ ]` to `- [x]`.

- [ ] **Step 4: Re-run the issues tests after the doc edit**

Run: `../../.venv/Scripts/python -m pytest tests/test_issues_relabel.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add docs/fix-backlog.md docs/superpowers/specs/2026-08-24-f123-issue-relabel-design.md docs/superpowers/plans/2026-08-24-f123-issue-relabel.md .superpowers/sdd/2026-08-24-f123-issue-relabel/QUESTIONS.md
git commit -F <message file>
```
