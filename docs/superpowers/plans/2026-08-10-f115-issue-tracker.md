# F115 Issue Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A persistent "Known issues" tracker: deterministic triggers open issues from the scorecard, the narrator assesses each open issue every cycle (improved/worsened/unchanged + reasoned note), sustained improvement resolves them, and a new section renders it all at the bottom of the category page.

**Architecture:** New `gpu_agent/issues.py` owns the register (`store/<cat>/issues/register.json`) + append-only `history.jsonl` and all lifecycle rules. The narrator answer schema gains an `issues` block (artifact schemaVersion 3); gate check 9, citation audit `issue:<id>` claims, and the prompt+pin move in lockstep. New CLI verb `issues` (`open`/`update`); run-cycle sub-steps (d4)/(e3b); dashboard schema 1.1→1.2 with a required `issues` section and a new React `Issues` component.

**Tech Stack:** Python (repo venv), pydantic v2, pytest; web/ React + vitest for schema 1.2 + render.

**Spec:** `docs/superpowers/specs/2026-08-10-f115-issue-tracker-design.md`.

## Global Constraints

- **GATED LANE — exclusive narrator-prompt lane.** Worktree `.worktrees/f115-issue-tracker`, branch `f115-issue-tracker`; python `../../.venv/Scripts/python`; `npm --prefix web`. No other narrator-touching lane may run while this is open.
- MUST NOT TOUCH: `fixtures/evals/` (F6 stays byte-untouched), `gpu_agent/evals/`, `gpu_agent/extraction/`, `gpu_agent/judgment/`, `gpu_agent/scoring.py`, `gpu_agent/report.py`, `registry/indicators.json`, `registry/series-indicators.json`, `registry/freshness.json`, `registry/chart-series.json`.
- Exactly TWO pins move, each once, each deliberately: the narrator prompt pin (`fixtures/narrator/prompt-pin.json`, Task 4 ONLY, same commit as the prompt/inputs change) and the F83 run-cycle fingerprint (Task 9 ONLY). F6 and the scoring-v1-replay pin must stay green and unmoved.
- Lifecycle constants (spec §5): `RESOLVE_STREAK = 5`; a worsened or unchanged-while-still-triggering cycle RESETS the streak; `not-assessed` freezes it (neither advances nor resets).
- No-silent-deletion invariant: no code path removes a register entry (proved by test, Task 1).
- Issue reasoning copy rules (gate-enforced, prompt-stated): ≤ 60 words, ≥ 1 sentence, plain English, existing banned-word lint applies, `claimFindingIds` non-empty and resolving.
- All issue steps are non-blocking in the cycle: failures log `issues-open|issues-update: failed`, never kill the run.
- Question-stop rule verbatim (CLAUDE.md) in every task brief. Commit per task; `git log --oneline -1` before each commit.

## File Structure

```
gpu_agent/issues.py                       NEW  register/history models + lifecycle rules + IO
gpu_agent/narrator/schema.py              MOD  IssueAssessment; issues on NarratorAnswer; schemaVersion 3
gpu_agent/narrator/gate.py                MOD  check 9: issue assessments
gpu_agent/narrator/inputs.py              MOD  openIssues key (Task 4 ONLY, with prompt+pin)
gpu_agent/narrator/prompt.py              MOD  issues section (Task 4 ONLY)
fixtures/narrator/prompt-pin.json         MOD  Task 4 ONLY, same commit
fixtures/narrator/hash-input.json         MOD  Task 4 ONLY (representative openIssues entry)
gpu_agent/citation_audit.py               MOD  claims_from_issues, keyed issue:<id>
gpu_agent/cli.py                          MOD  `issues` verb (open / update)
gpu_agent/dashboard/export_json.py        MOD  issues payload section; schemaVersion 1.2
web/schema/dashboard.schema.json          MOD  1.2: required issues section
web/src/load.ts                           MOD  Issue types + parse
web/src/components/Issues.tsx             NEW  Known-issues section
web/src/App.tsx                           MOD  <Issues> between Dimensions and Footer
tests/test_issues_lifecycle.py            NEW
tests/test_narrator_issues_schema.py      NEW
tests/test_narrator_issues_gate.py        NEW
tests/test_citation_audit_issues.py       NEW
tests/test_issues_cli.py                  NEW
tests/test_export_json_issues.py          NEW
web/src/__tests__/issues.test.tsx         NEW
.claude/skills/run-cycle/SKILL.md + tests/test_run_cycle_conformance.py  MOD  Task 9 only
```

---

### Task 1: `gpu_agent/issues.py` — models + lifecycle rules

**Files:** Create `gpu_agent/issues.py`; Test `tests/test_issues_lifecycle.py`.

**Interfaces — Produces (consumed by every later task):**

```python
RESOLVE_STREAK = 5

class IssueTrigger(BaseModel):          # extra="forbid" on every model here
    kind: Literal["binding-constraint", "dimension-weak"]
    label: str                          # constraintLabel, or the dimension key

class IssueLatest(BaseModel):
    status: Literal["improved", "worsened", "unchanged", "not-assessed"]
    reasoning: str                      # "" for not-assessed
    claimFindingIds: list[str]
    assessedAsOf: str

class Issue(BaseModel):
    id: str
    title: str
    state: Literal["open", "resolved"]
    openedAsOf: str
    resolvedAsOf: Optional[str] = None
    reopenedAsOf: list[str] = []
    trigger: IssueTrigger
    latest: Optional[IssueLatest] = None
    improvedStreak: int = 0
    worsenedCount: int = 0
    checkCount: int = 0

class IssueRegister(BaseModel):
    schemaVersion: Literal[1]
    categoryId: str
    asOf: str
    issues: list[Issue]

def issue_id(trigger: IssueTrigger) -> str
    # "constraint-<slug>" / "dim-<key>"; slug = lowercase, non-alnum runs -> "-",
    # strip leading/trailing "-". Same trigger later -> same id (reopen, not dup).

def open_issues(register: IssueRegister, scorecard: dict, as_of: str) -> tuple[IssueRegister, list[str]]
    # Applies BOTH triggers to the scorecard; returns (new register, ids opened/reopened).
    # (a) categoryStatus.constraintLabel truthy -> trigger ("binding-constraint", constraintLabel),
    #     title = constraintLabel verbatim.
    # (b) each dimensionRatings[dim] with rating.strip().lower() in {"weak","very weak"}
    #     AND direction == "worsening" -> trigger ("dimension-weak", dim),
    #     title = dimensionRatings[dim] has no display label; use the dim key split on
    #     camelCase into words, capitalized ("competitiveStructure" -> "Competitive structure").
    # Existing open issue with same id -> untouched. Resolved issue with same id ->
    # state="open" again, reopenedAsOf appended, counters (streak) reset to 0,
    # openedAsOf/resolvedAsOf/history preserved. Never removes or reorders entries;
    # new issues append.

def trigger_still_firing(issue: Issue, scorecard: dict) -> bool
    # Same predicates as open_issues, evaluated for one issue's trigger.

def apply_assessments(register: IssueRegister, assessments: list[dict],
                      scorecard: dict, as_of: str) -> tuple[IssueRegister, list[dict]]
    # assessments: [{"issueId","status","reasoning","claimFindingIds"}] from the narrator
    # (empty list = fellBack / no issues block -> every open issue gets a not-assessed latest).
    # Per OPEN issue: set latest, checkCount += 1 (except not-assessed: latest set, counters frozen).
    # Streak rules (spec §5):
    #   improved                                   -> improvedStreak += 1
    #   unchanged and not trigger_still_firing(...) -> improvedStreak += 1
    #   worsened                                   -> worsenedCount += 1; improvedStreak = 0
    #   unchanged and still firing                 -> improvedStreak = 0
    #   not-assessed                               -> improvedStreak unchanged
    # improvedStreak >= RESOLVE_STREAK -> state="resolved", resolvedAsOf=as_of.
    # Returns (register, history_lines): one line per open issue:
    #   {"asOf","issueId","status","reasoning","claimFindingIds","triggerStillFiring","streakAfter"}
    # Resolved issues get NO line. Assessment for an unknown/resolved id -> ignored with
    # no crash (the gate prevents it upstream; this layer stays tolerant).

def read_register(cat_dir: Path, category_id: str) -> IssueRegister
    # Missing file -> empty register (schemaVersion 1, issues=[]).
def write_register(cat_dir: Path, register: IssueRegister) -> Path
    # <cat_dir>/issues/register.json, UTF-8, LF, indent=1, sort_keys — byte-stable.
def append_history(cat_dir: Path, lines: list[dict]) -> Path
    # Appends JSONL to <cat_dir>/issues/history.jsonl; never truncates.
def read_history_tail(cat_dir: Path, issue_id: str, n: int) -> list[dict]
    # Last n lines for one issue, oldest first (feeds inputs + the render history strip).
```

- [ ] **Step 1: Write failing tests** covering, at minimum:
  - `issue_id` slugging ("HBM4 stacked-memory supply" → `constraint-hbm4-stacked-memory-supply`; `bottleneck` dim → `dim-bottleneck`).
  - open: fresh register + the real v5 scorecard shape (inline a trimmed dict with `categoryStatus` + `dimensionRatings` copied from `store/chips.merchant-gpu/2026-08-v5.json`) opens the constraint issue AND `dim-bottleneck` + `dim-moat` (both Weak+worsening); Mixed+worsening does NOT open; second `open_issues` call is a no-op (idempotent).
  - reopen: resolved issue + trigger firing again → open, reopenedAsOf grows, streak 0, same id, no duplicate entry.
  - streaks: improved ×5 → resolved at exactly 5; improved ×4 then worsened → streak 0, still open; unchanged with trigger gone → counts toward the streak; unchanged still-firing → resets; not-assessed after improved ×3 → streak stays 3, checkCount unchanged.
  - history: apply on 2 open issues appends exactly 2 lines with `streakAfter` correct; append twice → 4 lines (never truncates).
  - **no-silent-deletion:** for every function returning a register, `{i.id} for old issues` ⊆ `{i.id} for new issues` — parametrize over `open_issues` and `apply_assessments`.
  - IO: `read_register` on a missing dir → empty register; write → read round-trips; `write_register` twice on same data → byte-identical file.
- [ ] **Step 2: Run tests — FAIL (module missing).**
- [ ] **Step 3: Implement `gpu_agent/issues.py`.**
- [ ] **Step 4: Tests PASS; full suite green.**
- [ ] **Step 5: Commit** `feat(f115): issue register + lifecycle rules`.

---

### Task 2: Narrator schema — `IssueAssessment`, artifact v3

**Files:** Modify `gpu_agent/narrator/schema.py`; Test `tests/test_narrator_issues_schema.py`.

**Interfaces — Produces:**

```python
class IssueAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issueId: str
    status: Literal["improved", "worsened", "unchanged"]
    reasoning: str
    claimFindingIds: list[str]

class NarratorAnswer(BaseModel):
    ...existing fields...
    issues: Optional[list[IssueAssessment]] = None   # None = pre-F115 answer

class StoryArtifact(NarratorAnswer):
    schemaVersion: Literal[1, 2, 3]                  # was Literal[1, 2]
```

- [ ] **Step 1: Failing tests** — a v3 artifact dict with an `issues` list validates and round-trips; a v2 artifact (copy the shape of `store/chips.merchant-gpu/story/2026-08-08.json` — has `bullets`, no `issues`) still validates; a v1 artifact (no bullets either) still validates; `extra="forbid"` rejects unknown keys inside an assessment; `status: "resolved"` is rejected (narrator may not resolve — only the streak rule does).
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite (nothing downstream chokes on the widened Literal). Step 5: Commit** `feat(f115): IssueAssessment schema, artifact v3`.

---

### Task 3: Gate — check 9, issue assessments

**Files:** Modify `gpu_agent/narrator/gate.py`; Test `tests/test_narrator_issues_gate.py`.

**Interfaces:** `gate_narrator(answer, inputs, cfg)` returns `list[str]`; issue failures append. `inputs` gains an `openIssues` key in Task 4 — the gate treats a MISSING `openIssues` key as an empty list (so pre-F115 callers/tests stay green; do NOT add it to the required-keys loop at the top of `gate_narrator`). Reuse the existing banned-word lint helper (`lint_story_copy` usage in check 4) for reasoning text — do not duplicate detection logic.

Checks (each its own specific message):
1. When `inputs["openIssues"]` is non-empty: `answer.issues` must be present with EXACTLY one assessment per open issue id — a missing id, an unknown id, and a duplicate id are each named in their own violation.
2. When `openIssues` is empty/missing: `answer.issues` must be None or empty ("narrator invented issue assessments").
3. Each `reasoning`: non-empty, ≤ 60 words (`len(reasoning.split())`), banned-word lint clean.
4. Each `claimFindingIds`: non-empty, every id in `inputs.findings` (same membership check scenes use).

- [ ] **Step 1: Failing tests** — minimal valid answer + inputs with 2 open issues, mutated one way per test: all-clean passes (no issue-related failures); missing one assessment; extra unknown id; duplicate id; empty reasoning; 61-word reasoning; unknown finding id; empty claimFindingIds; openIssues empty but issues present; **inputs WITHOUT the `openIssues` key + `issues=None` answer → zero issue-related failures (pre-F115 compatibility).**
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite (existing narrator gate tests untouched and green). Step 5: Commit** `feat(f115): narrator gate check 9 — issue assessments`.

---

### Task 4: Inputs + prompt + pin re-record (SAME COMMIT — the only narrator-pin touch)

**Files:** Modify `gpu_agent/narrator/inputs.py`, `gpu_agent/narrator/prompt.py`, `fixtures/narrator/hash-input.json`, `fixtures/narrator/prompt-pin.json`; Tests: extend `tests/test_narrator_issues_gate.py`-adjacent inputs tests (new test in `tests/narrator/` matching where `build_narrator_inputs` is already tested), and the existing pin test is the tripwire.

**Interfaces — `build_narrator_inputs` returns one new key:**

```python
"openIssues": [
    {"id": i.id, "title": i.title,
     "trigger": {"kind": i.trigger.kind, "label": i.trigger.label},
     "recent": [{"asOf": h["asOf"], "status": h["status"]}
                 for h in read_history_tail(cat_dir, i.id, 8)]}
    for i in read_register(cat_dir, category_id).issues if i.state == "open"
]
```

(Import `read_register`/`read_history_tail` from `gpu_agent.issues`. Empty/missing register → `"openIssues": []` — deterministic, ordered as the register lists them.)

Prompt addition (place alongside the existing output-shape instructions; wording may be tuned to house style, meaning may not):

> When `openIssues` is not empty, also write `issues`: for EVERY listed open issue, exactly
> one entry `{issueId, status, reasoning, claimFindingIds}`. `status` is your judgment from
> today's findings: "improved", "worsened" or "unchanged". `reasoning` is one or two plain
> sentences, at most 60 words, saying WHY — name the number or event that moved your call,
> and cite the findings it comes from in `claimFindingIds`. Judge only from the findings you
> are given; if today's evidence says nothing about an issue, say "unchanged" and say that no
> new evidence arrived. Never invent an issue that is not in `openIssues`.

- [ ] **Step 1: Narrator pin test GREEN before (baseline).**
- [ ] **Step 2: Implement the inputs key + failing inputs test** (a store fixture with a register containing 1 open + 1 resolved issue → `openIssues` has exactly the open one, with its history tail; no register → `[]`). Add the prompt section + `issues` to the answer-shape description. Add a representative `openIssues` entry (one open issue, 2-entry `recent`) to `fixtures/narrator/hash-input.json` so the pin exercises the new section. **Run pin test — RED (proves the pin sees all of it).**
- [ ] **Step 3: Re-record the pin via the recorded recipe in `gpu_agent/narrator/pin.py`** (regenerate the hash from the emitted bundle — never hand-edit).
- [ ] **Step 4: Pin test GREEN; full suite; `git status` shows ONLY `inputs.py`, `prompt.py`, `hash-input.json`, `prompt-pin.json` + the new inputs test changed.**
- [ ] **Step 5: ONE commit** `feat(f115): narrator sees and assesses open issues (pin re-recorded in lockstep)`.

---

### Task 5: Citation audit covers issue reasoning

**Files:** Modify `gpu_agent/citation_audit.py`; Test `tests/test_citation_audit_issues.py`.

**Interfaces — Produces (mirror `claims_from_bullets` at `citation_audit.py:62` exactly):**

```python
def claims_from_issues(art: StoryArtifact) -> list[Claim]:
    # One claim per assessment, keyed `issue:<issueId>` (issues DO carry their own id,
    # unlike bullets -- so the key uses it, per spec §6). None/empty -> [] (v1/v2
    # artifacts audit exactly as before).
    if not art.issues:
        return []
    return [Claim(claimKey=f"issue:{a.issueId}", text=a.reasoning,
                  findingIds=tuple(a.claimFindingIds))
            for a in art.issues]
```

Wire it into the same collection point where `claims_from_bullets` is consumed (read that call site and add `claims_from_issues` beside it).

- [ ] **Step 1: Failing tests** — an artifact with an issue whose reasoning number matches its cited finding → audited, not flagged; a reasoning number tracing to nothing → flagged with key `issue:constraint-hbm4-stacked-memory-supply`; a v2 artifact (no issues) → claim list identical to before (regression pinned with a golden count over the 2026-08-08 story artifact).
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite. Step 5: Commit** `feat(f115): citation audit covers issue assessments`.

---

### Task 6: CLI verb `issues` (open / update)

**Files:** Modify `gpu_agent/cli.py`; Test `tests/test_issues_cli.py`.

**Interfaces — two subactions, mirroring the existing verb style (see `coverage-record` and `narrator` handlers):**

```
gpu-agent issues open   --category chips.merchant-gpu --store store [--as-of YYYY-MM-DD]
gpu-agent issues update --category chips.merchant-gpu --store store --story-date YYYY-MM-DD
```

- `open`: load latest monthly scorecard (reuse the same `latest_monthly`/`monthly_best_files` selection the narrator inputs use), `open_issues(...)`, `write_register`, print JSON `{"opened": [...], "open": N}` to stdout, exit 0. Missing scorecard → error message to stderr, exit 1 (the run-cycle step treats non-zero as `issues-open: failed`, non-blocking).
- `update`: read the story artifact for `--story-date` via `StoryStore`; assessments = `[a.model_dump() for a in artifact.issues]` if present else `[]` (a fellBack day or a pre-F115 artifact yields not-assessed entries — exactly spec §6's fallback); `apply_assessments(...)` with the latest scorecard; `write_register` + `append_history`; print JSON `{"assessed": N, "notAssessed": M, "resolved": [...]}`; exit 0. Missing artifact → stderr + exit 1.
- `--as-of` defaults to the scorecard's own `asOf` (open) / `--story-date` (update) — the verb takes no wall-clock reading, keeping reruns deterministic.

- [ ] **Step 1: Failing tests** (drive `main([...])` in-process against a tmp store, like the existing CLI tests do) — open on a store with the v5-shaped scorecard writes a register with the constraint + 2 dimension issues and prints their ids; update with a story artifact assessing both → register `latest` set, history has lines, second update run for the same date appends again (append-only is the contract; the run-cycle invokes it once); update when the artifact has NO issues block → all open issues `not-assessed`, streaks frozen; update reaching streak 5 → prints the resolved id; missing artifact → exit 1, register untouched.
- [ ] **Step 2: FAIL. Step 3: Implement (parser + dispatch + handler, same file regions as the other verbs). Step 4: PASS + full suite. Step 5: Commit** `feat(f115): issues CLI verb (open/update)`.

---

### Task 7: Exporter — `issues` section, schema 1.2 (both sides of the contract)

**Files:** Modify `gpu_agent/dashboard/export_json.py`, `web/schema/dashboard.schema.json`; regenerate `fixtures/dashboard/golden-dashboard.json`; Test `tests/test_export_json_issues.py` (+ extend the existing schema/export tests where they assert `"1.1"`).

**Interfaces — payload section (consumed by Task 8):**

```json
"issues": {
  "open": [
    {"id": "constraint-hbm4-stacked-memory-supply",
     "title": "HBM4 stacked-memory supply",
     "status": "worsened",                    // improved|worsened|unchanged|not-assessed
     "assessedAsOf": "2026-08-10",
     "trackedSince": "2026-08-10",
     "worsenedCount": 3, "checkCount": 5,
     "reasoning": "…narrator's note ('' when not-assessed)…",
     "sources": [ {…same ref objects bullets use…} ],
     "history": [ {"asOf": "2026-08-09", "status": "unchanged"}, … ]   // last ≤ 15, oldest first
    }
  ],
  "resolved": [
    {"id": "…", "title": "…", "resolvedAsOf": "2026-08-01",
     "finalNote": "…last reasoning before resolve ('' if none)…"}
  ]
}
```

- Exporter: in `build_dashboard_payload` (payload dict at `export_json.py:405-414`), read the register via `gpu_agent.issues.read_register` + per-issue `read_history_tail(cat_dir, id, 15)`; `sources` = the same `refs_for_finding_ids(...)`-style helper the bullets use over `latest.claimFindingIds`; missing register → `{"open": [], "resolved": []}` (honest empty, NOT an error — the determinism and validate-before-write contracts hold). `schemaVersion` → `"1.2"`.
- Schema: bump `const` to `"1.2"`; add `issues` to `properties` AND `required`; `$defs` gains `issueOpen`/`issueResolved` with `additionalProperties: false`, status enum incl. `not-assessed`, `history` items `{asOf, status}` strict.

- [ ] **Step 1: Failing tests** — schema: a payload with the issues section validates; a payload WITHOUT `issues` is REJECTED; unknown key inside an open issue REJECTED; exporter: store fixture with a register (1 open assessed, 1 open not-assessed, 1 resolved) → section built exactly as above, history capped at 15, oldest first; no register dir → empty lists, payload still validates; byte-identical on rerun.
- [ ] **Step 2: FAIL. Step 3: Implement both sides + regenerate the golden fixture. Step 4: pytest + `npm --prefix web test` PASS (contract test sees the regenerated golden + new schema). Step 5: Commit** `feat(f115): dashboard schema 1.2 — known-issues section`.

---

### Task 8: Web — `Issues` component

**Files:** Create `web/src/components/Issues.tsx`; Modify `web/src/load.ts` (types + `parseDashboard`), `web/src/App.tsx` (render between `Dimensions` and `Footer`, App.tsx:121-138 region); Test `web/src/__tests__/issues.test.tsx` (+ contract test already regenerated in Task 7).

Render rules (spec §3; existing components are the style/token authority — read `Dimensions.tsx` + `Bullets.tsx` first and reuse their patterns, incl. `SourceMark` for source badges):
1. Section heading "Known issues". If `open` and `resolved` are BOTH empty, render nothing at all (no orphan heading — the F110 review precedent).
2. Per open issue row: title; a status chip — improved / worsened / no change, dated `assessedAsOf` (`not-assessed` renders the chip text "Not assessed this cycle" in the muted style, never a fresh-looking chip); tenure line `tracked since <Mon YYYY> · worsened <worsenedCount> of last <checkCount> checks`; the reasoning sentence(s) with `SourceMark` badges inline at sentence end (F113 pattern); a history strip of one small tick per history entry (span with a class per status — `tick-improved` / `tick-worsened` / `tick-unchanged` / `tick-not-assessed` — title-attr the date).
3. `resolved` non-empty → a collapsed `<details>` block "Resolved" listing title, close date, `finalNote`.
4. All copy comes from the payload; the component adds no market claims of its own.

- [ ] **Step 1: Failing tests** — payload with 2 open (one assessed, one not-assessed) + 1 resolved: two rows, correct chip texts, tenure line rendered, 15 ticks with per-status classes, `<details>` present; empty-issues payload → no "Known issues" text in the DOM; not-assessed chip uses the muted class and the exact string "Not assessed this cycle".
- [ ] **Step 2: FAIL. Step 3: Implement (types in `load.ts` first — parse rejects a payload missing `issues`, matching the 1.2 schema). Step 4: `npm --prefix web test` + `npm --prefix web run build` PASS. Step 5: Commit** `feat(f115): known-issues section renders`.

---

### Task 9: Run-cycle sub-steps + F83 re-record (THE ONLY F83 TOUCH)

**Files:** Modify `.claude/skills/run-cycle/SKILL.md` + `tests/test_run_cycle_conformance.py` (`EXPECTED_STEPS` at :159-186 + the SKILL.md fingerprint comment, same commit — F109/F113 precedent).

Two sub-steps inside step 3, matching the house voice of (d3)/(e4):
- **(d4) issues-open (deterministic, no LLM)** — after (d3): `gpu-agent issues open --category <cat> --store store`; log `issues-open: done|failed` in the cycle log; failure never blocks.
- **(e3b) issues-update (deterministic, no LLM)** — after (e3) narrator, BEFORE (e4) citation audit: `gpu-agent issues update --category <cat> --store store --story-date <date>`; a fellBack narrator day still runs it (yielding not-assessed entries); log `issues-update: done|failed`.

`EXPECTED_STEPS` gains `("d4", "issues-open")` after `("d3", "coverage record")` and `("e3b", "issues-update")` after `("e3", "narrator")`.

- [ ] **Step 1: Conformance test GREEN before (baseline).**
- [ ] **Step 2: Add both SKILL.md sub-steps + both `EXPECTED_STEPS` entries; regenerate the fingerprint FROM `EXPECTED_STEPS` (`hashlib.sha256(repr(EXPECTED_STEPS)...)`) and re-stamp the SKILL.md comment.**
- [ ] **Step 3: Full suite green; `git status` shows NO `fixtures/` change.**
- [ ] **Step 4: Commit** `feat(f115): issues-open/issues-update run-cycle sub-steps (F83 re-record)`.

---

### Task 10: Lane gates + DONE sentinel

- [ ] **Step 1:** Full pytest + `npm --prefix web test` + `npm --prefix web run build` green. The four pins: F6 green AND `git diff main --name-only -- fixtures/evals` EMPTY; narrator pin green at its NEW hash (moved exactly once, in Task 4's commit — verify with `git log --oneline -- fixtures/narrator/prompt-pin.json` showing ONE lane commit); scoring replay green; F83 green at its NEW fingerprint (moved exactly once, Task 9).
- [ ] **Step 2:** Forbidden diff empty: `git diff main --name-only -- gpu_agent/evals gpu_agent/extraction gpu_agent/judgment gpu_agent/scoring.py gpu_agent/report.py fixtures/evals registry/` returns nothing.
- [ ] **Step 3:** No-silent-deletion + append-only spot-proof: `tests/test_issues_lifecycle.py` deletion tests present and green; grep `gpu_agent/` for `history.jsonl` shows append-mode writes only.
- [ ] **Step 4:** End-to-end dry run against a COPY of the real store in tmp: `issues open` → register with today's real constraint + weak dimensions; hand-write a v3 story artifact assessing them; `issues update` → history lines; `dashboard-json` → payload validates, section present; load the built page from disk and eyeball the section (open rows, ticks, resolved block). Fix before declaring done.
- [ ] **Step 5:** Write `.superpowers/handoffs/f115-issue-tracker-DONE.md` — state, deferred minors, the spec §10 live criteria (next scheduled cycle: register opens ≥ the binding-constraint issue, narrator assesses with reasoning, history.jsonl gains its first line, section renders live; an honest not-assessed fallback day is a later check, not a failure), and the ⚠ REQUIRED post-merge data refresh (F110/F113 precedent: the strict 1.2 app must never point at 1.1 data — rebuild `dashboard.json` + `site/` on merged main in the same session as the merge). Commit. **STOP — only the user merges.**

## Self-Review Notes

- Spec coverage: §3 render → Task 8; §4 data model → Task 1; §5 lifecycle → Task 1 (+ CLI Task 6); §6 narrator+guardrails → Tasks 2/3/4/5; §7 wiring/export/render → Tasks 6/7/8/9; §8 testing → per-task steps + Task 10; §9 sequencing + §10 criteria → Task 10 sentinel.
- The 60-word reasoning cap and the "never invent an issue" rule appear in both Task 3 (gate) and Task 4 (prompt) — spec §6 wording is the single source of truth; implementers keep them in sync.
- `openIssues` deliberately lands in Task 4, NOT Task 3, so the pin moves exactly once; the gate treats a missing key as empty to stay green in between.
- Constraint-label slugs can drift if the scorecard rewords `constraintLabel` (a new id would open while the old stays); accepted for v1 — the user can merge by editing the register (spec §4 override). Noted for the DONE sentinel's deferred list.
- Task 7 regenerates the golden dashboard fixture; Task 8's contract test depends on it — Tasks 7→8 are ordered, all other tasks are independent after Task 1/2.
