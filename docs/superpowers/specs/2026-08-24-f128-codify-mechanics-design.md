# F128 — Codify the unattended-run mechanics (design)

**Date:** 2026-08-24 · **Lane:** `f128-codify-mechanics` (off main `f53d2df`) · **Backlog item:** F128
**Authority:** `docs/fix-backlog.md` F128 + the 2026-08-22 interactive rulings in
`docs/superpowers/HANDOFF.md` (round 1, items 2–4).
**Decision log:** `.superpowers/sdd/2026-08-24-f128-codify-mechanics/QUESTIONS.md` — every fork below
was decided without a human present and is recorded there as an AFK-default.

## 1. The problem

Four things happen on every unattended cycle. All four are now **accepted practice** by the user's
2026-08-22 ruling. None of them is written down in the skill the session follows, so every run
re-discovers them, re-does them, and re-logs them as `deviations` — noise that hides the deviations
that actually matter.

The four:

1. **Brain tool posture.** The skill says "dispatch one TOOL-LESS Opus subagent". No tool-less
   subagent type exists in this harness, and the emitted prompts for judge/thesis/implication/narrator
   are far too large to inline. Real runs give each brain Read on its own split prompt files plus
   exactly one Write to its own answer file. Extraction still runs genuinely tool-less, inline.
2. **Gatherer wall.** The F88 no-Bash wall is *instructed* ("dispatch with these tools only"), not
   structural. `.claude/agents/web-gatherer.md` now exists with exactly Read/Write/WebSearch/WebFetch,
   and the 2026-08-22 cycle proved dispatching by that type works.
3. **Prompt splitting.** Emitted prompts are one physical line, too long for Read to page, so runs
   split them byte-exactly into ~30 KB pieces and assert the rejoin equals the original before
   dispatch.
4. **Report size (F67).** The rendered daily report (~123 KB) does not fit a final message, so runs
   ship the above-fold sections verbatim inline and reference the full text by path.

## 2. What this lane changes

Prose and a rot-lint test. **No product code, no prompts, no registry or store data.**

### 2.1 New section in `.claude/skills/run-cycle/SKILL.md`

`## Unattended-run mechanics (accepted practice — user ruling 2026-08-22)`, placed **after
`## Invariants` and before `## Inputs`** — i.e. outside `## Procedure`. Four numbered clauses, one per
mechanic, each stating the rule, the property it preserves, and the failure mode it replaces. The
section closes with the rule that **none of the four is a deviation**.

Placement is load-bearing: the F83 pin parser bounds the Procedure section at the next `## ` header, so
a new `## ` section inside Procedure would silently truncate the pinned step list.

### 2.2 Seam edits inside `## Procedure` (prose only)

| Step | Change |
|---|---|
| 3(a) Gather | dispatch names `subagent_type: web-gatherer` |
| 3(b) Extraction | keeps genuinely tool-less inline; points at mechanic 1 for the fallback |
| 3(c) Judgment | "tool-less" → brain-restricted dispatch per mechanic 1 |
| 3(e) Thesis | same |
| 3(e2) Implication | same |
| 3(e3) Narrator | same |
| 3(f) F67 session-output rule | adds the over-size clause (above-fold inline + full text by path) |
| 6 Finalize the cycle log | adds what counts as a deviation + the four that do not |

**No step is added, renamed, reordered or removed**, and no new line inside `## Procedure` may begin
with `### <n>.` or `**(<label>) `, because both shapes are what the F83 parser reads as a step.

### 2.3 `.claude/skills/gather-category/SKILL.md`

The Invariant and the step-3 fan-out line both name `subagent_type: web-gatherer` as the dispatch
form, with the explicit tool list retained as the definition of the wall (belt and braces: an agent
type can be edited; the tool list says what the type must be).

### 2.4 `docs/compliance-matrix.md`

Rows `P8.injection` and `P26.privsep` reference `.claude/agents/web-gatherer.md` alongside the existing
SESSION-PROSE reference. **Status values unchanged** — promoting them is a broader claim than this lane
verifies, and would move the summary counts table.

### 2.5 `docs/fix-backlog.md`

Tick the F128 checkbox. That line only.

## 3. Pins

| Pin | Expected | How verified |
|---|---|---|
| F83 run-cycle conformance (`ce869181…`) | **UNMOVED** | `tests/test_run_cycle_conformance.py` green; fingerprint comment byte-identical |
| F6 evals baseline (`tests/test_evals_baseline_pin.py`) | UNMOVED | test green |
| Narrator prompt pin (`tests/narrator/test_cli.py`) | UNMOVED | test green |
| scoring-v1 replay pin | UNMOVED | full suite |

**Deviation from the lane brief, recorded loudly.** The brief and the backlog both anticipated *one
deliberate F83 re-record*. That gate does not trip. The F83 fingerprint is
`sha256(repr(EXPECTED_STEPS))` — a hash over the ordered step id + title list only, not over the
skill's prose. Since §2.2 changes no step id or title, the recorded recipe regenerates the identical
hash, so a "re-record" would be a no-op edit dressed as a deliberate pin move. Inventing a step purely
to move the hash would make the skill worse and corrupt the pin's meaning. The pin is therefore
**verified unmoved** and the discrepancy is surfaced to the merger. (QUESTIONS.md D3.)

## 4. Test plan

New rot-lint `tests/test_unattended_mechanics_codified.py`, pure stdlib, no product imports (the
compliance-matrix lint's pattern). It asserts:

1. run-cycle SKILL.md has the `## Unattended-run mechanics` section, positioned before `## Procedure`.
2. The section names all four mechanics by their anchors (brain dispatch, `web-gatherer`,
   byte-exact split, F67 report-by-path).
3. It states the no-reach property for brains (no WebSearch/WebFetch/Bash) and the one-Write cap.
4. Every brain seam that used to assert an absolute "TOOL-LESS" now cross-references the section —
   checked as: the only surviving `tool-less` claims in Procedure are extraction's and the contrast
   note in 7(d2).
5. run-cycle's gather step and gather-category's fan-out both name `subagent_type: web-gatherer`.
6. `.claude/agents/web-gatherer.md` exists and its `tools:` line is exactly
   `Read, Write, WebSearch, WebFetch`.
7. Step 6 carries the deviation rule and lists the four as not-deviations.
8. The Procedure section contains no `## ` header (the F83-parser tripwire that guards §2.1's
   placement rule).

Plus the existing pins re-run, then the full suite.

## 5. Out of scope

- Promoting compliance-matrix Status values (needs its own lane).
- Any change to `gpu_agent/` code, emitted prompts, registry or store data.
- The other open backlog items sharing this cycle's rulings (F123/F124/F121 are separate lanes).
