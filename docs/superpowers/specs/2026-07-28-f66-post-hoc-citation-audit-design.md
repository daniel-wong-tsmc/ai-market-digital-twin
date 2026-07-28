# F66 — Post-hoc citation audit pass (design)

**Status: DRAFT — BLOCKED ON USER DECISIONS.** Five design forks are parked in
`.superpowers/handoffs/f66-citation-audit-QUESTIONS.md` (Q1–Q5). Everything below the
"Open decisions" section is investigation and evidence, which stands regardless of how the
forks resolve. The build shape (§6) is written against the lane's *recommended* picks and
must be re-read after the user answers.

Lane: `f66-citation-audit`, branch `f66-citation-audit`, worktree `.worktrees/f66-citation-audit`.
Priority: LOW (backlog says "do after the higher items"). Design-stage only for this dispatch.
Related: F61 (render surface — a separate lane owns it; nothing here modifies shared files),
F81 (model-diversity pool — the backlog names F66's audit subagent as F81's "early cheap slice"),
F83 (run-cycle conformance pin — adding a step costs a re-record; see §5).

---

## 1. The claim under audit

Backlog F66: citation integrity is enforced at *write* time (gates check `findingIds` and
excerpts), but nothing re-verifies the *finished* brief's claims against the findings they
cite.

That claim is correct, and the investigation below makes it precise: every existing gate is a
**referential-integrity** check ("does this id resolve?"), never a **support** check ("does
this finding actually say that?").

## 2. What write-time gating already covers

Eight gates touch citations. Verified file:line, all deterministic Python unless noted.

| # | Gate | Where | What it actually checks | On failure |
|---|---|---|---|---|
| 1 | Extraction | `gpu_agent/extraction/extractor.py:134-138` | `evidence[].excerpt` is a whitespace-folded **substring of the source document**; `evidence[].url == doc.url`; price unit matches registry; `value.number` finite | per-finding silent drop into `ExtractionOutcome.dropped` |
| 2 | `check_finding` | `gpu_agent/gate.py:16-64` | kind/value coherence; measured/observed need evidence (F2a); F2e distinct-publisher minimum via `publisher.collapsed_publisher_set` (netloc collapse + `content_hash(excerpt)` reprint collapse); ISO dates, no future-dated evidence; impact targets in taxonomy | drop or `GateError` |
| 3 | Scorecard | `gpu_agent/gate.py:78-96` | `dimensionRatings[d].findingIds` non-empty and every id resolves in `sc.findings`; rating within `_ANCHOR_TOL = 0.15` of the code-computed anchor; self-reference ban | `GateError` → hard block, nothing written |
| 4 | Judge conflicts | `gpu_agent/judgment/judge.py:109-129` | every cited id is in that dimension's indicator group (`briefing.grouped[dim]`) — the only *relevance* check anywhere, and it is pure indicator→dimension routing; confidence ceiling from cited findings; gate backstop | resample up to 3, then `JudgmentError` → exit 1 |
| 5 | F63 sufficiency | `gpu_agent/sufficiency.py:24-36, 74-97` | when a rating or bottleneck **changes**, the union of cited findings' evidence must contain a primary tier or ≥ N distinct publishers | hard block, exit 1 |
| 6 | Thesis | `gpu_agent/thesis.py:373-382` | `findingIds` non-empty + all resolve. That is the entire citation check | `THESIS GATE FAILED`, exit 1 |
| 7 | Implication | `gpu_agent/implication.py:184-218` | ≥1 id cited **across** `dimensions`/`thesisIds`/`findingIds` (an OR — a line citing only a dimension name and zero findings passes); each findingId resolves; prose lint; recommendation-verb ban | exit 1 |
| 8 | Narrator | `gpu_agent/narrator/gate.py:54-249` | every `claimFindingIds` entry resolves; a scene citing nothing must carry `sourceLine == NO_SOURCE_LINE`; `relatedDocs[].url` in the doc pool and `outlet` string-equals the pooled `source`; banned-word lint; scene count/order; **Check 7 (`gate.py:228-247`)**: if all a scene's cited findings are below `AGING_THRESHOLD` freshness, the paragraphs must contain *some* date token | re-dispatch brain once, then hard block |

**One existing precedent ties prose numbers to evidence** — the F14 wiki enrichment gate,
`gpu_agent/wiki/ingest.py:89-152`. It parses inline `[findingId]` markers, extracts numeric
tokens from the body (`_numeric_tokens`, ≥2 digits after comma-stripping), builds an allowed
set from the cited findings' `statement`, `why`, `value.number` in four renderings, evidence
`excerpt` and `date`, and raises `EnrichmentGateError` on an "uncited number". It hard-blocks
before any write. Grep confirms `_numeric_tokens` and "uncited number" exist **only** there.

The eval rubric names the concern but only scores it, never gates it:
`gpu_agent/evals/rubric.py:33, 46, 55, 85-87` ("one claim outruns its citation").
`gpu_agent/evals/cases.py:57` has `citationsResolve: bool = True` — resolution only.

## 3. The genuine residual risk

Three gaps, in descending order of how much they matter to a reader.

**(a) No claim ever gets checked for semantic support.** Scorecard `rationale`, thesis
`statement`/`mechanism`, implication `watchItem`, and every narrator `paragraph`, `headline`,
`deck`, and `whyCaption` are compared to the cited findings' *ids* and nothing else. A brain can
cite a real, correctly-routed, correctly-sourced finding and write a sentence that finding does
not support, and every gate passes.

**(b) Prose numbers are unconstrained outside the wiki.** The story page — the site front page —
is the densest numeric surface the agent produces, and it is the one with zero numeric checks.
Sample from `store/chips.merchant-gpu/story/2026-07-27.json` scene 1: `$49.24`, `$68.80`,
`$2.99`, `$7.39`, `$18.77`, `42 percent`, `11 percent`. Scene 2: `52 to 78 weeks`, `25 percent`,
`32 to more than 40 weeks`, `90 percent`. None of these is verified today.

**(c) The narrator brain cannot even see what it is citing.**
`gpu_agent/narrator/inputs.py:26-44` (`_finding_trim`) hands the brain
`{id, statement, evidence:[{source,url,date,tier}], freshnessWeight}` — **`excerpt`, `value`,
`why`, and `impact` are stripped**. So scene prose is written against `statement` alone, and
the gate has no quote to compare prose against even in principle. (The audit does not have this
limitation: it can read the full findings from `store/findings/<id>.json`.)

Secondary, found in passing and worth a separate backlog line rather than folding into F66:
`brief_render.py:251, 299` link to `appendix.html#f-<id>` and `#dim-<name>`, and
`site_render.render_appendix` (`site_render.py:303-326`) emits neither anchor — dead fragments
that `check_links` (`site_build.py:137-140`) does not validate. There is no HTML citation map at
all; `report.render_citation_map` (`report.py:767-784`) exists only in the text report.

## 4. Evidence: how much would a deterministic numeric audit actually catch?

Measured, not estimated. Probe: for each scene in the last three live story artifacts, build the
allowed numeric-token set from the scene's `claimFindingIds` (resolved out of `store/findings/`)
using the wiki gate's own `_numeric_tokens`, then diff against the tokens in the scene prose.

| Day | Numeric tokens in prose | Flagged, wide pool | Flagged, statement-only pool |
|---|---|---|---|
| 2026-07-25 | 18 | 0 | 0 |
| 2026-07-26 | 29 | 1 | 5 |
| 2026-07-27 | 33 | 0 | 2 |
| **total** | **80** | **1** | **7** |

"Wide pool" = `statement` + `why` + `value.number` (4 renderings) + evidence `excerpt` + evidence
`date`. "Statement-only" = `statement` + `value.number`; its extra flags are `22`/`23`, i.e.
day-of-month tokens that live in evidence `date`. **Conclusion: the pool must be the wide one.**

The single wide-pool flag is a **false positive from legitimate rounding**. Story 2026-07-26
scene 2 says "SK Hynix's board approved 7.09 trillion won"; finding
`www-ad-hoc-news-de-94ca546c-2026-07-1` says `7.0931 trillion won` in both `statement` and
`excerpt`. Exact set membership, which is what the wiki gate does, calls that uncited.

Two consequences for the design:

1. A numeric audit over exec prose **must be rounding-tolerant** — the wiki gate's exact-token
   rule is right for a wiki body that quotes figures verbatim, and wrong for prose deliberately
   written for a non-technical reader, which rounds by policy.
2. With rounding tolerance the measured yield over three live cycles is **0 findings out of 80
   numeric claims**. That is not an argument against building it — it is a tripwire, and its
   value is the day it fires — but it is a strong argument about *severity* (Q2): a check with
   no observed true positives and a demonstrated false-positive mode should not be the thing
   that stops a cycle on its last step.

Reproduce: `work/f66/probe.py` and `work/f66/probe2.py` in the root checkout (gitignored `work/`).

## 5. Where an audit can slot in, and what it costs

Run-cycle steps (`.claude/skills/run-cycle/SKILL.md`, `## Procedure`), abbreviated:

```
3(b) extract  3(c) judge  3(d) pipeline/score+store  3(d2) wiki write-back
3(e) thesis   3(e2) implication   3(e3) narrator → store/<cat>/story/<date>.json
3(f) render executive report (text, stdout)
6 cycle log   7 price-sync   8 report + `gpu-agent site` → site/
```

Three candidate seams:

- **3(e4), right after the narrator** — the audit reads the story artifact + implication
  artifact + `store/findings/`, i.e. everything it needs, and a failure is *actionable*: the
  session can re-dispatch the narrator, exactly as narrator-gate check-7 failures already do.
- **Step 9, after `gpu-agent site`** — sees the rendered HTML too, but the site is already built
  and the cycle log already finalized, so a failure is expensive to act on.
- **No run-cycle step** — a standalone `gpu-agent audit-citations` verb run ad hoc. Zero F83
  cost, and near-zero value: an audit nobody runs is not an audit.

**F83 cost, either way a step is added** (flag it, do not do it in this lane): three edits in
lockstep — the `## Procedure` block in `.claude/skills/run-cycle/SKILL.md`, the `EXPECTED_STEPS`
tuple at `tests/test_run_cycle_conformance.py:159-179`, and the regenerated
`run-cycle-step-fingerprint: sha256=…` comment at `SKILL.md:52`. Two tests go red until all
three match (`:343-348`, `:351-357`). The pinned ordering assertion
`test_gate_order_in_prescription` (`:281`) requires `extraction < judgment < thesis < render`;
a 3(e4) sub-step does not violate it. Sub-steps must be written as a bolded `**(e4) Title…` at
line start to be parsed (`:136`).

**F6 eval-pin cost: zero, if the lane touches no brain prompt.** The pin covers exactly
`("extract", "judge", "thesis", "implication")` — `gpu_agent/evals/prompt_hash.py:15`,
asserted at `tests/test_evals_baseline_pin.py:31-33`. The **narrator prompt is not pinned**, so
narrator-side changes are free; any change to the judge or implication prompt is not.

**Dispatch seam for a tool-less audit subagent** — the repo's existing convention, unchanged:
a CLI verb emits `--emit-prompt` JSON, the session dispatches a tool-less Opus subagent with
`model: "opus"` stated explicitly, pastes the answer into `<work>/…-answer.json`, and the same
verb ingests it with `--recorded`. Count mismatches exit 2 loudly
(`cli.py:337-341`, `485-489`). An audit subagent would be `audit --emit-prompt` /
`audit --recorded`, following `narrator` (`cli.py:695-760`) most closely.

## 6. Proposed shape (contingent on Q1–Q5)

Written against the lane's recommended picks. Re-read after the user answers.

**Phase 1 — deterministic numeric audit (`gpu_agent/audit.py`, new, ~150 lines).**

- Input: category + `asOf`. Reads `store/<cat>/story/<date>.json` and
  `store/implications/<cat>/<date>.json`; resolves ids from `store/findings/<id>.json`.
- Unit of audit: a `(claimKey, text, findingIds)` triple. `claimKey` is `scene:<n>` for story
  scenes (matching `story_model.py:637`'s existing evidence-map key) and `impl:<i>` for
  implication lines.
- Allowed pool per claim: wide pool as validated in §4 — `statement`, `why`, `value.number` in
  the four renderings the wiki gate already uses (`ingest.py:127-129`), evidence `excerpt`,
  evidence `date` — unioned over the claim's cited findings, plus the story artifact's own
  KPI/series values (the front page quotes computed medians that live in no finding).
- Match rule: a prose token is supported if it equals an allowed token **or** equals an allowed
  token rounded to the prose token's own decimal precision (`7.0931` supports `7.09`).
  Tokenizer reused from `wiki/ingest.py:97-105` — factored out to a shared home, not copied.
- Output: `store/<cat>/audit/<date>.json` — `{schemaVersion, categoryId, asOf, claims:[{claimKey,
  verdict, flaggedTokens, citedFindingIds}], summary:{claimsAudited, flagged}}`.

**Phase 2 — tool-less audit subagent, advisory.** `audit --emit-prompt` builds one prompt per
claim: the claim text, and the *full* cited findings including `excerpt` (which the narrator
brain never sees, per §3c). The subagent returns `supported | unsupported | overstated` plus a
one-sentence reason, no tools, no browsing, judging only against the supplied text. Verdicts
merge into the same audit artifact. Whether Phase 2 ships in this lane or rides F81's
model-diversity pool is **Q4**.

**Surfacing.** The audit artifact is written every cycle; a non-empty `flagged` list prints a
loud session-visible block and lands in the cycle-log entry. Whether it also blocks is **Q2**.

**Tests.** Unit tests over synthetic claim/finding pairs (exact match, rounding match, genuine
miss, unresolvable id, zero-citation scene); a replay test over the three live story artifacts
in §4 asserting the measured counts; no new eval baseline.

**Explicitly out of scope:** modifying `narrator/inputs.py` to pass excerpts to the brain
(see Q5); the dead `appendix.html#f-<id>` anchors and the missing HTML citation map (separate
backlog line); anything F61 owns.

## 7. Open decisions (blocking)

Full text with recommendations in `.superpowers/handoffs/f66-citation-audit-QUESTIONS.md`.

- **Q1 — audit scope.** Story scenes only / + implication lines / + dimension rationales + theses.
  Lane recommends: story scenes + implication lines.
- **Q2 — failure mode.** Block the cycle / annotate + loud log / silent artifact.
  Lane recommends: deterministic numeric flags block (wiki precedent), subagent verdicts annotate.
- **Q3 — run-cycle placement.** Sub-step 3(e4) after narrator / Step 9 after site / no step.
  Lane recommends: 3(e4), and accept the F83 re-record.
- **Q4 — phasing.** Deterministic only for now / both phases in this lane / Phase 2 deferred to F81.
  Lane recommends: build Phase 1, defer Phase 2 to ride F81.
- **Q5 — rounding tolerance + series-derived numbers.** Lane recommends: round-to-prose-precision
  equality, and add story KPI/series values to the allowed pool. Also asks whether to widen
  `narrator/inputs.py` to give the brain excerpts (recommends: no, out of scope).

## 8. Decision provenance

- Every substantive pick above is **lane-recommended, not decided** — parked as Q1–Q5.
- Mechanical choices made without asking: reusing `wiki/ingest.py`'s `_numeric_tokens`
  tokenizer rather than writing a second one; keying claims as `scene:<n>` to match the
  existing evidence-map key at `story_model.py:637`; artifact path
  `store/<cat>/audit/<date>.json` mirroring the story artifact's layout.
- No AFK-default decisions were taken. No code was written. No shared file was modified.
- Empirical numbers in §4 are from the lane's own probe over live artifacts, not estimates.
