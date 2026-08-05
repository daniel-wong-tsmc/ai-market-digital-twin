# F110 Dashboard Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the main category page with a verdict-led React 19 + Astryx dashboard fed by a daily `dashboard.json` that the pure-Python cycle exports, with per-bullet mini-charts from a curated series library and click-through source references on every statement.

**Architecture:** Python gains three seams — a source-reference resolver, a chart-series library (registry + fetchers + matcher), and a JSON exporter that turns existing store artifacts into `site/chips.merchant-gpu/data/dashboard.json`. A new `web/` Vite app (React 19 + Astryx) renders that JSON; its compiled output is committed and served statically. Node never runs in the daily cycle.

**Tech Stack:** Python 3 (repo venv), pytest; Vite, React 19, `@astryxdesign/core` + a theme package, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-05-dashboard-revamp-design.md`.
**Visual contract:** `docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html` — the build matches its tokens, type scale, chart forms, copy tone, and zone order. When a markup/CSS question arises, the mock is the answer.

## Global Constraints

- Lane: worktree `.worktrees/f110-dashboard`, branch `f110-dashboard`. Python from worktree = `../../.venv/Scripts/python`. Never work on root main.
- MUST NOT TOUCH: `gpu_agent/scoring.py`, `gpu_agent/report.py`, any brain prompt (`gpu_agent/extraction/`, `gpu_agent/judgment/`, `gpu_agent/narrator/prompt.py`), `gpu_agent/evals/`, `fixtures/evals/`, `fixtures/narrator/`, `registry/indicators.json`, `registry/series-indicators.json`, `registry/freshness.json`. `registry/chart-series.json` is NEW and allowed.
- All four pins stay green: F6 eval baseline, narrator prompt pin, scoring-v1 replay, F83 run-cycle conformance. F83 is legitimately re-recorded ONCE, in Task 7 only, by regenerating from `EXPECTED_STEPS` (F109 precedent).
- Every visible string is executive plain English: no acronyms (DMI/SMI appear only as "Demand"/"Supply" with a caption), no AI/internal jargon; run new copy through the stop-slop skill mentally; the mock's copy is pre-approved.
- Tests never hit the network. Fetcher tests parse saved sample pages in `fixtures/chartdata/`.
- A fetcher failure must never raise out of the daily cycle path — degrade to stale/no-chart.
- Question-stop rule (verbatim from CLAUDE.md) applies to every task: a design fork or mid-build discovery that reopens a design decision STOPS and writes `.superpowers/handoffs/f110-dashboard-QUESTIONS.md`.
- Commit after every task (green tests first); `git log --oneline -1` before each commit.

## File Structure

```
registry/chart-series.json                    NEW  curated series registry
gpu_agent/chartdata/__init__.py               NEW
gpu_agent/chartdata/registry.py               NEW  load + validate chart-series.json
gpu_agent/chartdata/fetch.py                  NEW  due-series scheduler + fetch driver
gpu_agent/chartdata/fetchers/__init__.py      NEW  FETCHERS dict
gpu_agent/chartdata/fetchers/amd_dc_revenue.py NEW first fetcher (pattern for the rest)
gpu_agent/dashboard/source_refs.py            NEW  finding-id -> source references
gpu_agent/dashboard/bullets.py                NEW  story -> 3 bullets + chart matching
gpu_agent/dashboard/export_json.py            NEW  dashboard.json builder + writer
gpu_agent/cli.py                              MOD  add `chart-fetch` + `dashboard-json` verbs (follow the existing verb pattern, e.g. `coverage-record`)
gpu_agent/dashboard/site_build.py             MOD  category index emission swaps to React shell + data dir
web/                                          NEW  Vite React app (src/, schema/, package.json)
web/schema/dashboard.schema.json              NEW  shared contract (validated by BOTH pytest and vitest)
site/chips.merchant-gpu/                      MOD  committed compiled app + data/dashboard.json
tests/test_chartdata_registry.py              NEW
tests/test_chartdata_fetch.py                 NEW
tests/test_source_refs.py                     NEW
tests/test_dashboard_bullets.py               NEW
tests/test_export_json.py                     NEW
tests/test_run_cycle_conformance.py           MOD  Task 7 only
fixtures/chartdata/amd-ir-q2-2026.html        NEW  saved sample page
fixtures/dashboard/                           NEW  golden dashboard.json + trimmed store fixtures
```

---

### Task 1: dashboard.json contract (shared schema)

**Files:**
- Create: `web/schema/dashboard.schema.json`
- Test: `tests/test_dashboard_schema.py`

**Interfaces:**
- Produces: JSON Schema (draft 2020-12) used by `export_json.py` (Task 6, via `jsonschema.validate`) and the web app's vitest contract test (Task 8). Top-level shape:

```json
{
  "schemaVersion": "1.0",
  "categoryId": "chips.merchant-gpu",
  "asOf": "2026-08-05",
  "verdict": {
    "question": "Is supply catching up to demand?",
    "answer": "Not yet. …",
    "chip": {"label": "Gap narrowing", "direction": "narrowing|widening|flat"},
    "confidence": "How sure we are, in one plain sentence",
    "soWhat": "…",
    "sources": ["<ref>"]
  },
  "gapChart": {
    "points": [{"date": "2026-07-03", "demand": 0.63, "supply": -0.45}],
    "annotation": {"date": "2026-07-28", "label": "Widest gap so far"},
    "caption": "…",
    "sources": ["<ref>"]
  },
  "bullets": [{
    "date": "2026-08-05", "text": "…", "storyHref": "story/",
    "chart": {"form": "columns|bars|line", "title": "…", "caption": "…",
               "unit": "USD bn", "points": [{"label": "Q1 24", "value": 2.3, "hollow": false, "sourceUrl": "https://…"}],
               "source": "<ref>"},
    "noChartReason": null,
    "sources": ["<ref>"]
  }],
  "dimensions": [{
    "id": "bottleneck", "plainName": "What is holding shipments back",
    "ratingWord": "Strained", "tone": "bad|mixed|good",
    "direction": "improving|worsening|flat", "confidence": "medium",
    "summary": "one line", "reasoning": "the why-panel paragraph",
    "evidence": ["<ref>"]
  }],
  "footerLinks": [{"label": "Every finding", "href": "findings/"}]
}
```

  where `<ref>` is `{"title": str, "outlet": str, "url": str|null, "date": str|null, "tier": "primary|secondary|null"}` or `{"assessment": true, "basedOn": [<ref>]}`. `bullets` has exactly 3 entries; `chart` XOR `noChartReason` is null. `dimensions` has exactly 6.

- [ ] **Step 1: Write the failing test** — `tests/test_dashboard_schema.py`:

```python
import json
from pathlib import Path
import jsonschema

SCHEMA = Path("web/schema/dashboard.schema.json")

def _minimal_payload():
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    return {
        "schemaVersion": "1.0", "categoryId": "chips.merchant-gpu", "asOf": "2026-08-05",
        "verdict": {"question": "q", "answer": "a", "chip": {"label": "Gap narrowing", "direction": "narrowing"},
                     "confidence": "c", "soWhat": "s", "sources": [ref]},
        "gapChart": {"points": [{"date": "2026-07-03", "demand": 0.6, "supply": -0.4}],
                      "annotation": {"date": "2026-07-28", "label": "Widest gap so far"},
                      "caption": "cap", "sources": [ref]},
        "bullets": [
            {"date": "2026-08-05", "text": "t", "storyHref": "story/", "chart": None,
             "noChartReason": "No published number.", "sources": [ref]}] * 3,
        "dimensions": [{"id": f"d{i}", "plainName": "n", "ratingWord": "Strained", "tone": "bad",
                         "direction": "flat", "confidence": "medium", "summary": "s",
                         "reasoning": "r", "evidence": [ref]} for i in range(6)],
        "footerLinks": [{"label": "Every finding", "href": "findings/"}],
    }

def test_minimal_payload_validates():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_minimal_payload(), schema)

def test_bullet_chart_xor_reason():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    bad["bullets"][0]["chart"] = {"form": "columns", "title": "t", "caption": "c", "unit": "USD bn",
                                    "points": [{"label": "Q1", "value": 1.0, "hollow": False, "sourceUrl": None}],
                                    "source": bad["bullets"][0]["sources"][0]}
    # chart set AND noChartReason set -> invalid
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)

def test_wrong_bullet_count_fails():
    import pytest
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload(); bad["bullets"] = bad["bullets"][:2]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
```

- [ ] **Step 2: Run to verify failure** — `../../.venv/Scripts/python -m pytest tests/test_dashboard_schema.py -v` → FAIL (schema file missing). If `jsonschema` is not importable in the venv, QUESTION-STOP (new dependency needs the user's nod).
- [ ] **Step 3: Write `web/schema/dashboard.schema.json`** implementing the shape above: `$defs/ref` as a `oneOf` (plain ref | assessment ref), `bullets` `minItems: 3, maxItems: 3`, `dimensions` 6/6, bullet XOR via `oneOf` on (`chart: null` + `noChartReason: string`) / (`chart: object` + `noChartReason: null`), `additionalProperties: false` everywhere.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** `feat(f110): dashboard.json contract schema`.

---

### Task 2: Source-reference resolver

**Files:**
- Create: `gpu_agent/dashboard/source_refs.py`
- Test: `tests/test_source_refs.py`
- Fixture: `fixtures/dashboard/scorecard-trimmed.json` (copy `store/chips.merchant-gpu/2026-08-v2.json`, keep ~6 findings incl. their `evidence` arrays, all `dimensionRatings`, `indices`, `categoryStatus`, `narrative`)

**Interfaces:**
- Produces:

```python
def refs_for_finding_ids(finding_ids: list[str], findings_by_id: dict[str, dict],
                          max_refs: int = 3) -> list[dict]
    """Each finding's evidence[] entries -> ref dicts
    {title, outlet, url, date, tier}; deduped by url; primary tier first;
    unknown ids skipped (never raise). title = evidence['excerpt'][:80] is WRONG —
    title comes from evidence['source'] before ' via ', outlet = the ' via ' tail
    or the full source string; url/date/tier copied verbatim."""

def assessment_ref(based_on: list[dict]) -> dict
    """{'assessment': True, 'basedOn': based_on} for synthesis sentences."""

def findings_index(scorecard: dict) -> dict[str, dict]
    """scorecard['findings'] keyed by id."""
```

- [ ] **Step 1: Failing tests** — real shapes from the trimmed fixture:

```python
import json
from pathlib import Path
from gpu_agent.dashboard.source_refs import refs_for_finding_ids, findings_index, assessment_ref

SC = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))

def test_resolves_url_and_tier():
    idx = findings_index(SC)
    fid = next(iter(idx))
    refs = refs_for_finding_ids([fid], idx)
    assert refs and refs[0]["url"].startswith("http")
    assert refs[0]["tier"] in ("primary", "secondary", None)

def test_unknown_id_skipped_not_raised():
    assert refs_for_finding_ids(["nope-1"], findings_index(SC)) == []

def test_dedupes_by_url_and_caps():
    idx = findings_index(SC)
    all_ids = list(idx) * 2
    refs = refs_for_finding_ids(all_ids, idx, max_refs=3)
    assert len(refs) <= 3
    assert len({r["url"] for r in refs}) == len(refs)

def test_assessment_ref_shape():
    r = assessment_ref([{"title": "t", "outlet": "o", "url": "u", "date": None, "tier": None}])
    assert r["assessment"] is True and len(r["basedOn"]) == 1
```

- [ ] **Step 2: Run, verify FAIL** (module missing).
- [ ] **Step 3: Implement** (~60 lines; pure functions, no I/O).
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(f110): source-reference resolver`.

---

### Task 3: Chart-series registry

**Files:**
- Create: `registry/chart-series.json`, `gpu_agent/chartdata/__init__.py`, `gpu_agent/chartdata/registry.py`
- Test: `tests/test_chartdata_registry.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ChartSeries:
    id: str; name: str; sourceName: str; sourceUrl: str
    cadence: str            # 'quarterly' | 'monthly'
    quality: str            # 'hard-fact' | 'estimate'
    topicTags: tuple[str, ...]   # matched against finding indicatorIds + entity
    form: str               # 'columns' | 'bars' | 'line'
    unit: str
    fetcher: str | None     # key into FETCHERS; None = series maintained elsewhere (e.g. price-sync)

def load_chart_series(path="registry/chart-series.json") -> dict[str, ChartSeries]  # validates; raises ValueError on bad entries
```

- Registry seed (exactly these three entries; more series are later data edits):
  1. `amdDataCenterRevenue` — quarterly, hard-fact, tags `["amdDataCenter", "amd"]`, form columns, unit "USD bn", fetcher `"amd_dc_revenue"`, source AMD investor relations `https://ir.amd.com/financial-information/quarterly-results`.
  2. `nvdaDataCenterRevenue` — quarterly, hard-fact, tags `["nvidia", "nvidiaDataCenter"]`, form columns, unit "USD bn", fetcher `null` (fetcher lands in a follow-up; entry exists so matching logic is exercised against a fetcherless series).
  3. `gpuSpotPrice` — monthly, **estimate** (`estimateGrade: true` in the store), tags `["gpuSpotPrice"]`, form line, unit "USD", fetcher `null` (price-sync owns it). Being `estimate`, it can never render as a mini-chart — it exists to prove the quality gate.

- [ ] **Step 1: Failing tests** — load returns 3 validated entries; a registry entry missing `quality` raises `ValueError` (test with `tmp_path` copy); `estimate` + any tag is loadable but flagged: `ChartSeries.chartable` property is False for `estimate`, True for `hard-fact`.
- [ ] **Step 2: Verify FAIL. Step 3: Implement registry JSON + loader. Step 4: PASS. Step 5: Commit** `feat(f110): curated chart-series registry`.

---

### Task 4: Fetcher framework + AMD quarterly revenue fetcher

**Files:**
- Create: `gpu_agent/chartdata/fetch.py`, `gpu_agent/chartdata/fetchers/__init__.py`, `gpu_agent/chartdata/fetchers/amd_dc_revenue.py`
- Create fixture: `fixtures/chartdata/amd-ir-q2-2026.html` — save the actual AMD Q2 2026 press-release page (or its results table section) during the task; if it cannot be fetched cleanly, QUESTION-STOP rather than hand-writing fake HTML.
- Modify: `gpu_agent/cli.py` (add `chart-fetch` verb following the existing verb pattern)
- Test: `tests/test_chartdata_fetch.py`

**Interfaces:**
- Consumes: `load_chart_series` (Task 3).
- Produces:

```python
# fetchers/__init__.py
FETCHERS: dict[str, Callable[[str], list[dict]]]  # html_text -> series points

# fetchers/amd_dc_revenue.py
def parse(html_text: str) -> list[dict]
    """[{'period': '2026-Q2', 'value': 6.718, 'unit': 'USD bn',
        'publishedAt': '2026-08-04', 'sourceUrl': <page url>, 'title': <page title>}]
    Raises ParseFailed (subclass of Exception, defined in fetch.py) on unrecognized markup."""

# fetch.py
def due_series(series: dict[str, ChartSeries], as_of_date: str,
               earnings_dates: list[str]) -> list[ChartSeries]
    """quarterly: due if as_of_date within +/-3 days of an earnings date OR the
    series file is missing; monthly: never due here (price-sync owns those);
    fetcher None: never due."""

def run_fetch(series: dict, as_of_date: str, earnings_dates: list[str],
              store_dir: str, fetch_html=None) -> dict
    """Returns {'fetched': [...], 'failed': [...], 'skipped': [...]}.
    NEVER raises. Appends new points to store/series/<id>.jsonl in the EXISTING
    series row format (indicatorId, period, value, unit, publishedAt, capturedAt,
    source={url,title}, estimateGrade, label) — dedup on (indicatorId, period):
    existing periods are never rewritten. fetch_html injectable for tests."""
```

- [ ] **Step 1: Failing tests** — parse() extracts ≥2 quarters incl. `('2026-Q2', 6.718)` from the saved page; `run_fetch` with a `fetch_html` stub that raises → returns the series under `'failed'`, file untouched, nothing raised; append is idempotent across two runs (same periods not duplicated); `due_series` quarterly logic (due on earnings day, not due mid-quarter when file exists).
- [ ] **Step 2: FAIL. Step 3: Implement + wire `chart-fetch` CLI verb** (`chart-fetch --category chips.merchant-gpu --as-of 2026-08-05` — reads the category manifest's `earningsDates`, prints the summary dict as JSON; exit code 0 even with failures).
- [ ] **Step 4: PASS + run the full suite. Step 5: Commit** `feat(f110): chart-data fetch framework + AMD data-center revenue fetcher`.

---

### Task 5: Bullets + chart matcher

**Files:**
- Create: `gpu_agent/dashboard/bullets.py`
- Test: `tests/test_dashboard_bullets.py`
- Fixture: `fixtures/dashboard/story-trimmed.json` (copy `store/chips.merchant-gpu/story/2026-08-05.json` minus `relatedDocs` bulk)

**Interfaces:**
- Consumes: `refs_for_finding_ids`/`findings_index` (Task 2), `load_chart_series` (Task 3), series jsonl rows.
- Produces:

```python
def build_bullets(story: dict, scorecard: dict, series_reg: dict[str, ChartSeries],
                   store_dir: str) -> list[dict]   # exactly 3, schema `bullets` shape
```

Rules (all deterministic, no AI):
1. Bullet text = scene `title` + first sentence of `paragraphs[0]`, for the first 3 scenes whose `title` is not "What to watch from here" (the mock's bullets came from these scenes).
2. Match: collect the scene's `claimFindingIds` → their findings' `indicatorId` + `entity` strings; a series matches if any of its `topicTags` appears in that set AND `series.chartable` AND its jsonl has ≥ 4 points → chart payload from the series rows (last 10 points, per-point `sourceUrl` from row `source.url`, caption "<name>. Source: <sourceName>.").
3. Fallback: the scene's findings' own numeric history — rows of `store/series/<indicatorId>.jsonl` for the scene's indicator ids — dense enough only if ≥ 6 points spanning ≥ 3 distinct months AND not `estimateGrade`; else `noChartReason` (plain English, states what's missing, mock tone: "No chart. …").
4. `sources` per bullet = `refs_for_finding_ids(scene['claimFindingIds'], …)`.

- [ ] **Step 1: Failing tests** — 3 bullets from the real story fixture; a synthetic story whose scene tags hit `amdDataCenterRevenue` (with a tmp series file of 8 points) yields a `chart` with 8 points and null `noChartReason`; a scene hitting only `gpuSpotPrice` (estimate) yields `noChartReason` mentioning why, chart null; XOR always holds; bullet text contains no "DMI"/"SMI" substrings.
- [ ] **Step 2: FAIL. Step 3: Implement (~120 lines). Step 4: PASS. Step 5: Commit** `feat(f110): story bullets + honest chart matching`.

---

### Task 6: The exporter

**Files:**
- Create: `gpu_agent/dashboard/export_json.py`
- Modify: `gpu_agent/cli.py` (add `dashboard-json` verb)
- Test: `tests/test_export_json.py` (+ golden `fixtures/dashboard/golden-dashboard.json`)

**Interfaces:**
- Consumes: everything above + existing `gpu_agent/dashboard/gap_chart.py` (reuse its scorecard-history loading to produce dated demand/supply points — read it first; do NOT reimplement its date logic) + `plain_language.py` (dimension renames — extend its mapping if a dimension lacks a plain name; that file is copy, not frozen core).
- Produces:

```python
def build_dashboard_payload(category_id: str, store_dir: str) -> dict   # validates against web/schema/dashboard.schema.json before returning
def write_dashboard_json(category_id: str, store_dir: str, site_dir: str) -> Path  # -> site/<cat>/data/dashboard.json, LF, utf-8, sorted keys
```

Verdict composition (mock precedent, deterministic): `question` fixed string; `answer` = story `headline` recast by rule — if headline already answers, use `deck` line 1 as the second sentence; `chip` from `indices.divergence` + latest-vs-previous sdgiGap (narrowing/widening/flat with 5% dead-band); `confidence` from scorecard `confidence`; `soWhat` = story `deck` (or `narrative` first sentence when deck missing); `verdict.sources` = `assessment_ref` over the top-3 refs of the headline scene's findings.

- [ ] **Step 1: Failing tests** — golden comparison on the trimmed fixtures (byte-stable across two runs — clock-free: `capturedAt` never enters the payload); schema validation is called (mock `jsonschema.validate` spy or corrupt a field and expect `ValidationError`); acronym lint: `json.dumps(payload)` contains no `"DMI"`/`"SMI"`; every `url` in every ref starts with `http` or is null.
- [ ] **Step 2: FAIL. Step 3: Implement + CLI verb. Step 4: PASS + full suite. Step 5: Commit** `feat(f110): dashboard.json exporter`.

---

### Task 7: Run-cycle steps + F83 re-record (THE ONLY PIN-TOUCHING TASK)

**Files:**
- Modify: the run-cycle skill's step list (where `coverage-record` was added by F109 — locate via `grep -rn "coverage-record" .claude/ skills/ docs/` in the worktree; follow F109's diff as the template)
- Modify: `tests/test_run_cycle_conformance.py` — add the two steps to `EXPECTED_STEPS`, regenerate the fingerprint FROM `EXPECTED_STEPS` (the F109 precedent: never hand-compute)

Steps added to the cycle (both after scoring, before site rebuild):
1. `chart-fetch` — refresh due curated series; failures logged, never blocking.
2. `dashboard-json` — export the payload; on failure the cycle logs and continues (the live page keeps yesterday's data — spec §8).

- [ ] **Step 1: Run the conformance test, confirm green BEFORE the change** (baseline sanity).
- [ ] **Step 2: Add the steps to the skill text + `EXPECTED_STEPS`; regenerate the fingerprint.**
- [ ] **Step 3: Full suite — everything green; verify the OTHER three pins did not move (`git status` must show no `fixtures/` change).**
- [ ] **Step 4: Commit** `feat(f110): run-cycle chart-fetch + dashboard-json steps (F83 re-record, F109 precedent)`.

---

### Task 8: web/ scaffold, theme tokens, data loading + verdict zone

**Files:**
- Create: `web/` — `package.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/tokens.css`, `src/load.ts`, `src/components/Verdict.tsx`, `src/components/SourceMark.tsx`, `web/src/__tests__/verdict.test.tsx`, `web/src/__tests__/contract.test.ts`

**Preflight (question-stop on failure):** `node --version` ≥ 20; `npm view @astryxdesign/core version` resolves and installs cleanly with React 19. If Astryx's real API diverges from assumptions (component names, theming mechanism), QUESTION-STOP with the discovered API and a recommendation — do not improvise a different design system.

**Interfaces:**
- Consumes: `dashboard.schema.json` (Task 1), `data/dashboard.json` at runtime.
- Produces:

```ts
// src/load.ts
export type Dashboard = /* generated or hand-written TS mirror of the schema */
export async function loadDashboard(url?: string): Promise<{data: Dashboard; stale: boolean}>
// stale = asOf older than 2 days vs document.lastModified date — renders the "as of" banner

// src/components/SourceMark.tsx — THE universal source-reference control
export function SourceMark({refs}: {refs: Ref[]}): JSX.Element
// small superscript marker; click opens a popover listing title/outlet/date with
// <a href target=_blank rel=noopener>; assessment refs render "Our assessment, based on:" + list
```

- `src/tokens.css`: port the token block verbatim from the mock (`:root` light + dark set). Astryx theme overrides map to these tokens.
- `Verdict.tsx` renders zone 1 exactly per the mock (question small, answer largest, chip + confidence row, so-what with left rule) with a `SourceMark` after the answer.
- `index.html` carries the `<noscript>` plain-text verdict fallback: a build-time-static one-liner + link to `story/` (content updated only on app rebuilds — acceptable, noted in spec §8).

- [ ] **Step 1: Scaffold vite + install; commit lockfile.** (`npm create vite@latest web -- --template react-ts` adjusted into the existing folder; add `@astryxdesign/core`, theme, vitest, @testing-library/react, jsdom.)
- [ ] **Step 2: Failing tests** — `contract.test.ts`: the golden `fixtures/dashboard/golden-dashboard.json` validates against `web/schema/dashboard.schema.json` (ajv) AND parses into the TS loader without error; `verdict.test.tsx`: renders answer text as the page's `<h1>`, renders the chip label, renders a source popover with a working href on click, shows the stale banner when `stale: true`.
- [ ] **Step 3: Implement. Step 4: `npm test` green + `npm run build` succeeds. Step 5: Commit** `feat(f110): web scaffold, tokens, loader, verdict zone`.

---

### Task 9: Gap chart component

**Files:**
- Create: `web/src/components/GapChart.tsx`, `web/src/components/NumbersTable.tsx`, `web/src/__tests__/gapchart.test.tsx`

**Interfaces:** Consumes `Dashboard['gapChart']`. Produces `<GapChart data={…}/>` — inline SVG, two lines + shaded band between them, single shared scale, end-of-line labels ("Demand"/"Supply"), the annotation marker, CSS hover readout, `aria-label` sentence (port the mock's), `<NumbersTable>` beneath (the mock's "Show the numbers" details element).

- [ ] **Step 1: Failing tests** — renders an `svg` with two `path` elements and one shaded `path`/`polygon`; the numbers table renders one row per point with formatted values; the aria-label mentions both series plainly; no axis text contains "DMI"/"SMI".
- [ ] **Step 2: FAIL. Step 3: Port geometry + styling from the mock's SVG (same forms, dataviz rules — colors come from tokens only). Step 4: PASS + build. Step 5: Commit** `feat(f110): gap chart`.

---

### Task 10: What-changed bullets + mini-charts + no-chart panel

**Files:**
- Create: `web/src/components/Bullets.tsx`, `web/src/components/MiniChart.tsx`, `web/src/components/NoChart.tsx`, `web/src/__tests__/bullets.test.tsx`

**Interfaces:** Consumes `Dashboard['bullets']`. `MiniChart` renders `form: columns` (thin columns, first/last labeled, hover titles), `bars` (horizontal, `hollow` points outlined), `line`; caption + source link below; `NoChart` renders the mock's dashed honest-omission panel with `noChartReason` text; each bullet ends with `SourceMark` and the row links to `storyHref`.

- [ ] **Step 1: Failing tests** — three bullets render; a bullet with `chart` renders an svg + caption link with the source url; a bullet with `noChartReason` renders the dashed panel containing that text and NO svg; hollow points get the outlined class; all three `form`s render without error.
- [ ] **Step 2–5:** FAIL → implement (port mini-chart markup/CSS from the mock) → PASS + build → Commit `feat(f110): what-changed bullets + honest mini-charts`.

---

### Task 11: Six dimensions + why-panels + footer

**Files:**
- Create: `web/src/components/Dimensions.tsx`, `web/src/components/WhyPanel.tsx`, `web/src/components/Footer.tsx`, `web/src/__tests__/dimensions.test.tsx`

**Interfaces:** Consumes `Dashboard['dimensions']`, `Dashboard['footerLinks']`. Each row: status dot + `ratingWord` text (color never sole signal) + `plainName` + one-line summary; a real `<button aria-expanded>` toggling the grid-rows slide (mock pattern); panel: `reasoning` left; direction/confidence/evidence (`SourceMark` list with outlet names) right; first row default-open.

- [ ] **Step 1: Failing tests** — six rows; `aria-expanded` flips on click and the panel content becomes visible; every evidence entry with a url renders an anchor; the first row is open on mount; keyboard: Enter toggles.
- [ ] **Step 2–5:** FAIL → implement → PASS + build → Commit `feat(f110): dimension rows + why-panels + footer`.

---

### Task 12: Integration — build, swap the page in, wire site_build, full gates

**Files:**
- Modify: `gpu_agent/dashboard/site_build.py` — for the category page: stop emitting the old story `index.html`; instead ensure `data/dashboard.json` is present (call `write_dashboard_json`) and leave the committed React `index.html` + `assets/` alone. Deep pages (`findings/`, `series/`, `story/`, `history.html`) still emitted exactly as before. Read `build_site` first; the swap must not disturb the link-integrity gate — the React `index.html` is a committed input, and gate-checked pages still resolve.
- Create: `docs/superpowers/plans/` nothing; Create DONE sentinel at the end.
- Modify: `web/vite.config.ts` — `base: './'`, build `outDir` = `../site/chips.merchant-gpu`, `emptyOutDir: false` (NEVER wipe the deep-page dirs — set explicitly and add a test/check).

- [ ] **Step 1: Failing test** — `tests/test_site_build_react_swap.py`: after `build_site` on the dashboard fixtures, `site/<cat>/data/dashboard.json` exists and validates; the emitted tree still contains `findings/index.html` (deep pages intact); the OLD story-page markup (`class="st-story"`) is absent from the category `index.html`.
- [ ] **Step 2: FAIL. Step 3: Implement the swap; `npm run build`; commit the compiled output** (`site/chips.merchant-gpu/index.html` + `assets/`) — verify `git status` shows NO deletions under `site/chips.merchant-gpu/{findings,series,story}/`.
- [ ] **Step 4: Full gates:** `../../.venv/Scripts/python -m pytest -q` green; `npm test` + `npm run build` green; forbidden diff empty: `git diff main --name-only -- fixtures/ registry/indicators.json registry/series-indicators.json registry/freshness.json gpu_agent/evals gpu_agent/extraction gpu_agent/judgment gpu_agent/narrator/prompt.py gpu_agent/scoring.py gpu_agent/report.py` returns ONLY the intentional F83 conformance-test change from Task 7 (which lives in `tests/`, so the list above must return nothing).
- [ ] **Step 5: Open the built page from disk, click through: verdict source popover, chart hover, a bullet source link, a why-panel, a footer link.** Fix what's broken before declaring done (verification-before-completion).
- [ ] **Step 6: Write `.superpowers/handoffs/f110-dashboard-DONE.md`** (state, deferred minors, live criteria from spec §11) **and commit. STOP — only the user merges.**

---

## Self-Review Notes

- Spec §3 zones → Tasks 8–11; §4 architecture → Tasks 1–7, 12; §5 flow → Tasks 6, 7, 12; §6 sources → Tasks 2, 8 (SourceMark used by every zone component), 4 (per-point urls); §7 guardrails → Global Constraints + Task 7 isolation; §8 errors → Tasks 4 (never-raise), 6 (validate-before-write), 8 (stale banner, noscript); §9 testing → every task + Task 8 contract test; §10 scope → no task touches deep pages/front page/brains.
- The "dense enough" fallback threshold deferred by the spec is fixed here: ≥ 6 points, ≥ 3 distinct months, not estimate-grade (Task 5).
- Astryx API risk is contained as a Task 8 preflight question-stop, not an improvisation.
- NVDA fetcher deliberately absent (registry entry with `fetcher: null`) — YAGNI; adding it later is a data + one-fetcher change, no design reopening.
