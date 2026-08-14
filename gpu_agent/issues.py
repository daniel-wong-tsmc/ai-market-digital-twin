"""gpu_agent/issues.py — F115 known-issues register + deterministic lifecycle rules.

An "issue" is a binding constraint or a weak-and-worsening dimension called out by the
gated scorecard. This module is the pure, code-owned layer: it decides when an issue
opens, reopens, and resolves, and it persists the register + an append-only history.
No brain call happens here — the narrator's per-issue assessment (improved/worsened/
unchanged/not-assessed) is produced elsewhere (Task 2+) and fed in as plain dicts.

Pattern: gpu_agent/thesis.py (book.json + append-only history.jsonl, model_copy-based
updates, indent+sort_keys for byte-stable writes).

No-silent-deletion invariant: every function that returns a register only appends to
`issues` or mutates an existing entry in place — nothing is ever removed or reordered.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

RESOLVE_STREAK = 5

WEAK_RATINGS = {"weak", "very weak"}


# --- models ------------------------------------------------------------------

class IssueTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["binding-constraint", "dimension-weak"]
    label: str  # constraintLabel, or the dimension key


class IssueLatest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["improved", "worsened", "unchanged", "not-assessed"]
    reasoning: str  # "" for not-assessed
    claimFindingIds: list[str] = Field(default_factory=list)
    assessedAsOf: str


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    state: Literal["open", "resolved"]
    openedAsOf: str
    resolvedAsOf: Optional[str] = None
    reopenedAsOf: list[str] = Field(default_factory=list)
    trigger: IssueTrigger
    latest: Optional[IssueLatest] = None
    improvedStreak: int = 0
    worsenedCount: int = 0
    checkCount: int = 0


class IssueRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1]
    categoryId: str
    asOf: str
    issues: list[Issue] = Field(default_factory=list)


class CorruptRegisterError(Exception):
    """register.json exists but cannot be parsed or validated (bad JSON, or a
    hand-edited issue that fails validation — the spec invites hand-editing
    the register, so a typo genuinely reaches this path).

    Deliberately NOT swallowed into an empty register: an empty register
    reads on the page as "no known issues", which would silently discard
    real, unreadable state and present broken data as if it were good data.
    This is a distinct, named error so the cycle log can show plainly which
    step failed and why, instead of a generic JSONDecodeError/ValidationError
    (or, worse, a quiet empty-looking register)."""


# --- id + title derivation -----------------------------------------------------

def _slug(text: str) -> str:
    """lowercase; runs of non-alphanumeric chars -> single '-'; strip leading/trailing '-'."""
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return s.strip("-")


def issue_id(trigger: IssueTrigger) -> str:
    """Deterministic id from the trigger alone: same trigger later -> same id (so a
    resolved issue that fires again is reopened, never duplicated)."""
    if trigger.kind == "binding-constraint":
        return f"constraint-{_slug(trigger.label)}"
    return f"dim-{trigger.label}"


def _title_from_dim_key(key: str) -> str:
    """dimensionRatings has no display label for a dim, so build one: split the camelCase
    key into words, lowercase them, and capitalize only the first word.
    "competitiveStructure" -> "Competitive structure"."""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", key)
    words = [w.lower() for w in spaced.split()]
    if not words:
        return key
    words[0] = words[0].capitalize()
    return " ".join(words)


# --- trigger predicates (shared by open_issues and trigger_still_firing) -------

def _constraint_label(scorecard: dict) -> str:
    cs = scorecard.get("categoryStatus") or {}
    return cs.get("constraintLabel") or ""


def _weak_worsening_dims(scorecard: dict) -> list[str]:
    dims = scorecard.get("dimensionRatings") or {}
    out = []
    for dim, rating_block in dims.items():
        rating_block = rating_block or {}
        rating = (rating_block.get("rating") or "").strip().lower()
        direction = rating_block.get("direction")
        if rating in WEAK_RATINGS and direction == "worsening":
            out.append(dim)
    return out


def _current_triggers(scorecard: dict) -> list[IssueTrigger]:
    triggers: list[IssueTrigger] = []
    label = _constraint_label(scorecard)
    if label:
        triggers.append(IssueTrigger(kind="binding-constraint", label=label))
    for dim in _weak_worsening_dims(scorecard):
        triggers.append(IssueTrigger(kind="dimension-weak", label=dim))
    return triggers


def trigger_still_firing(issue: Issue, scorecard: dict) -> bool:
    """Same predicates as open_issues, evaluated for this one issue's trigger."""
    trig = issue.trigger
    if trig.kind == "binding-constraint":
        return _constraint_label(scorecard) == trig.label and bool(trig.label)
    return trig.label in _weak_worsening_dims(scorecard)


# --- lifecycle: opening / reopening ---------------------------------------------

def open_issues(register: IssueRegister, scorecard: dict, as_of: str
                 ) -> tuple[IssueRegister, list[str]]:
    """Applies both triggers to the scorecard. Existing open issue with the same id is
    left untouched. A resolved issue whose trigger fires again is reopened in place
    (same id, reopenedAsOf grows, streak counters reset, opened/resolved history kept).
    New issues are appended. Never removes or reorders entries."""
    issues = list(register.issues)
    index_by_id = {issue.id: i for i, issue in enumerate(issues)}
    touched: list[str] = []

    for trig in _current_triggers(scorecard):
        iid = issue_id(trig)
        title = trig.label if trig.kind == "binding-constraint" else _title_from_dim_key(trig.label)

        if iid in index_by_id:
            idx = index_by_id[iid]
            existing = issues[idx]
            if existing.state == "open":
                continue
            issues[idx] = existing.model_copy(update={
                "state": "open",
                "reopenedAsOf": existing.reopenedAsOf + [as_of],
                "improvedStreak": 0,
                "worsenedCount": 0,
                # checkCount shares one window with worsenedCount: leaving it
                # at its pre-resolve value while worsenedCount resets to 0
                # would render "worsened 0 of last N checks" using an N that
                # counts checks from before the reopen -- flattering the
                # issue in the reassuring direction. Reset it too so both
                # counters describe only checks since this reopen.
                "checkCount": 0,
            })
            touched.append(iid)
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

    new_register = register.model_copy(update={"issues": issues, "asOf": as_of})
    return new_register, touched


# --- lifecycle: per-cycle assessment / streaks -----------------------------------

def apply_assessments(register: IssueRegister, assessments: list[dict],
                       scorecard: dict, as_of: str) -> tuple[IssueRegister, list[dict]]:
    """assessments: [{"issueId","status","reasoning","claimFindingIds"}]. An empty list
    (fellBack / no issues block) is treated as not-assessed for every currently open
    issue. Assessment for an unknown or already-resolved id is ignored, no crash.

    Streak rules (spec Sec 5):
      improved                                   -> improvedStreak += 1
      unchanged and not trigger_still_firing(...) -> improvedStreak += 1
      worsened                                   -> worsenedCount += 1; improvedStreak = 0
      unchanged and still firing                 -> improvedStreak = 0
      not-assessed                               -> improvedStreak unchanged (frozen)
    checkCount += 1 for every non-not-assessed assessment.
    improvedStreak >= RESOLVE_STREAK -> state="resolved", resolvedAsOf=as_of.

    Returns (register, history_lines): one line per OPEN issue that was actually
    processed. Resolved/unknown ids produce no line.
    """
    open_index_by_id = {
        issue.id: i for i, issue in enumerate(register.issues) if issue.state == "open"
    }

    if not assessments:
        assessments = [
            {"issueId": iid, "status": "not-assessed", "reasoning": "", "claimFindingIds": []}
            for iid in open_index_by_id
        ]

    issues = list(register.issues)
    history_lines: list[dict] = []

    for assessment in assessments:
        iid = assessment["issueId"]
        idx = open_index_by_id.get(iid)
        if idx is None:
            continue  # unknown or resolved id -> ignore, no crash

        issue = issues[idx]
        status = assessment["status"]
        reasoning = assessment.get("reasoning", "")
        claim_finding_ids = assessment.get("claimFindingIds", [])
        still_firing = trigger_still_firing(issue, scorecard)

        improved_streak = issue.improvedStreak
        worsened_count = issue.worsenedCount
        check_count = issue.checkCount
        state = issue.state
        resolved_as_of = issue.resolvedAsOf

        if status != "not-assessed":
            check_count += 1
            if status == "improved":
                improved_streak += 1
            elif status == "unchanged":
                improved_streak = 0 if still_firing else improved_streak + 1
            elif status == "worsened":
                worsened_count += 1
                improved_streak = 0

            if improved_streak >= RESOLVE_STREAK:
                state = "resolved"
                resolved_as_of = as_of

        latest = IssueLatest(
            status=status,
            reasoning=reasoning,
            claimFindingIds=claim_finding_ids,
            assessedAsOf=as_of,
        )

        issues[idx] = issue.model_copy(update={
            "latest": latest,
            "improvedStreak": improved_streak,
            "worsenedCount": worsened_count,
            "checkCount": check_count,
            "state": state,
            "resolvedAsOf": resolved_as_of,
        })

        history_lines.append({
            "asOf": as_of,
            "issueId": iid,
            "status": status,
            "reasoning": reasoning,
            "claimFindingIds": claim_finding_ids,
            "triggerStillFiring": still_firing,
            "streakAfter": improved_streak,
        })

    new_register = register.model_copy(update={"issues": issues, "asOf": as_of})
    return new_register, history_lines


# --- store (register.json + append-only history.jsonl) ---------------------------

def _issues_dir(cat_dir) -> Path:
    return Path(cat_dir) / "issues"


def read_register(cat_dir, category_id: str) -> IssueRegister:
    p = _issues_dir(cat_dir) / "register.json"
    if not p.exists():
        return IssueRegister(schemaVersion=1, categoryId=category_id, asOf="", issues=[])
    try:
        return IssueRegister.model_validate_json(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
        raise CorruptRegisterError(
            f"{p} exists but could not be parsed/validated: {exc}"
        ) from exc


def write_register(cat_dir, register: IssueRegister) -> Path:
    d = _issues_dir(cat_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "register.json"
    body = json.dumps(register.model_dump(), indent=1, sort_keys=True) + "\n"
    p.write_text(body, encoding="utf-8", newline="\n")
    return p


def append_history(cat_dir, lines: list[dict]) -> Path:
    d = _issues_dir(cat_dir)
    p = d / "history.jsonl"
    if not lines:
        # No-op: an empty list must not create a spurious empty history.jsonl
        # (or even the issues/ dir) when nothing has happened yet.
        return p
    d.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(json.dumps(line, sort_keys=True) + "\n")
    return p


def history_has_as_of(cat_dir, as_of: str) -> bool:
    """True if history.jsonl already contains at least one line for this `asOf`
    (i.e. a story date already had `apply_assessments` recorded for it). Used by
    the `issues update` CLI verb to make reruns for the same story date a no-op
    (F115, user-approved 2026-08-10 override of the original append-only-always
    plan -- see final-review.md).

    Same robustness contract as read_history_tail: a missing history.jsonl reads
    as False (first-ever run must work normally, not crash), and a malformed
    line is skipped rather than fatal, matching the safe-read behaviour added
    for the corrupt-history case elsewhere in this module."""
    p = _issues_dir(cat_dir) / "history.jsonl"
    if not p.exists():
        return False
    with p.open("r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if record.get("asOf") == as_of:
                return True
    return False


def read_history_tail(cat_dir, issue_id: str, n: int) -> list[dict]:
    p = _issues_dir(cat_dir) / "history.jsonl"
    if not p.exists():
        return []
    matches: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            # A malformed line -- a truncated final line from a killed
            # process, or a bad hand-edit -- is skipped, not fatal: the rest
            # of the (append-only, mostly-good) history still reads. This is
            # different from a corrupt register.json (see CorruptRegisterError):
            # history is a derived tail used for display/recency, not the
            # single source of truth for open/resolved state, so dropping one
            # bad line doesn't hide real state the way an empty register would.
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if record.get("issueId") == issue_id:
                matches.append(record)
    return matches[-n:] if n > 0 else []
