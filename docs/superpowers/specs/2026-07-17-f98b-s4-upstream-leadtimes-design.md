# F98 Part B — S4 `upstreamLeadTimes` adoption — design spec

**Date:** 2026-07-17
**Status:** Design APPROVED by user (interactive, 2026-07-17); spec awaiting user review. **Build lane dispatches only after Part A's DONE sentinel** (user-selected sequencing).
**Scope:** Adopt SDEWS S4 (upstream long-lead component lead-time index) as scoring indicator `upstreamLeadTimes` in `registry/indicators.json` — a prompt-affecting data change gated by the F6 eval pipeline — plus the post-Part-A manifest source and slot-family line. ONE registry change; nothing else prompt-affecting rides along.
**Origin:** F98 backlog entry Part B (`docs/fix-backlog.md`); candidate #3 of `docs/2026-07-11-sdews-metric-extraction.md` (complements coincident `leadTimes` with the upstream leading view, 1–2 quarters).

## Decision provenance (all interactive, zero AFK-defaults)

1. **Full scoring adoption on day one** — `scoring: true`, weight 0.12 (SDEWS's own S4 weight; S1/S2 precedent went straight in with SDEWS weights). One F6 gate, not two.
2. **All four component families** under the single indicator: optics/CPO (1.6T modules), liquid-cooling CDU & quick-disconnects, 800V power sidecars, high-end PCB/CCL (M8/M9).
3. **Spec+plan now; build after Part A merges** — avoids the manifest/slot-config file collisions with the running Part A lane and keeps one-change-at-a-time discipline at the eval gate.

## The registry entry (the gated change — exact content)

```json
"upstreamLeadTimes": {
  "label": "Upstream long-lead component lead times (S4)",
  "dimension": "bottleneck",
  "polarityTrack": "supply",
  "side": "supply",
  "weight": 0.12,
  "unit": "weeks",
  "kind": "measured",
  "readsLevelOrSlope": "slope",
  "decayLambda": 0.4,
  "scoring": true,
  "polarityDemand": 0,
  "polaritySupply": -1,
  "lifecycle": "active",
  "comparability": "Quoted lead times (weeks) for upstream AI-rack components — optics/CPO 1.6T modules, liquid-cooling CDU & quick-disconnects, 800V power sidecars, high-end PCB/CCL (M8/M9) — LENGTHENING = supply tightening; a family's lead time peaking then rolling over = that bottleneck clearing. Upstream LEADING view (1–2 quarters); distinct from leadTimes (finished merchant-GPU channel, coincident)."
}
```

- Shape copied from the S1/S2 entries (`pkgCapacityOrderSpread`/`hbmSupplyCapex`), the newest-generation registry shape (includes `polarityDemand/polaritySupply/lifecycle`).
- `readsLevelOrSlope: "slope"` — the SDEWS signal is the reversal (peak-and-rollover), not the level; matches `hbmSupplyCapex` precedent. Open to spec-review change.
- Weight 0.12 sits under S1 (0.20) and S2 (0.16), mirroring SDEWS's supply-family ordering.

## Correctness verifications (facts checked 2026-07-17, re-verified in-lane)

1. **No retroactive math shift:** `gpu_agent/scoring.py::dmi_smi_contribution` is a PLAIN weighted sum over findings present — no normalization by total registry weight (verified by reading the function). Stored scorecards contain zero `upstreamLeadTimes` findings, so every replay in `tests/test_scoring_v1_replay_pin.py` must stay byte-value identical. **The replay pin staying green is an acceptance criterion; if it reddens, the change did something this spec says it cannot — STOP.**
2. **F79 v2 shadow tolerance:** the lane verifies (read-first) that the shadow v2 scoring path iterates registry indicators defensively and tolerates a new entry. If the new indicator disturbs shadow compute in any way, that is a QUESTION-STOP (per repo CLAUDE.md), not an improvisation — G4 cutover governance owns v2.
3. **F6 pin red is the design, not a failure:** the registry edit changes emitted extract prompts; `tests/test_evals_baseline_pin.py` goes red BY DESIGN. Before running the eval, the lane diffs the emitted prompts vs baseline and confirms the ONLY change is the new indicator's lines (extract seam; judge/thesis/implication expected byte-identical → informational under the seam-scoped verdict logic, F65 precedent).

## The eval gate (by the book — eval-driver skill + repo run-eval skill)

- Sequence per `~/.claude/skills/eval-driver` (authoritative steps in the repo's `run-eval` skill): `eval emit-brain → (tool-less Opus subagents, byte-verbatim answers) → record-brain → emit-grade → record-grade → verdict`; marginal-pass/-fail ⇒ exactly ONE replication, two-run mean decides; rebaseline needs THREE replicate dirs; `append_run_to_history` non-poisoning invariant respected.
- NO `--force`, NO hand-edited answers, NO regenerating all samples for one violation (F38 protocol: re-dispatch only the violating case).
- After an accepted verdict: governance rebaseline (r1/r2/r3) writes the new baseline; F6 pin re-recorded. Raw runs in gitignored `work/`; never `git clean`.

## Trailing edits (post-Part-A-merge, same lane, NOT prompt-affecting)

1. `manifests/chips.merchant-gpu.json`: `expectedIndicators` entry for `upstreamLeadTimes`; one `expectedSources` entry `upstream-component-leadtimes` (trade-press + supplier-earnings domains already in the manifest's style: optics/cooling/power/PCB lead-time coverage), `tier: "secondary"`, `refresh: "monthly"` (or nearest allowed enum), `indicators: ["upstreamLeadTimes"]`. Validated by `load_manifest` (pydantic) + a test.
2. `registry/agenda-slots.json`: add `"upstreamLeadTimes"` to the **binding-constraint** family (the slot's question — "what caps shipments today, and how tight?" — is exactly what an upstream lead-time reversal answers). One line; slot-family test updated.
3. No series file, no backfill: findings-sourced from day one (unlike S1/S2 there is no historical series to sign off).

## Acceptance criteria

1. Registry entry exactly as specified (one new key; no other registry line touched).
2. `tests/test_scoring_v1_replay_pin.py` GREEN throughout (criterion, not assumption).
3. Emitted-prompt diff shows the new indicator only; F6 gate run per eval-driver; verdict accepted without `--force` or hand-edits; baseline rebaselined via governance path; F6 pin green at lane end.
4. F79 v2 shadow verified undisturbed (or QUESTION-STOP filed).
5. Manifest + slot-family edits landed post-Part-A with their tests; F83 conformance green.
6. Full suite green at lane end; the first live cycle after merge can extract an `upstreamLeadTimes` measured finding (weeks unit) without schema/gate violations — verified on the next scheduled cycle, not by forcing a cycle in-lane.
7. Lane discipline: worktree `.worktrees/f98b-s4-leadtimes`, branch `f98b-s4-leadtimes`; question-stop rule; stop-before-merge with `f98b-s4-leadtimes-DONE.md`; only the user merges.

## Out of scope

- Any other indicator change (one at a time); S6/S3/P-family (other agents' lanes per the extraction doc).
- Weight retuning of existing indicators; F79 G4 cutover interactions.
- An `upstreamLeadTimes` series file / agenda delta lines (possible later, renderer-side, ungated).
