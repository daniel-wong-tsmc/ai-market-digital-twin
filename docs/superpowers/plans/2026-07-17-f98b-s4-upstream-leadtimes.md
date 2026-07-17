# F98 Part B — S4 `upstreamLeadTimes` Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt SDEWS S4 as scoring indicator `upstreamLeadTimes` per spec `docs/superpowers/specs/2026-07-17-f98b-s4-upstream-leadtimes-design.md`, through the F6 eval gate, plus the manifest source and slot-family line.

**Architecture:** ONE prompt-affecting data change (`registry/indicators.json` + one new key), proven safe against the scoring-replay pin, gated by the eval pipeline per the eval-driver skill, then two ungated data edits (manifest, slot family). No code changes expected at all — this is a data-adoption lane.

**Tech Stack:** repo CLI (`gpu_agent.cli eval ...`), pytest, tool-less Opus subagents for brain/grader dispatch.

## Global Constraints

- Lane: worktree `.worktrees/f98b-s4-leadtimes`, branch `f98b-s4-leadtimes` (create at execution start). Python `../../.venv/Scripts/python`.
- **Precondition (verify, don't assume): F98 Part A merged** — satisfied as of main `7e2f657` (2026-07-17); confirm your base includes it before branching.
- ONE registry change only; nothing else prompt-affecting in this lane. DO NOT touch scoring.py, report.py, brains, eval harness code, or any other registry entry.
- `tests/test_scoring_v1_replay_pin.py` must be GREEN at every step of this lane. If it reddens, STOP — the spec's no-normalization proof failed.
- A RED `tests/test_evals_baseline_pin.py` after the registry edit is the F6 gate BY DESIGN (Task 3) — never "fix" the pin outside the governance rebaseline.
- Eval discipline (eval-driver skill, binding): byte-verbatim answers, no `--force`, no hand-edits, violation re-dispatch one case at a time, marginal-pass/-fail ⇒ exactly one replication, rebaseline from exactly 3 replicate dirs, never `git clean` (raw runs live in `work/`).
- Question-stop rule (repo CLAUDE.md): any design fork or v2-shadow disturbance → write `f98b-s4-leadtimes-QUESTIONS.md` and stop.
- `git log --oneline -1` before every commit. Stop before merge; only the user merges.

---

### Task 1: Lane preconditions + read-first verifications

- [ ] **Step 1:** From repo root: `git pull --ff-only`; confirm `git log --oneline -5` includes `7e2f657` (Part A merge). Create the worktree/branch per superpowers:using-git-worktrees.
- [ ] **Step 2:** Verify no other eval-adjacent lane is active: `ls .superpowers/handoffs/*QUESTIONS.md`, check HANDOFF's coordination section for lanes touching `registry/` or the eval harness. If one is active, STOP and report.
- [ ] **Step 3 (re-verify the spec's proof):** Read `gpu_agent/scoring.py::dmi_smi_contribution` and confirm it is a plain weighted sum with NO normalization by total registry weight (spec §Correctness-1, verified 2026-07-17 — re-confirm the code hasn't changed since).
- [ ] **Step 4 (v2 shadow):** Locate the F79 shadow scoring path (grep `v2` under `gpu_agent/`, e.g. a `scoring_v2`/`sdews` module) and read how it consumes the registry. Confirm an unknown/new indicator id cannot crash or silently alter shadow output (defensive iteration / registry-driven). If ANY doubt → QUESTION-STOP with your reading attached.
- [ ] **Step 5:** Baseline suite from the worktree: `../../.venv/Scripts/python -m pytest -q` → green (skips ok). Record the counts in the lane notes.

---

### Task 2: The registry entry + local proofs

**Files:**
- Modify: `registry/indicators.json` (ONE new key)
- Test: none new — existing pins ARE the tests.

- [ ] **Step 1:** Add the `upstreamLeadTimes` entry EXACTLY as the spec's JSON block (copy verbatim; place it adjacent to the other S-coded entries, matching the file's existing key ordering style).
- [ ] **Step 2:** Registry loads: `../../.venv/Scripts/python -c "from gpu_agent.registry.indicators import IndicatorRegistry; r = IndicatorRegistry.load('registry/indicators.json'); print(r.resolve('upstreamLeadTimes', 'chips.merchant-gpu'))"` → prints the spec with weight 0.12, side supply, scoring True.
- [ ] **Step 3:** Replay pin: `../../.venv/Scripts/python -m pytest tests/test_scoring_v1_replay_pin.py -q` → **ALL GREEN** (acceptance criterion 2). Red = STOP.
- [ ] **Step 4:** Full suite: expect exactly ONE failure — `tests/test_evals_baseline_pin.py` (F6, by design). Any OTHER failure = investigate before proceeding; more prompt seams moving than expected = STOP.
- [ ] **Step 5:** Prompt-diff audit: emit the brain prompts (`eval emit-brain --out work/f98b-audit`) and diff against the baseline's materialized prompts (normalize CRLF→LF first). Confirm the ONLY delta is the new indicator's lines in the extract seam; judge/thesis/implication byte-identical. Save the diff summary to the lane notes.
- [ ] **Step 6: Commit**

```bash
git add registry/indicators.json
git commit -m "feat(f98b): adopt upstreamLeadTimes (S4) - scoring supply indicator, weight 0.12"
```

---

### Task 3: The F6 eval gate

Follow the repo's `run-cycle`-adjacent `run-eval` skill as the authoritative step list, with the eval-driver skill's failure protocol. `<work>` = `work/eval-2026-07-<dd>/rN`.

- [ ] **Step 1 (r1):** `eval emit-brain --out <r1>` → dispatch each case to a SEPARATE tool-less Opus subagent (`model: opus`, explicit no-tool-use prompt), save answers byte-verbatim to `<r1>/brain-answers.json` → `eval record-brain --out <r1>` (exit 1 ⇒ F38 protocol: re-dispatch ONLY the violating case with the violation lines appended) → `eval emit-grade` → dispatch graders the same way → `eval record-grade --out <r1> --as-of <today>`.
- [ ] **Step 2:** `eval verdict --runs <r1>`. Key the decision off the `decision` field: clean pass → proceed; `marginal-pass` OR `marginal-fail` → run EXACTLY ONE replicate (r2, same procedure) and `eval verdict --runs <r1> <r2>`; two-run mean decides. Hard fail → STOP, report per the standing disposition rules (no third attempt without the user).
- [ ] **Step 3 (rebaseline):** produce the three replicate dirs governance requires (r1 + r2 + r3, running only what's still missing), then `eval rebaseline --runs <r1> <r2> <r3> --verdict <accepted>/verdict.json`. Only pass/marginal-pass runs enter the noise history (the CLI enforces it — do not work around a refusal).
- [ ] **Step 4:** F6 pin re-record per the rebaseline output/HANDOFF standing rule; `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py tests/test_scoring_v1_replay_pin.py -q` → all green.
- [ ] **Step 5: Commit** (baseline + pin fixtures only; raw runs stay gitignored):

```bash
git add fixtures/evals/ tests/
git commit -m "eval(f98b): F6 gate passed + governance rebaseline for upstreamLeadTimes"
```

(`git status` first; stage exactly what the rebaseline touched — nothing from `work/`.)

---

### Task 4: Manifest source + slot family (ungated data edits)

**Files:**
- Modify: `manifests/chips.merchant-gpu.json`, `registry/agenda-slots.json`
- Test: `tests/test_manifest_f98.py` (extend), `tests/dashboard/test_agenda.py` (extend the Part A slot-family test)

- [ ] **Step 1: Failing tests first.** Extend the existing Part A tests:

```python
# tests/test_manifest_f98.py — add to the existing test or as a new one
def test_manifest_covers_upstreamLeadTimes():
    m = load_manifest("manifests/chips.merchant-gpu.json")
    assert "upstreamLeadTimes" in {i.indicatorId for i in m.expectedIndicators}
    assert "upstreamLeadTimes" in {ind for s in m.expectedSources
                                   for ind in s.indicators}
```

```python
# tests/dashboard/test_agenda.py — extend test_real_slot_families_match_f98_spec
    assert "upstreamLeadTimes" in fam["binding-constraint"]
```

Run both → FAIL.
- [ ] **Step 2:** Manifest edit: add `upstreamLeadTimes` to `expectedIndicators` (copy an existing entry's exact shape); add source entry `upstream-component-leadtimes` — label "Upstream component lead-time coverage (optics/CPO, liquid cooling, 800V power, high-end PCB/CCL)", urlPatterns drawn from domains ALREADY present in this manifest (trade press + supplier IR), `accessMethod`/`tier: "secondary"`/`costUsd: 0`/`license: "public"`/`refresh`: the nearest allowed enum to monthly (check `gpu_agent/manifest.py`'s model), `indicators: ["upstreamLeadTimes"]`.
- [ ] **Step 3:** Slot edit: append `"upstreamLeadTimes"` to the binding-constraint family in `registry/agenda-slots.json` (current merged family: `["S10", "leadTimes", "pkgCapacityOrderSpread", "hbmSupplyCapex"]`). No other slot changes.
- [ ] **Step 4:** `../../.venv/Scripts/python -m pytest tests/test_manifest_f98.py tests/dashboard/ -q` → green. Full suite → green (F6 pin already re-recorded in Task 3; F83 conformance untouched — this lane adds no run-cycle step).
- [ ] **Step 5: Commit**

```bash
git add manifests/chips.merchant-gpu.json registry/agenda-slots.json tests/
git commit -m "feat(f98b): manifest source + binding-constraint slot for upstreamLeadTimes"
```

---

### Task 5: Lane close-out

- [ ] Full suite from the worktree one final time → green; record counts.
- [ ] Tick F98 Part B in `docs/fix-backlog.md`; note that live-extraction verification (spec criterion 6) happens on the next scheduled cycle, not in-lane.
- [ ] Write `.superpowers/handoffs/f98b-s4-leadtimes-DONE.md` (what shipped, eval verdict numbers, replicate dirs, decisions, NOT merged).
- [ ] Update `docs/superpowers/HANDOFF.md` (top line + session bullet + coordination entry; keep exactly one "resume point:" literal — the integrity test enforces it).
- [ ] `git push -u origin f98b-s4-leadtimes`; report with merge decision pending. After the user merges: the next scheduled cycle both exercises extraction of the new indicator and (per spec criterion 6) verifies it end-to-end.

---

## Self-review notes (plan-time)

- **Spec coverage:** registry entry (T2, verbatim from spec), replay-pin criterion (T2.3 + every-step constraint), prompt-diff audit (T2.5 = spec Correctness-3), v2 shadow question-stop (T1.4), eval gate by the book (T3 = spec gate section), manifest/slot trailing edits (T4 = spec trailing §, updated to the POST-MERGE Part A file state verified 2026-07-17), no series/backfill (spec: none needed), acceptance criteria 1–5,7 land in T1–T5; criterion 6 explicitly deferred to the next scheduled cycle.
- **Placeholder scan:** the two "check the pydantic enum / copy existing shape" instructions are read-then-pin steps against named files, not TBDs. Eval commands match the eval-driver skill verbatim.
- **Consistency:** worktree/branch name matches spec criterion 7; Task 4's slot expectation matches the real merged family list; no task touches anything on the must-not-touch list.
