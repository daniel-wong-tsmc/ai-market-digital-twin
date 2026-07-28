# F79 G4 — Series refresh, shadow soak, and cutover (design)

**Date:** 2026-07-28 · **Status:** user-approved design (interactive brainstorm, zero AFK)
**Parent:** F79 scoring v2.0 — plan `docs/superpowers/plans/2026-07-13-f79-scoring-v2.md` (POST-G3
section, which deferred these details to "the final pre-G4 stage"); backlog F79.

## Problem

The v2 engine shadow-merged 2026-07-15 (`b6db80a`), but the G4 preconditions never started:

- **Zero shadow invocations.** The `v2-shadow` CLI verb exists; no stored scorecard carries a v2
  provenance stamp. The soak ("≥5 live cycles compute v2 in shadow") is at 0 because invocation was
  left manual and scheduled cycles don't know about it.
- **The v2 data feed is stale.** The six scoring series (`store/series/*.jsonl`, excluding the three
  price series) were last fed by the G1 backfill (vintage 2026-07-13); none has a 2026-07 period.
  Nothing in the daily cycle refreshes them — cutting over without a refresh mechanism would freeze
  the headline index on June data. (The three price series have their own path, `price-sync`, fed
  from the local `gpu_leasing_data/` folder — itself stale since June, a user-side data chore
  outside this lane's scope.)

## Decisions (all user picks, interactive 2026-07-28)

| # | Question | Decision |
|---|----------|----------|
| D1 | How do the six scoring series get monthly updates? | **Build a series-refresh step** (vs manual feed, vs deriving from daily findings) |
| D2 | Soak mechanics | **Forward-only** — count only fresh cycles; no retroactive stamps counted (retroactive stamping allowed as labeled context only) |
| D3 | When does refresh run? | **Piggyback on the daily cycle** with a publication-calendar gap check (vs separate monthly job, vs manual) |
| D4 | What does "soak passed" mean? | **Pre-committed checklist** (§Soak pass terms), not a numeric agreement bar and not judgment-after-the-fact |
| D5 | Post-cut rendering | **Clean cut** — v2 is the only rendered index; one-line methodology note at the cut; v1 keeps computing invisibly in stored scorecards (vs dual display, vs v1-in-Explore) |

## Design

### 1. Series-refresh step (new build; the only new code of this lane)

Every daily cycle runs a cheap deterministic gap check over the six scoring series: "should a newer
monthly point exist by now?" — driven by each source's publication calendar (the manifest's
`earningsDates` from F103, plus per-series rules such as "TSMC/TWSE monthly revenue ~10th of the
following month"). Per-series calendar rules live in a small curated registry file (trust-boundary
pattern per `registry/price-benchmarks.json`).

- **No gap →** zero cost; one line in the cycle log.
- **Gap →** dispatch a reader subagent to fetch that series' source only. Deterministic code
  validates the returned point (shape, period, unit, plausible-range check against the series'
  history) and appends it to `store/series/<id>.jsonl` with today's vintage stamp. The series store
  stays append-only; a point that fails validation is logged and dropped, never written.
- A fetch that fails or a source not yet published logs a gap and never blocks the cycle
  (price-sync precedent: refresh never blocks).

**Not a scored brain seam.** The reader subagent is a gatherer, not one of the four scored brains:
no `fixtures/evals` case, no eval gate, and the F6 baseline must stay byte-untouched. The refresh
enters through the deterministic validation boundary, exactly like price-sync's curated rows.

### 2. Shadow hook (run-cycle edit)

The same run-cycle SKILL.md edit adds two steps to the daily cycle: the gap-check/refresh (§1) and
the `v2-shadow` invocation (stamp v2 indices into the just-written scorecard's provenance before the
cycle commit — the verb is already append-only, idempotent, and render-inert; stage-6 tripwire tests
guarantee no `v2.*` key renders). The SKILL.md edit re-records the **F83 conformance pin in
lockstep, same commit** (F98/F101b precedent). No other pin moves.

### 3. Soak (forward-only)

≥5 daily cycles with the shadow stamp, **at least 2 after the first 2026-07 points land** in the six
scoring series. Retroactive stamps on pre-existing scorecards, if ever made, are labeled
`retroactive` in provenance and do not count toward the five.

### Soak pass terms (pre-committed — written before the soak starts, per desk methodology)

The soak **passes** iff all of:

1. v2 computes cleanly on every soak cycle — no errors, no series silently absent from the walk.
2. ≥2 soak cycles ran after the July refresh points landed.
3. Every cycle where v2's verdict band disagrees with v1's rating has a written explanation
   traceable to the data (e.g. "v2 sees rental prices 2σ below trend; v1's fixed weights dilute
   it"), and no explanation resolves to an engine bug.

**Fails** on any unexplainable disagreement or any engine bug found while explaining one. A failed
soak blocks G4; the finding gets filed and the soak restarts after the fix merges. Band-level
disagreement per se is expected and does NOT fail the soak — v1 and v2 measure differently by
design, and a numeric agreement bar would quietly assume v1 is ground truth.

### 4. G4 package → clean cut

After the soak I write the G4 package (`.superpowers/handoffs/f79-scoring-v2-QUESTIONS.md`, message
begins `GATE-STOP: G4`): the shadow-vs-v1 comparison across all soak cycles with the per-disagreement
explanations, the cutover diff (which render paths switch to v2), and the one-line methodology note.
**STOP — only the user signs G4.** On sign-off, the cutover lands: the page renders v2 only; the
methodology note shows once at the cut; v1 keeps computing inside stored scorecards (replay pinned),
so rollback is one rendering change.

## Constraints

- MUST-NOT-TOUCH: `scoring.py` v1 paths, `report.py`, brain prompts, `gpu_agent/evals`,
  `fixtures/evals`, `registry/indicators.json`. F6 pin, scoring-v1 replay pin, narrator pin stay
  green; F83 re-records only in the SKILL.md-edit commit (§2).
- Series store stays append-only; validation failures never write.
- Refresh/shadow never block a cycle (non-fatal, logged).
- Lane: non-gated, `.worktrees/f79-g4-refresh` off main; subagent-driven; question-stop rule per
  CLAUDE.md; STOP before merge. Disjoint from the parked F105 lane (extraction files) and from
  daily cycles (never touches root `store/`).

## Acceptance

1. A daily cycle on a month with no new prints logs "no gap" and writes nothing to `store/series`.
2. A cycle after a known publication date fetches, validates, and appends exactly the missing
   point(s), correctly vintage-stamped.
3. Every post-merge daily cycle's scorecard carries the v2 shadow provenance stamp.
4. Soak ledger reaches ≥5 qualifying cycles (≥2 post-refresh) and the pass terms are evaluated
   against it verbatim.
5. G4 package delivered as a GATE-STOP; nothing renders v2 before the user signs.

## Decision provenance

All five design decisions (D1–D5) were user picks in the interactive 2026-07-28 brainstorm; no
AFK-defaults. The soak pass terms were pre-committed in this spec before any soak cycle ran.
