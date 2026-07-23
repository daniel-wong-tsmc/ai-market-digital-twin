# F101 Phase B — The Daily Narrator (gated lane)

**Date:** 2026-07-23
**Status:** Spec (brainstormed interactively; all decisions interactive user picks — zero AFK)
**Parent:** `docs/superpowers/specs/2026-07-22-f101-narrative-page-design.md` §4, §10.2
**Scope:** one new run-cycle step + one new tool-less brain prompt + deterministic gates +
renderer switch from the Phase A assembler to the narrator artifact. **THE GATED LANE:**
F6 pin fires by design (new emitted prompt); F83 fingerprint + `EXPECTED_STEPS` re-record
(new step). No other prompt-affecting lane may be active while this is open.

## 1. Goal

Replace the Phase A machine-stitched story with a genuinely narrated daily entry: the agent
writes the day's story as structured scenes, with continuity against previous entries, driving
the KPI band picks and related-coverage rows that were static stand-ins in Phase A.

## 2. Decisions (interactive, this session)

| Decision | Pick |
|---|---|
| Narrator memory | **Sees recent entries** — yesterday's full story artifact + last 7 headlines |
| Gate-failure behavior | **Fall back to the Phase A assembler** for that day's build; logged; retry next cycle |
| Eval treatment | **Gates + pin only** — register the prompt in the F6 hash pin; deterministic gates carry quality; NO scored eval bar |
| Dispatch shape | Single-dispatch narrator (one brain call + one retry), matching all existing brains — over two-stage outline/write and over folding into the implication brain (rejected: touches a frozen evaluated seam) |

## 3. Artifact contract

Path: `store/<category>/story/YYYY-MM-DD.json` (append-only per day; a re-run same day
overwrites its own date only). Shape = the Phase A `build_story_model` output contract
(headline, deck, dateline, gap callouts, kpis.picks, scenes[], evidence claim links), i.e.:

- `headline: str` — plain newspaper English, answers the one question for today
- `deck: str` — one-line why
- `scenes: [{n, title, paragraphs[], visual: {kind, seriesId|chartRef, label}, claimFindingIds[],
  sourceLine, relatedDocs: [{url, title, outlet, date}]}]` — 2–5 scenes; last is forward-looking
- `kpiPicks: [{indicatorId, whyCaption, scene}]` — one per scene; anchored gauge NOT included
  (the renderer always adds `gpuRentalOnDemand` itself)
- `calloutMonths: [{monthKey, text, scene}]` — ≤2, for the gap chart
- `narratorMeta: {model, promptHash, retries, fellBack: bool, wroteAt}`

The renderer gains a reader (`story_model.read_story_artifact`) that maps this artifact onto the
exact model dict Phase A's assembler produces — the renderer itself does not change. If no
artifact exists for the build date (or `fellBack`), the Phase A assembler runs unchanged.

## 4. The narrator step

Position: run-cycle step between **implication** and **site build**. Tool-less brain
(behavioral enforcement via explicit no-tool prompt, `model: opus` pinned — same precedent as
extract/judge/thesis/implication; deterministic gates are the backstop).

**Inputs (assembled by the step, passed in the prompt):**
1. Today's scorecard (ratings, categoryStatus, demandSupply), today's findings (id, statement,
   evidence source/date/tier/url), implication lines, series latest values + 8-point tails
   (the KPI candidate pool, with plain-language labels from the Phase A chip table).
2. **Memory:** yesterday's story artifact (full) + the last 7 days' headlines (date + headline).
3. The day's gathered corpus doc list (url, title, source, date) — the ONLY pool related
   coverage may cite.

**Prompt editorial rules (verbatim from the parent spec §3.4, plus):** the story answers only
"why isn't supply catching up — and what would change that"; a scene that doesn't change the
reader's understanding of the gap doesn't run; 2–5 scenes; the last scene is always
forward-looking; plain newspaper English (banned-word list included in the prompt); every claim
must cite finding ids from the provided list; related coverage only from the provided doc list;
continuity is welcome ("the squeeze we flagged Tuesday eased") but every carried-forward claim
must still cite a finding from TODAY's list; quiet days may run 2 scenes and say plainly that
little changed.

## 5. Gates (deterministic, pre-acceptance)

1. Schema validation (pydantic model of §3).
2. Every `claimFindingIds` entry exists in today's store; empty claim lists are allowed only
   with `sourceLine` = the no-source wording (Phase A review finding #1 precedent: a claim with
   no sources says so — never borrows).
3. Every `relatedDocs.url` ∈ the day's corpus doc list; https only.
4. Banned-word lint = Phase A `lint_story_copy` applied to all prose fields.
5. Scene count 2–5; per-scene `sourceLine` present; `kpiPicks` ids resolve to series with data;
   `calloutMonths` keys exist in the gap window.
6. One retry with the gate's rejection reasons appended; second failure → **fallback** (§6).

## 6. Fallback

On second gate failure (or narrator dispatch error): site build proceeds with the Phase A
assembler; the cycle log records `narrator: fellBack` + the gate reasons; no third attempt.
The page stays fresh; the artifact for that date is written with `fellBack: true` and no scenes
(so the archive shows the gap honestly). Next cycle retries normally.

## 7. Gate crossings (their own plan tasks, by the book)

- **F6:** the narrator prompt joins the emitted-prompt set → pin red by design → register in
  the pin under eval-driver governance as a REGISTRATION (user decision §2: no scored bar).
  Seam-scope proof: extract/judge/thesis/implication prompts byte-identical before/after.
- **F83:** run-cycle step addition → fingerprint + `EXPECTED_STEPS` lockstep re-record.
- Scoring v1 replay pin: must stay green untouched (the narrator cannot reach scores).
- MUST-NOT-TOUCH: `scoring.py`, `report.py`, existing brains' prompts, eval fixtures,
  `registry/indicators.json`.

## 8. Testing

- Unit tests per gate (schema, id-existence, corpus-membership, lint, bounds, fallback wiring).
- Stub-brain dry-run: fixture cycle input → valid artifact → rendered page shows narrated
  scenes + dynamic picks + related rows.
- Fallback path: invalid artifact twice → assembler page renders + log entry + `fellBack` artifact.
- Contract test: artifact reader and Phase A assembler emit the same model-dict shape.
- **Live criterion (post-merge, not forced in-lane):** the first scheduled cycle after merge
  produces a narrated page with `fellBack: false` (F98 criterion-6 precedent).

## 9. Out of scope

Story archive pages + Explore sub-pages (Phase C); F96/F102 fixes (filed separately, `75c775e`);
deploy (user-directed: after Phase B lands, rebuild `site/` + push — one step, F100 precedent).
