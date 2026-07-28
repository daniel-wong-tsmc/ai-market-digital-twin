# F66 — Post-hoc citation audit pass (design)

**Status: FINAL — decisions taken 2026-07-28 (interactive, user-approved; see §8).**
Implementation plan: `docs/superpowers/plans/2026-07-28-f66-citation-audit.md` (5 tasks).
Build NOT started — dispatched separately (F61 and F105 lanes run concurrently and the
F83/F6 gating rules limit concurrent step-touching lanes).

Lane: `f66-citation-audit`, branch `f66-citation-audit`, worktree `.worktrees/f66-citation-audit`.
Priority: LOW (backlog says "do after the higher items").
Related: F61 (render surface — a separate lane owns it; nothing here modifies shared files),
F81 (model-diversity pool — Phase 2 is deferred to ride it; the backlog already names F66's audit
subagent as F81's "early cheap slice"), F83 (run-cycle conformance pin — one task pays the
re-record, §5), F14 (`wiki/ingest.py`'s uncited-number gate — the precedent this reuses).

---

## 1. The claim under audit

Backlog F66: citation integrity is enforced at *write* time (gates check `findingIds` and
excerpts), but nothing re-verifies the *finished* brief's claims against the findings they cite.

That claim is correct, and the investigation below makes it precise: every existing gate is a
**referential-integrity** check ("does this id resolve?"), never a **support** check ("does this
finding actually say that?").

## 2. What write-time gating already covers

Eight gates touch citations. Verified file:line, all deterministic Python.

| # | Gate | Where | What it actually checks | On failure |
|---|---|---|---|---|
| 1 | Extraction | `gpu_agent/extraction/extractor.py:134-138` | `evidence[].excerpt` is a whitespace-folded **substring of the source document**; `evidence[].url == doc.url`; price unit matches registry; `value.number` finite | per-finding silent drop into `ExtractionOutcome.dropped` |
| 2 | `check_finding` | `gpu_agent/gate.py:16-64` | kind/value coherence; measured/observed need evidence (F2a); F2e distinct-publisher minimum via `publisher.collapsed_publisher_set` (netloc collapse + `content_hash(excerpt)` reprint collapse); ISO dates, no future-dated evidence; impact targets in taxonomy | drop or `GateError` |
| 3 | Scorecard | `gpu_agent/gate.py:78-96` | `dimensionRatings[d].findingIds` non-empty and every id resolves in `sc.findings`; rating within `_ANCHOR_TOL = 0.15` of the code-computed anchor; self-reference ban | `GateError` → hard block, nothing written |
| 4 | Judge conflicts | `gpu_agent/judgment/judge.py:109-129` | every cited id is in that dimension's indicator group (`briefing.grouped[dim]`) — the only *relevance* check anywhere, and it is pure indicator→dimension routing; confidence ceiling from cited findings; gate backstop | resample up to 3, then `JudgmentError` → exit 1 |
| 5 | F63 sufficiency | `gpu_agent/sufficiency.py:24-36, 74-97` | when a rating or bottleneck **changes**, the union of cited findings' evidence must contain a primary tier or ≥ N distinct publishers | hard block, exit 1 |
| 6 | Thesis | `gpu_agent/thesis.py:373-382` | `findingIds` non-empty + all resolve. That is the entire citation check | `THESIS GATE FAILED`, exit 1 |
| 7 | Implication | `gpu_agent/implication.py:184-218` | ≥1 id cited **across** `dimensions`/`thesisIds`/`findingIds` (an OR — a line citing only a dimension name and zero findings passes); each findingId resolves; prose lint; recommendation-verb ban | exit 1 |
| 8 | Narrator | `gpu_agent/narrator/gate.py:54-249` | every `claimFindingIds` entry resolves; a scene citing nothing must carry `sourceLine == NO_SOURCE_LINE`; `relatedDocs[].url` in the doc pool and `outlet` string-equals the pooled `source`; banned-word lint; scene count/order; **Check 7 (`gate.py:228-247`)**: if all a scene's cited findings are below `AGING_THRESHOLD` freshness, the paragraphs must contain *some* date token | re-dispatch brain once, then honest-gap fallback |

**One existing precedent ties prose numbers to evidence** — the F14 wiki enrichment gate,
`gpu_agent/wiki/ingest.py:89-152`. It parses inline `[findingId]` markers, extracts numeric tokens
from the body (`_numeric_tokens` @:97-105, ≥2 digits after comma-stripping), builds an allowed set
from the cited findings' `statement`, `why`, `value.number` in four renderings (`str(v)`, `repr(v)`,
`f"{v:g}"`, and `str(int(v))` when integral), evidence `excerpt` and `date`, then raises
`EnrichmentGateError` on an "uncited number". It hard-blocks before any write. Grep confirms
`_numeric_tokens` and "uncited number" exist **only** there.

The eval rubric names the concern but only scores it, never gates it:
`gpu_agent/evals/rubric.py:33, 46, 55, 85-87` ("one claim outruns its citation").
`gpu_agent/evals/cases.py:57` has `citationsResolve: bool = True` — resolution only.

## 3. The genuine residual risk

**(a) No claim ever gets checked for semantic support.** Scorecard `rationale`, thesis
`statement`/`mechanism`, implication `watchItem`, and every narrator `paragraph`, `headline`,
`deck`, and `whyCaption` are compared to the cited findings' *ids* and nothing else. A brain can
cite a real, correctly-routed, correctly-sourced finding and write a sentence that finding does not
support, and every gate passes.

**(b) Prose numbers are unconstrained outside the wiki.** The story page — the site front page — is
the densest numeric surface the agent produces, and it is the one with zero numeric checks. Sample
from `store/chips.merchant-gpu/story/2026-07-27.json` scene 1: `$49.24`, `$68.80`, `$2.99`, `$7.39`,
`$18.77`, `42 percent`, `11 percent`. Scene 2: `52 to 78 weeks`, `25 percent`, `32 to more than 40
weeks`, `90 percent`. None of these is verified today.

**(c) The narrator brain cannot even see what it is citing.**
`gpu_agent/narrator/inputs.py:26-44` (`_finding_trim`) hands the brain
`{id, statement, evidence:[{source,url,date,tier}], freshnessWeight}` — **`excerpt`, `value`, `why`,
and `impact` are stripped**. So scene prose is written against `statement` alone, and the gate has
no quote to compare prose against even in principle. The audit does not share this limitation: it
reads full findings from `store/findings/<id>.json`.

Secondary, found in passing, **deliberately out of scope** — belongs in its own backlog line:
`brief_render.py:251, 299` link to `appendix.html#f-<id>` and `#dim-<name>`, and
`site_render.render_appendix` (`site_render.py:303-326`) emits neither anchor — dead fragments that
`check_links` (`site_build.py:137-140`) does not validate. There is no HTML citation map at all;
`report.render_citation_map` (`report.py:767-784`) exists only in the text report. The render layer
also silently truncates citations (`deepdive_model.py:77` keeps 5; `brief_render.py:251` links 1;
`story_model.py:592, 614, 625` cap by publisher), so a cited finding can vanish from the page.

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

The single wide-pool flag is a **false positive from legitimate rounding**. Story 2026-07-26 scene 2
says "SK Hynix's board approved 7.09 trillion won"; finding
`www-ad-hoc-news-de-94ca546c-2026-07-1` says `7.0931 trillion won` in both `statement` and
`excerpt`. Exact set membership — what the wiki gate does — calls that uncited.

Two consequences, both carried into the design:

1. The audit **must be rounding-tolerant** (D5a). The wiki gate's exact-token rule is right for a
   wiki body that quotes figures verbatim and wrong for prose deliberately written for a
   non-technical reader, which rounds by policy.
2. With rounding tolerance the measured yield over three live cycles is **0 flags out of 80 numeric
   claims**. The user saw this and accepted it: the value of a tripwire is the day it fires.

Reproduce: `work/f66/probe.py` and `work/f66/probe2.py` in the root checkout (gitignored `work/`).

## 5. Placement, and what it costs

Run-cycle steps (`.claude/skills/run-cycle/SKILL.md`, `## Procedure`), abbreviated:

```
3(b) extract  3(c) judge  3(d) pipeline/score+store  3(d2) wiki write-back
3(e) thesis   3(e2) implication   3(e3) narrator → store/<cat>/story/<date>.json
3(f) render executive report (text, stdout)
6 cycle log   7 price-sync   8 report + `gpu-agent site` → site/
```

**D3: a new sub-step `(e4)`, immediately after the narrator and before the report render.** It runs
after both artifacts it audits exist (`(e2)` implication, `(e3)` narrator), and a failure is
*actionable* — the session re-dispatches the narrator exactly as narrator-gate failures already do.
The rejected alternatives were a Step 9 after `gpu-agent site` (sees rendered HTML, but the site is
built and the cycle log closed, so failures are expensive) and no run-cycle step at all (an audit
nobody runs is worth nothing).

**F83 cost — accepted, and it gets its own plan task (F98 precedent).** Three edits in lockstep:
the `## Procedure` block in `.claude/skills/run-cycle/SKILL.md`, the `EXPECTED_STEPS` tuple at
`tests/test_run_cycle_conformance.py:158-179` (insert `("e4", "citation audit")` between
`("e3", "narrator")` and `("f", "render the executive report")`), and the regenerated
`run-cycle-step-fingerprint: sha256=…` comment at `SKILL.md:52`. Two tests stay red until all three
agree (`:343-348`, `:351-357`). The pinned ordering assertion `test_gate_order_in_prescription`
(`:281`) requires `extraction < judgment < thesis < render`; `(e4)` does not violate it. Sub-steps
must be written as a bolded `**(e4) Title…` at line start to be parsed (`:136`).

**F6 eval-pin cost: zero.** The pin covers exactly `("extract", "judge", "thesis", "implication")`
— `gpu_agent/evals/prompt_hash.py:15`, asserted at `tests/test_evals_baseline_pin.py:31-33`. This
lane touches no brain prompt at all. (Noted for Phase 2: the **narrator prompt is not pinned**, so
narrator-side prompt work would also be free.)

## 6. The build (Phase 1 — deterministic numeric audit)

**Scope (D1): story scenes + implication lines.** Dimension `rationale` strings and thesis
statements are excluded — they sit below the fold or in the book, and auditing them would triple
the volume for surfaces the executive reader never sees.

**Module:** `gpu_agent/citation_audit.py` (new). No frozen-core file is touched.

**Unit of audit** — a `Claim(claimKey, text, findingIds)` triple:
- story scene → `claimKey = f"scene:{n}"`, matching the evidence-map key already used at
  `story_model.py:637`; `text = " ".join(scene.paragraphs)`; ids = `scene.claimFindingIds`.
- implication line → `claimKey = f"impl:{i}"`; `text = line.watchItem`; ids = `line.findingIds`.
- A claim with zero `findingIds` is **skipped, not flagged** — both gates already enforce an
  honest-empty posture there (`narrator/gate.py:74-77` requires `NO_SOURCE_LINE`;
  `implication.py:203-204` allows a dimension-only citation).

**Allowed pool** per claim, unioned over its cited findings, read from `store/findings/<id>.json`:
`statement`, `why`, `value.number` in the same four renderings the wiki gate uses
(`ingest.py:127-129`), every evidence `excerpt`, every evidence `date` — plus (D5b) the story
artifact's own KPI/series values, so the page is not flagged for quoting arithmetic we computed
ourselves (e.g. "a median of $18.77 per chip-hour", which lives in no finding). An id that does not
resolve is a violation in its own right, not a silent skip.

**Match rule (D5a):** a prose token is supported if it equals an allowed token **or** equals an
allowed token rounded to the prose token's own decimal precision — `7.0931` supports `7.09`. The
tokenizer is `wiki/ingest.py`'s `_numeric_tokens`, **factored out to a shared home and imported by
both call sites, not copied**; the wiki gate's own behaviour must stay byte-identical (it keeps
exact matching — a wiki body quotes verbatim).

**Artifact:** `store/<cat>/audit/<date>.json` —
`{schemaVersion, categoryId, asOf, claims:[{claimKey, verdict, flaggedTokens, unresolvedIds,
citedFindingIds}], summary:{claimsAudited, flagged}}`. Mirrors the story artifact's layout
(`narrator/store.py:19-20`). Needs a `.gitignore` store-whitelist entry, like `store/implications/`
before it (`implication.py:224-226`).

**CLI:** `gpu-agent audit-citations --store store --category <id> --date <today>`, modelled on the
`narrator` verb (`cli.py:1483-1496`). Exit 0 clean, non-zero with a violation block on flags.

**Severity (D2) — blocks the story artifact, not the cycle.** Numeric mismatches are a hard failure
with a re-dispatch path, matching the wiki gate. Consistency detail, agent-recommended (§8): steps
`(e2)` and `(e3)` are both explicitly *non-blocking for the cycle* — the implication step marks
`implication: failed` after two attempts and proceeds; the narrator step records the honest-gap
fallback and proceeds. `(e4)` therefore blocks **the artifact under audit**, on the same ladder:
re-dispatch the narrator once with the flagged tokens appended, and on a second failure record the
narrator honest-gap fallback and mark `citation-audit: failed` in the cycle log. It never strands a
scorecard. Reading-pass verdicts, when Phase 2 lands, annotate only.

**Phase 2 (deferred, D4):** the tool-less reading subagent — `audit-citations --emit-prompt` builds
one prompt per claim carrying the claim text and the *full* cited findings including `excerpt`
(which the narrator brain never sees, §3c); a tool-less Opus subagent returns
`supported | unsupported | overstated` plus a one-sentence reason, judging only the supplied text;
verdicts merge into the same artifact as **annotations**. Deferred to ride F81's model-diversity
pool. The artifact schema above already carries `verdict` per claim so Phase 2 needs no migration.
**The user accepted the caveat that this deferred half is where the real residual risk lives.**

**Explicitly out of scope:** widening `narrator/inputs.py` to pass excerpts to the brain (D5c);
dimension rationales and theses; the dead appendix anchors and missing HTML citation map (§3);
anything F61 owns.

## 7. Decisions of record

| # | Decision | Provenance |
|---|---|---|
| D1 | Scope = story scenes + implication lines | **user-approved** (interactive 2026-07-28) |
| D2 | Numeric mismatches block with a re-dispatch path; reading-pass verdicts annotate only | **user-approved**; the zero-true-positives caveat (§4) was shown and accepted |
| D3 | Placement = run-cycle sub-step `(e4)` right after the narrator; F83 re-record cost accepted | **user-approved** |
| D4 | Phase 1 (deterministic) now; Phase 2 (reading subagent) deferred to ride F81 | **user-approved**; "the deferred half is where the risk lives" caveat accepted |
| D5a | Rounding tolerance: round-to-prose-precision equality | agent-recommended, orchestrator-relayed — **not** individually user-approved |
| D5b | Self-computed KPI/price-series values count as supported | agent-recommended, orchestrator-relayed — **not** individually user-approved |
| D5c | Do **not** widen what the narrator brain sees | agent-recommended, orchestrator-relayed — **not** individually user-approved |
| D2′ | "Blocks" = blocks the audited artifact (re-dispatch → honest-gap fallback), not the whole cycle — the only reading consistent with `(e2)`/`(e3)` being explicitly non-blocking | agent-recommended interpretation of D2 |

## 8. Decision provenance

- D1–D4 were put to the user interactively this session and answered directly: **user-approved,
  not AFK-default.** No AFK-default decision exists in this lane.
- D5a/D5b/D5c were the lane's own recommendations and were **not individually put to the user**;
  the orchestrator relayed "proceed on your own recommendations". They are labelled
  agent-recommended/orchestrator-relayed above and must be re-surfaced if they turn out to matter.
- D2′ is the lane's interpretation of D2 against the run-cycle's existing non-blocking posture for
  steps `(e2)`/`(e3)`. It is the smallest reading that keeps D2 true without contradicting the
  skill; flagged here because it narrows what "block" means.
- Mechanical choices made without asking: reusing `wiki/ingest.py`'s `_numeric_tokens` rather than
  writing a second tokenizer; keying claims `scene:<n>` to match `story_model.py:637`; artifact path
  `store/<cat>/audit/<date>.json` mirroring the story artifact layout; CLI verb shaped after
  `narrator`.
- Empirical numbers in §4 are from the lane's own probe over live artifacts, not estimates.
- Original question text and the lane's recommendations are preserved in
  `.superpowers/handoffs/f66-citation-audit-QUESTIONS.md` (marked ANSWERED).
