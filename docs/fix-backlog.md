# Fix Backlog — from the 2026-07-02 full-repo review

> Source: three parallel deep reviews (core pipeline, temporal store/brief, ops/docs) plus direct
> inspection of the live `store/chips.merchant-gpu/2026-06-v6.json` scorecard. Suite green at
> review time: **417 passed / 3 skipped @ c5358bf**.
>
> **Must-have** = corrupts numbers or judgments, violates a binding doctrine rule, loses data, or
> lets fabricated/injected content reach a rating. **Should-have** = scale-out readiness,
> robustness, hygiene, presentation. Descending priority within each bucket.
>
> Execution model (lanes, waves, merge protocol) is at the bottom — fixes are tagged with their
> lane. Frozen-contract items (`gate.py` / `scoring.py` / Finding schema) ship as **one versioned
> v1.2 migration** (charter Part 33), never piecemeal.

> **Provenance labels:** `user-approved` = an actual user answer exists; `AFK-precedent` =
> proceeded on best judgment while the user was away; `AFK-default` = a specific reversible
> decision taken while away, re-surfaced on the user's return.

> **Wave 2 MERGED 2026-07-02** (main d933b7e, suite 626 passed / 3 skipped): lanes F (F18, F29,
> F33, F34, F49 Price Momentum overlay, F51 per-series price dedup incl. the cross-cycle fix), G
> (F41 minus the frozen schemaVersion-default bump - explicitly skipped, F42, F50, F26-cli), H
> (F26 personas, F27 frontier-closed runnable - note: the old empty-weights-zero-indices claim was
> stale, registry-weight fallback meant indices were never zero; the real deliverables are explicit
> weights + manifest + persona + runnability pins), I (F28 host-aware matching + auditable waivers,
> F40 signpost), J (F39 rating anchors). Reviews: opus on F, sonnet on G/H/I, controller on J.
> Controller wiring: persona threads via --persona/personaLabel (d933b7e).

> **Wave 1 MERGED 2026-07-02** (main f1c0835, suite 516 passed / 3 skipped): the contract v1.2
> migration (F2, F3, F7, F8, F9, F16, F17, F21, F36, F37 - shadow-run + replay v7-v12 in
> docs/migrations/2026-07-contract-v1.2.md) and lanes C (F19, F20, F35, F38), D (F10, F11, F12,
> F13-report, F22-cli), E (F14, F15, F30, F31, F32, F13-wiki, F22-lint). Reviews: opus on the
> contract diff, sonnet on C/D/E; every stream READY-TO-MERGE with fixes applied where demanded.

## Must-have

- [x] **F1 — Protect the canonical store.** `store/` is gitignored; all history is one
  `git clean -xdf` from gone. Commit it or add a versioned backup. *(Wave 0 — DONE f7ace81:
  canonical paths tracked; scratch subtrees stay ignored)*
- [x] **F2 — Evidence-integrity gate bundle** (`gate.py`, `extraction/`): **(a)** `observed`
  requires ≥1 evidence (today `gate.py:7-14` only checks measured); **(b)** `evidence.excerpt`
  must appear in the source document content; **(c)** `evidence.url == doc.url`;
  **(d)** `evidence.tier` code-stamped from the document tier, stripped from model output;
  **(e)** secondary-only evidence → confidence ≤ medium enforced in the gate. Closes the
  fabrication/injection path. *(Lane A)*
- [x] **F3 — Enforce the Part-37 headline-protection rule.** A dimension rating resting solely on
  secondary sources must be confidence-capped + flagged. v6's `bottleneck` and `moat` each rest on
  one blog yet report `grounded` / `confidenceCap: null` (`pipeline.py:60-76`). *(Lane B)*
- [x] **F4 — Wire memory into judgment. DONE (sub-project 5-1, merged 7197226).** `gpu_agent/memory.py`
  builds the prior-state bundle (prior scorecard summary, thesis book, wiki states, price series, cycle
  chronology) and renders the fenced MEMORY block; injected additively into the judge emit path
  (`judge --emit-prompt --store`) and the thesis prompt — byte-identical prompts when absent. Verified
  live in the 2026-07-03 daily cycle: the judge received MEMORY and judged direction vs the 07-02 prior
  (category direction steady vs prior improving). *(Feature track)*
- [x] **F5 — Anti-whipsaw check. DONE (sub-project 5-1, merged 7197226).** Code-owned in
  `gpu_agent/thesis.py` apply engine: a secondary-only reversal defers as a pendingChallenge
  (`CHALLENGED — pending confirmation ⚠` in THE CALLS); primary evidence or a second consecutive
  same-direction signal applies; conviction moves ≤1 level per applied cycle; applied `broken` retires.
  All branches test-pinned (scenarios a–k). *(Feature track)*
- [x] **F6 — Depth Rubric + Golden Set — DONE 2026-07-04** (recorded Action Item 1). Half 1
  (sub-project 5-1): depth fields (mechanism / falsifiableTrigger / sensitivity) carried on every
  thesis judgment and GATE-ENFORCED. Half 2 (merged `87f281a`, baseline `0344949`): eval harness
  (gpu_agent/evals/ + eval CLI + run-eval skill), 18-case golden set, and the ARMED hash-pin
  regression gate — any brain-prompt edit turns the suite red until run-eval + rebaseline. Initial
  baseline (post-F67 prompts): extract 6.62 / judge 6.75 / thesis 5.50; calibration held (negatives
  2/1/0/2 of 8, limit 4). The first live run caught and shipped fixes for: missing demand/supply
  indicator vocabulary in the extract prompt (completes F55), acronym-allowlist gaps + an
  abbreviation-blind sentence splitter in the F67 voice lint. Spec
  docs/superpowers/specs/2026-07-04-f6-eval-harness-design.md. *(Feature track)*
- [x] **F7 — DMI/SMI entity shadowing.** `scoring.py:25-30` buckets by `indicatorId` only; NVDA and
  AMD erase each other per indicator. Bucket by `(entity, indicatorId)`. *(Lane B, contract v1.2)*
- [x] **F8 — Price-indicator handling — DECIDED 2026-07-02: overlay-only.** Flip D6 to
  `scoring: false` (price findings never feed DMI/SMI, per charter v1.1); static levels with
  `trend: unknown` carry polarity 0 — levels without a baseline are not momentum. Follow-ups:
  visible Price Momentum Index = **F49** (Wave 2); change-based price scoring deferred until F12
  provides price history and F6 can grade the judgment. *(Lane B + extraction guidance in Lane A)*
- [x] **F9 — Deterministic anchor polarity track.** `briefing.py:23` lets the last finding's
  indicator pick the dimension's track (order-dependent gate outcomes). Define per dimension at
  registry level. *(Lane B, contract v1.2)*
- [x] **F10 — Corroboration merge + dispersion emission.** Same (entity, indicator, value, period)
  from two sources = one finding with two evidence entries (v6 stores NVIDIA's $75.2B twice);
  conflicting same-key findings must set `dispersion` instead of recency-collapse
  (`gathering/dedup.py:171-189`). *(Lane D)*
- [x] **F11 — Recorded-replay alignment.** The live path IS `--recorded`; a failed validation
  consumes the *next* document's answer → silent cross-attribution (`llm/recorded.py:11-14` +
  `cli.py:209-214`). Pair answers to docs explicitly; hard-fail on length mismatch. *(Lane D)*
- [x] **F12 — L1 dedup: content-hash before URL; record "seen" only after extraction commits.**
  Stable-URL price pages are dropped forever after first sight (`dedup.py:74-79`); crash
  pre-extraction permanently loses docs (`dedup.py:105`). *(Lane D)*
- [x] **F13 — Fix the asOf-grain trap.** Month grain drops a second same-month ingest's
  contradictions (`wiki/ingest.py:142-145`) and empties intra-month diffs; day grain silently breaks
  `find_prior`'s regex (`report.py:37`). Validate the grain, key ingest events by run, make
  `find_prior` fail loud. *(Lane D + Lane E)*
- [x] **F14 — Gate the wiki enrichment channel.** `apply_enrichment` (`wiki/ingest.py:125-146`)
  writes LLM body/state/salience with no check that cited `[f-...]` ids exist and no numeric gate —
  the one path where un-gated claims reach the brief. *(Lane E)*
- [x] **F15 — Salience computed in code, never brain-invented.** The 4-1 spec forbids exactly what
  the shipped prompt asks (`wiki/ingest.py:11`); model salience currently drives materiality, decay,
  pruning, STORYLINES order. *(Lane E)*
- [x] **F16 — Injection hardening at extraction.** Escape/robustly delimit document content in the
  prompt fence (`extraction/prompt.py:32-34`); never fold system into user; dispatch extraction
  subagents tool-less. *(Lane A)*
- [x] **F17 — Vintage honesty validation.** `evidence.date` = publication date, not fetch date (v6
  is full of `2026-07-02` fetch stamps in a June scorecard); validate `observedAt`/date formats;
  flag future-dated evidence relative to `asOf`. *(Lane A)*
- [x] **F18 — `_traj_arrow` keyword bug.** "supply glut worsening" renders UP ▲ because
  `"up" ⊂ "supply"` (`brief.py:123-139`); make trajectory a constrained enum. *(Lane F)*
- [x] **F19 — Single-sample "unanimity."** A dimension in 1 of 3 samples gets high confidence with
  basis "1/1" (`judge.py:64-74`); require a real quorum. *(Lane C)*
- [x] **F20 — Propagate confidence caps upward.** A dimension driven by hypothesis/capped findings
  must inherit the cap; finding-level confidence is never consulted at aggregation. *(Lane C)*
- [x] **F21 — Impact quality gate.** Empty `targets`/`mechanism` pass; require non-empty and
  taxonomy-valid targets. v6's impacts are 100% self-referential — starving the future
  recommendation layer. *(Lane A)*
- [x] **F22 — Kill the silent drops.** `_pipeline` discards gate-dropped findings unlogged
  (`cli.py:277-280`); lint discards untagged-indicator lists and swallows exceptions
  (`lint.py:98-99,164-165,200,225`); report silently skips unreadable priors. *(Lane D + Lane E)*

## Should-have

- [x] **F23 — Charter compliance matrix. DONE — merged `dc0f218` (2026-07-13, user "merge them
  all").** `docs/compliance-matrix.md` (123 rows over all 39 Parts: 57 ENFORCED / 25 PARTIAL /
  10 SESSION-PROSE / 27 DEFERRED / 4 NOT-ENFORCED, 65 test-function pins) +
  `tests/test_compliance_matrix.py` rot lint. Review round 1 caught 1 Critical (P16.version
  cited a nonexistent taxonomy version field) + 3 Important — all fixed, re-verified. Open
  decision A4 recorded in the sentinel (P19.budget DEFERRED vs NOT-ENFORCED; reviewer leans
  DEFERRED). Clause → enforcement point → test; stops "binding"
  drifting into aspiration (would have caught F2/F3/F5). *(Feature track)*
- [ ] **F24 — Entity canonicalization + per-category namespacing.** `NVDA` vs `nvidia` fragments
  pages; `entity:amd` is global across future categories. Part 18/21 registry with aliases +
  category scoping before fan-out. *(Feature track)*
  **STATUS 2026-07-13: STAGE 1 MERGED `6d40f82`** (spec
  `docs/superpowers/specs/2026-07-12-f24-entity-resolver-stage1-design.md`, all forks
  user-approved interactively): `gpu_agent/entities.py` resolver over taxonomy seedEntities;
  canonical ids at the new-finding seams (extractor + wiki ingest); unregistered names pass
  byte-unchanged, flagged stderr + cycle log; 10 test files migrated (review: all FAITHFUL).
  **STATUS 2026-07-14: STAGE 2 MERGED `3b712fa`** (spec
  `docs/superpowers/specs/2026-07-13-f24-stage2-design.md`, forks user-approved interactively):
  13 entity registrations (amd/intel/broadcom own merchant-gpu; 5 hyperscalers, 3 memory makers,
  2 neoclouds appear-in only); the user-signed nvda→nvidia consolidation (5 observations moved
  with original vintages, nvda retired + pointer, NVIDIA retitle) executed in-session under the
  user's direct signature; the append-vs-append wiki-log conflict with the 2026-07-14 daily v7
  cycle was reconciled (disjoint pages, consolidation events renumbered seq 115-124). **STAYS
  OPEN:** the 5 server ODMs stay UNREGISTERED by user decision (no honest category — creating one
  is a Part-16 human gate; revisit when an ODM-adjacent desk onboards) + full multi-category
  counting at desk #2.
- [x] **F25 — Wiki store performance + concurrency. DONE — merged `bf8ad6c` (2026-07-13, user
  "merge them all").** Incremental byte-cursor log cache (every read revalidates via stat;
  truncation detected), Aho-Corasick health scan, lockfile-guarded seq mint (Windows-safe
  O_EXCL). Measured on a 300-page store: index 5.42s→0.10s (~54×), per-page reads ~40×, build
  ~6×, health ~3.6×. Review: Ready to merge, 0 Critical; its one forward-looking flag became
  F87 (now also merged). O(N) full-log re-reads per operation,
  O(pages²) health scans, `seq = len(read())` TOCTOU race — fatal at 34 concurrent categories.
  *(Feature track)*
- [x] **F26 — De-GPU the template.** "GPU market analyst" persona hardcoded for every category;
  `judge --category` defaults to merchant-gpu; `--primary-sources` defaults to sec.gov; skills
  hardcode the merchant-gpu assignment. Parameterize by assignment. *(Lane H)*
- [x] **F27 — Make `frontier-closed` runnable.** Empty weights (zero indices), no manifest, flat
  indicator namespace. Second category = the generalization proof. *(Lane H)*
- [x] **F28 — Coverage-gap matching.** Substring URL patterns produced false "required gaps"
  (10-Q via s201.q4cdn.com, BIS via www.bis.gov) that were waved off in free text. Indicator-level
  credit or mirror patterns; overrides become a structured, auditable field. *(Lane I)*
- [x] **F29 — Single-source ⚠ flag in the brief** (deferred 4-5 item) — v6 shows it can't stay
  deferred. *(Lane F)*
- [x] **F30 — Log lifecycle promotions.** `update_header` writes no event; registered/provisional
  flips are invisible to replayable history (`wiki/store.py:107-114`). *(Lane E)*
- [x] **F31 — Real corroboration for promotion.** Distinct free-text `evidence.source` strings count
  the same publisher twice (`lifecycle.py:56-65`); key by domain/publisher. *(Lane E)*
- [x] **F32 — Read paths must not write.** `wiki-lifecycle` propose calls `lint()` which appends a
  log event and can mint a "cycle," aging every page (`cli.py:152`); provenance-only events must not
  count as cycles for decay (`lint.py:127-128`). *(Lane E)*
- [x] **F33 — Bound brief growth.** STORYLINES renders every page forever; pruned pages never
  archive. Add an archived state or render cap. *(Lane F)*
- [x] **F34 — Recalibrate the materiality fold.** New secondary threads score 0.27 &lt; 0.3 threshold —
  structurally hides the discovery class the lifecycle exists to catch. Retune or document. *(Lane F)*
- [x] **F35 — Judgment citation coherence.** The judge can cite a momentum finding for a moat rating
  (`gate.py:43-47` checks existence only); validate `findingIds` against the dimension's indicator
  group. *(Lane C)*
- [x] **F36 — Tighten the anchor band; fix its label.** ±0.5 tolerance allows "Very strong" at
  −0.49 (`gate.py:30-35`); the "z=" message references a z-score that doesn't exist (`zscore()` is
  dead code — use it for trend-vs-blip or delete it). *(Lane A, contract v1.2)*
- [x] **F37 — Check `Finding.side` against the registry** — currently decorative; silent
  contradictions persist in stored data. *(Lane B)*
- [x] **F38 — Honest self-consistency.** All 3 judgment samples come from one subagent generation
  (correlated); sample independently, and move the vote spread out of `confidence.basis` into its
  own field. *(Lane C)*
- [x] **F39 — Per-dimension rating anchor definitions.** "Weak" bottleneck (built) vs "Very strong
  choke point" (charter Part 17 example): write the five-word definitions per dimension so two
  analysts pick the same word. *(Lane J)*
- [x] **F40 — Fix or delete `ClaudeCodeClient`.** Reads `message.text` (SDK uses content blocks),
  leaves tools enabled, zero coverage, not the path the skills use. *(Lane I)*
- [x] **F41 — Input robustness bundle.** Reject NaN; parse timestamps (lexical compare misorders
  mixed offsets, `scoring.py:14`); bump `Finding.schemaVersion` default to 1.1; validate wiki page
  ids/slugs (path escape, `wiki/store.py:82-84`); crash-recoverable `route_findings`. *(Lane G)*
- [x] **F42 — Hardcoded paths → config.** `registry/indicators.json` / `docs/taxonomy.json` are
  cwd-relative literals across the CLI. *(Lane G)*
- [x] **F43 — Move gather outputs out of `docs/`; reconcile `ingested/`.** 20 scraped JSONs beside
  the charter (the skill's `--out docs` example is the cause); duplicate folder missing
  `coverageGaps`; gitignore the artifacts. *(Wave 0 — DONE 839113b: skill writes to work/;
  artifacts archived under work/gather-2026-07-02/)*
- [x] **F44 — Refresh continuity docs.** HANDOFF.md instructs redoing the merged 4-5b;
  START-HERE.md describes the dead OAuth backend. *(Wave 0 — DONE 7b93be3)*
- [x] **F45 — Honesty overlay on `swarm-graph.html`.** Mark built vs deferred; today it presents
  all 34 agents + 3 tiers as existing. *(Wave 0 — DONE f173165: build-status overlay,
  BUILT/PARTIAL/DEFERRED badges + panel status + legend)*
- [x] **F46 — Run a real second cycle.** Sub-project 4's machinery has never executed against real
  state (no `store/wiki/`, no `seen_docs.jsonl`; v1–v6 are same-month reruns). Cheapest integration
  test available. *(Validation gate after Wave 1 — DONE 2026-07-02: live daily cycle →
  `store/chips.merchant-gpu/2026-07-02-v1.json` DMI +0.227/SMI +0.053, Δ vs the v1.2-replayed
  2026-06-v12; L1 index seeded, L2 dedup 9 new/8 dup, wiki 3 entity pages, lint 3 material.
  Surfaced F50 + F51 below.)*
- [x] **F47 — Retire or sync the stale doc tree** in `Documents\TSMC\ai4bi\ai_state_of_the_market`;
  pull `action-items.md` into this repo. *(Wave 0 — DONE c83ae83: action-items.md in-repo;
  external tree got a RETIRED.md pointer, nothing deleted)*
- [x] **F48 — Front door.** Real readme (and consider the repo name before anything is shown under
  TSMC branding). *(Wave 0 — DONE 86d0224: real readme with honest build status; repo RENAME
  remains a user call, flagged in the readme)*
- [x] **F50 — Run asOf must own the scorecard label** (born from the F46 gate). `Scorecard.asOf`
  comes from `assignment.asOf` (a committed fixture pinning `2026-06`), not the run's `--as-of` —
  the F46 daily cycle first wrote its scorecard as `2026-06-v13` (removed; re-run with a
  run-scoped assignment copy). Make the pipeline's `--as-of` override the assignment's, or
  fail-loud on mismatch. *(Wave 2, Lane G — cross-cutting robustness)*
- [x] **F51 — Finer dedup key for price series** (born from the F46 gate). L2 keys by
  `(entity, indicatorId)`, so every NVDA D6 row across providers and SKUs (B200 vs H100; Lambda vs
  CoreWeave vs Runpod) collapses to one rep + dispersion. The F49 price track needs a per-series
  key (SKU/provider) before it can chart anything. *(Wave 2, with F49 in Lane F)*
- [x] **F49 — Price Momentum Index overlay** (born from the F8 decision). Compute the price-side
  rollup in code as a third, clearly-labeled confirmation track beside DMI/SMI — displayed, never
  blended (charter Part 17's overlay, formalized). Needs the F8 polarity-0 rule already in.
  *(Wave 2, Lane F)*
- [x] **F52 — Vintage-scoped finding ids** (born from the sub-project-5 integration gate,
  2026-07-03 daily cycle). Finding ids are `docId-<n>` and docIds derive from the URL, so a URL
  re-gathered on a later day (a daily price page, a re-excerpted news article) reuses prior-cycle
  finding ids; when content differs, the append-only FindingStore's collision check fails loud in
  `route_findings` (observed: `www-digitimes-com-f88ca4e6-1`, `lambda-ai-845323fc-1`). L1's
  url+hash known-check cannot catch it because gatherer excerpts vary run-to-run. Scope the finding
  id (or docId) by asOf/vintage, or make L1 url-aware for static-content sources. The 2026-07-03
  cycle worked around it with a logged wiki-ingest exclusion (`work/daily-2026-07-03/
  ingest-exclusions.json`); scorecard path unaffected. *(DONE 2026-07-03: vintage-scoped
  docIds at the gather seam — `{slug}-{digest}-{asOf}`; `ingest --as-of` now required;
  finding ids inherit via the existing `{docId}-{n}` stamp; L1 url+hash unchanged, so
  unchanged content is still skipped cross-day. Spec
  docs/superpowers/specs/2026-07-03-f52-f53-f54-small-fixes-design.md)*
- [x] **F53 — Cross-cycle indicator consistency for price rows** (born from the same gate). The
  07-02 extraction labeled marketplace price levels `D6`; 07-03's labeled them `gpuSpotPrice` —
  both registered price indicators, so the F49/F51 per-series price track finds 0 matched series
  across the two cycles and PMI renders `—`. Pin ONE indicator id per price-source class in
  extraction guidance (or normalize at price-track level) so day-over-day deltas can ever compute.
  *(DONE 2026-07-03: both halves — the extractor seam rejects a measured price-side row whose
  value.unit != the registered canonical unit (catches the mislabel AND free-text unit drift,
  loud → re-dispatch), and `extract --emit-prompt` lists the registry's price-side ids +
  canonical units, F55 pattern. tests/test_extractor_price_unit.py)*
- [x] **F55 — Emitted prompts carry the id vocabularies the gates enforce. DONE (session,
  2026-07-03).** Born from BOTH live cycles on the sp5 stack: each coordinating session had to
  hand the brains the valid taxonomy ids (extraction impact.targets) and the judge citation
  groups out-of-band, and each got them wrong first try — one full re-dispatch wave per cycle.
  Now `extract --emit-prompt` appends the taxonomy's category ids to the system prompt
  (`build_system(valid_targets=...)`, sourced from the same `taxonomy.categories` the gate
  checks), `judge --emit-prompt` appends a `<citationGroups>` block (code-computed per-dimension
  id groups + the six DIMENSIONS names, `build_user_prompt(include_groups=True)`), and the
  thesis SYSTEM states the v1 observable heuristic verbatim instead of letting the brain
  discover it by rejection. All default paths byte-identical (F26/F4 additive pattern);
  `judge_findings`' frozen internal path untouched. tests/test_prompt_vocab.py. *(DONE)*
- [x] **F54 — Seed thesis triggers should pass the gate heuristic they will be judged under**
  (born from the same gate). Two committed seed triggers (`supply-constraint-binding`,
  `custom-asic-substitution`) name no observable under the thesis gate's v1 heuristic; the brain
  echoing them back verbatim was correctly rejected and had to reword (e.g. "lead times" does not
  match the id `leadTimes`). Either upgrade the seed data's trigger prose to heuristic-passing
  form, or document that seeds are grandfathered DATA and only judgments are gated. One-file data
  fix + a seed-lint test. *(DONE 2026-07-03: the two triggers reworded to heuristic-passing form
  — semantics preserved, observables named ("2 consecutive quarters");
  tests/test_seed_thesis_lint.py locks every seed trigger + depth field. Live store book
  untouched: history.jsonl's seeded event embeds the entries.)*
- [x] **F56 — Validate `--as-of` shape at the seams** (born from the F52/F53/F54 final review,
  2026-07-03). **DONE — merged `0c49d6a` (2026-07-13, user-directed) after a clean rebase onto
  the post-stage-6 main (the feared cli.py conflict never materialized). All 10 CLI `--as-of`
  seams validated loud; both cosmetic minors fixed; review verdict (Ready to merge, 0
  Critical/Important, both AFK picks endorsed) in `.superpowers/handoffs/f56-asof-DONE.md`.
  Suite 1336/5 → 1346/5.** `--as-of` is required everywhere but any non-empty string is accepted, and F52 now
  embeds it in doc ids → snapshot + FindingStore filenames; a fat-fingered `2026/07/03` would mint
  a path-unsafe id. Pre-existing convention (asOf already flowed unvalidated into the dedup index
  and wiki stamps; the skills always pass ISO dates), so defense-in-depth only: validate
  `^\d{4}-\d{2}(-\d{2})?$` once at the seam. Also fold in two deferred cosmetic minors from the
  same review: the seed-lint depth-fields comment overclaims "mirrors gate rule 3" (rule 3 doesn't
  check statement), and `build_system(price_indicators=[])` renders a malformed trailing "shown: ."
  sentence (unreachable while the registry has price-side indicators). *(Next wave — tiny)*

---

## From the 2026-07-03 freshness & exec-gap review (F57–F65)

> Source: three parallel deep explorations (design docs, live-output source audit, gather
> fan-out trace) prompted by the observation that briefs lean on lagging 10-Q data. Evidence,
> verified against the live store:
>
> - Flagship `store/chips.merchant-gpu/2026-07-v1.json`: 72 findings, **32 (44%) from the
>   Apr–May Q1 earnings cycle** (10-Q + releases + transcripts, 6–10 weeks stale at run time).
>   The only sub-week evidence is 12 weight-0 vendor price levels. Zero fresh headlines back any
>   of the six dimensions; the Apr-26 NVDA 10-Q is the sole primary/high-confidence evidence.
> - `work/live-2026-07/gather-log.json`: the 20-doc cap tripped in round 2 with 60+ fresh leads
>   logged "not chased" (TechCrunch Anthropic–Samsung 2nm, Tom's Hardware ASIC roundup, NVIDIA
>   blog posts); `open-web-asic` and `open-web-gpu-share` ended "not-covered".
> - The standard live gather has **no news/headline slice at all** ("news" appears once in the
>   skills, inside Daily mode) and seeds filing URLs first; the recency window is Daily-only.
> - The daily runs DO capture fresh signal (`store/findings/`: Anthropic–Samsung 2nm, NVIDIA
>   vendor-financing, Digitimes 2H26 order boom) — but the standard live path never reads the
>   wiki/findings store back (`run-cycle/SKILL.md:219`), so the flagship re-derives from its own
>   ≤20 docs and discards it. Smoking gun: `vendor-financed-demand-circularity` was proposed
>   from the July-1 NVIDIA newsroom announcement in the morning daily and demoted to conviction
>   low by the evening flagship **the same day** ("no primary support") — even though the
>   evidence is NVIDIA's own official post, stamped secondary because the primary allowlist is
>   just `sec.gov,investor.nvidia.com`, narrower than the charter's "filings, official posts".
>
> Exec-lens verdict: the brief reads as a well-organized summary of last quarter's earnings
> season, not an intelligence product. F57–F61 make it **current**; F62–F65 make it a
> **product**. Priority order (user-approved 2026-07-03, amended same day after report
> reconciliation): **step 0 = the F6-second-half rubric eval → F62 → F63 → F57/F58/F59 → F60 →
> F64 → F65 → F66**, with F61 shippable immediately (cheap, independent). Roadmap items
> surfaced by the same review (more categories, layer tier, Main roll-up) are not re-logged
> here — they are the existing deferred build.
>
> **Reconciled 2026-07-03 with the deep-research report**
> (`docs/2026-07-03-agent-best-practices-research.md`), which independently converged on the
> same gather-aim diagnosis. Adopted: **step 0 is the eval harness** (F6 second half / Action
> Item 1's Depth Bar, scoped as ~20 recorded-cycle cases graded by a brief rubric — it gates
> every prompt change in F57/F58); the evidence-sufficiency gate folds into F63; Brier scoring
> folds into F64; the citation-audit pass is F66. Graphiti = architecture reference for F24
> when it runs (its benchmark claims are refuted — see report §7). **Considered and REJECTED
> (user-approved 2026-07-03 — do not resurrect without new evidence):** (a) the SEC EDGAR
> structured pipeline / sec-api.io spend — it deepens the filings strength while the leading
> pipeline is the weakness; only F59's tier-classifier fix survives; (b) the
> search-API/scraper-stack benchmark (Tavily/Exa/Firecrawl…) — the headline gap is aim +
> doctrine, not fetch tech (the gatherers found the right stories; the system didn't chase or
> use them); revisit only if fetch failures remain the binding constraint after F57/F58.

### Fixes (bounded — lane-style)

- [x] **F57 — Headline + forward-signal slices in the standard gather. DONE — merged `72261a4`
  (lane-freshness, 2026-07-04): headline + forward-signal slices, per-class doc floors, a
  price-fetch cap, and don't-re-fetch-seen-filings; gather-skill prose + `tests/test_lane_freshness.py`.**
  Round-1 seeds in
  `.claude/skills/gather-category/SKILL.md` contain no news angle; the only open-web query is
  one `"<entity-names> <source.label>"` per free-web source, and the entity×metric slices
  append "latest official filing / 10-Q / 10-K / investor relations". Add per-entity headline
  slices ("<entity> news / announcements past N days") and forward-signal slices (guidance
  revisions, lead-time drift, design wins), **interleaved with — not after — the filing URL
  seeds**, and partition `maxDocuments` into per-class floors (filing / news / forward) so
  filings cannot starve the open web. Skill prose + manifest data; the gather-log's coverage
  classes prove the fix. Two additions adopted from the research report's companion diagnosis:
  **cap price-page fetches at 2–3 per cycle** (the class floors set news/forward minimums; this
  sets the price-class maximum — dailies currently burn ~half their findings on weight-0 price
  scrapes), and **stop re-fetching already-seen filings mid-quarter** (thread the L1 seen-doc
  filter, today daily-only, into the standard live path for filing URLs, or skip known-hash
  filing seeds).
- [x] **F58 — Recency window in live mode. DONE — merged `72261a4` (lane-freshness, 2026-07-04):
  live-mode `recencyDays = 45` window, filing seeds exempt. SUPERSEDED by F78 — the window rule is
  reworked to a 7-day initial sweep + discretionary older-lead pursuit (logged).** `recencyDays`, "since <date> / past week"
  qualifiers, and the date-window lead drop exist only in Daily mode; the standard live path
  has no freshness bias at all — which is how a 2026-07 flagship's freshest substantive doc was
  an April filing. Add a live-mode recency dial (wider than daily's 7, e.g. 45 days; filing
  seeds exempt) applied to seed queries and the on-topic filter.
- [x] **F59 — Primary allowlist matches the charter's definition of primary. DONE — merged `72261a4`
  (lane-freshness, 2026-07-04): official IR/newsroom domains count as primary via the manifest's
  `primaryDomains` allowlist (not a hardcoded pair); `tests/test_lane_freshness.py`.** Charter says
  primary = "filings, **official posts**", but ingest stamps primary only for
  `--primary-sources sec.gov,investor.nvidia.com` (gather-category SKILL.md:114; `cli.py:590`
  defaults to `sec.gov`). So `blogs.nvidia.com`, `nvidianews.nvidia.com`, `ir.amd.com`,
  `intc.com` — the vendors' own announcements — land secondary → confidence-capped → "no
  primary support" demotions for claims the vendor itself made. Extend the allowlist to
  official IR/newsroom domains, driven per-category from the manifest's source inventory
  instead of a hardcoded flag value. Regression case: the July-1 vendor-financing announcement.
- [ ] **F60 — Let fresh signal score.** Every fresh-cadence indicator is excluded from
  DMI/SMI: `gpuSpotPrice`/`D6` are `side:"price"`, `designWins` is `side:"structural"` (both
  skipped by `scoring.py`'s dmi_smi_contribution); `leadTimes` scores but its deep source is
  paywalled; and the two "leading" scoring indicators (`rpoBacklog`, `vendorRevenueGuidance`)
  are themselves 10-Q/earnings-sourced. Result in the flagship: outlook ran 5 findings vs
  momentum's 34 with `smiContribution: 0.0`. Give the leading set real weight in
  `registry/indicators.json` and/or admit a news-sourced leading indicator. **Frozen-contract
  caveat:** registry-weight changes are DATA and safe; any `scoring.py`/side-semantics change
  ships only as a versioned migration (Part 33), never piecemeal.
  **STATUS 2026-07-08 (S1 lane `fix/freshness-weights`): DATA half done — Option A reweighted the
  leading DEMAND set (`rpoBacklog` 0.10→0.14, `vendorRevenueGuidance` 0.12→0.16) so
  corpus-persisted leading findings move DMI. Weight-only → F6 pin stayed green; `scoring.py`
  untouched. Verified effective in live scoring (the assignment overrides only `{D2,D6,S9,S10}`, so
  these two use the registry default). One consequence handled: the v1.2 replay-fidelity test was
  frozen to its historical weight vector (no store scorecard edited). F60 STAYS OPEN
  (wave-plan §6 Deferred Ledger): (1) the `scoring.py` side-semantics half ships as the future
  v1.5 migration; (2) the `smiContribution: 0.0` residual is a SUPPLY gap — no leading *supply*
  indicator exists, so a demand reweight cannot move it; needs an Option-C indicator or the v1.5
  half. Do NOT tick F60 done on this merge.**
  **UPDATE 2026-07-11: both residuals fold into F79** (SDEWS-style scoring v2.0 — the v1.5
  side-semantics slot is superseded by v2.0, and leading supply arrives as backfilled series
  S1/S2 per the extraction doc). F60 stays open until F79 lands them.
- [x] **F61 — Staleness banner; honest confidence label. DONE — story-page half built on branch
  `f61-honesty-banner` (2026-07-28, awaiting user merge); `report.py` half done-by-F67
  (`b0e8061`, 2026-07-04).** Original entry: the brief renders "confidence: high
  (self-consistency over 3 samples)" — vote agreement, not evidence currency — atop evidence
  with a ~6-week median age, while the gather-log quietly records TrendForce / SemiAnalysis /
  channel-checks as not-covered. Render an evidence-vintage line (median + oldest evidence date
  vs `asOf`, share older than N weeks) and the coverage gaps in the brief header, and relabel
  the confidence basis. `report.py` only — pure projection, replayable for $0.
  **Resolution (2026-07-28, all forks answered interactively by the user — zero AFK):**
  (1) The `report.py` half shipped inside F67 four months' worth of lanes ago —
  `report.evidence_vintage()` + the `render_header` vintage and vote-agreement lines are
  F61's original text verbatim. It was never ticked. (2) F103 did NOT overlap: F103 is per-row
  (dating, weight-sorting, publisher cap, aging dim) and computes no aggregate. (3) The
  **surface moved** — since F101 the live category page is the story page, which carried none
  of it; the two other renderers that still compute an aggregate vintage
  (`site_model._why`'s trust entry, the F97 `brief_render` footer) feed pages `site_build` no
  longer emits. So the repo computed the number three times and showed the reader zero times.
  **Built:** one quiet plain-English line under the story-page dateline —
  `story_model.evidence_honesty()` (reusing `report.evidence_vintage` via a duck-typed adapter,
  `report.py` untouched) + `story_render._honesty_line()`; humanised dates at day/month/year
  grain; each half renders alone and nothing renders when neither is available; malformed data
  degrades with a warning instead of crashing the page. Renderer-only; all four pins untouched.
  Spec `docs/superpowers/specs/2026-07-28-f61-honesty-banner-design.md`, plan
  `docs/superpowers/plans/2026-07-28-f61-honesty-banner.md`.
  **Coverage gaps are OUT of F61 by user decision** — they are not obtainable from committed
  data today; filed as F109 below.

### Features (per repo convention: brainstorming → spec → plan, own sub-project — not lane work)

- [x] **F62 — Flagship consumes the daily store.** Daily mode WRITES fresh findings into the
  wiki (`wiki-ingest`, run-cycle SKILL.md:209) but the standard path never READS the wiki or
  `store/findings/` back (SKILL.md:219): the monthly brief is a projection of one cycle's ≤20
  docs, so everything the dailies learn is discarded at exactly the moment someone reads the
  output. Make the accumulated store a first-class input corpus to flagship extraction /
  judgment / thesis, demoting the web gather to top-up. **Highest-leverage item of this
  review.** Interacts with F52 (vintage-scoped ids) and L2 dedup.
  **STATUS 2026-07-04: implemented on branch `f62-flagship-consumes-store` (pushed; final
  review approved; frozen core untouched). Eval RESOLVED on merit: after two failed attempts
  isolated a judge prompt/rubric mismatch, the user-approved consensus-departure clause
  (commit b8f41f8) took attempt 3 to PASS (extract 6.75 / judge 7.50 / thesis 6.00) and the
  baseline was rebaselined without --force (f605a77). Suite 970 passed / 3 skipped / 0
  failed. See docs/superpowers/2026-07-04-f62-eval-run-notes.md for all three attempts.
  MERGED to main `eb925bc` (2026-07-04, user go); suite on merged main 974/3/0. The f62
  worktree is retained for the gitignored eval raw data (attempts 1-3) — see the RETAINED
  WORKTREES REGISTRY in `docs/superpowers/HANDOFF.md`.**
- [x] **F63 — Corroboration doctrine for secondary evidence. DONE — merged `017b592`
  (2026-07-05), re-gated under eval-v2; charter Part 37 + gate F2e secondary-corroboration
  exception (contract v1.3), migration note docs/migrations/2026-07-contract-v1.3.md.** Secondary evidence is
  confidence-capped at medium (extraction prompt + gate F2e) and secondary-only findings may
  not move headline status (Part 37) — so no quantity of independent open-web reporting can
  move status or conviction until a filing confirms it. The desk resolves at filing cadence;
  the exec decides at headline cadence. Amend the doctrine: **N independent secondary sources
  (distinct publishers, not syndication) within the window may move status/conviction one
  bounded step**, logged with the corroboration set; the next filing remains the confirm/deny
  checkpoint. Touches charter Part 37, gate rule F2e, thesis judging — a charter amendment,
  handled with migration discipline. **Counterweight (adopted from the research report §3,
  MAST Insight 3 — same spec, ships together):** a deterministic **evidence-sufficiency gate**
  — "is there enough fresh, corroborated evidence to justify *changing* the binding constraint
  / a dimension rating this cycle?" — so corroborated news can move ratings and insufficient
  news cannot. Loosening without the tightening half reintroduces the whipsaw the anti-whipsaw
  machinery exists to prevent.
- [x] **F64 — Trigger-first daily brief — FOLDED INTO F78 — DONE, F78 stage 6 merged `77708f3` 2026-07-13.** (F78's change-first opening leads with
  which theses moved and why — F64's core; its optional Brier-scoring add-on folds into F78 or defers.
  Do not build separately; tick when F78 ships.) The thesis book's falsifiable triggers are the one
  asset an exec cannot get from a news terminal, but the daily output leads with findings and
  trigger matching stays implicit inside judging. Lead the daily brief with a trigger-watch:
  which standing theses' `falsifiableTrigger`s did today's findings touch, which conviction
  moved, and why. Render + a thesis-engine step. **Include Brier discipline (adopted from the
  research report §5):** log every thesis judgment as a probabilistic call and Brier-score it
  as triggers resolve — conviction language earns a track record instead of assuming the
  judgment is calibrated.
- [x] **F65 — "So what for TSMC" section. DONE — merged `a01d840` (2026-07-14, user-directed).**
  Dedicated registry-driven implication brain (`gpu_agent/implication.py` + `registry/
  implications.json` — decision variables as DATA, so new issues are data edits; category-
  agnostic for desk #2), runs after judgment reading the final gated scorecard + thesis book +
  memory bundle (one author, no sampling); deterministic gate (citations resolve, voice lint,
  length cap, hard no-recommendation-verb rule — lane discipline); `store/implications/` carve-
  out; a "FOR TSMC" section in the brief below the exec top band. Spec
  `docs/superpowers/specs/2026-07-13-f65-tsmc-implication-design.md`. **Eval re-gate: the first
  two runs FAILED the judge seam on a byte-identical prompt (grader noise, ε at its 3-run
  quantum floor); resolved by the user-chosen SEAM-SCOPED VERDICT rule (bars bind only to seams
  whose emitted prompt actually changed — spec
  `docs/superpowers/specs/2026-07-13-eval-seam-scoped-verdicts-design.md`); run 3 scored judge
  7.50; 3-run rebaseline gave an honest judge ε 0.50.** The charter's north star is a prioritized
  recommendation; this is the implication (never a recommendation — Layer/Main altitude), now
  a Main-tier roll-up input later.
- [x] **F66 — Post-hoc citation audit pass (low priority).** Adopted from the research report
  §1: citation integrity is enforced at write time (the gate checks findingIds/excerpts), but
  nothing re-verifies the *finished* brief's claims against the findings they cite — the
  production pattern (Anthropic's Research system) runs a dedicated citation-verification
  stage after generation. Add a tool-less audit subagent (or deterministic excerpt-match where
  the claim is numeric) over the rendered brief that flags claims whose cited finding does not
  actually support them. Pairs naturally with F61's render surface. Do after the higher items —
  our write-time gating already covers the worst failure mode.
  **DONE — Phase 1 (deterministic half) MERGED `f19d830` (`--no-ff`) + PUSHED 2026-07-29, user
  authorized.** Built on `f66-citation-audit` (branch + worktree now retired); spec
  `docs/superpowers/specs/2026-07-28-f66-post-hoc-citation-audit-design.md`, plan
  `docs/superpowers/plans/2026-07-28-f66-citation-audit.md`, sentinel
  `.superpowers/handoffs/f66-citation-audit-DONE.md`. Every number in the day's story scenes and
  implication lines is re-checked after the prose is written against the findings that claim cites,
  with rounding tolerance so honest rounding ("7.09" for 7.0931) is not a false alarm. New run-cycle
  sub-step `(e4)` after the narrator; failures re-dispatch the narrator once, then fall back to the
  honest-gap story and mark `citation-audit: failed` — **never blocks the cycle, never strands a
  scorecard**. Artifact at `store/<cat>/audit/<date>.json`, written on both the clean and the flagged
  path (the audit record is evidence). New modules `gpu_agent/numeric_tokens.py` +
  `gpu_agent/citation_audit.py`, new `audit-citations` CLI verb, +32 tests. F83 conformance was
  legitimately re-recorded in-lane per the approved design (`EXPECTED_STEPS` gains `(e4)`;
  fingerprint regenerated from `EXPECTED_STEPS`, never hand-computed). Suite on merged main:
  **2146 passed / 6 skipped**; all four pins green (F6 eval, scoring-v1 replay, narrator, F83);
  forbidden diff EMPTY over `fixtures/`, `registry/`, `gpu_agent/evals`, `gpu_agent/judgment`,
  `gpu_agent/extraction`, `gpu_agent/narrator/prompt.py`, `gpu_agent/scoring.py`, `gpu_agent/report.py`.
  **⚠ Phase 2 — the reading pass that judges whether a sentence is *semantically* supported, not just
  numerically — remains DEFERRED to ride F81, and that is where the residual risk lives** (user
  accepted this caveat; `ClaimResult.verdict` already carries the field Phase 2 will annotate, so no
  schema migration is needed). Provenance caveat from the sentinel: D1-D4 and D5b's sourcing
  mechanism are user-approved; **D5a** (rounding tolerance) and **D5c** (do not widen what the
  narrator brain sees) remain agent-recommended / orchestrator-relayed, not individually
  user-approved. **Live criterion MET 2026-08-04:** the scheduled cycle (`ce593cc`) ran `(e4)` and
  wrote `store/chips.merchant-gpu/audit/2026-08-04.json` with `summary.flagged == 0` (12 claims
  audited, 0 flagged, 0 skipped). The 2026-08-05 audit then flagged one implication line (`impl:7`,
  two China-revenue figures tracing to no cited finding — logged not re-dispatched per the
  implication rule, narrator scenes all clean; the audit catching an unsourced number is the
  feature working, and that line is awaiting a human look). The in-lane
  substitute had been a read-only smoke over a scratch copy (exit 0, 4 claims, 0 flagged).
- [x] **F67 — The output contract: renderer structure + analyst voice. DONE (merged to main
  `b0e8061`, 2026-07-04; suite 828→873/3).** Executed via subagent-driven development from plan
  `docs/superpowers/plans/2026-07-03-f67-output-contract.md` (9 tasks, all task-reviewed; final
  whole-branch review found 1 Critical + 5 Important, all fixed and re-review-verified against
  LIVE store renders — daily and monthly both clean above the `── APPENDIX ──` divider).
  Delivered: `gpu_agent/reader.py` + `registry/acronyms.json` (label maps, allowlist, prose
  lint), `constraintLabel` (additive-optional), voice lint on `judge --recorded` AND
  `pipeline --recorded-judge` (live path) with per-sample indexing + `--no-voice-lint`,
  staleness banner + vote-agreement confidence label, single-reason BLUF with constraint noun,
  calls/why/board/what-moved speak statements + source counts + registry labels,
  `reader.label_ids_in_text` maps indicator ids to labels in "breaks if" display (book keeps
  ids per F54), section reorder + appendix fold + citation map + raw-index table below the
  fold, price dead-metric fold, `report --daily`, run-cycle session-output rule (F38-safe
  re-dispatch, composes with Step 7). Deviations recorded in the spec's 2026-07-04 section.
  Execution ledger + per-task reports: `.superpowers/sdd-f67/` (untracked scratch).
  Original scope, for reference: (1) `report.py` renders one fixed
  inverted-pyramid section order (staleness-banner header → ≤8-line BLUF with the constraint
  *named* via a new additive-optional `constraintLabel` → what-moved with honest empty states →
  compressed calls → why-tree → human-labeled demand/supply board → F65 slot → trust footer →
  appendix), no raw ids above the appendix, no duplicated paragraphs, dead metrics folded;
  (2) an analyst-voice guideline in the judgment/thesis prompt builders (3-sentence narrative =
  state/crux/watch-item, ≤2-sentence rationales, banned-id + sentence-cap **deterministic
  lint**, one re-dispatch then fail loud); plus a run-cycle session rule (final message = brief
  verbatim + ≤3-line run-health footer, logs by path only) and a shared daily shell (daily
  leads with what-moved; calls section becomes F64's trigger-watch when it lands). Absorbs
  **F61**; reserves **F65**'s slot. **Reader contract (user-directed 2026-07-03):** the reader
  is a TSMC executive — internal/doctrine/repo vocabulary is banned above the appendix (label
  map for tier/status jargon; index acronyms words-first), an industry-standard acronym
  allowlist is lint-enforced, brain prompts embed the stop-slop pattern rules (tool-less
  brains can't invoke skills), and the session runs stop-slop on its final message.
- [x] **F68 — F67 follow-ups (born from the F67 final review, 2026-07-04) — partly ABSORBED by F78's brief rewrite.**
  **✓ DONE — merged `a723dac` (`--no-ff`) 2026-08-05, user-authorized; merged-main suite 2173
  passed / 5 skipped, all four pins green.** Bundle of small
  deferred items, none merge-blocking: **(a)** thesis-prose deterministic lint (spec §2b thesis
  slice ships as prompt rules only; add a lint symmetrical to the judgment one — statement ≤1
  sentence, mechanism ≤1, ids only in `falsifiableTrigger`); **(b)** citation map renders only
  each finding's first evidence item — render all; **(c)** BLUF reconciliation note keys off
  `rating + smiContribution < 0` — key off `sdgiDirection`; **(d)** what-moved empty state
  duplicates the folded count with the pre-existing "lower-materiality items folded" line when
  both render — collapse to one; **(e)** `reader.label_ids_in_text` iterative substitution has
  a latent chaining fragility if a future registry label contains another id as a token (no
  collision today — add a registry lint or single-pass substitution); **(f)** pre-existing live
  thesis-store prose carries off-allowlist tokens (`MI`, `GB300`) — cleans up as entries are
  re-judged under the new prompts, or allowlist them if they persist.
  **AUDIT 2026-08-04 (lane `f68-output-followups`, spec
  `docs/superpowers/specs/2026-08-04-f68-followups-audit.md`): (b)–(f) were ALREADY BUILT
  and merged on `fix/lane-polish` (`e173ebc`, 2026-07-04) — all five survived the F78
  rewrite, are live in the current render path, and are test-pinned in
  `tests/test_lane_polish.py`; the entry was just never ticked.** Only **(a)** had residual
  work: `lint_thesis_prose` existed (`gpu_agent/thesis.py`) with its thresholds already
  chosen, but had ZERO callers — the lane-polish plan deferred the wire-up. Wiring it was
  behaviour-shaping, so it was question-stopped, and the user answered interactively
  2026-08-04: **switch it ON, BLOCK on violation** (judge-path semantics — one targeted
  rewrite re-dispatch, then fail loud), **and allowlist `ASE` now**. Shipped:
  `lint_answer_prose` + the shared `_adjusted_statement` parse in `gpu_agent/thesis.py`,
  the block in `cli.py` `_thesis` (before `gate_answer`, shared `voice-lint: ` prefix,
  book byte-unchanged on failure), `ASE` added to `registry/acronyms.json`, 11 tests in
  `tests/test_thesis_prose_lint.py`. Baseline pin GREEN (no emitted prompt bytes changed).
  5 of 52 standing entries still carry two-sentence statements; per the user they are NOT
  to be rewritten by hand — they clean up as those theses are next re-judged, and are inert
  until then (only an `adjusted` verdict rewrites a statement). The recurring off-allowlist
  token problem itself stays with the durable fix below (line ~1050).
  All six sub-items are closed; the tick above carries the merge commit `a723dac`.
- [x] **F69 — The web-reach layer: pluggable external fetchers for the gather swarm. DONE (merged `e167c6b`, suite 923/3).** Spec
  `docs/superpowers/specs/2026-07-04-web-reach-layer-design.md`, plan
  `docs/superpowers/plans/2026-07-04-web-reach-layer.md`. Data-driven registry
  `registry/web-reach-tools.json` (first tool `agent-reach`; the second github drops in as a
  data entry), a health-check preamble + gatherer-contract additions in `gather-category`
  (complementary to WebSearch/web_fetch; secondary tier; chase-to-primary + cross-reference),
  doctrine appended to charter **Part 37**, operator doc `docs/web-reach.md`. Frozen core
  untouched; **no scoring change** (the "N publishers → one bounded step" corroboration math
  stays **F63**). User-approved 2026-07-04 (4 AskUserQuestion forks; charter home = append to
  Part 37, not a new Part). **F63 handoff note:** F69 has gatherers *record* the
  chase/corroboration result as free text in the blob `content` (no structured field); F63
  must add a blob/finding field for the scoring to consume it.
- [x] **F70 — last30days as a discovery-role web-reach tool. DONE (branch f70-last30days-webreach).**
  Adds the second web-reach github (`mvanhorn/last30days-skill`) to `registry/web-reach-tools.json`
  as tool #2, introducing a `role` field: `fetch` (agent-reach — raw content → secondary blobs) vs
  `discovery` (last30days — a last-30-days multi-platform synthesizer used for **leads only**: mine
  its cited sources / hot threads, fetch those as raw blobs, never ingest its synthesized brief —
  charter Part 37 "gatherers return raw material only"). One-time doctrine add for the new `role`
  concept (gather-category tool-roles block + charter Part 37 clause + `docs/web-reach.md`); future
  same-role tools stay pure data entries. User-approved 2026-07-04 (discovery/leads-only). Frozen
  core untouched.
- [x] **F71 — Gate precedence: anchor bound vs. evidence-sufficiency deadlock; `--no-sufficiency`
  too blunt — DONE: shipped in the contract v1.4 migration, merged `e16672a` (P3, 2026-07-08).**
  (born from the first live flagship on the post-F63 stack, 2026-07-05 monthly v3;
  user-approved 2026-07-05). Two code guards demanded contradictory outcomes with no defined
  precedence: the judge rated moat Weak; the +0.50 measured anchor makes Weak illegal (the
  Part 7 bias guardrail — code bounds the rating), forcing Weak→Mixed; F63's
  evidence-sufficiency gate then correctly objected that the move rests on 2 secondary
  publishers (<3, no primary). After one rewrite attempt the run completed under
  `--no-sufficiency` — a whole-run bypass for a one-dimension corner case, on the sufficiency
  gate's first live cycle (recorded in `store/cycle-log.json` gates.sufficiency; the shipped
  moat record itself is defensible — capped medium, honest rationale). Fix, lean: an
  anchor-forced move is code-computed measured evidence, not a judgment re-rate — **exempt it
  from the sufficiency gate**, stamp the rating "anchor-bounded on thin evidence" (rendered in
  the trust footer), keep the existing confidence-cap propagation; and make the bypass
  **per-dimension with a required reason**, or remove it. Alternative considered
  (rejected-lean): sufficiency wins and the rating holds prior + flags under-supported
  (Part 18 principle 8) — but that publishes a rating the measured anchor declares illegal.
  Gate-semantics change → ships as a Part 33 versioned migration; prompts untouched (no
  eval-gate impact unless guidance text changes). Acceptance: the deadlock scenario
  test-pinned (anchor forces a move the sufficiency evidence cannot support → exemption path +
  stamp, no bypass); the whole-run `--no-sufficiency` flag gone or per-dimension + reason +
  logged. **Must land before any unattended loop runs a cycle** — an instance facing this
  deadlock with nobody watching needs a coded rule, not a flag.

---

## Execution model — parallel lanes, 5 at a time

**The constraint that shapes everything:** superpowers' subagent-driven-development forbids
parallel implementers on one branch, and dispatching-parallel-agents requires disjoint domains with
no shared files. So parallelism comes from **file-ownership lanes, each in its own git worktree**,
each lane internally sequential.

**Decisions recorded 2026-07-02 (user-approved — do not re-ask):** (1) F8 = overlay-only now, F49
price track in Wave 2, change-based scoring later. (2) **Contract v1.2 approved as ONE migration:
Lanes A+B are a single coupled stream** (one worktree, `fix/contract-v1.2`) — so Wave 1 runs as
**four concurrent streams** (A+B, C, D, E). The migration must include a one-shot **shadow-run**
(old vs new scoring over the same stored findings; diff in the migration note) and a **replay**
(recompute the stored 2026-06 scorecards' indices under v1.2 as new versions, originals immutable,
so vs-prior comparisons stay continuous).

### Lane map

| Lane | Owns (no other lane touches) | Fixes |
|---|---|---|
| **Wave 0** (ops/docs, no code — run first, fully parallel) | docs, .gitignore, app/ | F1, F43, F44, F45, F47, F48 |
| **A — Evidence integrity** (contract v1.2 part 1) | `gate.py`, `extraction/`, `schema/finding.py` | F2, F16, F17, F21, F36 |
| **B — Index math** (contract v1.2 part 2) | `scoring.py`, `judgment/briefing.py`, `pipeline.py`, `registry/` | F3, F7, F8, F9, F37 |
| **C — Judgment aggregation** | `judgment/judge.py`, `judgment/prompt.py` | F19, F20, F35, F38 |
| **D — Gather/dedup/CLI robustness** | `gathering/`, `cli.py`, `report.py:find_prior` | F10, F11, F12, F13, F22 |
| **E — Wiki integrity** | `wiki/` | F14, F15, F30, F31, F32 |
| **F — Brief/report** (wave 2) | `brief.py`, `report.py` | F18, F29, F33, F34 |
| **G — Robustness bundle** (wave 2) | cross-cutting small fixes | F41, F42 |
| **H — Generalization** (wave 2) | prompts params, assignments, manifests | F26, F27 |
| **I — Coverage + backends** (wave 2) | `manifest.py`, `llm/claude_code.py` | F28, F40 |
| **J — Method docs** (wave 2) | rating anchor definitions | F39 |

### Protocol per wave

1. **Plan per lane** (superpowers:writing-plans): one short implementation plan per lane in
   `docs/superpowers/plans/`, tasks ordered, tests named. Lanes A+B jointly declare the
   **contract v1.2 migration** (Part 33): schema version bump, golden-fixture regeneration, one
   migration note.
2. **Worktree per lane** (superpowers:using-git-worktrees): branch `fix/lane-a` … `fix/lane-e`.
3. **Dispatch all 5 lane agents in one message** (dispatching-parallel-agents) — each agent
   executes its lane's plan sequentially inside its worktree: TDD, self-review, commit per task.
4. **Merge gate, sequential:** merge order A → B → C → D → E; rebase each onto the accumulated
   result; **full suite (417+) green before the next merge**; task-review each lane's diff at merge
   time (subagent-driven-development's reviewer step, applied per lane).
5. **Validation:** after Wave 1 merges, run F46 (a real live cycle) before starting Wave 2.

### What does NOT go in a lane

F4+F5 (memory + anti-whipsaw), F6 (depth rubric + golden set), F23 (compliance matrix), F24
(entity registry), F25 (storage scaling) are **features, not fixes** — each starts with
superpowers:brainstorming → a spec → a plan, executed with subagent-driven-development as its own
sub-project (the repo's existing sp1–sp4 pattern). Do not let a lane agent improvise these.

## F63 eval-run findings (2026-07-04, F63 branch — resolved 2026-07-05)

- **Extraction prompt — corroboration scope**: DONE — folded into F63 before its re-gate
  (prompt now says "across separately fetched documents (… publishers merely quoted inside
  one document do not count)"). Origin: 2/2 fresh extract-04 generations counted publishers
  quoted inside one document toward the 3-distinct-publishers exception.
- **Extraction prompt — impact.direction enum**: DONE — folded into F63 before its re-gate
  (SYSTEM now states `direction: positive|negative|mixed`). Origin: all 8 r2 extract brains
  guessed 'up'/'rising' and failed schema.
- **registry/acronyms.json — 'CEO'**: DONE — allowlisted, folded into F63 (echoed verbatim
  from finding text by brains 4x across F62+F63 runs).
- **Eval infra — multi-attempt bar**: DONE as **eval-v2** (merged to main `c0d5dd2`,
  2026-07-05): baseline = 3 replicate runs; bar = mean − ε (ε = max(half-range, quantum));
  marginal fail ⇒ exactly one replication; per-case crater prong at median − 3. Spec:
  docs/superpowers/specs/2026-07-05-eval-v2-replicate-baseline-design.md.

## From the 2026-07-05 outside-eyes state review (F72–F76)

> Source: a fresh-context review of main @ `99ca522` (post-F63 merge, post 2026-07-v3 flagship),
> requested by the user ("what are we least confident about / what am I missing"). Two findings
> from the same review are already cataloged and are NOT re-logged: external ground truth for
> judgment quality = **F64**'s Brier half; generalization-unproven (frontier-closed is
> config-only; wiki scaling) = **F25/F27** + roadmap. Priority lean (user to confirm):
> **F74 immediately** (tiny; active data-loss exposure in the working tree), **F72** with or
> right after F71 (both are gate-semantics Part-33 work), **F75 before any unattended loop**
> (same bar F71 set), F73/F76 as capacity allows.

- [x] **F72 — Cross-domain wire syndication defeats the F31 corroboration key. DONE — shipped in
  the contract v1.4 migration, merged `e16672a` (P3, 2026-07-08): `registry/syndicators.json` + L1
  near-dup collapse. FOLLOW-UP RESOLVED 2026-07-13: contract v1.4.1 merged `1a5ee33` —
  `sufficiency.py::_sufficient` now counts the SAME collapsed set as gate F2e (9-line seam via
  the shared helper; read-only shadow-check over all stored cycles: ZERO past verdicts flip,
  independently reproduced by the reviewer; migration note
  `docs/migrations/2026-07-contract-v1.4.1.md`).** (must-have
  caliber: lets one press release move judgments, silently). `publisher_key`
  (`gpu_agent/publisher.py:17`) is the evidence URL's netloc, nothing else; the F63 spec
  collapses only *same-domain* syndication ("N outlets hosted at one domain collapses to one
  publisher"). One wire story republished across N domains therefore counts deterministically
  as N distinct publishers — and the live store already holds archetypal PR-syndication
  endpoints (`stocktitan.net`, `markets.financialcontent.com`, `finance.yahoo.com`), so
  `minDistinctPublishers: 3` can be satisfied by a single vendor press release, unlocking gate
  F2e high confidence, thesis rule-6 corroborated reversals, and wiki page promotion at once
  (shared key = shared hole). The only current defense is the un-gated extraction-prompt
  sentence ("distinct outlets, not syndication of one story") — exactly the pattern "nothing
  un-gated reaches a number" forbids — and the failure is silent: the logged corroboration set
  looks healthy. Note the asymmetry with F71: the sufficiency gate's first live firing blocked
  *honest* thin evidence (2 real publishers) and was bypassed, while *disguised* thin evidence
  (one story, 3 netlocs) would have passed unremarked. Fix, lean: make distinctness
  deterministic — **(a)** content-similarity collapse across domains using the existing L1
  near-dup infrastructure (wire bodies are near-identical); and/or **(b)** a
  `registry/syndicators.json` data list of known wire/aggregator netlocs that collapse to the
  originating publisher. Closes F69's open handoff note while there: give the gatherer's
  chase/corroboration result the structured home it lacks — record the *originating* publisher
  on the blob/finding instead of free text in `content`. Counting-semantics change in F2e →
  ships as a Part-33 versioned migration; if the prompt sentence tightens, the hash pin trips →
  run-eval. Acceptance: test-pinned — one story with near-identical bodies on 3 syndicator
  domains fails the ≥3 bar; 3 genuinely distinct outlets still pass; thesis rule 6 and wiki
  promotion inherit via the shared key.
- [x] **F73 — Eval-v2 gate power: ε is small against documented run noise; the gate has never
  demonstrably caught a real regression. DONE — merged `6d098a7` (P2, 2026-07-08): pooled-dispersion
  ε + symmetric marginal-pass band + seeded-regression canary (scaffolded). FOLLOW-UP: the canary
  fixture still needs a one-time live eval capture to fill it (must not be hand-authored).** ε = max(half-range of 3 replicate means, quantum)
  yields 0.19–0.5 per seam, but the F63 run notes document identical-prompt seam swings of
  6.25–7.50; the F63 re-gate passed extract by **0.042** (6.625 vs bar 6.5833) — deep inside
  noise. Both error directions are live: draw-luck passes of true regressions, and draw-luck
  fails of good prompts (F63's two v1 failures were diagnosed as exactly that). Fix, lean:
  **(a)** a **seeded-regression canary** — demonstrate once (and after any harness change) that
  the gate hard-fails a deliberately damaged prompt (e.g. corroboration sentence stripped),
  and commit the calibration note; **(b)** symmetric marginal band — a PASS within ε of the bar
  auto-replicates once and the two-run mean decides, mirroring the existing fail side (today a
  0.04 pass decides alone); **(c)** pooled dispersion — append each gate run's fresh seam
  scores to the baseline's stored history so ε converges on a real noise estimate instead of a
  3-point half-range. `evals/harness.py` + baseline schema only; no prompt changes → no
  hash-pin trip; rebaseline governance untouched.
- [x] **F74 — post-run writer clobbers the session-authored cycle log. DONE (merged to main
  `257cf1b`, 2026-07-05, user go; suite on merged main 1066/4).** Born 2026-07-05: sometime after `99ca522`, a
  post-run process rewrote working-tree `store/cycle-log.json` as a machine skeleton (bare
  `status: ready`; no asOf/gather/gates/thesis/report; no trailing newline), deleting the v3
  run journal **including the F71 `gates.sufficiency: "bypassed…"` record** — the doctrine's
  "every cap/skip/drop is logged, never silent" line erased by a writer, surviving only in git
  history. The next routine `git add store/` commits the erasure. Fix: **(1)** immediate —
  identify the writer (likely the pipeline/cycle finalize step that emits a fresh minimal log)
  and `git restore store/cycle-log.json` once no live instance owns the change; **(2)** the
  writer must merge/append, never overwrite — refuse to write an entry carrying fewer keys
  than the existing entry for the same (scope, asOf); **(3)** guard test — live entries
  require `gates`/`asOf`, and a rewrite that loses fields fails the suite; **(4)** rule: the
  session-authored log is canonical; machine writers extend it. Acceptance: clobber scenario
  test-pinned; restored log recommitted; the offending writer named in the fix commit.
  **STATUS 2026-07-05: implemented on branch `f74-cycle-log`.** Writer identified:
  `cli._cycle_plan` blind `write_text`, aimed at the canonical journal by run-cycle SKILL.md
  step 1 on every run start. Shipped: cycle-plan refuses to overwrite anything richer than a
  bare plan (or unreadable/unrecognized content — null containers, directories, truncated
  files) and names F74; key sets derive from the CyclePlan/CycleEntry models (no hand-copy
  drift); BOM-tolerant read (`utf-8-sig`); run-cycle step 1 now writes the plan to the run's
  `work/<run-dir>/cycle-plan.json`; finalize step requires `asOf`/`mode`/`capturedAt`, forbids
  bare `ready` entries for mid-run skips, and gains an uncommitted-journal STOP rule; tripwire
  `tests/test_store_cycle_log_integrity.py` fails the suite on any skeleton (clobber scenario
  pinned in `tests/test_cli_cycle_plan.py`, 7 F74 cases). 8-angle review + empirical verify
  run on-branch; all confirmed findings fixed. The restore step became moot: the daily
  instance finalized and committed a healthy journal (`d9cfb3f`, asOf 2026-07-05); the
  monthly v3 journal (with the F71 bypass record) is preserved at `99ca522`. **Follow-ups
  (out of F74's scope, logged not lost):** the tripwire is pytest-time and reads the working
  tree — a store commit made without a suite run, or a stale staged blob, still slips through
  (pre-commit hook or index-blob check would close it); finalize is still session-hand-
  authored JSON (a validating `cycle-finalize` CLI through a guarded journal-write seam is
  the deeper fix); three dated 2026-06 plan/spec docs still show the old
  `--out store/cycle-log.json` invocation (historical records, left as-is — the guard fails
  loud with the corrective message if followed).
- [x] **F75 — No whole-run gate bypass flags (umbrella policy over F71). DONE — shipped as
  companion doctrine on the contract v1.4 branch, merged `e16672a` (P3, 2026-07-08).** The pattern, not
  the incident: every gate ships a whole-run bypass (`--no-sufficiency`, `--no-voice-lint`),
  and on the sufficiency gate's first live contest the bypass won after one rewrite attempt —
  meaning the first flagship on the post-F63 stack ran in the exact configuration the F63 spec
  forbade (loosening live, counterweight off). F71 fixes the sufficiency-specific deadlock;
  F75 is the policy: before ANY unattended loop, every whole-run bypass becomes per-item +
  required reason + logged, or is removed; and a cycle whose log records any bypass cannot
  stamp `status: ready` without a waiver line rendered in the brief's trust footer (the reader
  sees what the gate didn't). Small retro clause: the next monthly brief's trust footer notes
  that 2026-07-v3 ran under a sufficiency bypass (the store stays immutable; the render is the
  right surface). Acceptance: no whole-run `--no-<gate>` flags remain on live paths; the
  bypass ledger renders in the trust footer; run-cycle instructs re-dispatch/hold — never
  bypass — when a gate contests.
- [x] **F76 — Coordination-substrate integrity: handoff self-consistency, provenance labels,
  retained-worktree registry. DONE — merged `a0e3123` (P1, 2026-07-08): handoff discipline +
  controlled provenance vocabulary + retained-worktrees registry + `test_handoff_integrity.py`.**
  Three wounds in four days, all concurrent-instance shaped:
  the HANDOFF was self-contradictory (title `da58b94` says F63 merged; the body's top section
  still said "Remaining before merge" — unreadable without git); decisions are recorded
  "user-approved" under the AFK precedent (F52–F54's spec flags it; the label is now
  ambiguous); merged-feature worktrees/branches are deliberately retained for gitignored eval
  raw data but recorded only as scattered "do not git clean" prose warnings. Fix, lean:
  **(a)** handoff discipline — one CURRENT STATE block replaced atomically; superseded text
  moves to HISTORICAL in the same edit; **(b)** standardized provenance labels everywhere
  (backlog, handoff, specs): `user-approved` only for an actual user answer, `AFK-precedent`
  otherwise; **(c)** a retained-worktrees registry (one doc section: each retained worktree,
  why, what's inside, when it can go) replacing the scattered warnings. Docs/process only; no
  code, no eval impact.
- [x] **F77 - Brief hierarchy: order by importance, consolidate sections, cap volume — FOLDED INTO F78 — DONE, F78 stage 6 merged `77708f3` 2026-07-13** (born
  from the 2026-07 blind baseline ablation, user-scored 2026-07-06 - verdict recorded in
  `docs/action-items.md`). The desk WON the blind read on substance (implications + watch
  items; neither web-only baseline produced them), and every deficit the user named is
  presentation: "topics and sections are very scattered and all over the place"; "way too
  much information so we would need to order by importance and adjust format." Concretely:
  the render gives all ~13 calls equal visual weight regardless of conviction/recency of
  change; WHY, DEMAND|SUPPLY, STORYLINES, and TRUST read as parallel flat sections with no
  salience ranking; a daily-plus-monthly render concatenation duplicates state. Fix direction
  (renderer-only, `report.py` - pure projection, $0 replay): a ranked top section (what
  changed this cycle + the 3-5 highest-conviction/most-moved calls), remaining calls
  compressed to one line each, section consolidation, an explicit length budget above the
  appendix. Interacts with F64 (trigger-first daily leads with the same ranking) and F65
  (the "So what" slot is the actionability anchor); does not touch prompts (no eval-gate
  impact). *(Feature-track lean, renderer lane)*

---

## From the 2026-07-08 daily-refresh redesign (F78)

> Source: this session started as "retune the F58 recency window to 7 days" and, on inspecting the
> live 2026-07 **v4** flagship, uncovered that the brief leans on old evidence for a structural
> reason, not a broken threshold. Evidence (live store, run ref 2026-07-08):
>
> - **Dailies are clean** (07-02/03/05/06: zero stale open-web evidence — the 7-day daily window
>   holds). **The monthly flagship accumulates staleness and it worsens each top-up**: stale
>   secondary evidence went 5 → 5 → 8 across v2 → v3 → v4; oldest item grew 170 → 320 days
>   (a NVIDIA product/spec page dated 2025-08-22 freshly pulled into v4).
> - **Two root causes, neither is the threshold value.** (a) The gather recency window is *advisory
>   skill prose*, so the agent keeps old-dated evergreen official pages by discretion (v4 logged 0
>   recency drops for the kept pages). (b) The corpus (F62) windows on a finding's *cycle stamp*
>   (`asOf`), never the evidence's real publication date (`gpu_agent/corpus.py::in_window`), so old-
>   content findings ride forward and pile up.
> - **It changes ratings.** In v4, `strategicRisk` and `unitEconomics` (both stamped HIGH confidence)
>   rest ENTIRELY on stale evidence; the headline `momentum` ("Very strong, improving") is 3-of-4
>   supported by ~2-month-old earnings echoes; `competitiveStructure`/`moat` lean on AMD web content
>   from January (~174 days). Caveat: a large share of "stale" is quarterly filings/earnings
>   (49-64d) — inherently the freshest primary that exists; that part is by design, not the leak.
>
> **User direction (user-approved 2026-07-08):** retire the separate "monthly" product. Ship ONE
> market-state brief run **every day** that keeps BOTH the fresh gather AND the corpus, and leads
> with **what is different** across three horizons — since yesterday / last week / last month —
> saying "unchanged since <date>" explicitly rather than repeating the same standings. The corpus's
> job is reframed from "don't forget" to "the baseline we measure change against"; carried-forward
> fundamentals render with their real age. OPEN design question (to confirm): last-week/last-month =
> exactly 7/30 days ago (point-in-time) vs this-week-whole-vs-last-week (aggregate).

- [x] **F78 — Daily-refreshed, change-first market-state brief (retires the monthly product). DONE — ALL 6 STAGES MERGED, closed with stage 6 `77708f3` 2026-07-13.**
  One brief, run daily. Fresh gather = a **7-day initial sweep** with **discretionary older-lead
  pursuit that is LOGGED** (reworks F58, replacing its 45-day hard-drop; the agent may chase an
  older lead when it judges it worth it and records the age + one-line reason — closing the v4 gap
  where old pages entered with no recency record). Corpus = the change-detection baseline: window /
  age it by the evidence's **real publication date**, not the cycle stamp, so old-content findings
  stop accumulating (fixes the v2→v4 pile-up). Renderer leads with three horizon deltas (day / week
  / month) over the six ratings + demand/supply direction + thesis watch-items + headline numbers,
  with explicit "unchanged" states and real-age tags on carried fundamentals. **Delivers F64**
  (trigger-first daily) **and F77** (importance-ordered, consolidated, length-capped brief);
  **supersedes F58**'s window rule; **absorbs part of F68**. Does **NOT** subsume F60 (index scoring
  math — arguably more important now), F25 (store speed — B reads the store daily at 3 lookbacks,
  so it matters more), F65 ("so what for TSMC"), or F66 (citation audit). Frozen-core caveat: any
  `scoring.py`/schema change ships as a versioned migration (Part 33); the corpus-window change is
  in `corpus.py` (not frozen core) but must be shadow-checked against stored scorecards.
  *(Feature — own spec/plan/SDD; brainstorming in progress 2026-07-08.)*
  **AMENDED 2026-07-11 (user-approved, interactive):** stage 6's renderer gains an executive top
  band (Demand/Supply/Gap word tiles + a GREEN/YELLOW/ORANGE/RED alert dot with rule-based v1
  triggers) and a dashboard-parity task — spec
  `docs/superpowers/specs/2026-07-11-executive-brief-format-design.md` (amendment mechanics §5).

## From the 2026-07-12 F78-stage-3 lane (F80 + one doc fix)

- [x] **F80 — DONE — merged `ab48786` (2026-07-13; mechanism user-approved 2026-07-12: hand
  edit + tripwire; diff shown to the user, sign-off given with "merge them all"). Both pages
  tagged `chips.merchant-gpu`; permanent tripwire `tests/test_wiki_page_category.py`
  (red-green verified) fails the suite on any future null-category wiki page. NVIDIA now
  contributes store findings to its own corpus.** Original entry: Live-store data gap:
  `category: null` wiki pages silently excluded from every corpus. The F78-stage-3 shadow-check (2026-07-12, independently verified) found
  `store/wiki/entity/nvidia.md` and `store/wiki/entity/multi.md` carry `category: null`, so
  `enumerate_store`'s category filter (unchanged since F62's first commit) skips them whole —
  NVIDIA, the anchor entity of chips.merchant-gpu, contributes ZERO store findings to its own
  category corpus, under the old window rule and the new aged rule alike. Fix = tag the two
  pages (a `store/` edit — decide the mechanism: hand edit with user sign-off vs a lint/repair
  step in the next cycle; the corpus's SKIPPED-PAGE stderr lines have been reporting this on
  every run). After tagging, the ~343-day NVIDIA spec-page fact correctly fades under aging
  (eff 0.069 < 0.1 floor). *(Small but judgment-bearing: store writes are sacred.)*
  **Forward pointer:** F82 (2026-07-12 wave, above) generalizes this into the full
  corrections/retraction pathway — pick an F80 mechanism F82 can inherit.
- [ ] Doc drift (non-blocking, plan-flagged): `.claude/skills/desk-config-and-flags/references/cli-verbs.md`
  still documents the removed `--window-days`/`--corpus-window-days`; replace with
  `--salience-floor`/`--corpus-salience-floor` once stage 3 merges.

## From the 2026-07-12 gap review (F81–F86) — the post-current-backlog wave

> Source: a "what is missing for a fully fledged digital analysis team?" review (2026-07-12),
> adjudicated by the user the same day. **Sequencing (user-approved 2026-07-12): these start only
> after the current pipeline closes** — F78 → F79, then F65 / F66 / F80 and the F56/F68 small
> items — and slot beside the standing F23/F24/F25 track and Phase-2 prep. Directions marked
> `user-approved` are the user's 2026-07-12 answers; the mechanics beneath them are the
> assistant's lean, to be confirmed when each item's own brainstorm runs (repo convention: each
> is a feature — brainstorm → spec → plan when picked up). **STANDING ORCHESTRATION RULES
> (user-approved 2026-07-12, interactive; the question-stop rule supersedes the same-day
> solo-brainstorm allowance):** (1) design-weight items — F79, F24, and this whole F81–F87
> wave — get their brainstorm run INTERACTIVELY WITH THE USER before any lane is dispatched.
> (2) QUESTION-STOP: any dispatched lane agent that hits a question or fork while writing its
> brainstorm, spec, or implementation plan stops, writes the question(s) + recommendation to
> `.superpowers/handoffs/<lane>-QUESTIONS.md`, and ends its turn; the orchestrator relays to
> the user and resumes the agent with the answers. Proceeding on AFK-precedent design picks is
> no longer permitted (trivial mechanical choices may proceed but still land in the spec's
> decision-provenance section). Full rule text: repo CLAUDE.md "Orchestrated lane agents".
> Two quieter observations from the same
> review, recorded but deliberately not minted as F-items: the ~1-session desk-recipe estimate
> predates F79's backfill requirement (the roadmap already says recalibrate after Phase 2), and
> the org's bus factor is one human (approver, reader, onboarding author, incident responder —
> no succession story; revisit if a second operator ever appears).

- [ ] **F81 — Brain diversity: decorrelate the validators (user-approved direction 2026-07-12:
  Sonnet, Haiku, and possibly older model versions).** Today every brain, validator, and grader
  is the same model, so blind spots correlate across the whole org — and the Phase-3 structured
  challenge inherits them (a validator sharing the author's bias agrees with the mistake).
  Direction: draw *validator / challenger / grader* roles from a model-diversity pool (sonnet,
  haiku, maybe older versions) while authoring brains stay opus. This amends the standing model
  policy for those roles; "Claude Code is the brain" holds — these are still tool-less Claude
  Code dispatches. Lean: measure first — dispatch the same validation task across tiers on
  recorded cases and check whether disagreement is actually decorrelated or just noisier — then
  wire the pool in as registry data (model tier per role, per gate). Early cheap slice: F66's
  citation-audit subagent and the grade-the-grader cadence run on the pool. Interacts with F86
  (per-role model pinning); any prompt change rides the F6 gate.

- [ ] **F82 — Corrections & retraction pathway (truth maintenance).** No designed exit exists for
  evidence later proven wrong (source retraction, restated figure, mis-extraction found
  post-cycle): the store is append-only and sacred, so a bad finding can today only be diluted,
  never corrected — and every judgment that leaned on it stands silently. Plan (user asked for
  one 2026-07-12; lean, to confirm at brainstorm): **(a)** an append-only `correction` event
  referencing finding id(s) + reason + evidence — store sacredness holds, nothing edited or
  deleted; **(b)** corpus/judge exclusion — corrected findings drop out of corpora and citation
  groups (`corpus.py` is not frozen core; any gate/sufficiency semantics change ships as a
  Part 33 migration); **(c)** re-judgment trigger — a dimension or thesis whose citations include
  a corrected finding is flagged for re-judgment next cycle; **(d)** a visible corrections line
  in the brief (real desks issue corrections; silence is the failure mode); **(e)** entry
  channels: upstream retraction caught by gather/watchlist, restatements, operator-entered
  correction. F80 is the degenerate first case of "store repair with provenance" — build F82's
  mechanism compatible with whatever F80 decides.

- [ ] **F83 — Scheduled daily unblocked + event-triggered wake (user-approved 2026-07-12: grant
  the scheduled session ALL tools).** Resolves the standing 07-09/07-11/07-12 open gate in the
  grant direction, not keep-skipping: the scheduled daily session gets full tool access
  (WebSearch, WebFetch, agent-reach, file writes). Brains stay tool-less — this is the
  orchestrating session's permissions, doctrine untouched. **The grant is FLIPPED 2026-07-12
  (user-approved, interactive):** the Task Scheduler job script (machine-local
  `~/.claude/jobs/gpu-daily-cycle.ps1`, NOT in the repo) now launches headless claude with
  `--dangerously-skip-permissions` — scoped to the scheduled session only; interactive sessions
  keep their normal prompting. Residual to watch: the one-time bypass-mode acceptance dialog is
  not recorded on this machine; headless `-p` is expected not to show it — the next scheduled
  run (2026-07-13 08:57) confirms; fallback = the user runs
  `claude --dangerously-skip-permissions` once interactively and accepts. The rest of this item
  waits for the wave. Folded-in
  prerequisite (already standing on the roadmap's autonomy track): the **orchestration-prose
  conformance pin** — run-cycle's session-orchestrated behavior gets its replay-based conformance
  test before cycles run genuinely unattended. Second half (the timeliness gap): an
  **event-triggered off-schedule cycle** — the standing watchlist poller (desk-maturity list)
  detects a sufficiently large event (rule-based v1: reuse F78 stage 6's alert-ladder triggers)
  and may trigger ONE off-schedule cycle, logged, depth-1 (Part 5 one-level rule; rides the
  Phase-3 trigger pathway design). Also seeds the ops track: the fleet currently lives on one
  Windows machine; the owner/monitoring/restart story lands with Phase 6's unattended
  scheduling. The three skipped July days stay skipped per the 07-07 precedent unless the user
  says otherwise.
  **✓ RELIABILITY HALF DONE 2026-08-20 (user-approved interactively; diagnosis memo
  `.superpowers/handoffs/f83-scheduler-diagnosis-QUESTIONS.md`, fix record
  `.superpowers/handoffs/f83-scheduler-fix-DONE.md`).** Machine-local: task now starts/continues
  on battery and repeats every 2h for 12h until one run succeeds that day (never WakeToRun);
  job script sets `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` (the 08-19 600s background-kill),
  judges success by today's cycle-log entry (exit 1 + toast otherwise — catches the 08-12
  "polite stop" and the 08-14 auth-expiry classes, auth gets its own toast), and fast-exits
  ALREADY-DONE on repeat fires; new `Claude GPU Cycle Watchdog` task (logon + 20:30) toasts on
  missed days. Repo: `scripts/cycle_gap.py` gap banner wired into `scripts/session-orient`;
  operator-rebuild §1 re-mirrored. Pre-change task XML + script backed up in
  `.superpowers/handoffs/f83-scheduler-fix-BACKUP/`. **Explicitly deferred by the user
  2026-08-20:** event-triggered wake (this entry's second half), auto-resume of parked runs
  (future brainstorm), trigger-hour re-registration after the timezone move, backfilling the
  08-13..08-18 gap days.

- [ ] **F84 — Recurring external scoreboard (how we know the desk beats a cheap alternative).**
  Assistant's proposed resolution (user requested 2026-07-12; mechanics to confirm at
  brainstorm). **(1) Recurring blind ablation** — every N cycles (lean: quarterly, and after any
  major desk change such as F79), re-run the procedure that already worked once in 2026-07:
  same-day desk brief vs a web-only baseline from a plain Claude+search session, blinded,
  user-scored on the same rubric, verdict recorded in `docs/action-items.md`. Champion-vs-
  baseline as a standing eval instead of a spent one-off. **(2) Forecasts vs actuals** — once
  F79's series and range forecasts exist, score every interval forecast against the realized
  print (quarterly filings, TWSE monthly revenue — sources the desk already ingests): interval
  hit rate + calibration curve logged beside the F64 Brier record; external ground truth with
  zero new gathering. **(3) Deferred:** consensus-departure scoring (was the desk right when it
  departed from visible consensus?) — valuable, harder to source cleanly; revisit at the Layer
  tier. Renders as a scoreboard line in the trust footer. Needs no new reader — consistent with
  the first-reader decision (user, 2026-07-04).

- [ ] **F85 — Manipulation-resistance early slice (Part 26 pulled forward, thin).** Assistant's
  proposal (user requested 2026-07-12; mechanics to confirm at brainstorm). Desks ingest the
  open web daily NOW; the full Part 26 threat model stays Phase 7, but three cheap deterministic
  pieces land early: **(a) publisher-reputation registry** — per-publisher tier/notes as data (a
  sibling of `registry/syndicators.json`); unknown or first-seen publishers stamped provisional;
  **(b) new-publisher tripwire** — a lint: any rating/conviction move whose corroboration set
  leans on publishers first seen < N days ago is flagged in the cycle log + trust footer, never
  silent (F72's asymmetry lesson: disguised thin evidence is the dangerous kind); **(c)
  content-lineage collapse** — generalize F72's syndication collapse from known wire domains to
  same-origin content tracing: if every "corroborating" story quotes one origin, it counts as
  one publisher. Data + lint only — no frozen core, no prompt changes (no F6-gate hit) unless
  gatherer prose tightens; any F2e counting-semantics change rides a Part 33 migration as F72
  did.

- [x] **F87 — DONE — merged `7d65c64` (2026-07-13, user "merge them all"; pulled forward from
  the post-backlog wave by user decision 2026-07-12 since unattended dailies went live that
  day). Lock body carries {pid, hostname, timestamp}; takeover ONLY when the holder is provably
  dead on this host and the lock is stale; review round 1 caught a real two-reclaimers race —
  fixed (re-read-before-unlink + OSError routing), mutation-test-verified in round 2.**
  Original entry: Stale-lock takeover for the wiki log lock (before unattended runs are
  load-bearing). Born from the F25 final review (2026-07-12, reviewer-recommended follow-up;
  review verdict in `.superpowers/handoffs/f25-wiki-scale-DONE.md`). F25's lockfile-guarded seq
  mint chose fail-loud on a leftover `store/wiki/log.jsonl.lock` (hard crash → every later run
  raises TimeoutError until a human deletes the lock) — right default for attended runs, but it
  collides with F83's unattended scheduled dailies: a crashed 3am run bricks every following
  morning. Fix, per the review: record PID + timestamp inside the lock file; on lock timeout,
  take over ONLY if the lock is stale AND its PID is provably dead, else keep failing loud.
  Include the two review minors while there: the timeout message should name the remedy
  ("delete this file if no writer is running"), and note the pre-existing torn-write edge in
  the spec's risk section. Small, wiki-lane only. **Sequencing: before unattended scheduled
  runs become load-bearing** — effectively alongside F83's conformance-pin half.

- [ ] **F86 — Model-swap recalibration plan (the analysts get replaced on Anthropic's schedule,
  not ours).** User asked for this 2026-07-12; assistant's lean, to confirm at brainstorm. The
  eval baseline, voice, and gate behavior are all tuned to one model version, backed by a single
  line of doctrine ("shadow runs qualify any model swap") and no machinery. Build the procedure
  while it is cheap: **(a) pin + record** — cycle log and eval baseline carry the exact model id
  per brain role (extends the commit-trailer rule into run data); **(b) qualification protocol**
  — a candidate model runs the F6 eval as brain (3 replicates per eval-v2) plus one
  recorded-gather shadow cycle diffed against the incumbent: seam scores, gate-rejection and
  re-dispatch rates, voice-lint failures, thesis-movement deltas; **(c) acceptance bar** — meet
  the eval-v2 bar AND no gate-behavior regression → rebaseline under the new model id (baselines
  become model-version-scoped); **(d) canary-desk rollout** — swap one desk, soak N cycles, then
  the fleet; never mid-cycle. Doubles as the deliberate-downgrade path (sonnet/haiku for cost —
  Phase 4's dials) and supplies the per-role model pinning F81 needs. Harness/baseline-schema
  work; no prompt changes.

---

## From the 2026-07-13 F78-stage-6 final-review follow-ups

> Source: the F78-stage-6 whole-branch final review's fix wave. Re-running the shadow-check the
> way the CLI actually runs it (thesis book loaded, not `book=None`) exposed that Task 10's
> original 53/88 and 57/88 line counts undercounted the real path; both items below were logged
> instead of fixed, per the instruction not to chase the budget or patch the lint mechanism inside
> this wave. Both are unnumbered — next free F-number to be assigned by the user.

- [ ] **F119 — Change-first above-fold budget overshoots on live data.** *(Numbered 2026-08-20,
  user-assigned; F117/F118 were concurrently minted by the v8-finish session, so the "next free"
  numbers landed here.)* The CLI-real shadow-check (thesis book loaded from
  `store/theses/chips.merchant-gpu/book.json` — the actual daily-run path) measures **101 lines**
  above `reader.APPENDIX_DIVIDER` against the 88-line budget (`report.py::_ABOVE_FOLD_BUDGET`);
  Task 10's original `book=None` measurement (53/57 lines) never exercised the loaded-book render
  and so never caught this. The auto-tightening loop already in `render_report` (`while
  len(body.split(reader.APPENDIX_DIVIDER)[0].splitlines()) > _ABOVE_FOLD_BUDGET and k > 1: k -= 1`)
  only has one lever — compressing `THE CALLS` (`top[4]`) down to `top_k == 1` — and still
  overshoots once it hits that floor with a book this size (17 standing calls). Fix direction:
  extend the fold mechanism to a second section once ranked calls bottom out (candidates: `WHAT
  CHANGED`'s `_CHANGE_LINE_CAP`, or `QUICK GLANCE` Tier 2/3 rows), or deliberately re-scope the
  88-line budget now that the 2026-07-11 exec top band and the change-first lead both live above
  the fold together. USER-ACCEPTED for now (2026-07-13): ship over budget rather than chase it —
  101 still beats the legacy (pre-F78) monthly renderer's 112 above-fold lines. Renderer-only;
  no schema/scoring change; F79-adjacent only in that both touch report volume.
- [ ] **F120 — Render-time acronym-lint enforcement gap on the assembled brief.** *(Numbered
  2026-08-20, user-assigned; see F119's concurrent-mint note.)* `reader.lint_acronyms` is enforced per-section at
  write time (the F67 output contract), but nothing re-lints the fully assembled above-fold text
  after live thesis-book titles and finding statements are substituted in — true in both legacy
  and change-first render modes. The current stopgap is allowlisting real tokens as they surface
  in `registry/acronyms.json` (this wave added `CUDA`, `LPDDR`, `LPDDR5X`, `MI325`; Task 10's
  `DRAM`/`B300` additions and F68(f)'s `MI`/`GB300` note are the same pattern recurring). Fix
  direction: add one lint pass over the fully assembled above-fold string right before
  `render_report`/`render_daily` returns it, so a genuinely novel off-allowlist token BLOCKS the
  render instead of shipping silently until a shadow-check happens to catch it.
- [x] **F121 — registry/indicators.json labels carry old-scheme id tails.** *(Numbered
  2026-08-20, user-assigned via the orchestrator during the report-quality-pair lane; same
  concurrent-mint caveat as F119/F120 — if another session minted F121 first, take the next
  free number.)* Seven labels embed retired-scheme ids in parentheses — e.g.
  `hyperscalerCapexRevision` -> "Hyperscaler capex-revision direction (D1)" (also S1, S2,
  S4, D4, D9, X5) — and any label row rendered above the fold (DEMAND | SUPPLY board, quick
  glance, change lines) would leak them; the F120 assembled-brief acronym gate blocks on
  them. Interim cover (F120 round-3, user-approved 2026-08-20): the display layer strips
  the tails via `reader.strip_stale_paren_ids` inside `reader.indicator_label`, registry
  data untouched. The REAL fix — cleaning the label strings themselves — must run in its
  own lane because labels are baked verbatim into the emitted brain prompts (cli.py
  scoring/price indicator vocab), so it entails a deliberate F6 baseline-pin re-record.
  Until then the display-layer strip covers it. Note: the dashboard brief reads labels via
  its own `dashboard/brief_model._indicator_labels`, not `reader.indicator_label`, so the
  web brief still shows the tails until F121 lands.

- [x] **F122 — Daily GPU leasing-price pull, in-repo, feeding the brief.** *(Numbered 2026-08-20,
  assistant-minted after F121 was taken mid-session by the report-quality-pair lane.)* The user's
  standalone `C:\Users\danie\gpu-price-tracker\pull_gpu_prices.py` (Azure / AWS / RunPod / Vast.ai /
  CoreWeave, optional Lambda) is now `gpu_agent/pricepull.py` behind `gpu-agent price-pull --as-of
  <day>`, run inside run-cycle step 7 ("Price-pull + price-sync") every cycle. One LOCAL, gitignored
  snapshot per day in `gpu_agent/data/leasing_snapshots/` (user decision: not committed). Once ANY
  snapshot exists on a machine, `pricefeed.load_points` answers ONLY from snapshots (newest at/before
  the label; on-demand, US regions) — dates before the first snapshot show no price and no
  comparison, so a snapshot basket is never compared with the legacy `scrape_data/` basket (final
  review caught that a cross-source "−26 % H100" would otherwise have shipped); the legacy folders
  are read only on a machine with no snapshots at all. This revives the dashboard H100 tile, the
  brief's price lines and `gpuRental{OnDemand,Spot,1yr}`; `price_local` no longer lets the stale
  hardware purchase-price folder suppress fresh rental rows (separate `stale rental data` warning)
  and fills rental months from snapshot files even when no cycle ran that month. Supersedes the
  launcher skill's 2026-08-20 "Step 4" subagent dispatch (now a pointer). NOT covered, on purpose:
  hardware purchase prices (thinkmate/serversimply) — that `stale price folder` warning persists
  honestly. Spec `docs/superpowers/specs/2026-08-20-f122-price-pull-design.md`; plan
  `docs/superpowers/plans/2026-08-20-f122-price-pull.md`. Lane `f122-price-pull`.

> Numbering note 2026-08-22: F123–F128 below were minted 2026-08-22 in the relayed decision
> session (user-assigned via the orchestrator; usual concurrent-mint caveat — renumber if collided).

- [x] **F123 — Issue identity must survive a constraint relabel.** The register minted three
  "different" issues for one real problem in three cycles because the id derives from the exact
  binding-constraint label (`constraint-hbm-stacked-memory-supply` v8 →
  `constraint-stacked-memory-and-server-dram` v9), and every stranded id drifts toward a false
  reader-facing "Resolved" after 5 quiet cycles. The 2026-08-22 hand-consolidation (user-approved:
  duplicates removed from `register.json`, history untouched) fixed the instance, not the class.
  Fix direction (design fork for the lane): match new constraint labels against open
  constraint-kind issues by token overlap or a stable indicator anchor before minting a new id;
  a relabel then RENAMES the standing issue (title updates, id and history persist) instead of
  opening a twin. Touches `gpu_agent/issues.py` open-trigger logic only; narrator prompt and pins
  untouched.

  **Follow-up, 2026-08-25 (user-approved hand merge of the leftover pair).** F123 stops new twins
  from being minted but left the pair that already existed in `register.json`. On the user's
  interactive decision the older issue `constraint-stacked-memory-and-server-dram` ("HBM4 and
  server DRAM supply") survives and the twin `constraint-stacked-high-bandwidth-memory-supply`
  ("Stacked memory supply per accelerator") was removed; the survivor's
  `latest.claimFindingIds` gained the twin's finding id (union, survivor's first) and keeps its
  own title, trigger label and counters — the two issues were checked on the same days, so the
  check counts were deliberately not summed. `constraint-hbm4-memory-allocation-per-accelerator`
  is a different question and was left alone. `history.jsonl` was left untouched as the audit
  trail. The merge is a re-runnable, idempotent one-off in
  `scripts/oneoff_merge_issue_twin_2026_08_25.py`, pinned by
  `tests/test_oneoff_merge_issue_twin_2026_08_25.py`; a dry run of `open_issues` against the
  merged register with the 2026-08-v13 scorecard reports `touched: []`, so the next cycle does
  not re-mint the twin.

- [x] **F124 — Footer disclaimer on every public page (approved wording).** Posture doc §4,
  wording and placement DECIDED 2026-08-22: "Independent personal project. The analysis here is
  one individual's own work, produced from public sources. It is not affiliated with, endorsed
  by, or representative of any employer, and it is not investment advice." Small template change
  in the site builder (`gpu_agent/dashboard/` + the React footer); no schema change; the live
  site currently has NO disclaimer at all.

- [ ] **F125 — Honest-removal mechanism for publisher objections.** Posture doc §3(3) DECIDED
  2026-08-22: on a publisher request, the finding stays but its excerpt is replaced by a removal
  note, the link stays, the cycle log records the action. Touches the append-only guarantee —
  must be DESIGNED, not improvised: needs its own small brainstorm before build (how a
  replacement writes without violating no-silent-deletion and the F66 verbatim-excerpt gate).

- [x] **F126 — Publisher do-not-fetch list wired into the fetch runner.** Posture doc §3(4)
  DECIDED 2026-08-22. A refusal list already exists in the fetch runner for other reasons;
  add a publisher-objection list beside it, with the source inventory recording why a domain
  is refused. Small, mechanical.
  **DONE on branch `f117-f126-fetch-registry`** (built as one lane with F117, which needed
  the same file). `registry/do-not-fetch.json` holds both kinds: `publisher-objection` (the
  publisher asked not to be used at all) and `blocks-plain-readers` (F117's kind). Only the
  first is a refusal — `webreach.validate_request` refuses it with
  `refused: publisher objection (<domain>)` before argv is built, the manifest row carries
  that reason, and the chart verifier rejects any point citing such a domain before a single
  request goes out. The second kind is deliberately NOT refused in the fetch runner, because
  it records a fact about the chart verifier's plain reader rather than a request from the
  publisher, and gatherers still read those pages for claims. Both commands that fetch
  (`webreach-fetch`, `chart-research accept`) take `--do-not-fetch`, defaulting to the
  repo-relative path, and a missing file is an empty list rather than a failed cycle. **No
  publisher has ever objected**, so that kind ships wired and tested but with an empty list;
  honouring the first objection is a one-line entry, not a build. Posture doc §3(4)'s
  bracketed note updated to match; the DECIDED clause text is untouched.

- [x] **F127 — Enforce the 50-word/two-sentence excerpt cap in the extraction gate.** Posture
  doc §2 DECIDED 2026-08-22. Today the cap is policy only (measured: all 334 stored excerpts
  ≤ 40 words). Add a length check beside the existing verbatim check so an over-long excerpt is
  rejected the way an invented one already is. Gated: extraction prompt/gate changes re-run the
  eval gate; F6 expected byte-untouched (gate code, not prompt bytes — verify in-lane).
  **DONE on branch `f127-excerpt-length`.** The check lives in `gpu_agent/gate.py::check_finding`,
  not beside the verbatim check in `extraction/extractor.py`: the verbatim check needs the fetched
  page and cannot move, while `check_finding` is the one function both the extractor and
  `check_scorecard` route through, so one edit covers every path an excerpt travels. An excerpt is
  rejected when it is **over 50 words AND over two sentences**, or when it passes a **100-word
  absolute ceiling** regardless of sentence count. Word count is `len(excerpt.split())`; sentence
  count is terminal punctuation minus abbreviations, initials and decimals, deliberately biased to
  under-count. 25 new tests, including one that scans every committed excerpt and fails if the new
  rule would reject any. F6 verified byte-untouched: `git diff --name-only main` lists only
  `gpu_agent/gate.py`, two test files and the two design docs, and
  `tests/test_evals_baseline_pin.py` passes 2/2. Full suite 2745 passed / 6 skipped.
  **Three AFK-defaults — the user was AFK and approved none of them** (full reasoning in
  `.superpowers/handoffs/f127-excerpt-length-QUESTIONS.md`):
  (1) **"two sentences **or** 50 words" is read as OR, not AND.** Re-measuring the store on this
  branch falsified the item's own premise above: the store has grown from 334 to **644** excerpts,
  and one is now **70 words** — a verbatim one-sentence AMD 10-Q gross-margin quote in
  `store/findings/ir-amd-com-cfa508a5-2026-08-3.json`. Two others run to three and four sentences
  (both under 30 and 40 words). None breaks both limits. A hard 50-word cap would therefore have
  rejected a real, well-sourced finding, contradicting the posture doc's own claim that the norm
  "costs nothing today". The OR reading is also literally what the DECIDED text says.
  (2) **The 100-word ceiling is invented**, not in the posture doc. Without it the OR rule has a
  trivial bypass: text with no sentence-ending punctuation counts as one sentence and passes at any
  length. 100 is twice the norm and well clear of the largest excerpt ever stored (70).
  (3) **Nothing under `store/` was edited** — it is append-only, and under the rule as built
  nothing stored is non-conforming, so no exemption list was needed.

- [x] **F128 — Codify the unattended-run mechanics the user ruled on 2026-08-22 (GATED: F83
  fingerprint re-record).** Four standing per-cycle deviations are now ACCEPTED PRACTICE by
  interactive ruling and must move from "re-flagged every run" into the run-cycle skill's text:
  (1) brains run with Read on their own split prompt files + exactly one Write to their own
  answer file (replaces the literal "tool-less" wording; extraction stays genuinely tool-less
  inline when it fits); (2) gatherers dispatch as the restricted `web-gatherer` agent type
  (`.claude/agents/web-gatherer.md`, tools Read/Write/WebSearch/WebFetch) — the F88 wall becomes
  structural; (3) oversized emitted prompts split byte-exactly with a rejoin-equals-original
  assertion; (4) F67: a report too large for the final message ships above-fold sections inline
  + full text by path. One lane, one deliberate F83 conformance-pin re-record via the recorded
  recipe; F6 and the narrator pin byte-untouched. After it merges, cycle logs stop recording
  these four as deviations.

- [x] **F129 — small-sample-corrected eval epsilon (t-based prediction band) + recompute-eps
  verb.** DONE on branch `f129-eval-eps`. The F6 noise allowance was statistically
  overconfident on a small pool: `pooled_epsilon` used a fixed `EPS_Z = 2.0` times the sample
  stdev, which assumes the stdev is known. At the typical post-rebaseline pool of n=3 it is
  not. Live evidence: the extract seam's bar of 6.163 failed two good runs by 0.038 on
  2026-08-24 (F121) while historical same-golden-set draws span 5.375-7.125 — the same swings
  F73 and F107 already documented. The band is now size-aware,
  `t_{0.975,n-1} * sqrt(1 + 1/n) * sample stdev`, floored at the quantum: a 95% prediction
  band for the NEXT run rather than a confidence band on the mean. t quantiles are a hardcoded
  df=1..30 table (1.96 beyond), stdlib only, no new dependencies; it still converges — at large
  n the multiplier returns to ~2.0, so this only loosens the small-sample case. `EPS_Z` stays
  for back-compat and the non-poisoning invariant in `append_run_to_history` is untouched.
  New `gpu-agent eval recompute-eps` recomputes `epsilon` from the committed `seamHistory` and
  the true quanta, writes `fixtures/evals/baseline.json`, prints old->new per seam and stamps
  `provenance.epsRecompute` — deterministic, no runs, and the only sanctioned writer of an
  epsilon-only baseline change (project law: never hand-edit baseline.json). Applied in-lane:
  extract 0.629 -> 1.563; implication/judge/thesis have flat pools (stdev 0) and stay at their
  quantum floors 1.0/0.25/0.5. promptHashes byte-unchanged; the F6 pin, narrator pin, F83
  fingerprint and scoring replay pin all stay green.

## From the 2026-07-13 documentation gap review (F88–F94) — what the docs still don't cover

> Source: a "what is missing from our documentation to achieve the goal?" review (2026-07-13),
> run against the roadmap, the 39-part charter, this backlog (including the F81–F86 wave), the
> compliance matrix, and HANDOFF; minted as F-items the same day (user-directed, interactive).
> The mechanics beneath each item are the assistant's lean, to confirm at that item's own
> brainstorm. The STANDING ORCHESTRATION RULES from the F81–F86 preamble apply unchanged
> (design-weight items get an interactive brainstorm with the user before any lane dispatch;
> question-stop binds every dispatched lane). **Sequencing (user-directed 2026-07-13): F88 is
> pulled forward and starts NOW — its interactive brainstorm runs this session; the rest slot
> beside the F81–F86 wave under the same start-after-current-pipeline rule.** Numbering note:
> the two unnumbered F78-stage-6 follow-ups (section above) keep their user-assigned-number
> reservation; this wave took the next free numbers at mint time (F88–F94).

- [x] **F88 — DONE (on branch `f88-orchestrator-hardening`, awaiting user merge; spec
  `docs/superpowers/specs/2026-07-13-f88-unattended-orchestrator-hardening-design.md`, plan
  `docs/superpowers/plans/2026-07-13-f88-orchestrator-hardening.md`, sentinel
  `.superpowers/handoffs/f88-hardening-DONE.md`).** Four sub-parts delivered: **(1)** the written
  threat model (`docs/threat-model-unattended.md`, T1); **(2)** the injection wall — a
  registry-templated, shell=False argv fetch runner with scheme/tool/verb validation
  (`gpu_agent/gathering/webreach.py`) plus no-Bash-reader / receipts-not-content skill prose; **(3)**
  the third-party web-reach supply-chain pin (`registry/web-reach-tools.json` version pins +
  `gpu_agent/web_reach_ensure.py`, which never installs unattended); **(4)** D6's licensed-source
  allow-but-flag rework (mid-build, user-decided 2026-07-13) — the fetch tool now identifies and
  flags licensed/inventoried sources instead of hard-blocking them. **F88 follow-ups (logged not
  lost, next free F-number — user to assign):** agent-reach's exact-ref install pin (D7 needs an
  upstream tag/commit; interactive install still pulls `main`); a per-finding licensed-source
  trust-footer tag (needs a `RawDocument` schema field — a frozen-core Part 33 migration); the
  web-reach runner's in-memory capture has no streaming cap (only the on-disk result is capped,
  bounded today only by the request timeout); the fetch manifest's `sha256` is gatherer-agent-
  reported, not code-computed/verified (make the coordinator or assembler compute/verify it); and
  a charter Part 22/37 edit to match the D6 doctrine (this lane only put the doctrine note in
  `docs/web-reach.md`).
  Original entry: Unattended-orchestrator threat model (the injection boundary, one level up — and
  the exposure went live 2026-07-13). The F16/Part-8 boundary protects the *brains*: tool-less
  dispatches, fetched text fenced as data-not-instructions. Nothing protects the *orchestrating
  session* — and since 2026-07-13 that session runs headless on a schedule with
  `--dangerously-skip-permissions` (F83 flip): full tools (file writes, git push, arbitrary
  commands, further fetches), reading open-web content daily, nobody watching. No doc asks what
  happens when a fetched page carries instruction-shaped text aimed at THAT session. Part 26/31
  stay Phase 7; this is the thin now-slice: **(a)** a written threat model for the scheduled
  session — assets (store integrity, git push rights, the machine itself), entry points (gather
  content, tool output, third-party CLI output), blast radius, and the containment cheap enough
  to take now; **(b)** doctrine + verification: fetched content enters the orchestrating session
  only through sanctioned shapes (blob files read by dispatched brains; structured summaries) —
  audit the current gather path against this and pin it with F83's replay-based conformance
  test; **(c)** least-privilege pass on the scheduled job — enumerate which tools the cycle
  actually needs; the ALL-tools grant was expedient, not designed (amends F83, does not reopen
  it); **(d)** third-party web-reach supply chain: version-pin agent-reach / crawl4ai /
  last30days in `registry/web-reach-tools.json`, record installed versions in the cycle log,
  upgrades become logged decisions, never silent drift (extends Part 37's health preamble).
  Interacts: F83 (same session), F85 (content-level manipulation; F88 is session-level), F90
  (same machine). Design-weight → interactive brainstorm. *(User-directed start 2026-07-13.)*

- [ ] **F89 — Cost metering: the Phase-4 pilot's measuring instrument does not exist.** Part 27
  and Phase 4's gate demand "measured $/cycle from real runs, not estimates" — but the whole
  system runs on a Claude Code subscription: no per-run bill, no token meter, and no doc says
  HOW tokens/wall-clock per cycle get counted. Second, unasked feasibility question: subscription
  usage ceilings — 34 desks × daily may be infeasible on limits alone even when dollars are
  fine. Lean: **(a)** start cheap accrual NOW — per-cycle wall-clock + dispatch counts (brains,
  graders, gatherers, re-dispatches) logged in the cycle log at the next cycle-touching change;
  **(b)** token accounting via whatever the harness exposes (transcript/artifact sizes as a
  stated proxy if no true meter); **(c)** a usage-ceiling probe recorded before Phase 4's
  go/no-go math; **(d)** the go/no-go template names its denominator and its instrument.
  Sequencing: the instrument must exist before Phase 4 opens; (a) is opportunistic any time.

- [x] **F90 — Operator-machine continuity: the machine-local layer has no rebuild story.**
  **✓ DONE — `docs/operator-rebuild.md` merged `44d2507` 2026-08-05** (lane `f90-operator-rebuild`;
  filename deviates from the lean's `docs/operator-machine.md` — the dispatch brief named it, noted
  in the doc). Everything inventoried BY INSPECTION: scheduled task (settings exported; **6 missed
  runs since 2026-07-29** — laptop off/on battery at 08:57, silent), job script content mirrored
  into the doc (live copy stays machine-local per F83), all 6 coordination skills + edit-guard hook
  confirmed (**exist ONLY on this laptop, no backup — repo-copy recommendation OPEN for the user**),
  .venv (py 3.13.7, 13 pkgs), web-reach installs verified live (`agent-reach doctor` run read-only).
  **One lean assumption CORRECTED:** no stored "bypass-permissions acceptance state" exists — the
  bypass is a per-run flag in the job script. 9 open questions (mostly credentials + "which
  web-reach channels are SUPPOSED to work") listed in the doc's final section — those are the open
  half for the user; the runbook itself is shipped. Sentinel
  `.superpowers/handoffs/f90-operator-rebuild-DONE.md`. The
  repo survives the laptop; the operational layer does not, and no doc inventories it: the Task
  Scheduler registration + `~/.claude/jobs/gpu-daily-cycle.ps1` (explicitly NOT in the repo),
  the `~/.claude/skills` launcher/coordination skills (run-gpu-market, resume-desk, eval-driver,
  instance-sync, concurrent-edit-guard, desk-handoff), `.claude/settings.local.json` hooks, the
  root `.venv`, web-reach tool installs (agent-reach; crawl4ai + Playwright browsers), and the
  one-time bypass-permissions acceptance state. The F81–F86 preamble records the HUMAN bus
  factor; the MACHINE bus factor is unrecorded. Lean: one committed runbook
  (`docs/operator-machine.md`) — every machine-local artifact, its rebuild command, a
  quarterly-verify note — plus the job script's CONTENT mirrored into the repo as reference
  (the live copy stays machine-local per F83). Doc + inventory work; no code.

- [x] **F91 — Public-repo exposure decision (broader than the rename).** The repo is public
  (recorded in the 2026-07-06 dashboard spec §privacy); the store commits findings quoting
  fetched articles (no written posture on republishing quoted text — Part 22 governs fetching,
  not re-publishing); the desk's daily market calls are world-readable; TSMC-branded analysis
  sits under a tsmc-named GitHub account. Open question 3 / F48 cover only the NAME. Needs a
  user decision pair: **(a)** visibility — private now vs stay public (lean: flip private now;
  zero cost, reversible, and it collapses most of (b)'s urgency); **(b)** a written
  quoted-content posture for whatever stays visible. One decision + a short doc; no code.
  **(a) DECIDED 2026-07-29 (user, interactive, after reviewing the F91/F92 decision memo
  `.superpowers/handoffs/f91-f92-decision-MEMO.md`): the old public repo STAYS PUBLIC — the
  memo's flip-private recommendation was declined.** The memo's findings stand on record: the
  old `random_for_fun` repo is live/public/un-archived (112 TSMC-mentioning files) and the
  `ai-market-digital-twin.pages.dev` site is public (TSMC mentions on 10 pages, kept
  advice-free only by convention). **(b) remains OPEN:** the written posture doc for what may
  appear publicly is now the more important half, since everything stays visible.
  **(b) STATUS 2026-08-05: DRAFT SHIPPED, approvals pending — `docs/publishing-posture.md` merged
  `30b64ba`** (lane `f91b-posture-doc`; sentinel `.superpowers/handoffs/f91b-posture-doc-DONE.md`).
  Grounded in measurement: all 334 stored excerpts ≤ 40 words (median 14), always attributed +
  linked; whole articles never stored; the site renders ≤ 60-char fragments. **Biggest gap found:
  the live site has NO disclaimer of any kind.** Every undecided clause is tagged
  `[DRAFT — user to approve]` — **8 approval points open** (framing; 50-word excerpt cap +
  whether to code-enforce it, which would be a gated lane; quote-stacking rule; takedown procedure
  vs the append-only store — needs a small design; do-not-fetch list; the employer-material
  firewall = the memo's unanswered Option A; disclaimer wording + footer build; never-commit list +
  secret-scan). **F91 stays open until the user approves the draft; nothing in it is in force.**
  **(b) DECIDED 2026-08-22 (user, interactive, relayed decision session): ALL 8 APPROVAL POINTS
  APPROVED AS WRITTEN — the posture doc is IN FORCE.** `docs/publishing-posture.md` updated
  DRAFT→DECIDED clause by clause. Build items minted at approval: **F124** (footer disclaimer),
  **F125** (honest-removal mechanism), **F126** (publisher do-not-fetch wiring), **F127**
  (excerpt-length gate check). F91 is CLOSED; the four build items carry the remaining work.

- [ ] **F92 — Store retention & archival policy (append-only forever meets git forever).**
  Doctrine keeps the store append-only, sacred, and git-committed — correct for trust, unbounded
  by construction: 34 desks × daily × years compounds both working-tree size and git history
  (clone time, tooling latency). Wiki lifecycle prunes PAGES; scorecards, findings, cycle-log,
  and git history have no policy. Lean: a recorded decision now, implementation deferred behind
  a threshold — pick the escape hatch in advance (cold-archive branch / per-year store
  partitions / git-lfs for blobs), add a store-size line to the cycle log (Part 29-style
  monitor), act only when the recorded threshold trips. Decision-sized today; migration-sized
  if ignored until Phase 6.
  **STATUS 2026-08-05: DECISION MEMO SHIPPED, decision pending —
  `docs/superpowers/specs/2026-08-04-f92-retention-decision-memo.md` merged `306a510`** (lane
  `f92-retention-memo`; sentinel `.superpowers/handoffs/f92-retention-memo-DONE.md`). Measured:
  store 8.5 MB (scorecards 69%), growing **~18× faster than the 2026-07-29 memo assumed**
  (~2.6 GB/desk/yr; 570–790 GB @ 34 desks × 5 yr; the old 250 MB alarm trips ~10 weeks out).
  **Root cause found: every scorecard embeds a full ~2,100-byte copy of each finding it scored**,
  while git already packs the whole scorecard HISTORY to 353 KB — so the pre-listed cold-archive
  and git-lfs hatches solve an already-solved problem. **Memo recommends: forward-only
  reference-based scorecards** (measured 501 KB → ~22 KB; no existing file moves, all 37+
  replay-pinned scorecards keep reproducing exactly) — a DESIGN-WEIGHT build requiring its own
  interactive brainstorm before any lane; year-partitioning reserved behind written trip points
  (500 MB store / 5 MB scorecard / 2-min clone / 5 live desks). **4 decision boxes open at the
  memo's end — decide this month; nearest hard limit ~9 months out. F92 stays open until the
  user decides.**
  **DECIDED 2026-08-22 (user, interactive, relayed decision session) — all 4 boxes answered:**
  (1) YES to forward-only reference-based scorecards — green-lights the DESIGN-WEIGHT interactive
  brainstorm, which must run with the user before any build lane; (2) cutover = first cycle after
  that build merges, no back-dating, no migration of existing files; (3) trip points ACCEPTED as
  written (500 MB store / 5 MB scorecard / 2-min clone / 5 live desks) with year-partitioning the
  pre-chosen hatch; (4) git-lfs PERMANENTLY RULED OUT on the memo's §3C measurements — do not
  re-litigate. Answers recorded in the memo's decision box. F92 CLOSES when the reference-scorecard
  build ships; until then the decision stands recorded and the store-size monitor rides with it.

- [ ] **F93 — Eval-gate economics: the gate itself needs a budget.** The golden set grows per
  archetype and per tier (Part 24), eval-v2 made every gate run 3 replicates, and a
  template-level prompt change at 34 desks re-gates EVERYTHING; nothing bounds the gate's own
  cost or wall-clock, and nothing shards it. Lean: per-archetype sharding — a prompt change
  re-gates only archetypes whose emitted bytes changed (the F6 pin already computes exactly
  this); a recorded per-gate-run ceiling; F86's qualification protocol reuses the same shards.
  Harness work; no prompt bytes; F6 pin untouched (green stays green).

- [ ] **F94 — Fleet-scale git concurrency (locks protect files, not pushes).** F25/F74/F87
  serialize same-machine writers on the wiki store; Phase 4's parallel category fan-out has N
  concurrent runs committing and pushing ONE repo — push races, interleaved cycle-log commits,
  and non-fast-forward rejects hitting unattended sessions with no human to reconcile. Lean:
  single-writer-per-repo for store commits — category runs return artifacts; only the
  orchestrating driver commits and pushes, serially. Decide it in the Phase-4 execution-seam
  spec; recorded now so the Workflow-driver design inherits it instead of discovering it.

## From the 2026-07-11 executive-format session (F79)

- [~] **F79 — SDEWS-style index rebuild (scoring v2.0). SHADOW-ONLY MERGED `b6db80a`
  (2026-07-15, user-directed); NOT YET LIVE — G4 cutover pending.** Full build: spec
  `docs/superpowers/specs/2026-07-13-f79-scoring-v2-design.md` (all forks user-approved
  interactively), plan `docs/superpowers/plans/2026-07-13-f79-scoring-v2.md`. Delivered: 6
  vintage-stamped series (S1 pkgCapacityOrderSpread / S2 hbmSupplyCapex / D1
  hyperscalerCapexRevision / D9 odmMonthlyAiRevenue / D4 tokenEconomics / X5
  marginalBuyerFinancing) backfilled 2023→now with per-point provenance; z-score engine as the
  versioned v2.0 migration (v1.x replay fidelity pinned byte-for-byte); σ-band alert engine
  (shadow); shadow wiring (v2 computes into scorecard.provenance, NOTHING user-facing renders it).
  **Gates: G1 backfill SIGNED; G2 backtest PASSED under the user-signed Option-B event-list
  amendment (detection-only, frozen run, original 3-turn FAIL still reproducible); G3 eval
  re-gate PASSED under seam-scoped verdicts (only extract bound; honest baseline; canary
  captured).** Final whole-branch review: READY TO MERGE, 0 critical (replay fidelity + shadow
  isolation both airtight). **REMAINING: shadow soak ≥5 live cycles (needs manual `v2-shadow`
  CLI invocation per cycle — the auto-hook is deferred to G4) → G4 CUTOVER (user-signed; flips
  v1→v2 rendering).** Absorbs F60's deferred scoring half. Original scope below.
  **UPDATE 2026-07-28 — G4 stage (series refresh + soak automation) BUILT on branch
  `f79-g4-refresh`; NOT merged, soak not yet started.** Spec:
  `docs/superpowers/specs/2026-07-28-f79-g4-series-refresh-soak-design.md`. This closes the
  "needs manual `v2-shadow` CLI invocation" gap noted above: a curated publication calendar
  (`registry/series-calendar.json`) plus a new `series-refresh` command now check each scoring
  series for missing prints and can pull in new candidate readings on a schedule, and the daily
  run-cycle now runs that check and the v2 shadow-scoring step automatically as steps 7b/7c. The
  soak clock (the ≥5-live-cycle count from G3, with the "needs a human to run it each time" gap
  now closed) **starts counting on the next scheduled cycle after this lane is merged** — it has
  not started yet. The pass/fail terms for finishing the soak were already agreed and written
  down in the G4 spec before this build started, so no new sign-off is needed to grade it later.
  **Correction: that "next cycle after merge" start applies to the ≥5-cycle count only.** The
  spec's second term — ≥2 cycles after the first 2026-07 series points land — cannot start that
  early: the gap check reports nothing today (no monthly print is due yet on the calendar) and the
  first real gap appears **2026-08-12**, so that term cannot be met before roughly **2026-08-14**.
  Both terms must hold, so the earliest possible G4 package is mid-August regardless of merge date.
  **Flag for the record: the publication-calendar numbers (expected release day, allowed lag,
  tolerance) seeded in `registry/series-calendar.json` are the assistant's proposed starting
  defaults, not numbers the user has reviewed and approved — they are plain JSON and can be
  edited at any time.** Full build record: `.superpowers/handoffs/f79-g4-refresh-DONE.md`.
- [x] **F96 — Monthly-grain write-back collision: same-period price re-gather mints a stable id
  **✓ DONE 2026-07-26** — content-vintage ids merged `439fa6e`; live criterion PASSED (v18: 11 same-month updates, zero collisions).
  over changed content (F52-class residual).** Found in the live 2026-07-15 v8 daily cycle
  (`store/cycle-log.json` stageStatuses.writeBack = "failed (finding-id collision on
  lambda-ai-1252bbe3-2026-07-1 — same-month live-price re-gather, id stable but content moved;
  partial write rolled back to keep store consistent)"). F52 vintage-scoped finding ids by asOf
  (`{slug}-{digest}-{asOf}`), which fixes cross-DAY collisions — but a MONTHLY cycle's asOf is
  `2026-07`, so re-gathering the same price URL within the same month yields the SAME id with
  DIFFERENT content → the append-only FindingStore's collision check trips and the corpus
  write-back rolls back (the scorecard still published; the corpus just didn't absorb the
  re-gather). Not data-corrupting (rollback kept the store consistent), but the flagship's corpus
  silently misses same-month price refreshes. Fix direction: digest-in-id already exists
  (`{slug}-{digest}-{asOf}`) — verify why the digest didn't differentiate (the id may derive from
  URL not content for price rows), or scope price-row ids by capture time within the month. Small,
  gather/dedup-seam. *(Concurrent-mint caveat: F96 chosen against a backlog max of F95 on
  2026-07-15; if the F88 session also minted F96, renumber this one.)*
  **PROMOTED 2026-07-23 (third sighting: v8, v14, v15).** The v15 daily cycle could NOT resolve it
  by logged exclusion (that would mean hand-editing the deduped stream) — `wiki-ingest` aborted
  partway, 12/17 findings written, 5 left un-ingested (ids in the v15 HANDOFF entry; partial wiki
  state left as-is, fix-forward). The v15 run's recommendation stands: a real fix (day-grain or
  content-hash finding-id scoping for price rows), not another exclusion.
  FIXED 2026-07-26 — content-vintage ids (spec docs/superpowers/specs/2026-07-25-f96-content-vintage-ids-design.md, plan docs/superpowers/plans/2026-07-25-f96-content-vintage-ids.md); store tripwire retained; un-ingested v15/v17 findings accepted as history (spec §3.5). Live criterion: next monthly-grain price re-gather logs zero collisions.
- [ ] **F79 (original scope) — SDEWS-style index rebuild (scoring v2.0 migration; the backtest becomes real).**
  Re-architect the index layer per the SDEWS spec (`docs/2026-07-11-sdews-metric-extraction.md`
  maps it): every scoring indicator becomes a monthly, vintage-stamped time series (2023→now
  backfilled from dated archives — EDGAR, TWSE monthly revenue); values z-scored vs the series'
  own rolling history; DMI/SMI = weighted z-sums; SDGI σ-band alerts with a ΔSDGI momentum
  trigger and asymmetric demand-reversal sensitivity; event signals enter as decaying impulses.
  News-flow gates/findings/thesis book stay as the event channel + qualitative overlay (standing
  decision #3 unchanged — Claude stays the brain). Acceptance: a vintage-honest backtest against
  the known 2023–2025 turns (recall, orange+ false-alarm rate, lead time); no weight tweaks off
  single misses. **Frozen-core versioned migration (Part 33) — v2.0; absorbs F60's deferred
  scoring half (the v1.5 slot is superseded); replay fidelity for all stored v1.x scorecards
  required.** Sequencing (user-approved): starts only after F78 closes. Full record: spec
  `docs/superpowers/specs/2026-07-11-executive-brief-format-design.md` §6. **Decision provenance:
  user chose the full rebuild against the assistant's incremental-two-layer recommendation
  (interactive, 2026-07-11).** *(Feature — own brainstorm/spec/plan/SDD when it starts.)*
  **Forward pointer:** the 2026-07-12 wave (above) consumes F79's outputs — F84 scores its
  range forecasts against realized prints; F86 model-scopes the eval baselines its re-gate
  produces.

## From the 2026-07-13 three-tier site brainstorm (F95)

- [x] **F95 — Three-tier market site on Cloudflare Pages (category page build-now; layer/market
  **✓ DONE 2026-07-15→24** — merged `2725578`; live at ai-market-digital-twin.pages.dev since; index page since superseded by F101.
  rollup contract pinned).** Public static site rendering the exec page per tier: E2 word tiles
  + alert dot PLUS one dynamic numerical "featured metric" (library-backed,
  `registry/featured-metrics.json`, deterministic selector — rule-hit → biggest-move →
  priority, selection reason always rendered); bottom "WHY IT READS THIS WAY" explanation
  block; full drill-down trail on every KPI (components/weights → findings → evidence
  publisher/date/tier/link). Layer + market pages = computed rollups (worst-color-wins,
  disagreement shown not averaged, mandatory coverage chip — real layer/market brains
  explicitly rejected for now), **contract-only until ≥2 categories run**. Architecture:
  extend `gpu_agent/dashboard/` to emit a committed `site/` folder; Cloudflare Pages serves it
  with no build step (commit-then-serve). Renderer-only — F6 pin green, frozen core untouched.
  **Launch gates (user): repo-rename/TSMC-exposure decision + Pages subdomain naming before
  FIRST deploy** (build/commit may proceed). Sequencing: F95's run-cycle prose step lands
  before F88 merges (F88 goes last of the prose-touchers, per its own rule). Spec:
  `docs/superpowers/specs/2026-07-13-f95-market-site-design.md` (decisions S1–S8, all
  user-approved interactive 2026-07-13). *(Feature — spec done; next is writing-plans.)*

## From the 2026-07-16 executive-brief format design (F97)

- [x] **F97 — Executive Brief renderer (the exec-facing category page).** BUILT subagent-driven on
  branch `f97-exec-brief` (13 feature/fix commits + final-review fix `7e07d8c`); **NOT merged —
  awaiting the user's merge decision (only the user merges).** Renders blocks A–H per spec
  `docs/superpowers/specs/2026-07-16-executive-brief-format-design.md` (v5) from the monthly
  deep-read: masthead + attention chip, hero verdict + narrative, dynamic five-slot agenda band
  (`registry/agenda-slots.json` + deterministic freshness×magnitude×grade selection with
  stickiness), "what this means for TSMC" bullets, standing-calls board, dated signal strip, six
  dimension tiles, evidence footer; a register-lint gate makes a banned-token regression
  un-deployable. New modules `gpu_agent/dashboard/{agenda,brief_model,brief_render}.py`; the brief
  replaces the F95 category `index.html`; appendix gained `#dim-`/`#f-` anchors. Renderer/copy
  layer only — frozen core, brains, `report.py`, eval fixtures untouched; F6 pin green; full suite
  **1701 passed / 6 skipped**. Real-store smoke build clean (all blocks populate; attention chip
  resolves to real ELEVATED with hysteresis wording). Plan:
  `docs/superpowers/plans/2026-07-16-f97-executive-brief-renderer.md`. In-lane user-approved
  decision (interactive 2026-07-16): Task-3 stickiness "code governs" — kept the 0.75 bonus, relaxed
  the contradicting test. *(Concurrent-mint caveat RESOLVED: F97 confirmed free — backlog max was
  F96; no collision.)*
  **Evidence-anchor bug — RESOLVED (user-approved interactive fix, commit `e866c3d`).** The brief
  anchors on the MONTHLY read (`2026-07-v9`) but the F95 dashboard was reading a stale DAILY
  (`2026-07-06-v1`) for the appendix/alert/featured, so the brief's `#f-`/`#dim-` links dead-ended
  (spec criterion 6). Root cause: `load_scorecards`' regex matched daily-only (excluded the monthly),
  and two more selectors (`build.py` + `site_model.py` `latest_path = max()`) let a same-month daily
  outrank the monthly by raw-string compare. Fix (user chose "prefer the monthly read as latest"):
  all THREE latest-scorecard selectors now prefer the monthly grain when present (legacy intra-month
  dailies ignored); `report.py` (frozen change engine) untouched. All 11/11 real-store brief anchors
  now resolve; full suite **1703 passed / 6 skipped**; F6 pin green; OPUS review "ready to merge."
  Small follow-up noted: `build.py`'s selector (feeds alert/change, no anchor) isn't independently
  test-locked (correct by code symmetry). Doc note: the plan's Task-8 smoke command used
  `--store store`; the correct value is the CLI default `--store store/chips.merchant-gpu`.

## From the 2026-07-17 SDEWS cross-reference (F98)

- [x] **F98 — Agenda-band completeness + unit hygiene (Part A, renderer/config) and S4 upstream
  **✓ DONE 2026-07-17/20** — Part A merged `7e2f657`, Part B merged `6b0bf37` (gated lane cleared by the book).
  lead-time adoption (Part B, gated).**
  **► PART A DONE + MERGED 2026-07-17 (merge `7e2f657`, subagent-driven branch `f98-agenda-data`).**
  Shipped: new `price-sync` CLI verb + run-cycle step turn the local `gpu_agent/data/gpu_leasing_data/`
  folder into `store/series/*.jsonl` (gpuSpotPrice + rental on-demand/1-year; DISPLAY-ONLY, never scoring);
  curated `registry/price-benchmarks.json` trust boundary; slot-family fixes; unit hygiene
  ("500 USD billion"→`$500B`, "1 credit_condition_index"→`loosening`, plain labels, `[DSPX]\d` tile-label
  lint, money-unit change-line); manifest sources for apiArr/releaseCadence. Full suite 1724/6, F6 pin +
  F83 conformance green, frozen core untouched. User decisions (interactive, not AFK): price tiles insist
  on the newest chip (dim when its price is stale); apiArr/releaseCadence manifest priority = optional.
  Known non-blockers: spot series empty (source has no GPU spot rows); rental graceful-degradation
  roll-down retained but dormant; record `.superpowers/handoffs/f98-agenda-data-DONE.md` (in the retained
  worktree). **► PART B (S4 `upstreamLeadTimes`) BUILT 2026-07-18 (subagent-driven, branch
  `f98b-s4-leadtimes`) — AWAITING USER MERGE.** Adopted `upstreamLeadTimes` as a scoring supply indicator
  (weight 0.12, bottleneck/supply/slope, weekly-leading cadence tag) through the F6 eval gate: eval PASS
  (seam-scoped to extract; r1 clean, r1+r2 mean 6.688), 3-run governance rebaseline (no `--force`), replay
  pin + F6 pin green; manifest source + binding-constraint slot added. Whole-branch Opus review: READY TO
  MERGE. Live-extraction of an `upstreamLeadTimes` finding is verified on the next scheduled cycle (spec
  criterion 6), not in-lane. **Side effect handled (user Option B):** the rebaseline widened the extract
  noise band below the F79 canary's 6.25 damaged score, so that canary test is parked — tracked as **F99**.
  Records: `.superpowers/handoffs/f98b-s4-leadtimes-DONE.md` +
  `docs/superpowers/eval-notes/2026-07-18-f98b-upstreamLeadTimes-regate-note.md`. Provenance: user-directed cross-reference of the SDEWS v1.0
  spec (docx) against the taxonomy and the live F97 brief, building on
  `docs/2026-07-11-sdews-metric-extraction.md` (whose lane calls stand: S3/P1/P4 → chips.hbm-memory;
  D7/X2 → energy; S5/S6/S7/S8/P5/P6/X1/D10 → other agents or layer tier).
  **Part A — renderer/config only, NO F6 exposure:** (1) slot-family fixes in
  `registry/agenda-slots.json` — move `S9` (alternative supply) out of *binding-constraint* into
  *customer-mix*; decide `S10`'s home; add the tracked-but-unslotted merchant-gpu indicators
  `gpuSpotPrice` (SDEWS P3, early-glut), `apiArr` (D5, demand self-funding), `releaseCadence` (D8),
  `flopsPerDollar` to their agreed families. (2) Unit hygiene in `agenda.format_value` +
  candidates: canonicalize unit aliases (`"USD billion"` → `USD_B` — live bug: the
  binding-constraint tile renders "500 USD billion"), format `USD_B` as `$NB`, add
  `flops_per_USD`, and word-map index-style units (`credit_condition_index` 1.0 currently renders
  as "1 credit_condition_index"). (3) Plain-English tile metric labels (registry labels/glossary
  instead of raw indicator ids). DATA CAVEAT (2026-07-17 store check): `gpuSpotPrice` /
  `apiArr` / `releaseCadence` currently have NO measured-value findings and no series files —
  slotting alone renders nothing until readings land; Part A scope decision (config-only vs.
  also making these data-ready) is a brainstorm question.
  **Part B — gated, one change at a time:** adopt **S4 — upstream long-lead component lead-time
  index** (optics/CPO, liquid-cooling CDU/UQD, 800V power, high-end PCB/CCL) into
  `registry/indicators.json` per the extraction doc's candidate #3 (complements coincident
  `leadTimes` with the leading upstream view). Prompt-affecting data → brainstorm → spec →
  F6 eval gate (run-eval → rebaseline), per the standing rule. *(Concurrent-mint caveat: F98
  chosen against a backlog max of F97 on 2026-07-17; renumber if collided.)*

- [x] **F99 — Re-capture the F79 seeded-regression canary with more-severe extract damage
  (restore gate teeth).** Surfaced by F98 Part B (2026-07-18).
  **✓ DONE 2026-08-04 — CATCH on the first attempt, user-granted interactive capture.** D1 damage
  (extract prompt template: single-claim cap + anti-invention rule deleted + name-every-category
  nudge deleted) applied in a throwaway worktree only; ONE live run (~44 Opus dispatches incl. 9
  F38 re-dispatches, zero hand-edits, zero bypasses); damaged extract seamMean **5.375** vs hard
  bar 5.533 → **HARD-FAIL naming extract**, all 5 calibration negatives ≤ 2. New fixture
  `fixtures/evals/canary/extract-rules-stripped/report.json` (old `extract-series-vocab-stripped/`
  kept as history), canary test un-skipped + repointed (suite skips 6 → 5), baseline byte-untouched,
  no rebaseline, live prompt verified untouched (empty diff, F6 pin green). Raw run preserved at
  root `work/eval-f99-canary/`. Note:
  `docs/superpowers/eval-notes/2026-08-04-f99-canary-recapture-note.md` (headroom now ~0.8 pts
  below the soft bar; side observation: thesis informational seam 4.00 vs bar 5.50 — F107 LEVEL
  caveat still stands). Original entry: The F98b `upstreamLeadTimes` governance
  rebaseline widened the extract seam's noise band (epsilon 0.382 → 0.901, bar 6.285 → 5.599 — an
  n=3 replicate spread within the dispersion guard, but wide) below the F79 canary's damaged-run extract
  score (6.25), so `tests/test_evals_canary_f79.py::test_f79_series_vocab_stripped_is_rejected` no longer
  holds — the seam-scoped gate no longer rejects that damaged run. **Root cause is the canary's own
  calibration, not the F98b change:** the original canary (F79 G3, `accc064`) stripped only the 6 series
  ids, damaging just 2 of 8 extract cases → a razor-thin 6.25-vs-6.285 catch that the 2026-07-15 note
  itself flagged as fragile. Any honest re-measurement of the real (wider) extract noise drops the bar
  below 6.25. **Fix:** re-capture the canary with a *more-severe* damage whose extract score lands clearly
  below the current noise band (a broad vocab strip is fenced in by the eval cases' own indicator
  references; the effective lever is corrupting the extract prompt template — a human-driven capture,
  since a safety guard blocks an agent from running the eval on an edited prompt). Until then the canary
  test is **skipped** (user-directed 2026-07-18, Option B) with the reason recorded in the test + the
  eval-note `docs/superpowers/eval-notes/2026-07-18-f98b-upstreamLeadTimes-regate-note.md`. The F6 hash
  pin still catches any prompt change; only this "gate has teeth" meta-proof is parked. *(Concurrent-mint
  caveat: F99 chosen against a backlog max of F98 on 2026-07-18; renumber if collided.)*

- [x] **F100 — Merchant-GPU deep-dive dashboard revamp (renderer/copy layer).** DESIGNED + PLANNED
  **✓ DONE 2026-07-21** — merged `2e1effa`, deployed at rev 13; superseded as index by F101 (panel/model = donors).
  interactively 2026-07-20 (spec `1c93f68`, 12-task TDD plan `7aab4d6`, both docs-only on local main). Rebuilds
  the `chips.merchant-gpu` category page (`site/`): light editorial theme, 2-sentence brief, the existing agenda
  band restyled as 5 dynamic KPI cards (DMI/SMI excluded), a demand-vs-supply dual-line chart, a clickable
  six-dimensions list, and a **slide-in "why" panel on every element** (rationale, evidence, rating trend,
  confidence, trigger). Folds the "What this means for TSMC" bullets (by `dimensions` tag) and Standing calls (by
  a lens→dimension map) into the panels; keeps the latest-signal strip on the page; per-topic "full page →" reuses
  appendix `#dim-` anchors. Adds one self-contained inline `<script>` on the category page (scoped relaxation of
  the F95 no-scripting convention, user-approved). **Frozen core / F6 / F83 untouched; scope = merchant-GPU page
  only.** Build lane: `.worktrees/f100-dashboard`, subagent-driven, STOP-before-merge → user merges.
  *(Concurrent-mint caveat: F100 chosen against a backlog max of F99 on 2026-07-20; renumber if collided.)*

- [x] **F101 — Narrative-first category page: "Is supply catching up to demand?" (page redesign + daily narrator step).**
  **✓ DONE 2026-07-23/24** — Phase A `d01bb11`, Phase B `3e1049e`, Phase C `fcf996a`; deployed `ed5a332`; narrator live criterion PASSED 2026-07-25 (fellBack:false).
  DESIGNED interactively 2026-07-22 (spec `docs/superpowers/specs/2026-07-22-f101-narrative-page-design.md`;
  full visual-companion brainstorm, all decisions interactive, zero AFK). Rebuilds the `chips.merchant-gpu`
  page around ONE question answered in plain newspaper English: headline verdict → demand-vs-supply time
  chart with the shaded gap as the graphic → KPI band (anchored rent gauge + story-picked gauges, one per
  scene) → NYT-graphics scroll story (scenes with own charts, "Source:" lines, related outside coverage,
  hover tooltips + the slide-in evidence panel on every claim) → archive strip → Explore band. Adds a NEW
  daily narrator run-cycle step writing structured scene artifacts (`store/<cat>/story/`) — additive,
  never touches scores; new brain prompt = F6 eval gate; new step = F83 lockstep re-record. Supersedes
  F100 as the index page (F100's panel/model plumbing = salvage donors). Three phases: A renderer
  skeleton on existing data (no F6), B narrator (gated lane), C Explore sub-pages + story archive.
  *(Concurrent-mint caveat: F101 chosen against a backlog max of F100 on 2026-07-22; renumber if collided.)*

- [x] **F102 — `price-sync` crashes on month-grain as-of; series stale (repeat: v11, v14, v15 cycles).**
  `ValueError` in `gpu_agent/price_local.py::_yymmdd_date` — a month-grain `--as-of 2026-07` is parsed as
  `YYMMDD` and the day field comes back empty (v11 saw the sibling empty-string date parse). Non-blocking
  per run-cycle step 7 ("price-sync never blocks the cycle"), but `store/series/*` did not refresh on the
  affected cycles. **Priority raised 2026-07-23:** the F101 story page's KPI band — including the anchored
  "what a GPU rents for" gauge — reads these series directly, so a stale series now shows on the front
  page. Small dedicated fix lane: parse both grains + regression tests; verify next cycle refreshes.
  *(Concurrent-mint caveat: F102 chosen against a backlog max of F101 on 2026-07-23; renumber if collided.)*
  FIXED 2026-07-26 — `_parse_as_of` (day + month grain, month-end anchor), graceful skip on malformed input (spec docs/superpowers/specs/2026-07-25-f102-price-sync-grain-design.md / plan docs/superpowers/plans/2026-07-25-f102-price-sync-grain.md). Live criterion: next cycle's price-sync refreshes store/series and the front-page rent gauge drops its aging mark.

- [x] **F103 — Evidence freshness: half-life decay + stale-official-source fixes (user critique 2026-07-24).**
  **✓ DONE 2026-07-24/25** — merged `62676f6`, deployed `dce8dbd`; the aging treatment is live.
  Official NVIDIA earnings-call material (May vintage) keeps surfacing as current evidence on the live
  page. Root chain: manifest primaryDomains steer gatherers to IR domains daily; no downstream decay;
  evidence rows undated, judge-ordered. Fix (spec `docs/superpowers/specs/2026-07-24-f103-freshness-decay-design.md`):
  new `gpu_agent/freshness.py` half-life engine (weight = 0.5^(age/half-life), anchored publishedAt,
  NEVER capturedAt) + curated `registry/freshness.json` (**user-set half-lives: news 3d / filings 5d /
  structural 45d**, tunable by JSON edit); applied to page evidence rows (dates always shown, weight
  sort, dim <0.25, one row per publisher per scene), narrator inputs + prose-dating rule (dedicated
  narrator pin re-record, NOT F6) and an aged-claim gate check, and manifest earnings-window cadence
  for official IR domains. **Judge explicitly untouched (user decision — scores comparable, no F6);
  judge-side decay is a separate gated follow-up if ratings still skew stale.**
  *(Concurrent-mint caveat: F103 chosen against a backlog max of F102 on 2026-07-24; renumber if collided.)*

- [ ] **F104 — Social-media signal ingestion (RSS-first, via the repaired webreach path).**
  User wants agent-reach-style social reach feeding the GPU market view. Design direction (interactive
  2026-07-26, to be brainstormed fully before any lane): (1) CORE: curated social RSS feeds (subreddits
  r/hardware / r/LocalLLaMA / r/nvidia, key YouTube channels, HN query feeds) registered in the coverage
  manifest as a social slice, fetched through the healthy `rss` channel via webreach (recorded manifest
  rows; keyless; enters as secondary-tier docs — no brain prompts touched, no gates); (2) COMPLEMENT:
  promote `last30days` as a weekly social-discovery pass; (3) DEFERRED: per-platform agent-reach backends
  (twitter/reddit/youtube native) — credentialed + fragile, only on demand. **OPEN DESIGN QUESTION for the
  brainstorm: should social-sourced findings carry a visibly distinct "community signal" treatment on the
  page (e.g., excluded from scene evidence, confined to related coverage / a dedicated strip)?** Platform
  health snapshot 2026-07-26: web/rss/bilibili/v2ex ok; twitter/github/xueqiu warn; rest off.
  *(Concurrent-mint caveat: F104 chosen against a backlog max of F103 on 2026-07-26; renumber if collided.)*

- [x] **F105 — `extract --recorded` silently reports "0 findings" on a malformed answer envelope (v19 sighting 2026-07-27).**
  `ExtractionResult` (`gpu_agent/extraction/extractor.py`) is the ONLY brain-answer model without
  `extra="forbid"`, and its `drafts` field defaults to `[]`. A recorded answer that is a bare
  `FindingDraft` object (or any wrong-shaped JSON object) validates as an EMPTY ExtractionResult —
  extra keys ignored, drafts defaulted — so `extract --recorded` reports "0 findings, 0 dropped" and
  exits 0. The v19 headless run hit exactly this (brain returned bare drafts without the
  `{"drafts":[…]}` wrapper) and only a human noticing "0 findings" caught it; a scheduled run could
  publish an empty-looking cycle as a success. Fix: `extra="forbid"` + `drafts` required (no default)
  so a malformed envelope fails validation loudly and enters the standard retry path, matching every
  sibling answer model (judge/thesis/implication/narrator). Schema-only; no prompt text changes — the
  F6 pin must stay green.
  *(Concurrent-mint caveat: F105 chosen against a backlog max of F104 on 2026-07-27; renumber if collided.)*
  **DONE 2026-07-29** (lane `f105-extract-strict`). `ExtractionResult` now sets `extra="forbid"` and
  makes `drafts` required; a malformed envelope fails validation loudly and enters the standard retry
  path, while an explicit `{"drafts": []}` stays valid. New `tests/test_extractor_envelope.py` (4
  tests) covers the exact v19 shape. Also corrected five test files that used a stand-in extract
  answer of `{"findings": []}` — a key the prompt has never asked for, which the loose schema
  silently swallowed as "nothing found", so those tests were exercising the bug rather than the
  behaviour they named.
  The premise "schema-only, no prompt text changes" turned out to be wrong: the emitted extract
  prompt embeds `ExtractionResult.model_json_schema()`, so tightening the model moved the extract
  bundle hash and reddened the F6 pin. Cleared properly, not bypassed — full F6 eval, 3 replicates,
  **PASS on merit** (decision run r1: extract 6.500 vs bar 5.599, no craters; extract 6.500 / 6.750
  / 7.125 across r1/r2/r3, range 0.625). No `--force`, no hand-edited answers, calibration negatives
  held ≤4 in all three runs.
  A whole-baseline rebuild was refused by the dispersion guard on the **thesis** seam (range 2.500 >
  1.0) — a seam this lane never touched; that refusal is F107. Landed instead via the F108
  seam-scoped path: `eval rebaseline --seams extract`, which rebuilt only extract and carried
  implication/judge/thesis forward byte-identical. **New extract bar 5.599 → 6.163** (mean 6.500 →
  6.792, epsilon 0.901 → 0.629) — stricter, and the only bar that moved. Suite 2052 passed / 7
  skipped; all four pins green.

- [x] **F106 — HuggingNews as a desk-wide news source (all categories, not just GPU).** *(BUILT + merged 2026-07-29 — see the "F106 BUILT" entry below for what shipped.)*
  User-provided keyed API access to huggingnews.com — an AI-news wire whose stories are AI-written
  from primary source material (X posts, announcements, filings, papers) with per-story source links
  and topic tags (`ai-compute-chips`, `ai-model-releases`, `ai-fundraising`, …). Read-only JSON API:
  `api.huggingnews.com/api/stories` (latest/search/detail; skill contract published at
  `huggingnews.com/SKILL.md`; env `HUGGINGNEWS_API_KEY`). Verified live 2026-07-28: anonymous covers
  3 ET days; the key unlocks feed pagination + 21-day search; detail returns `summary` +
  `selectedTweets` with source URLs. **Key handling: machine-local gitignored
  `.superpowers/secrets/HUGGINGNEWS_API_KEY` — the key never enters git, briefs, prompts, or logs.**
  Design direction to brainstorm (interactive, standing rule): role (discovery/leads channel chased
  to primary sources per the last30days precedent vs direct secondary-tier ingest — its articles are
  aggregator-written), per-category tag mapping in manifests, registry entry on the web-reach path
  (relates to F104's social-ingestion design space), cost/budget per cycle, and whether the desk's
  D6 licensed-source discipline applies. *(Feature — own brainstorm/spec/plan when it starts.)*
  *(Concurrent-mint caveat: F106 chosen against a backlog max of F105 on 2026-07-28; renumber if collided.)*

- [x] **F107 — thesis seam replicate instability: range 2.5 on an UNCHANGED prompt (2026-07-28).**
  The F105 3-replicate eval run showed the thesis seam scoring 5.000 / 7.500 / 5.500 across three
  independent draws — a 2.5-point spread on a prompt whose hash (`4a9d9817951c`) did not move and is
  identical to the incumbent baseline. Three-run mean is 6.000, exactly the incumbent baseline mean,
  so the seam is not drifting — it is *noisy*. Historical thesis dispersion has been <= 0.5 (the
  stored baseline replicates are 6.0 / 6.0 / 6.0). The swing traces to the `steelman` criterion,
  which moves 0 <-> 2 on whether the answer is judged to argue against itself; the other three
  criteria are comparatively stable. This tripped the `DISPERSION_LIMIT = 1.0` guard in
  `rebaseline_v2` and blocked F105's rebaseline (see `.superpowers/handoffs/f105-extract-strict-QUESTIONS.md`).
  Investigate: is this grader disagreement on the same material (rubric anchor ambiguity in
  `steelman`), or genuine brain-answer variance? The 2026-07-28 diagnostic already answered part of
  this: it was ANSWER variance, not grader noise (r2's answers argue against themselves, r1/r3's
  don't; every phrase r2's grader quoted exists only in r2's answer).
  **Evidence: `.superpowers/handoffs/f105-extract-strict-QUESTIONS.md` (diagnostic preserved
  verbatim — per-criterion tables, quote probes, grader extracts, historical comparison). ⚠ The RAW
  per-case answer/grade files under the f105 worktree's `work/eval-2026-07-28/{r1,r2,r3}/` were
  DESTROYED 2026-07-29 by an erroneous `git worktree remove --force` during lane retirement
  (orchestrator error, disclosed); any deeper investigation needs fresh draws.** Likely outcome is a sharpened `steelman` anchor in `gpu_agent/evals/rubric.py`, which is
  a rubric change, not a prompt change (the F6 pin covers brain prompts only) — but confirm before
  assuming. F108 (seam-scoped rebaseline) unblocks F105 without needing this answered first; this
  item is the real fix for the underlying noise.
  *(Concurrent-mint caveat: F107 chosen against a backlog max of F106 on 2026-07-28; renumber if collided.)*
  **CLOSED 2026-07-29 — user decision (a), interactive (NOT AFK): close as a single-run outlier.**
  Diagnosed by running option B of the decision package: 3 fresh replicates over the **thesis seam
  only**, prompt untouched, ~23 Opus dispatches, pre-committed disposition written before any
  dispatch. Seam means **5.50 / 5.00 / 5.00**; `steelman` = **1 in all six fresh draws**; negatives
  0-2 throughout (calibration held). The 2026-07-28 swing did not reproduce and the escalation branch
  did not fire — dispersion (range 0.5) supports the historical ~0.28 wobble, **not** the 1.32
  scenario. Zero hand-edits, zero `--force`, zero bypass flags; two disclosed deviations (a
  coordinator transcription slip on r1, restored byte-verbatim; r2/r3 dispatch wording expanded after
  r1's gate round-trips). Baseline untouched — these filtered thesis-only runs **must NEVER be fed to
  `eval rebaseline`** (pre-committed, standing).
  **Durable record: `docs/superpowers/eval-notes/2026-07-29-f107-thesis-replicates-note.md`.**
  **CAVEAT carried forward:** the closure branch required the seam in 5.5-6.5 and it did not land
  there — the **level** sat at or below the 5.5 bar in 2 of 3 draws, so a healthy unchanged prompt
  would marginal-fail a real gate today. That is a LEVEL question (grader severity drift vs a true
  level shift), not the DISPERSION question F107 asked, and it is latent: the thesis bar only binds
  when the thesis prompt changes. **Revisit grader-severity-vs-bar ONLY when the thesis prompt next
  changes.**
  **Side findings that remain OPEN (named here deliberately, NOT minted as new F-items):** (1) the
  rubric is not pin-covered — `tests/test_evals_baseline_pin.py` hashes the four brain prompts but not
  the rubric text, so a `steelman` wording edit would change all future grading with no test turning
  red; (2) `append_run_to_history` — the function that widens epsilon as real noise accumulates — has
  **no production caller** anywhere in the package and is exercised only by its own tests.

- [x] **F108 — seam-scoped rebaseline (`eval rebaseline --seams <seam> ...`).**
  `rebaseline_v2` today rebuilds the entire baseline from all four seams at once: every seam's mean,
  epsilon, quantum, history and case medians are recomputed, and the dispersion guard is applied to
  every seam. That makes a single-seam prompt change hostage to unrelated noise in seams the change
  never touched — the F105 case exactly (extract passed cleanly at 6.50 / 6.75 / 7.125, range 0.625,
  but thesis's unrelated 2.5 range refused the whole rebaseline; see F107). The only escape hatches
  today are a whole-baseline `--force`, which would have collapsed the thesis bar 5.50 -> 3.35 and
  loosened judge and implication too, or parking the fix. Build a seam-scoped mode: named seams get
  new mean/epsilon/quantum/history/case-medians from the replicate reports, every unnamed seam's
  baseline entry carries forward BYTE-IDENTICAL from the incumbent, the dispersion guard applies only
  to the seams being rebuilt, and the baseline records which seams were rebuilt when. No seams named
  = today's whole-baseline behaviour, unchanged and byte-identical on the default path. Harness code
  only — no prompt text, no hand-edited baseline content; all four pins must stay green.
  *(Concurrent-mint caveat: F108 chosen against a backlog max of F107 on 2026-07-28; renumber if collided.)*
  **BUILT 2026-07-28** in `.worktrees/f108-seam-rebaseline` — spec
  `docs/superpowers/specs/2026-07-28-f108-seam-scoped-rebaseline-design.md`, plan
  `docs/superpowers/plans/2026-07-28-f108-seam-scoped-rebaseline.md`. Awaiting user merge; the F105
  lane then runs `eval rebaseline --seams extract` to land its change.

- [x] **F110 — Dashboard revamp: executive React/Astryx rebuild of the main category page (user-directed, 2026-08-05). BUILT + MERGED `d62e800` + PUSHED 2026-08-06.**
  The live story page "tells a lot and nothing at the same time" for an executive reader.
  DESIGNED interactively 2026-08-05 (all decisions user-approved, zero AFK-defaults): verdict-led
  five-zone page, full React 19 + Astryx rebuild of the main category page ONLY (F95 no-script
  rule user-overridden for this page), build-once/data-daily (daily cycle stays pure Python,
  writes `dashboard.json`), per-bullet mini-charts from a new curated series library
  (`registry/chart-series.json` + `gpu_agent/chartdata/` fetchers) with findings-history fallback
  and an honest no-chart panel, and universal click-through source references (exporter must
  resolve evidence IDs → original URLs). Approved visual contract:
  `docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html` (hallmark + dataviz, real data).
  Spec: `docs/superpowers/specs/2026-08-05-dashboard-revamp-design.md`. No brain/prompt changes;
  F6/narrator/scoring pins must not move; F83 re-records in-lane (new fetch + export steps).
  Design-weight item: brainstorm was run interactively per the standing rule.
  **✓ BUILT subagent-driven 2026-08-05/06 (12 TDD tasks, fresh implementer + per-task spec+quality
  review each, whole-branch review, one final fix wave). MERGED `d62e800` (`--no-ff`) + data
  refresh `d29291d`, PUSHED; `main == origin/main`.** Merged-main suite **2318 passed / 5 skipped**;
  all four pins green (57) — only the F83 run-cycle fingerprint moved, in Task 7, per the F109
  precedent; forbidden diff empty; zero deletions under `site/chips.merchant-gpu/`. Worktree +
  branch `f110-dashboard` retired post-merge.
  **Shipped:** shared contract `web/schema/dashboard.schema.json`; `gpu_agent/dashboard/`
  `source_refs.py` / `bullets.py` / `export_json.py`; `gpu_agent/chartdata/` (registry + fetch
  framework + AMD data-centre revenue fetcher with landing-page link discovery); new registries
  `chart-series.json` + `plain-units.json`; CLI verbs `chart-fetch` + `dashboard-json`; run-cycle
  steps 7d/7e (both non-blocking); and a Vite + React 19 + `@astryxdesign/core` app in `web/`
  (pinned exactly at 0.3.0) whose compiled output is committed and served statically. Node never
  enters the scheduled run.
  **Interactive user decisions during the build (five; ZERO AFK-defaults):** (1) `jsonschema` added
  as a real dependency so the exporter validates during the daily run, not just in tests;
  (2) the gap chart mixes dated and monthly readings; (3) that choice REAFFIRMED after being shown
  it compares unlike scales; (4) the dimension legend uses the rating words the rows actually
  render ("Green strong · amber mixed · red weak") rather than the mock's wording — a deliberate,
  user-approved departure from the visual contract; (5) the AMD source follows the landing page's
  link to each quarter's release automatically.
  **KNOWN, USER-ACCEPTED LIMITATION:** the gap chart's daily readings hold one day of findings
  (~0.04–0.23) while monthly readings accumulate all of them (~3.4–3.7), so the line appears to
  collapse and recover across the grain seam, and the direction badge can flip depending on which
  grain is most recent. The caption discloses the mix but not that the two are non-comparable
  magnitudes. Filed as **F111**.
  **Other limitations recorded:** no mini-chart renders until a curated series accumulates enough
  history (AMD needs one more quarterly release); the mock's numeric context note beside the
  confidence line and its bolded so-what clause cannot render (contract carries plain strings only).
  Full record: `docs/superpowers/f110-dashboard-DONE.md`.
  **Live criteria (post-merge, not yet confirmed):** (1) the next scheduled cycle writes
  `dashboard.json` with zero manual steps and the live page renders it; (2) at least one bullet
  renders a curated-series mini-chart with a working source link while another shows the honest
  no-chart panel; (3) every visible statement resolves to a working source reference.

- [ ] **F111 — Gap chart mixes non-comparable scales (from the F110 whole-branch review, 2026-08-06).**
  The demand/supply series draws from two kinds of reading: dated files hold a single day's findings
  (~0.04–0.23) while month-versioned files accumulate a month of them (~3.4–3.7). Plotted together
  the line appears to collapse and rebound inside five weeks — an artifact of file grain, not the
  market — and `gap_trend_word` compares the last two points across that seam, so the verdict's
  opening phrase, the direction badge and the chart caption can all flip on it. The caption
  discloses that the grains differ in time coverage but not that their magnitudes are
  non-comparable. **The user was shown this consequence twice and chose to keep the mix**, so this
  is a filed follow-up, not a defect to fix unasked.
  Options when picked up: (a) plot monthly readings only and let the line densify once readings
  carry a date; (b) show the dailies as a separate, separately-labelled element with the direction
  computed from the monthly series alone; (c) stamp a real date on every reading so the series
  becomes uniformly daily — that last one touches the frozen scorecard write path, so it needs its
  own lane. Related: only four readings on disk carry a day in their filename; the rest record
  `asOf` at month granularity.

- [ ] **F112 — Small F110 follow-ups deferred at merge (2026-08-06).**
  Each was found in review, judged non-blocking, and recorded rather than fixed.
  (a) The AMD link discovery has **no staleness check** — if AMD ever listed quarters oldest-first
  inside a year block, the run would fetch and parse an older release and look successful; assert
  the discovered quarter is newer than the newest stored period. This is the one silent-wrong-data
  path left in the lane. — **DONE 2026-08-20 (lane f112a-amd-staleness):** generic staleness guard
  in `gpu_agent/chartdata/fetch.py` `run_fetch`; a strictly-older newest parsed quarter raises
  `StalenessViolation` → loud `failed` entry, store untouched, run continues (never-raises intact).
  Same-or-newer and first-ever-fetch pass (user-approved decisions 2026-08-20; plan:
  `docs/superpowers/plans/2026-08-20-f112a-amd-staleness.md`).
  (b) `amd_dc_revenue.py` assumes three quarterly columns (`all_dates[:3]`); deriving the count from
  the "Three Months Ended" header colspan would be safer.
  (c) `gpu_agent/dashboard/render.py:140` still holds reader-style copy containing the internal
  index acronyms — unreachable today, but it would leak the moment anyone re-wires it.
  (d) Nothing validates that a chart series' `sourceUrl` is a real URL rather than an `internal:`
  label, so a future hard-fact entry could ship a non-clickable source.
  (e) The annotation marker resolves its point by date, so with two same-date readings it attaches
  to the month anchor; deterministic now, but still not a deliberate choice.
  (f) The verdict's supporting sentence inherits the narrator headline verbatim, so when that
  headline carries no terminal punctuation the answer reads without a full stop — visible on the
  2026-08-06 reading ("Not yet. Memory now decides how many chips get built").

- [x] **F113 — Same-day chart researcher + dashboard render fixes (user-directed, 2026-08-06 screenshot review).**
  The F110 matcher is passive; on 2026-08-06 all three bullets rendered "No chart" panels. User
  decisions (interactive, zero AFK): add a tool-using research step that digs external sources for
  a published series relevant to each chartless bullet; **quarantine + verify** trust model —
  researched series live in `store/<cat>/research-series/`, render only after a deterministic
  verifier re-finds every number in its cited source page (F66 tolerance rules), are labeled
  "found today — single source", and NEVER auto-enter the human-curated `registry/chart-series.json`
  (promotion stays a human edit). Render fixes ride along: chartless bullets go full-width with one
  quiet line, no-chart copy varies by cause, source badges inline at sentence end. F83 re-record
  in-lane (new step). Spec: `docs/superpowers/specs/2026-08-06-f113-chart-researcher-design.md`.
  **Sequencing: dispatch only after F114 merges** (shared files). Design-weight; brainstormed
  interactively 2026-08-06. Next: writing-plans.
  **✓ BUILT + MERGED `705a5ee` 2026-08-08.** Live 08-10/08-11: quarantine held, 0 series accepted — brief gaps filed as F116.

- [x] **F114 — Narrator-authored "What changed" bullets (user-directed, 2026-08-06 screenshot review). GATED LANE (narrator prompt + pin).**
  Mechanical scene-title+first-sentence bullets proved hollow ("They are dated 2027 and 2028" —
  no antecedent). User decision (interactive, zero AFK): the narrator writes the 3 bullets in its
  artifact — each ≤ 28 words, self-contained, ≥ 1 concrete anchor, `claimFindingIds` attached;
  gate additions all mechanical (count/word cap/digit/pronoun-start/banned words/ids resolve);
  citation audit extends to bullet numbers; exporter prefers artifact bullets, mechanical
  condenser kept as fallback. Narrator prompt pin re-recorded in the same commit (F101b/F103
  lockstep); F6 byte-untouched; no scored eval bar (F101b decision carries).
  Spec: `docs/superpowers/specs/2026-08-06-f114-narrator-bullets-design.md`.
  **Sequencing: build FIRST, before F113; exclusive prompt lane.** Next: writing-plans.
  **✓ BUILT + MERGED `092ef0e` 2026-08-08.**
  (g) The Nvidia investor-relations URL in `registry/chart-series.json` was never verified live;
  that series has no fetcher so it renders nothing today, but check it before giving it one.
  (h) `npm run build` rewrites the committed `index.html` with different line endings, so a rebuild
  always dirties the tree even when nothing changed.

- [x] **F115 — Category-page issue tracker ("Known issues", user-directed, 2026-08-10). GATED LANE (narrator prompt + pin).**
  Recurring structural problems (memory lacking, advanced packaging lacking) are re-discovered
  each cycle but never tracked as named persistent issues. User decisions (interactive, zero
  AFK): agent-minted issues via deterministic triggers (binding constraint; weak+worsening
  dimension); the narrator assesses each open issue every cycle (improved/worsened/unchanged +
  1–2 sentence reasoning + `claimFindingIds`); resolve after 5 consecutive good cycles (flap
  resets, `not-assessed` freezes); storage Option A — `store/<cat>/issues/register.json` +
  append-only `history.jsonl` (thesis-book pattern, no-silent-deletion invariant). New step-3
  sub-steps (d4) issues-open / (e3b) issues-update; citation audit keys `issue:<id>`; dashboard
  schema 1.1→1.2 with a required `issues` section; new React `Issues` component above the footer.
  Narrator pin re-records once in lockstep; F83 re-stamped in-lane; F6 byte-untouched.
  Spec: `docs/superpowers/specs/2026-08-10-f115-issue-tracker-design.md`.
  **Exclusive narrator-prompt lane.** Next: writing-plans.
  **✓ BUILT + MERGED `a3aa2ae` 2026-08-14** (data refresh `bfe7b8c`); NOT yet exercised live — no register
  exists until the next scheduled cycle runs sub-step 3(d4). See HANDOFF for the live watch-list.
  **✓ EXERCISED LIVE 2026-08-19 cycle (commit `70c8aab`) — spec §10's live criteria all MET except the 5-cycle one.** The register opened 3 issues (binding constraint + `dim-bottleneck` + `dim-moat`); the narrator assessed all 3 with reasoning and cited findings (all `worsened`);
  `history.jsonl` was created with its first 3 lines; the story artifact stamped `schemaVersion 3`; the dashboard's `issues` section rendered populated at schema 1.2. The idempotence guard also fired for real and correctly — the post-audit narrator re-dispatch
  re-wrote the story and `issues update` returned `{"skipped": true, "reason": "already-recorded"}` instead of double-counting. Still unseen: the resolved-`<details>` block (needs 5 consecutive improved cycles). ⚠ The WATCH ITEM is now REAL: v8's constraint
  label is "HBM stacked memory supply" and the opened id is `constraint-hbm-stacked-memory-supply`, while v6/v7 used "stacked-memory supply for accelerators" — a relabel in a later cycle mints a NEW id and strands this one, which would
  drift into the reader-facing "Resolved" list after ~5 cycles claiming a fix that never happened. Remedy is still a human edit to `register.json`.

- [x] **F116 — Chart-researcher brief says what the gate enforces (bare numbers, hedges, bot-blocking
  sources). Filed + FIXED 2026-08-15, branch `chart-brief-fix`.**
  Three consecutive live cycles (2026-08-10, 2026-08-11 ×2) rejected EVERY researched series, and each
  time the brief, not the researcher, was at fault: values came back as prose ("$35.6 billion",
  "over $1.3 trillion") where `CandidatePoint.value` is a float; the 08-10 candidate honestly relayed
  the source's hedges ("below 60%", "close to 80%") as values; and a TrendForce series failed re-fetch
  verification with HTTP 403 on all five points. The brief said none of this. Fix, prompt-only
  (`gpu_agent/chartdata/research_prompt.py`, deliberately UNPINNED per the F113 spec — no F6 / narrator /
  F83 exposure): rule 8 explains that a plain automated reader re-opens every cited URL and names the
  registered licensed publishers from `registry/licensed-sources.json` (read at build time, generic
  warning if the file is absent); rule 9 says `value` is a bare number in the stated unit and that a
  hedge or range is NOT a number to be converted — leave the point out or give up; the points-format
  line repeats it. Tests pair each instruction with the enforcement it mirrors (F113 doctrine).
  **Live criterion:** on the next cycle with chartless bullets, a researcher either returns a series
  that passes the verifier or an honest `NO-SERIES-FOUND` — no more prose-value or 403 rejections.
  Still open, separate: whether the verifier itself should classify a 403 as "blocked source" rather
  than "number not found" (diagnostic clarity only; the quarantine already holds).
  *(Concurrent-mint caveat: F116 chosen against a backlog max of F115 on 2026-08-15; renumber if collided.)*
  **✓ LIVE CRITERION MET 2026-08-19 cycle (commit `70c8aab`).** 3 bullets researched, 2 series ACCEPTED — the first verifier-passing researched series ever (`store/chips.merchant-gpu/research-series/` now exists): HBM per NVIDIA data-center GPU by
  generation (developer.nvidia.com) and AI compute per Cerebras wafer (ServeTheHome). Zero prose-value and zero hedge rejections; both surviving researchers explicitly routed around sites that refuse automated readers, which is exactly what rule 8 was written to cause. The
  one rejection (Counterpoint Research foundry share, 5/5 points HTTP 403) is the NEW gap filed as F117 below, not a recurrence of this one.

- [x] **F117 — Rule 8's bot-blocking list is a registry lookup, and the registry is missing the
  domains that actually block (found live, 2026-08-19 cycle).**
  F116's rule 8 names the bot-blocking publishers by reading `registry/licensed-sources.json`.
  On the first cycle after that fix, the one rejected candidate cited
  **counterpointresearch.com**, which returns HTTP 403 to the verifier's plain reader but is
  **not in that registry** — so rule 8 never warned the researcher off it, and all 5 points died
  at verification. Worse, the researcher had no way to know: its own WebFetch opened the page
  cleanly three times. **Two distinct problems, and the second is the real one:**
  (a) the registry needs the domains that empirically 403 the verifier (counterpointresearch.com
  first), and a hand-maintained list will always lag; (b) **a research agent's fetcher and the
  verifier's fetcher are different readers**, so "I checked and it opens" is not evidence the
  point will verify. Candidate fixes, cheapest first: have the researcher's brief say plainly
  that its own fetch proves nothing and name the verifier's reader; expose the verifier's own
  fetch as a pre-flight the researcher can call before committing to a source; or record every
  403 the verifier meets into a learned blocklist the brief then reads. Ties into the still-open
  F116 tail (the verifier reports a 403 as "number not found" rather than "blocked source") —
  fix them together, since a learned blocklist needs the verifier to distinguish the two.
  *(Concurrent-mint caveat: F117 chosen against a backlog max of F116 on 2026-08-20; renumber if
  collided. Number minted by the assistant, not the user.)*
  **DONE on branch `f117-f126-fetch-registry`** (built as one lane with F126). All three
  problems are closed together. `registry/do-not-fetch.json` is the one place a domain we
  must not read is written down, with a `kind` on every entry saying which of the two
  reasons applies (see F126 below for the other kind). It ships seeded with
  **counterpointresearch.com** as `blocks-plain-readers`. The verifier no longer has to be
  told: any point whose page answers HTTP 401, 403 or 429 gets that domain appended to the
  same file automatically, once, with the page that proved it and the story date — so the
  list stops lagging the sites that actually block, which was problem (a). The F116 tail is
  fixed with it: a failure line now reads `blocked (HTTP 403)`, `not found (HTTP 404)` or
  the old `unreachable (...)`, three different things that used to arrive as one word.
  Problem (b), the real one, is answered in rule 8 itself: the brief now tells the
  researcher plainly that the machine re-checking its numbers is a DIFFERENT reader with
  different access, so a page opening cleanly for it proves nothing — and rule 8 names both
  do-not-fetch lists beside the licensed one. **What stays open:** the middle candidate fix,
  exposing the verifier's own fetch as a pre-flight the researcher can call. Research agents
  are dispatched WebFetch-only, with no shell, so they cannot call the verifier's reader at
  all; closing that would mean a new tool seam, not a flag. Telling them their own fetch
  proves nothing is the honest fix available today. Also open by design: nothing ever
  un-blocks a domain — a site that starts answering again still verifies normally (the
  verifier keeps fetching `blocks-plain-readers` domains), so a stale entry costs a warning
  line in a brief, not a lost series, and removing it is a human edit.

- [ ] **F118 — A curated series can go permanently un-refillable when its construction recipe is
  not written down (found live, 2026-08-19 cycle).**
  Step 7b hands each series reader a `latestNote` describing how the newest stored point was
  built, because these series are constructions, not published figures, and a point built a
  different way silently changes what the series means. For **`tokenEconomics`** that note
  records the basket SIZES ("median of 6 vol rates ... + median of 14 price rates ... in trailing
  9mo") but **not the basket MEMBERSHIP** — which 6, which 14. The reader correctly returned an
  empty envelope rather than build a differently-composed number, and that gap will recur every
  cycle: the series can never be refilled from public sources as specced. The honest empty answer
  is the system working; the un-refillable series is the defect. Fix: carry the basket definition
  (member ids and the window rule) in the series metadata so `latestNote` can reproduce it, and
  audit the other constructed series for the same hole before their next gap comes due.
  *(Concurrent-mint caveat: F118 chosen against a backlog max of F117 on 2026-08-20; renumber if
  collided. Number minted by the assistant, not the user.)*

- [x] **F109 — Coverage gaps are computed but never recorded durably (found while building F61, 2026-07-28).**
  Nothing downstream can render or audit what the gather run failed to cover.
  `manifest.compute_coverage_gaps()` has **no production caller in the package** — it runs only
  from the gather skill's inline snippet, and its output is written to
  `work/<cycle>/docs/gather-log.json` under `coverageGaps`, in the **gitignored** `work/` tree.
  Scorecards carry no coverage field at all, so a rebuild on any other machine — or any rebuild
  after the work dir is swept — has no coverage data whatsoever.
  **Worse, it is currently not being written even there:** the 2026-07-27 (v19) cycle's
  `gather-log.json` has **no `coverageGaps` key**, and `corpus-report.json`'s `notCovered` is
  `[]`, while that same cycle's log prose claims "Coverage gaps this cycle: 21 (13 source,
  8 indicator)" — the only surviving record of those 21 gaps is a free-text sentence in
  `store/cycle-log.json`. So the number is unverifiable and un-renderable.
  Fix: persist the structured gap list into committed store data at cycle end (alongside the
  scorecard), so the renderer and any audit can read it, and so "what we did NOT look at" stops
  being a claim only the run itself can make. Blocks the coverage half of F61 (deliberately
  descoped there, 2026-07-28) and is a prerequisite for any honest coverage disclosure on the
  page.
  *(Concurrent-mint caveat: renumbered F106→F109 at merge time 2026-07-29 — F106 (HuggingNews), F107, F108 were minted concurrently on main.)*
  **BUILT 2026-08-04** on branch `f109-coverage-gaps` (awaiting user merge) — spec
  `docs/superpowers/specs/2026-08-04-f109-coverage-gaps-design.md`. All four design forks were
  question-stopped and answered interactively by the user (zero AFK-defaults). **Root cause was not
  the file format:** the only route from `compute_coverage_gaps()` to any record ran through a human
  pasting JSON into `gather-log.json`, and that step got skipped. **Built:** a `CoverageRecord`
  model + pure `build_coverage_record()` (clock-free, so reruns are byte-identical) in
  `gpu_agent/manifest.py`, and a `coverage-record` CLI verb that computes AND persists in one call,
  writing the tracked `store/<categoryId>/coverage-<asOf>.json` — the same sidecar shape as the L2
  dedup report. The record is self-auditing: it carries the fetched-URL set, the covered indicator
  ids, and the manifest reference it judged over, so the verdict survives a `work/` sweep. Covered
  indicators come from the **gated findings**, not the URLs (fetching a source proves nothing about
  learning the indicator), which is why it runs at new run-cycle step **(d3)**, after write-back;
  the F83 fingerprint was re-recorded `d7359d33`→`5b25bf8f`, regenerated from `EXPECTED_STEPS`. The
  gather skill's inline snippet is deleted and a test guards against its return. An empty gap list
  is still written — a missing file means the check never ran, never "full coverage". No backfill by
  user decision: `store/` gains no data here; history starts honest at the next cycle. 14 new tests;
  suite 2160 passed / 6 skipped; all four pins green. **Unblocks the coverage half of F61** (still
  unrendered — F109 records, it does not display).
  **✓ MERGED `dea3bff` (`--no-ff`) 2026-08-05, user-authorized; merged-main suite 2173 passed /
  5 skipped. LIVE CRITERION MET the same day:** the 2026-08-05 scheduled cycle (`febaad4`) wrote
  the first committed artifact `store/chips.merchant-gpu/coverage-2026-08.json` with no human step.
- [x] **F106 BUILT 2026-07-29 — HuggingNews desk-wide source, first slice shipped.** Branch
  `f106-huggingnews`, commits `5fd18ae`..`fe19717` (7 commits). What shipped: (1) `gpu_agent/gathering/webreach.py`
  gained `resolve_secret` (env var first, else the gitignored `.superpowers/secrets/<NAME>` file, else
  `None` — a missing key degrades silently to anonymous, never errors) plus per-verb `auth` argv appended
  only when a secret resolves, and scrubbing of any resolved secret value out of every recorded error
  string; (2) `registry/web-reach-tools.json` gained the `huggingnews` tool (verbs `latest` / `search` /
  `detail`, tool-level `secretName`) and `gpu_agent/web_reach_ensure.py` preflight reporting now appends
  `(keyed)` / `(anonymous-only)` per tool; (3) `gpu_agent/manifest.py` validates an optional
  `huggingnewsTags: list[str]` field against a `HUGGINGNEWS_TAG_SLUGS` allowlist (unknown slug fails to
  load, loud not silent), and `manifests/chips.merchant-gpu.json` seeds `["ai-compute-chips"]`; (4)
  `.claude/skills/gather-category/SKILL.md` gained a tiered discovery sub-step — leads from a HuggingNews
  story are chased to their primary sources first; the story itself is only ingested as a documented
  fallback when it had leads and every one proved unreachable (a story with zero leads is dropped, never
  a fallback); fallback docs are logged in `huggingnewsFallback[]` and count as ONE publisher for
  corroboration, regardless of how many fallback docs land.
  **Decision provenance (both user-approved, interactive — not AFK-defaults):**
  (a) *Task 2:* the plan's `huggingnews` registry entry leaves `install` empty for all three OSes (it's a
  pure read-only API, nothing to install), which collided with the pre-existing invariant
  `tests/test_web_reach_registry.py::test_enabled_tools_have_per_os_install_recipes` (every enabled tool
  must carry non-empty per-OS install recipes). The lane stopped and asked rather than picking; the user
  chose an explicit `"installNotNeeded": true` flag on the entry, with that invariant test amended to
  honour it — when the flag is set, all three install lists must be exactly empty; every tool without the
  flag keeps the strict non-empty rule. (b) *Task 5 close-out:* the plan's guard test in
  `tests/test_webreach_huggingnews_entry.py` spelled the literal key prefix while asserting no key
  material is present, which made the branch-wide leak scan (`git log -p main..HEAD | grep -c "<prefix>"`)
  return a nonzero hit that was the guard string itself, not a real leak. The user chose to rebuild the
  guard from a locally-constructed value instead of spelling the prefix (commit `fe19717`); see the
  close-out sentinel below for the full key-hygiene attestation, including why the raw `git log -p`
  history count still cannot reach exactly 0 without rewriting a prior, already-completed commit — which
  was explicitly ruled out.
  **Deferred, not built in this slice:** the weekly 21-day keyed `search` sweep (spec item D3) is parked
  pending about a week of real hit-rate data before it's worth scheduling; an ad-hoc/one-off HuggingNews
  lookup skill is also deferred (no lane opened for it yet).
  **Live criteria (checked post-merge, not forced in this branch):** (a) the next scheduled cycle's
  web-reach preflight reports `huggingnews … (keyed)`, confirming the key resolves in the real
  environment; (b) a HuggingNews-referred lead lands as a chased primary-source doc on a news day that
  provides one; (c) any fallback ingest appears in a `huggingnewsFallback[]` list and corroboration counts
  it as exactly one publisher, never one-per-fallback-doc. Full detail: `.superpowers/handoffs/f106-huggingnews-DONE.md`.
  **UPDATE 2026-07-29 — final whole-branch check-through wave, commit `f96811d`.** A full read of the
  finished branch (an independent double-check of the whole thing, not just the pieces) came back
  "ready to merge, but fix four things first." All four were fixed the same day and a follow-up
  check confirmed the fixes hold with no new problems. Final commit list: `5fd18ae`, `008c649`,
  `be74a7e`, `3623df6`, `666b434`, `3fd55f3`, `fe19717`, `d56d9c0`, `f96811d` (9 total). Full test
  suite: **2009 passed / 7 skipped** (was 2005/7 right before this fix wave; 1987/7 before this
  branch started). The two guardrail tests that must never silently break stayed green throughout.
  The four things fixed: (1) the gather instructions told the robot to run HuggingNews through a
  generic search step that this feature isn't supposed to use yet — one sentence now carves out
  HuggingNews so it only uses its intended leads-first path; (2) a record of "we had to fall back to
  a HuggingNews summary because every source link was dead" had nowhere to be saved — fixed by
  adding it to the coordinator's existing after-the-fact note-taking step, the same way an existing
  similar record already works, rather than touching the core program logic (kept out of this lane's
  assigned files on purpose); (3) the "this tool has a working API key" vs. "no key, running in
  limited mode" flag only showed up in a human-readable log line, never in the machine-readable
  status file that every automated preflight check actually reads — fixed so that flag now appears
  in both places; (4) one of the safety-check files had accidentally started depending on a heavier
  code library, which would make it crash on a bare-bones computer that only has plain Python — fixed
  by moving the small piece of logic it needed into the safety-check file itself, so it works
  standalone again. None of these fixes touched the frozen scoring/eval files this branch was never
  allowed to touch. Full detail, including known small loose ends left on purpose (harmless,
  documented) and the things nobody has proven yet against the real live service (also documented,
  not assumed true): `.superpowers/handoffs/f106-huggingnews-DONE.md`.
