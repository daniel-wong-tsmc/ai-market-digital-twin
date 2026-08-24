# F121 — Registry Indicator Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip the retired-scheme parenthesised id tails from the seven affected labels in
`registry/indicators.json` so the data itself is exec-clean, not just the display layer.

**Architecture:** One data edit plus one regression test. The display-layer strips
(`reader.strip_stale_paren_ids`, `dashboard/brief_model._TILE_CODE_SUFFIX`) stay as
belt-and-braces — they also serve stored thesis-book text that F121 does not touch. Rendered
output is byte-unchanged everywhere; only the emitted `extract` brain prompt moves, which turns
the F6 pin red by design.

**Tech Stack:** Python 3 + pytest (shared root venv `../../.venv/Scripts/python`), JSON registry data.

**Spec:** `docs/superpowers/specs/2026-08-24-f121-indicator-labels-design.md`

## Global Constraints

- Run tests from the worktree root as `../../.venv/Scripts/python -m pytest -q`. NEVER create a venv.
- Label strings lose ONLY the trailing ` (Xn)` tail. No rewording, no case or punctuation changes.
- Do not hand-edit `fixtures/evals/baseline.json` or any pin hash. Ever.
- Stage files explicitly by name; never `git add -A`. Run `git log --oneline -1` immediately before every commit.
- Commit on branch `f121-indicator-labels` only. Do not merge. Do not push.
- Leave `site/**` generated output and historical `docs/**` untouched.

---

### Task 1: Clean the seven labels + add the data regression test

**Files:**
- Modify: `registry/indicators.json` (7 `label` values)
- Test: `tests/test_registry_indicators.py` (append one test)

**Interfaces:**
- Consumes: `IndicatorRegistry.load(pathlib.Path("registry/indicators.json"))`, whose
  `.indicators` is a dict of RAW dicts (read `v.get("label")`, not `v.label`).
- Produces: nothing new in code; the seven cleaned label strings are the deliverable.

- [ ] **Step 1: Write the failing test** — append to `tests/test_registry_indicators.py`:

```python
def test_f121_labels_carry_no_old_scheme_paren_id_tail():
    # F121: seven labels used to end in a retired-scheme short id, e.g.
    # "Hyperscaler capex-revision direction (D1)". Those tails leaked raw ids into
    # every above-the-fold label row and tripped the F120 acronym gate; the F120
    # display-layer strip covered them, this asserts the DATA itself is clean.
    import re
    tail = re.compile(r"\s*\([A-Z]\d{1,2}\)\s*$")
    reg = IndicatorRegistry.load(REG)
    offenders = sorted(k for k, v in reg.indicators.items()
                       if v.get("label") and tail.search(v["label"]))
    assert offenders == [], f"labels still carry old-scheme id tails: {offenders}"


def test_f121_cleaned_labels_are_exact():
    reg = IndicatorRegistry.load(REG)
    expected = {
        "pkgCapacityOrderSpread": "Advanced-packaging capacity-order spread",
        "hbmSupplyCapex": "HBM bit-supply growth + memory capex",
        "upstreamLeadTimes": "Upstream long-lead component lead times",
        "hyperscalerCapexRevision": "Hyperscaler capex-revision direction",
        "odmMonthlyAiRevenue": "Taiwan ODM monthly AI-server revenue",
        "tokenEconomics": "Inference token economics",
        "marginalBuyerFinancing": "Marginal-buyer financing conditions",
    }
    assert {k: reg.indicators[k]["label"] for k in expected} == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_registry_indicators.py -q -k f121`
Expected: FAIL — the first names all seven ids, the second shows the `(D1)`-style tails.

- [ ] **Step 3: Make the data edit**

In `registry/indicators.json`, delete the trailing ` (S1)`, ` (S2)`, ` (S4)`, ` (D1)`, ` (D9)`,
` (D4)`, ` (X5)` (each with the space before it) from the `label` of, respectively:
`pkgCapacityOrderSpread`, `hbmSupplyCapex`, `upstreamLeadTimes`, `hyperscalerCapexRevision`,
`odmMonthlyAiRevenue`, `tokenEconomics`, `marginalBuyerFinancing`. Change nothing else on those
lines — not `comparability`, not weights.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_registry_indicators.py -q -k f121`
Expected: PASS (2 passed).

- [ ] **Step 5: Refresh the two stale explanatory comments**

`gpu_agent/reader.py` (`indicator_label` docstring) and
`gpu_agent/dashboard/brief_model.py` (`_indicator_labels` comment) both say the registry data
still carries the tails. Update each to say F121 cleaned the data and the strip is retained as
belt-and-braces for stored thesis-book text. Do not change any code on either path.

- [ ] **Step 6: Confirm the display-layer tests still pass untouched**

Run: `../../.venv/Scripts/python -m pytest tests/test_report_change_first.py tests/dashboard/test_brief_render.py tests/test_brief_board.py -q`
Expected: PASS, with no edits to any assertion in those files.

- [ ] **Step 7: Commit**

```bash
git log --oneline -1
git add registry/indicators.json tests/test_registry_indicators.py gpu_agent/reader.py gpu_agent/dashboard/brief_model.py
git commit -F <message file>
```
Message: `fix(F121): drop retired-scheme id tails from 7 indicator labels` plus a body noting
that the F6 `extract` prompt hash moves as a result.

---

### Task 2: Record the pin state and close the backlog line

**Files:**
- Modify: `docs/fix-backlog.md` (the F121 checkbox line only)
- Create: `docs/superpowers/specs/2026-08-24-f121-indicator-labels-design.md` (already written)
- Create: `docs/superpowers/plans/2026-08-24-f121-indicator-labels.md` (this file)

**Interfaces:**
- Consumes: the measured hash movement from `gpu_agent.evals.prompt_hash.compute_prompt_hashes`.
- Produces: the recorded old→new `extract` fingerprint that the session-level operator needs.

- [ ] **Step 1: Confirm which pins moved and which did not**

Run: `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py tests/narrator/test_prompt_pin.py tests/test_scoring_v1_replay_pin.py tests/test_run_cycle_conformance.py -q`
Expected: `test_prompt_hashes_match_baseline` FAILS naming `drifted: ['extract']`; every other
listed test PASSES. Any other drift is a STOP-and-record-a-blocker condition.

- [ ] **Step 2: Do NOT rebaseline in this lane**

The recorded recipe (`.claude/skills/run-eval/SKILL.md`) is a live multi-replicate eval run and
states "Run-eval is SESSION-level work: never delegate dispatches to an implementer subagent."
Leave the pin red. Never hand-edit `fixtures/evals/baseline.json`.

- [ ] **Step 3: Tick the F121 checkbox in `docs/fix-backlog.md`**

Change only that item's `- [ ]` to `- [x]`. Touch no other line.

- [ ] **Step 4: Run the full suite**

Run: `../../.venv/Scripts/python -m pytest -q` (~6 min)
Expected: exactly one failure — the F6 pin — plus the usual skips (a worktree adds one expected
skip for price scrape data).

- [ ] **Step 5: Run the web suite**

Run: `npm --prefix web test`
Expected: PASS, unchanged (the web brief's rendered labels do not move).

- [ ] **Step 6: Commit**

```bash
git log --oneline -1
git add docs/fix-backlog.md docs/superpowers/specs/2026-08-24-f121-indicator-labels-design.md docs/superpowers/plans/2026-08-24-f121-indicator-labels.md
git commit -F <message file>
```
Message: `docs(F121): spec + plan; tick backlog; record extract-seam pin movement`, with the
old→new `extract` fingerprints and the `eval rebaseline … --seams extract` instruction in the body.

---

## Remaining work handed to the session-level operator

`fixtures/evals/baseline.json` still pins the pre-F121 `extract` hash. Unlock (once, deliberately):
run `.claude/skills/run-eval/SKILL.md` steps 1-6, top up to three replicates, then
`eval rebaseline --runs <d1> <d2> <d3> --verdict <run>/verdict.json --seams extract`, commit the
new baseline on its own with the old→new fingerprints in the message:

```
extract  43afd610cda461bd3c7323c51c3efdc6ab3c6e39772fb494209527b1c53c6152
      -> 09a6a5e19227f6b1f21809618fb76a2fc2d248f08c8c8a781b7e4f3b484e2093
```
