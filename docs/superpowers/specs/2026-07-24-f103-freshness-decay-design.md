# F103 — Evidence Freshness: Half-Life Decay + Stale-Official-Source Fixes

**Date:** 2026-07-24
**Status:** Spec (brainstormed interactively; all decisions interactive user picks — zero AFK)
**Trigger:** user critique of the live page — official NVIDIA coverage (May earnings-call
material) keeps surfacing as current evidence. Diagnosis chain verified 2026-07-24: the
coverage manifest steers gatherers to official IR domains daily (`manifests/chips.merchant-gpu.json`
primaryDomains); nothing downstream decays old evidence (the judge keeps citing the strongest
findings regardless of age); evidence rows render undated and in judge order.
**Scope:** the freshness engine + three application layers (page, narrator, gather).
**Explicitly OUT:** the judge (user decision — scores stay comparable, no F6 exposure; if
stale evidence still dominates the RATINGS after this ships, judge-side decay is a separate
gated follow-up and this spec's known limit).

## 1. Decisions (interactive, this session)

| Decision | Pick |
|---|---|
| Fix layers | ALL of A (renderer) + B (narrator rule) + C (gather cadence) + the decay engine |
| Decay scope | Everything but the judge |
| Half-life model | Per-kind |
| Half-lives (user-set) | **news/blogs 3 days · earnings/filings 5 days · structural facts 45 days** |

## 2. The freshness engine

New module `gpu_agent/freshness.py`:
- `weight(published: date, today: date, kind: str) -> float` = `0.5 ** (age_days / half_life)`,
  clamped [0,1]; age anchored on the evidence's **published date** (fallback `observedAt`;
  NEVER `capturedAt` — re-fetching old content must not refresh it). Missing/unparseable
  date → treat as 30 days old (visible but discounted; never crashes).
- `classify(url: str, indicator_id: str | None) -> str` via curated
  **`registry/freshness.json`** (trust-boundary pattern, like `registry/price-benchmarks.json`):
  `{"halfLives": {"news": 3, "filings": 5, "structural": 45}, "filingsDomains":
  ["investor.", "ir.", "sec.gov", "nvidianews.nvidia.com", ...], "structuralIndicators":
  ["leadTimes", "upstreamLeadTimes", "pkgCapacityOrderSpread", ...]}` — default kind = news.
  Tuning = a JSON edit, no code change. (Registry file is NEW — it is not
  `registry/indicators.json` and feeds no brain prompt; not F6-relevant. Verified precedent:
  F98's `price-benchmarks.json`.)

## 3. Application layers

### 3.1 Page (renderer-only)
- Every evidence row (panel, scenes, Explore findings) shows its date — always.
- Evidence rows sort by decayed weight (not judge order); related coverage likewise.
- Weight < 0.25 → row renders dimmed with an "aging" mark (the F98 stale-price-tile
  treatment precedent).
- Publisher-diversity cap: max ONE row per registrable domain per scene's evidence block and
  per related-coverage row set (overflow reachable via the panel/Explore).
- Explore findings page default sort = decayed weight; the filter script untouched.

### 3.2 Narrator (prompt edit — dedicated narrator pin re-record, NOT F6)
- Narrator inputs annotate every finding + doc-pool entry with `freshnessWeight` (computed
  by the step, engine above).
- Prompt rules added: prefer the freshest evidence for every claim; ANY evidence older than
  ~3 weeks cited in prose must be dated in the prose ("at their late-May earnings call …");
  quiet-day entries must not lean on sub-0.25-weight evidence to manufacture news.
- Gate addition (deterministic): if a scene's `claimFindingIds` ALL carry weight < 0.25, the
  scene must date its claims in prose (checked: a four-digit-year or month-name token in the
  paragraphs); violation → standard retry → fallback path (existing machinery).
- Pin re-record is its own task with the prompt edit in the same commit (Phase B convention).

### 3.3 Gather (manifest cadence)
- `manifests/chips.merchant-gpu.json` gains per-source `cadence` for official IR domains:
  `earnings-window` (heavy: every cycle within ±7 days of a known/announced earnings date;
  light: at most weekly otherwise). Known earnings dates live in the manifest as a small
  editable list per entity (next-earnings-date, user-maintained; absent → light cadence).
- The gather planner respects cadence when allocating the daily doc budget (soft cap
  precedent: the weakest-slice drop rule already exists); official-domain re-fetches outside
  the window rank last for budget.
- Manifest edits are NOT prompt-affecting (F98a precedent: manifest sources added with F6
  green) — verify with the F6 pin at every commit anyway.

## 4. Constraints

- The judge briefing, judge prompt, and all scored-eval seams: byte-untouched. F6 pin +
  scoring replay pin + F83 + narrator pin (until its deliberate re-record task) green.
- The engine is display/selection-layer: scorecards, DMI/SMI, thesis, implication unchanged.
- Half-life values live ONLY in `registry/freshness.json` — no constants scattered in code.
- Wall-clock isolation: `today` threaded, never `date.today()` inside the engine.
- The user's half-lives are aggressive by design (3/5/45); the spec records them as the
  user's pick, tunable post-ship by JSON edit without a new lane.

## 5. Testing

Engine unit tests (weights at 0/half-life/2×half-life; capturedAt never used; missing-date
fallback; classification precedence filingsDomain > structuralIndicator > news default).
Renderer: date always present, weight ordering, dim threshold, publisher cap, Explore sort.
Narrator: input annotation present; the aged-claim prose-date gate (pass + violation + retry
path). Manifest: cadence respected in planning (unit over the planner), window arithmetic.
Live criterion (post-merge, not forced): the next cycles' pages stop surfacing undated
May-vintage official material in top evidence rows.

## 6. Sequencing

One lane; the narrator-prompt + pin re-record task LAST so the pin re-records once. After
merge: deploy folds into the next cycle's rebuild (or explicit rebuild+push, user's call).
