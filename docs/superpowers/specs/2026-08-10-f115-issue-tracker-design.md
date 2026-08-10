# F115 — Category-Page Issue Tracker ("Known issues")

Designed 2026-08-10 in an interactive brainstorm. Every design fork below was a user pick
(zero AFK-defaults). GATED LANE: touches the narrator prompt + pin.

## 1. Problem

The cycle keeps re-discovering the same structural problems — stacked-memory supply lacking,
advanced-packaging capacity lacking — but nothing tracks them as named, persistent issues.
The binding constraint is re-stated each cycle with no memory; the thesis book tracks calls,
not reader-facing issues; the reader cannot see "how long has memory been the problem, and is
it getting better?". F115 adds a persistent issue tracker rendered at the bottom of the
category page, updated by every daily cycle with an AI-reasoned improved/worsened/unchanged
assessment per issue.

## 2. Decision provenance (all interactive user picks, 2026-08-10)

1. **Issue source: agent-minted, with rules.** The cycle opens issues automatically from
   evidence triggers; the user can rename/delete by editing the register (option chosen over
   human-curated registry and quarantine-promote).
2. **Assessment: the AI assesses with reasoning** — not a purely mechanical derivation.
3. **Which brain: extend the narrator** (cheap pin lane) — not a new dedicated brain, not the
   F6-gated scored brains.
4. **Lifecycle: resolve after sustained improvement** — 5 consecutive good cycles (user
   accepted the recommended bar); not instant-close, not never-close.
5. **Storage: Option A, register + append-only history log** (mirrors the thesis book), over
   per-day snapshot files.

## 3. Reader-facing surface

New "Known issues" section on the category page, between the six-dimensions zone and the
footer. Per open issue, one row:

- Plain-words title (e.g. "Stacked memory supply for accelerators").
- This cycle's status chip: improved / worsened / no change, dated.
- Tenure line: "tracked since <month year> · worsening N of last M checks".
- The narrator's 1–2 sentence reasoning for today's call, with inline source badges
  (same treatment as the F114 bullets).
- A history strip: one small colored tick per past check (improved/worsened/no-change/
  not-assessed), no chart machinery.

Resolved issues sit under a collapsed "Resolved" heading with close date and final note —
the track record stays visible. If the assessment did not run or fell back, the section shows
"Not assessed this cycle" honestly; stale chips are never presented as fresh (house honesty
rule, F110 precedent).

## 4. Data model (Option A)

New directory `store/<categoryId>/issues/`:

- **`register.json`** — current state; leading keys `schemaVersion`, `categoryId`, `asOf`,
  then `issues[]`: `id` (stable slug derived from the trigger), `title`, `state`
  (`open`/`resolved`), `openedAsOf`, `resolvedAsOf?`, `trigger` (`binding-constraint` |
  `dimension-weak`, plus the dimension/constraint label), `latest` (status + reasoning +
  `claimFindingIds` + assessedAsOf | `not-assessed`), counters (`improvedStreak`,
  `worsenedCount`, `checkCount`), and re-open history (`reopenedAsOf[]`).
- **`history.jsonl`** — append-only, one line per issue per cycle:
  `{asOf, issueId, status, reasoning, claimFindingIds, trigger-still-firing, streak-after}`.
  Never rewritten; feeds the history strip and audits.

**No-silent-deletion invariant:** no code path removes a register entry; a test proves the
updater can only add issues or change state. Deleting/renaming is a human edit.

## 5. Lifecycle rules (plain code, deterministic)

**Open** a new issue when either:
(a) the scorecard's `categoryStatus` names a binding constraint not covered by an open issue
    (id derived from the constraint label), or
(b) a dimension is rated weak AND direction worsening (id derived from the dimension name).
Same trigger later → same id (re-open, not duplicate).

**Resolve** after 5 consecutive cycles where the narrator said improved, or said no-change
while the trigger no longer fires. Any worsened/unchanged-while-still-triggering cycle resets
the streak (flap resistance). A `not-assessed` cycle neither advances nor resets the streak.
Resolved issues re-open under the same id if a trigger fires again.

## 6. Narrator extension + guardrails (GATED)

- Narrator inputs gain the open-issue list (title, trigger, recent history). Its artifact
  schema gains an `issues` block: for EVERY open issue exactly one status
  (`improved`/`worsened`/`unchanged`) + 1–2 sentences of reasoning + `claimFindingIds`
  resolving to this cycle's findings.
- Mechanical gate additions: all open issues assessed, no extras, ids resolve, banned-word
  and length caps — same style as gate checks 1–8.
- Citation audit extends to issue reasoning, claims keyed `issue:<id>` (F114 `bullet:<i>`
  precedent).
- Fallback: 2 gate failures → issues get `not-assessed` entries (streaks frozen, page shows
  it honestly). Bullets/story fall back independently — a bad issues block must not take
  down the story, and vice versa.
- **Pin discipline:** the narrator prompt pin re-records EXACTLY ONCE, in the same commit as
  the prompt change (F103/F114 lockstep). F6 baseline and the four scored brains'
  emitted prompts stay byte-identical — forbidden-diff check at every commit. Exclusive
  prompt lane: no other narrator-touching lane may run while this is open.

## 7. Cycle wiring + export + render

- Two new step-3 sub-steps, so a newly opened issue is assessed the SAME day:
  **3(d4) issues-open** — after (d3) coverage, plain code applies the opening triggers to the
  fresh scorecard and writes the register; **3(e3b) issues-update** — after the narrator,
  apply its verdicts, advance/reset streaks, resolve, append `history.jsonl`, before (e4)
  citation audit reads the claims. `7e` dashboard-json then reads the register unchanged.
  Non-blocking house rule: each logs `issues-…: done|failed|skipped`, never kills the cycle.
  F83 fingerprint re-stamped deliberately in-lane (same commit as the SKILL.md step edit).
- `dashboard.json` gains a required `issues` section; schema bumps 1.1 → 1.2 (strict,
  `additionalProperties: false`); exporter stays clock-free/deterministic and validates
  before write. Post-merge data refresh required (F110/F113 precedent — the strict app never
  points at old-schema data).
- React app: new `Issues` component between `Dimensions` and `Footer`; golden payload +
  contract test extended; open/resolved/not-assessed render states tested.

## 8. Testing

Unit tests for open/resolve/streak/flap/reopen rules; register no-silent-deletion; gate
tests for the new narrator checks; citation-audit `issue:<id>` coverage; exporter
determinism (byte-identical on same inputs); render tests for all three states; suite green
with pins accounted for: narrator pin + F83 fingerprint move once each, deliberately; F6 and
scoring-v1-replay must not move.

## 9. Sequencing

Build subagent-driven in `.worktrees/f115-issue-tracker`. Exclusive narrator-prompt lane —
nothing else narrator-touching concurrently. STOP before merge →
`.superpowers/handoffs/f115-issue-tracker-DONE.md`; only the user merges.

## 10. Live criteria (post-merge, not forced)

The next scheduled cycle: opens at least the binding-constraint issue in
`store/chips.merchant-gpu/issues/register.json`, the narrator assesses it with reasoning and
cited findings, history.jsonl gains its first line, and the "Known issues" section renders
on the live page. An honest `not-assessed` fallback day rendering correctly is a later
still-unproven check, not a failure.
