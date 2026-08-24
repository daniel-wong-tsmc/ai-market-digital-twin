# F128 Codify Unattended-Run Mechanics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move four accepted-practice unattended-run mechanics out of per-cycle `deviations` logging and into the run-cycle skill's prescriptive text, pinned by a rot-lint test.

**Architecture:** Prose-only change to two skill files plus the compliance matrix and the backlog, guarded by one new stdlib-only rot-lint test. One new `## Unattended-run mechanics` section in the run-cycle skill is the single authority; the seam steps cross-reference it rather than restating it. Nothing inside `## Procedure` gains or loses a step, so the F83 conformance fingerprint stays put.

**Tech Stack:** Markdown skill text (`.claude/skills/`), pytest (stdlib-only lint test), shared root venv at `../../.venv/Scripts/python`.

**Spec:** `docs/superpowers/specs/2026-08-24-f128-codify-mechanics-design.md`

## Global Constraints

- Run tests from the worktree root: `../../.venv/Scripts/python -m pytest -q`. Never create a venv.
- **Do not add, rename, reorder or remove any step in `## Procedure`.** No new line inside that section may start with `### <n>.` or `**(<label>) ` — both shapes are read by the F83 parser as a step.
- **Do not place a `## ` header between `## Procedure` and `## Daily mode`.** The F83 parser bounds the Procedure section at the next `## `.
- The F83 fingerprint comment in `.claude/skills/run-cycle/SKILL.md` (`sha256=ce869181dbe4c8ba0782e04acffa4da33d69fc9930f2d33a74405985f3dc7505`) is **byte-untouched**. It is verified unmoved, never re-recorded (spec §3, QUESTIONS.md D3).
- No change to `gpu_agent/`, emitted prompts, `registry/`, or `store/`. F6 baseline and the narrator prompt pin must stay green and unmoved.
- Stage files explicitly by name. Run `git log --oneline -1` immediately before every commit. Commit on `f128-codify-mechanics` only; never merge, never push.
- Exact tool set for the gatherer agent type, copied verbatim: `Read, Write, WebSearch, WebFetch`.
- Exact agent type name, copied verbatim: `web-gatherer`.

---

### Task 1: Rot-lint test pinning the codified mechanics

**Files:**
- Create: `tests/test_unattended_mechanics_codified.py`

**Interfaces:**
- Consumes: nothing (pure stdlib; reads files from the repo root).
- Produces: the assertions Task 2 and Task 3 must satisfy. Module constants `SKILL` (run-cycle SKILL.md path), `GATHER` (gather-category SKILL.md path), `AGENT` (`.claude/agents/web-gatherer.md`), and helper `_procedure_text()` returning the text between `## Procedure` and the next `## ` header.

- [ ] **Step 1: Write the failing test**

```python
"""F128 - rot-lint over the codified unattended-run mechanics.

The user ruled on 2026-08-22 that four standing per-cycle deviations are accepted
practice. This lint keeps them written down: without it, a later prose edit can
delete a clause and cycles silently start re-flagging accepted practice as a
deviation again. Pure stdlib, no product imports (the compliance-matrix lint's
pattern) - it pins ANCHORS and cross-references, never whole paragraphs, so
ordinary prose editing stays possible.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "run-cycle" / "SKILL.md"
GATHER = ROOT / ".claude" / "skills" / "gather-category" / "SKILL.md"
AGENT = ROOT / ".claude" / "agents" / "web-gatherer.md"

SECTION_HEADER = "## Unattended-run mechanics"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(text, header):
    """The lines from `header` up to (not including) the next top-level `## `."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    return "\n".join(lines[start:end])


def _procedure_text():
    return _section(_text(SKILL), "## Procedure")


def test_mechanics_section_exists_and_sits_outside_procedure():
    text = _text(SKILL)
    assert SECTION_HEADER in text, (
        f"{SKILL} lost the '{SECTION_HEADER}' section - the four accepted-practice "
        "mechanics have no home and cycles will re-flag them as deviations (F128)")
    assert text.index(SECTION_HEADER) < text.index("## Procedure"), (
        "the mechanics section must sit BEFORE '## Procedure': the F83 parser bounds "
        "the Procedure section at the next '## ' header, so a section inside it would "
        "silently truncate the pinned step list")


def test_procedure_section_contains_no_top_level_header():
    """Tripwire for the placement rule above (F83 parser guard)."""
    body = _procedure_text().splitlines()[1:]
    assert not [l for l in body if l.startswith("## ")], (
        "a '## ' header appeared inside '## Procedure' - this truncates the F83 "
        "pinned step list silently")


def test_all_four_mechanics_are_named():
    sec = _section(_text(SKILL), SECTION_HEADER)
    for anchor in ("web-gatherer", "byte-exact", "rejoin", "above-fold", "F67",
                   "answer file"):
        assert anchor in sec, f"mechanics section does not mention {anchor!r} (F128)"


def test_brain_dispatch_keeps_the_no_reach_property():
    sec = _section(_text(SKILL), SECTION_HEADER)
    for forbidden in ("WebSearch", "WebFetch", "Bash"):
        assert forbidden in sec, (
            f"the brain-dispatch clause must name {forbidden} as forbidden - "
            "Read-own-prompt + one-Write only preserves the no-reach property if the "
            "tool set excludes the reaching tools (F128)")
    assert re.search(r"exactly ONE Write|exactly one Write", sec), (
        "the brain-dispatch clause must state the one-Write cap verbatim (F128)")


def test_gatherer_dispatch_names_the_restricted_agent_type():
    for path in (SKILL, GATHER):
        assert "subagent_type: web-gatherer" in _text(path) or \
               '"web-gatherer"' in _text(path), (
            f"{path} does not name the restricted web-gatherer agent type - the F88 "
            "wall is back to being merely instructed (F128)")


def test_web_gatherer_agent_definition_holds_exactly_the_walled_tool_set():
    line = next(l for l in _text(AGENT).splitlines() if l.startswith("tools:"))
    assert line.strip() == "tools: Read, Write, WebSearch, WebFetch", (
        f"web-gatherer tool set drifted: {line!r} - the F88 injection wall requires "
        "exactly Read, Write, WebSearch, WebFetch (no Bash, ever)")


def test_step_six_carries_the_deviation_rule():
    step6 = _section(_procedure_text(), "### 6.")
    assert "deviation" in step6.lower(), (
        "Step 6 (finalize the cycle log) carries no deviation guidance - this is why "
        "every cycle re-flagged accepted practice (F128)")
    assert "NOT deviations" in step6 or "not deviations" in step6, (
        "Step 6 must say explicitly that the four codified mechanics are NOT "
        "deviations, or cycles keep logging them (F128)")


def test_tool_less_absolutes_survive_only_where_the_ruling_allows():
    """extraction stays genuinely tool-less; the 7(d2) contrast note still refers to
    the tool-less brain pattern. Every OTHER seam must point at the mechanics section
    instead of asserting an absolute the harness cannot honour."""
    hits = [l for l in _procedure_text().splitlines()
            if re.search(r"tool-?less", l, re.I)]
    for line in hits:
        assert ("Extraction" in line or "extraction" in line
                or "NOT the tool-less" in line), (
            f"stale tool-less absolute still prescribed: {line.strip()!r} - "
            "judge/thesis/implication/narrator dispatch Read-own-prompt + one Write "
            "(F128 mechanic 1)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_unattended_mechanics_codified.py -q`
Expected: FAIL — `StopIteration` / assertion errors, because `## Unattended-run mechanics` does not exist yet, `subagent_type: web-gatherer` is nowhere, and Step 6 has no deviation guidance. (`test_procedure_section_contains_no_top_level_header` and `test_web_gatherer_agent_definition_holds_exactly_the_walled_tool_set` should already PASS — they guard existing state.)

- [ ] **Step 3: No implementation in this task**

The test file is the deliverable. Implementation lands in Tasks 2 and 3.

- [ ] **Step 4: Commit the failing test**

```bash
git log --oneline -1
git add tests/test_unattended_mechanics_codified.py
git commit -m "test(F128): failing rot-lint for the codified unattended-run mechanics"
```

---

### Task 2: Codify the mechanics in the run-cycle skill

**Files:**
- Modify: `.claude/skills/run-cycle/SKILL.md` (new section after `## Invariants`; prose edits in steps 3(a), 3(b), 3(c), 3(e), 3(e2), 3(e3), 3(f), 6)
- Test: `tests/test_unattended_mechanics_codified.py`, `tests/test_run_cycle_conformance.py`

**Interfaces:**
- Consumes: the assertions from Task 1.
- Produces: the section header string `## Unattended-run mechanics (accepted practice — user ruling 2026-08-22)` and the cross-reference phrase `Unattended-run mechanics` that seam steps use.

- [ ] **Step 1: Insert the mechanics section**

Insert immediately after the `## Invariants` block and before `## Inputs`:

```markdown
## Unattended-run mechanics (accepted practice — user ruling 2026-08-22)

These four are how an unattended cycle actually runs. The user ruled on them interactively on
2026-08-22 (F128). They are **prescription, not deviation** — do not re-derive them per run, and do
not log them in the cycle log's `deviations`.

**1. Brain dispatch: Read own prompt, write own answer.** Extraction stays genuinely tool-less —
dispatch it with no tools at all and inline the prompt, which fits. The other four brain seams
(judgment, thesis, implication, narrator) emit prompts far too large to inline, so each is dispatched
with **Read on its own prompt files and exactly ONE Write, to its own answer file** — and nothing
else. **Never WebSearch, WebFetch, Bash, or any other tool**: the property the old "tool-less" wording
bought was that a brain cannot reach outside its prompt, and that property is preserved here only by
the tool set. The brain writes its own answer file rather than returning text for the coordinator to
transcribe, because hand-transcribing a 60-plus-judgment answer risks a silent typo in a stored
artifact; a gate retry re-dispatches the brain to rewrite its own file.

**2. Gatherers are the `web-gatherer` agent type.** Every gatherer dispatch passes
`subagent_type: web-gatherer` (`.claude/agents/web-gatherer.md`, tools Read/Write/WebSearch/WebFetch).
This makes the F88 injection wall **structural** rather than merely instructed: an agent that reads
attacker-reachable page text is now unable to hold a shell, whatever a fetched page tries to tell it.
Keep the tool list in the dispatch prompt as well — it says what the type must be.

**3. Oversized emitted prompts split byte-exactly.** An emitted prompt is one physical line and can be
too long for Read to page. Split it into pieces of roughly 30 KB under
`work/<run-dir>/<seam>-parts/`, then **assert that rejoining the pieces reproduces the original
byte-for-byte before dispatching** — if it does not, stop; never dispatch a prompt you cannot prove is
intact. Splitting changes no prompt text and moves no prompt hash.

**4. A report too large for the final message ships above-fold inline, full text by path (F67).**
The rendered daily report runs to six figures of bytes. When it does not fit the session's final
message, carry the above-fold sections **verbatim** in the message and reference the full rendered
text by its path (`work/<run-dir>/report.txt`). Never summarize the report in place of quoting it,
and never silently truncate it.
```

- [ ] **Step 2: Point the seam steps at it**

In `### 3. Run each ready category`:

- **(a) Gather** — after the sentence naming the `gather-category` skill, add: `Dispatch every gatherer with `subagent_type: web-gatherer` (Unattended-run mechanics 2 — the F88 wall is structural, not instructed).`
- **(b) Extraction** — keep `Dispatch one TOOL-LESS Opus subagent`; append to that sentence's paragraph: `Extraction is the seam that stays genuinely tool-less: its prompt fits inline (Unattended-run mechanics 1).`
- **(c) Judgment** — replace `Dispatch `samples` SEPARATE tool-less Opus subagents in one message` with `Dispatch `samples` SEPARATE brain-restricted Opus subagents in one message (Read on their own prompt files + exactly ONE Write to their own answer file — Unattended-run mechanics 1)`. Also update the retry paragraph in (d): `each as its own SEPARATE tool-less subagent` becomes `each as its own SEPARATE brain-restricted subagent (Unattended-run mechanics 1)`.
- **(e) Thesis**, **(e2) Implication**, **(e3) Narrator** — replace each `Dispatch ONE TOOL-LESS Opus subagent` with `Dispatch ONE brain-restricted Opus subagent (Unattended-run mechanics 1)`.

Do not touch step headings. Do not start any new line with `**(`.

- [ ] **Step 3: Extend the F67 session-output rule in 3(f)**

Append to the `**Session-output rule (F67).**` paragraph:

```markdown
When the rendered report is too large for one message (a daily report routinely is), ship the
above-fold sections VERBATIM in the final message and reference the full rendered text by path —
`work/<run-dir>/report.txt` — per Unattended-run mechanics 4. Above-fold inline plus full text by
path is the accepted form; a summary in place of the report is not.
```

- [ ] **Step 4: Add the deviation rule to Step 6**

Append to `### 6. Finalize the cycle log`:

```markdown
**What belongs in `deviations`.** A deviation is something this run did that the skill does NOT
prescribe — a bypassed gate, a hand-edit, a step skipped or improvised, a fallback taken. Record each
one with what was done and why. The four Unattended-run mechanics above are prescription, so they are
**NOT deviations** and must not be logged as such: brain seams running Read-own-prompt + one Write,
gatherers dispatched as `web-gatherer`, byte-exact prompt splitting, and an F67 above-fold-plus-path
final message. Logging accepted practice buries the deviations that actually need a human.
```

- [ ] **Step 5: Run the tests**

Run: `../../.venv/Scripts/python -m pytest tests/test_unattended_mechanics_codified.py tests/test_run_cycle_conformance.py -q`
Expected: PASS, all of both files. In particular `test_procedure_step_list_matches_pinned_constant` and `test_skill_fingerprint_in_sync` must still pass — if either fails, a step heading was changed or a `**(` line was added; revert that edit rather than re-recording the pin.

- [ ] **Step 6: Confirm the fingerprint comment is byte-untouched**

Run: `git diff -- .claude/skills/run-cycle/SKILL.md | grep -c "run-cycle-step-fingerprint"`
Expected: `0` (the line appears in no diff hunk).

- [ ] **Step 7: Commit**

```bash
git log --oneline -1
git add .claude/skills/run-cycle/SKILL.md
git commit -m "docs(F128): codify the four accepted unattended-run mechanics in run-cycle"
```

---

### Task 3: Structural gatherer wall in gather-category, matrix + backlog

**Files:**
- Modify: `.claude/skills/gather-category/SKILL.md` (Invariants bullet ~line 16; step 3 fan-out ~line 244)
- Modify: `docs/compliance-matrix.md` (rows `P8.injection`, `P26.privsep`)
- Modify: `docs/fix-backlog.md` (the F128 checkbox line only)
- Test: `tests/test_unattended_mechanics_codified.py`, `tests/test_compliance_matrix.py`

**Interfaces:**
- Consumes: the agent type name `web-gatherer` fixed in Task 2.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Name the agent type in the gather-category Invariant**

In the `**Reader-gatherers never hold Bash.**` bullet, after the existing tool sentence, add:

```markdown
  Dispatch them as `subagent_type: web-gatherer` (`.claude/agents/web-gatherer.md`, whose `tools:`
  line is exactly that set) so the wall is structural, not merely instructed — the tool list stays in
  the dispatch prompt as the definition of what that type must be.
```

- [ ] **Step 2: Name it in the step-3 fan-out line**

Change `Dispatch each with tools **Read, Write, WebSearch, WebFetch ONLY — never Bash** (Invariants above).` to `Dispatch each with `subagent_type: web-gatherer` — tools **Read, Write, WebSearch, WebFetch ONLY, never Bash** (Invariants above).`

- [ ] **Step 3: Reference the agent file in the compliance matrix**

In row `P8.injection`, inside the Enforcement cell, change `SESSION-PROSE (no-Bash gatherers, receipts-not-content hand-off, .claude/skills/gather-category/SKILL.md)` to `.claude/agents/web-gatherer.md (restricted gatherer agent type, tools Read/Write/WebSearch/WebFetch) plus SESSION-PROSE (receipts-not-content hand-off, .claude/skills/gather-category/SKILL.md)`.

In row `P26.privsep`, change `SESSION-PROSE (tool-less gatherer dispatch; .claude/skills/gather-category/SKILL.md)` to `.claude/agents/web-gatherer.md (no-shell gatherer agent type) plus SESSION-PROSE (.claude/skills/gather-category/SKILL.md)`.

**Do not change either row's Status cell** and do not touch the summary counts table — that would make a compliance claim this lane has not verified (spec §2.4).

- [ ] **Step 4: Tick the F128 checkbox**

In `docs/fix-backlog.md`, change the single line `- [ ] **F128 — Codify the unattended-run mechanics the user ruled on 2026-08-22 (GATED: F83` to `- [x] **F128 — Codify the unattended-run mechanics the user ruled on 2026-08-22 (GATED: F83`. No other line changes.

- [ ] **Step 5: Run the tests**

Run: `../../.venv/Scripts/python -m pytest tests/test_unattended_mechanics_codified.py tests/test_compliance_matrix.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git log --oneline -1
git add .claude/skills/gather-category/SKILL.md docs/compliance-matrix.md docs/fix-backlog.md
git commit -m "docs(F128): dispatch gatherers as the restricted web-gatherer agent type; tick F128"
```

---

### Task 4: Verify the pins and the full suite

**Files:** none modified.

**Interfaces:** consumes the finished state of Tasks 1–3.

- [ ] **Step 1: Re-run the three pins that must not move**

Run: `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py tests/narrator/test_cli.py tests/test_run_cycle_conformance.py -q`
Expected: PASS. F6 baseline and the narrator prompt pin are hashes over Python-emitted prompt bytes and this lane touched no Python, so a failure here means something outside the plan changed — stop and report it as a blocker rather than re-recording anything.

- [ ] **Step 2: Prove no emitted-prompt bytes changed**

Run: `git diff --stat main...HEAD -- gpu_agent/ registry/ store/ fixtures/`
Expected: empty output.

- [ ] **Step 3: Prove the F83 fingerprint value is unchanged**

Run: `git diff main...HEAD -- .claude/skills/run-cycle/SKILL.md | grep "run-cycle-step-fingerprint" || echo "fingerprint line untouched"`
Expected: `fingerprint line untouched`.

- [ ] **Step 4: Full suite**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: ~2619 passed / ~6 skipped, plus the new file's tests. Zero failures.

- [ ] **Step 5: Write the handoff sentinel**

Write `C:\Users\danie\random_for_fun\.superpowers\handoffs\f128-codify-mechanics-DONE.md` (ROOT repo, not the worktree) with: date, branch, commit list, full-suite result, which pins moved (**none**) and which were verified unmoved, and every AFK-default decision from `QUESTIONS.md` — including D3, the anticipated F83 re-record that did not trip.

- [ ] **Step 6: Commit the SDD ledger and design docs**

```bash
git log --oneline -1
git add .superpowers/sdd/2026-08-24-f128-codify-mechanics/QUESTIONS.md docs/superpowers/specs/2026-08-24-f128-codify-mechanics-design.md docs/superpowers/plans/2026-08-24-f128-codify-mechanics.md
git commit -m "docs(F128): spec, plan and AFK-default decision log"
```

---

## Self-review

**Spec coverage.** §2.1 → Task 2 Step 1. §2.2 → Task 2 Steps 2–4. §2.3 → Task 3 Steps 1–2. §2.4 → Task 3 Step 3. §2.5 → Task 3 Step 4. §3 (pins) → Task 4 Steps 1–3. §4 (test plan, all eight assertions) → Task 1. §5 (out of scope) → enforced by the Global Constraints and Task 3 Step 3's explicit "do not change Status".

**Placeholders.** None: every edit is given as the exact before/after string or the exact block to insert.

**Consistency.** The section header string, the cross-reference phrase `Unattended-run mechanics`, the agent type `web-gatherer`, and the tool list `Read, Write, WebSearch, WebFetch` are identical in the spec, the test in Task 1, and the edits in Tasks 2 and 3.
