# F113 Chart Researcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When no curated series fits a bullet, a same-day research step digs external sources for a published series, a deterministic verifier re-finds every number in its cited page, and only then does the chart render — labeled "found today — single source" — plus the chartless-layout, copy-variation, and source-badge render fixes.

**Architecture:** New `chart-research` CLI verb with the repo's emit/accept idiom (emit writes research prompts for the coordinator to dispatch; accept verifies candidate files and writes passing series to the quarantine store `store/<cat>/research-series/`). `export_json.py`'s preference chain becomes curated → researched → findings-fallback → none. Dashboard schema bumps to 1.1 (`noChartReason` object with `cause`; `chart.researched` flag). The curated registry gains no writers.

**Tech Stack:** Python (repo venv) + pytest; web/ React (vitest) for schema 1.1 + render fixes.

**Spec:** `docs/superpowers/specs/2026-08-06-f113-chart-researcher-design.md`.
**Precondition:** F114 MERGED (shares `gpu_agent/dashboard/bullets.py` + web bullet components).

## Global Constraints

- Lane: worktree `.worktrees/f113-chart-researcher`, branch `f113-chart-researcher`; python `../../.venv/Scripts/python`; `npm --prefix web`.
- MUST NOT TOUCH: all pinned prompts (incl. `gpu_agent/narrator/prompt.py` — F114 just moved that pin; this lane may not), `gpu_agent/evals/`, `fixtures/evals/`, `fixtures/narrator/`, `gpu_agent/scoring.py`, `gpu_agent/report.py`, `registry/indicators.json`, `series-indicators.json`, `freshness.json`. **`registry/chart-series.json` gains NO writers — grep-proved in Task 7.**
- The researcher prompt (`gpu_agent/chartdata/research_prompt.py`) is NEW and UNPINNED; its quality mechanism is the verifier. It is dispatched tool-USING (WebSearch/WebFetch/agent-reach), never inline into the coordinator.
- The ONLY pin touch: F83 re-record for the new run-cycle step (Task 6, F109 precedent).
- Verifier and researcher failures never block the cycle; all-or-nothing per candidate (no partial charts).
- Tests never hit the network (`fetch_html` injectable everywhere).
- Question-stop rule verbatim (CLAUDE.md); commit per task; HEAD guard before each commit.

## File Structure

```
web/schema/dashboard.schema.json          MOD  v1.1: noChartReason object, chart.researched
gpu_agent/dashboard/bullets.py            MOD  emit cause codes; researched preference hook
gpu_agent/dashboard/export_json.py        MOD  preference chain wiring
gpu_agent/chartdata/research_prompt.py    NEW  prompt builder (emit side)
gpu_agent/chartdata/research.py           NEW  candidate model + emit/accept orchestration
gpu_agent/chartdata/verify.py             NEW  deterministic number-in-page verifier
gpu_agent/cli.py                          MOD  `chart-research` verb (emit / accept)
web/src/components/Bullets.tsx            MOD  full-width chartless layout; inline badges
web/src/components/NoChart.tsx            MOD  quiet-line vs dashed-panel modes; copy by cause
web/src/components/MiniChart.tsx          MOD  "Found today — single source:" caption prefix
tests/test_chart_research.py              NEW
tests/test_chart_verify.py                NEW
tests/test_dashboard_bullets.py           MOD  cause codes + researched preference
fixtures/chartdata/research/              NEW  candidate JSONs + saved source pages for verify tests
run-cycle skill step list + tests/test_run_cycle_conformance.py  MOD  Task 6 only
```

---

### Task 1: Dashboard schema 1.1 (both sides)

**Files:** Modify `web/schema/dashboard.schema.json`, `gpu_agent/dashboard/bullets.py` (reason emission), `web/src/` TS types + `NoChart.tsx` consumption; Tests: `tests/test_dashboard_schema.py` (extend), web contract test.

**Interfaces — Produces (consumed by every later task):**

```json
"noChartReason": {"reason": "No published number behind this yet.",
                    "cause": "no-published-number" | "estimate-only" | "too-sparse"}
"chart": { ...existing..., "researched": false }
```

- Python: `_fallback_reason(...)` in `bullets.py` already knows WHY it declined (estimate-grade vs sparse vs nothing) — read it and map each branch to a cause code; `schemaVersion` → "1.1".
- TS: `NoChartProps` becomes `{reason: string; cause: Cause}`; `splitReason` retired in favor of the structured fields.

- [ ] **Step 1: Failing tests** — schema: object-form reason validates, bare-string reason REJECTED, `cause` enum enforced, `researched` defaults allowed; Python: each `_fallback_reason` branch yields its right cause (unit tests per branch); web contract test regenerated golden validates.
- [ ] **Step 2: FAIL. Step 3: Implement both sides + regenerate `fixtures/dashboard/golden-dashboard.json`. Step 4: pytest + `npm --prefix web test` PASS. Step 5: Commit** `feat(f113): dashboard schema 1.1 — structured no-chart causes`.

---

### Task 2: Render fixes (chartless layout, varied copy, inline badges)

**Files:** Modify `web/src/components/Bullets.tsx`, `NoChart.tsx`; Tests: `web/src/__tests__/bullets.test.tsx`.

Rules (from spec §6, mock remains the token/type authority):
1. If EVERY bullet is chartless → each bullet's text spans full width; the reason renders as ONE quiet grey line under the text (`class="nochart-quiet"`), no dashed box anywhere.
2. Mixed state → charted bullets keep the chart column; chartless ones keep the dashed panel (the omission is meaningful next to real charts).
3. Copy varies by cause — exact strings:
   - `no-published-number`: "No published number behind this yet."
   - `estimate-only`: "The only number we hold is our own estimate, so we don't draw it."
   - `too-sparse`: "Too few published readings yet to draw honestly."
   The payload `reason` string may add specifics; the cause line is the lead. If two chartless bullets share a cause, the second renders the payload `reason` sentence instead of repeating the cause line verbatim.
4. `SourceMark` renders inline, immediately after the final character of the sentence (superscript), never wrapped alone to a new line: render it inside the last text node's span (`white-space: nowrap` on the last word + marker pair).

- [ ] **Step 1: Failing tests** — all-chartless payload: no `.nochart-panel` in the DOM, three `.nochart-quiet` lines, three distinct strings; mixed payload: dashed panel present only on the chartless bullet; badge is a sibling inside the sentence-end span (assert DOM structure), not after a `<br>`/block.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + `npm --prefix web run build`. Step 5: Commit** `feat(f113): chartless layout, cause-varied copy, inline source badges`.

---

### Task 3: Researcher — candidate model + prompt + emit

**Files:** Create `gpu_agent/chartdata/research.py`, `research_prompt.py`; Modify `gpu_agent/cli.py`; Test `tests/test_chart_research.py`.

**Interfaces — Produces:**

```python
class CandidatePoint(BaseModel):   # extra="forbid"
    label: str; value: float; sourceUrl: str; publishedAt: str
class CandidateSeries(BaseModel):
    seriesName: str; unit: str; form: str            # columns|bars|line
    sourceName: str; points: list[CandidatePoint]    # >= 3 unless pair=True
    pair: bool = False                                # supply-vs-demand two-series case
    notes: str = ""

def build_research_prompt(bullet: dict, findings: list[dict]) -> str
    # bullet text + its findings' statements/urls as context; rules from spec §3 verbatim:
    # published numbers only; per-point URL; >=3 points or a labeled comparison pair;
    # no estimates as fact; give up honestly (output the literal token NO-SERIES-FOUND).

def emit_research(category_id: str, store_dir: str, work_dir: str) -> list[Path]
    # builds dashboard bullets via build_bullets(), writes one prompt file per CHARTLESS
    # bullet to work/<cycle>/chart-research/bullet-<n>-prompt.txt, returns paths.
```

CLI: `chart-research emit --category chips.merchant-gpu --work work/daily-<date>` → prints the prompt paths as JSON (the run-cycle skill dispatches a tool-USING agent per prompt; answers land as `work/<cycle>/chart-research/bullet-<n>.json`).

- [ ] **Step 1: Failing tests** — emit on a fixture day with 3 chartless bullets writes 3 prompt files, each containing that bullet's text and at least one finding URL, and containing the literal strings "published" and "NO-SERIES-FOUND"; a day whose bullet has a curated chart emits NO prompt for it; CandidateSeries rejects 2 points when `pair` is false.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `feat(f113): chart-research emit — candidate model + prompts`.

---

### Task 4: Verifier + quarantine store (accept)

**Files:** Create `gpu_agent/chartdata/verify.py`; extend `gpu_agent/cli.py` (`chart-research accept`); Test `tests/test_chart_verify.py`; Fixtures: `fixtures/chartdata/research/` — 2 candidate JSONs + 2 saved HTML pages (one where every number appears, one where a point's number is absent).

**Interfaces — Produces:**

```python
def verify_candidate(cand: CandidateSeries, fetch_html: Callable[[str], str]) -> tuple[bool, list[str]]
    # For each point: fetch its sourceUrl, strip tags, and re-find `value` in the text
    # using the SAME tolerance rules as the citation audit — read gpu_agent/citation_audit.py
    # and IMPORT its number-matching helper (do not re-implement tolerance). Any miss ->
    # (False, ["point 3: 6.7 not found at <url>"]). All-or-nothing.

def accept_research(category_id: str, store_dir: str, work_dir: str,
                     fetch_html=None) -> dict
    # {'accepted': [paths], 'rejected': [{file, failures}], 'missing': [...]}
    # Passing candidates -> store/<cat>/research-series/<storyDate>-<slug(seriesName)>.json
    # (append-only: refuse to overwrite an existing file — collision = reject with message).
    # NEVER raises out; exit code 0 always.
```

- [ ] **Step 1: Failing tests** — good candidate + matching page → accepted, quarantine file written with the candidate verbatim plus `{"verifiedAt-free": stable}` — NO wall-clock field (byte-stable reruns; the story date IS the time stamp); bad candidate → rejected with the point named, nothing written; `fetch_html` raising → rejected as unreachable, cycle-safe; overwrite attempt → rejected; a `NO-SERIES-FOUND` answer file → counted under `missing`, not an error.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite. Step 5: Commit** `feat(f113): chart-research verifier + quarantine store`.

---

### Task 5: Exporter preference chain + researched rendering

**Files:** Modify `gpu_agent/dashboard/bullets.py`, `export_json.py`, `web/src/components/MiniChart.tsx`; Tests: extend `tests/test_dashboard_bullets.py`, `web/src/__tests__/bullets.test.tsx`.

**Interfaces:** In `build_bullets`, between the curated match and the findings fallback: look for `store/<cat>/research-series/<storyDate>-*.json` whose `seriesName` slug matches this bullet index's accepted candidate (the accept step records `bulletIndex` in the quarantine file — add it to the model in Task 3 if missing; keep `extra="forbid"` satisfied). Researched chart payload = candidate points mapped to the existing chart shape + `"researched": true`; caption = `"Found today — single source: <sourceName>."`; per-point `sourceUrl` carried through. Web: `MiniChart` renders the caption prefix from `researched` (string comes from the payload caption — web adds no copy).

- [ ] **Step 1: Failing tests** — Python: bullet with no curated match but an accepted quarantine file for its index → researched chart, `researched: true`, findings fallback NOT consulted; no quarantine file → old behavior byte-identical (golden); quarantine file for a DIFFERENT storyDate ignored. Web: researched chart shows the caption and a source link; non-researched charts unchanged.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: pytest + npm test + build PASS. Step 5: Commit** `feat(f113): researched charts render with found-today label`.

---

### Task 6: Run-cycle step + F83 re-record (THE ONLY PIN TOUCH)

**Files:** Modify the run-cycle skill's step list + `tests/test_run_cycle_conformance.py` (F109/F110 precedent — find the F110 diff that added `chart-fetch`/`dashboard-json` and mirror it).

Step inserted AFTER the narrator/citation-audit steps, BEFORE `dashboard-json`:
`chart-research` — emit prompts for chartless bullets; dispatch one tool-USING research agent per prompt (max 3); `accept` verifies and stores; failures logged, never blocking.

- [ ] **Step 1:** Conformance test green BEFORE (baseline). **Step 2:** Add the step + `EXPECTED_STEPS` entry; regenerate the fingerprint FROM `EXPECTED_STEPS`. **Step 3:** Full suite green; `git status` shows no `fixtures/` change. **Step 4: Commit** `feat(f113): chart-research run-cycle step (F83 re-record, F109 precedent)`.

---

### Task 7: Lane gates + DONE sentinel

- [ ] **Step 1:** Full pytest + `npm --prefix web test` + `npm --prefix web run build` green; four pins green (narrator pin at its F114 hash, untouched by this lane — verify `git diff main --name-only -- fixtures/narrator gpu_agent/narrator` EMPTY).
- [ ] **Step 2:** Registry trust proof: `grep -rn "chart-series.json" gpu_agent/ | grep -v registry.py` shows READ paths only — no writer exists; assert in a test (`tests/test_chart_research.py::test_no_registry_writers` greps the package source for `chart-series.json` near `open(...,"w")`/`write_text` — belt and suspenders).
- [ ] **Step 3:** Forbidden diff empty over the Global Constraints list.
- [ ] **Step 4:** Built-page click-through from disk (all-chartless day payload + a researched-chart payload): quiet lines, dashed panel in mixed state, inline badges, found-today caption with working link. Fix before declaring done.
- [ ] **Step 5:** Write `.superpowers/handoffs/f113-chart-researcher-DONE.md` (state, deferred minors, spec §10 live criteria). Commit. **STOP — only the user merges.**

## Self-Review Notes

- Spec §3 → Task 3; §4 → Task 4; §6 render fixes → Task 2 (+ Task 5 label); §7 schema → Task 1; §8 guardrails → Global Constraints + Task 7 proofs; §10 criteria → sentinel.
- `bulletIndex` on the quarantine file is defined in Task 3's model (Task 5 consumes it) — flagged in both places so the implementers stay consistent.
- The verifier IMPORTS the citation audit's tolerance helper rather than re-implementing (single source of numeric truth); if that helper turns out not to be importable cleanly, QUESTION-STOP (extracting it would touch `citation_audit.py`, fine, but it's a shared-code decision worth surfacing).
