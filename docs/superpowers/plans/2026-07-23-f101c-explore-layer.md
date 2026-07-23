# F101 Phase C — Explore Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the narrative's footnote system — story archive permalinks, question-grouped findings browser, grouped series page, entity dossiers with live evidence, and the verdict-timeline history page — all wired from inside the story, with a link-integrity build gate.

**Architecture:** Two new modules in `gpu_agent/dashboard/`: `explore_model.py` (data assembly: findings load, entity roles, series groups, timeline) and `explore_render.py` (page renderers + shared scaffold + the findings filter script + link-integrity check). `site_build.build_site` emits the new page families and runs the link gate last. Story permalinks reuse `story_render._scene_html` unchanged.

**Tech Stack:** Python 3 (`.venv/Scripts/python`; worktree `../../.venv/Scripts/python`), stdlib only, pytest. Server-side SVG via existing `gap_chart` helpers.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-23-f101c-explore-layer-design.md` (§1 governing principle is binding: narrative-first entry, pre-filtered landings, breadcrumbs, one-line question tie-back on every page, no generic data library).
- **PRECONDITION: the F101b lane is MERGED to main before this lane branches.** Task 1 Step 0 verifies (`git log --oneline | grep -i "f101 phase b\|f101b"` shows the merge; `gpu_agent/narrator/` exists). If not merged: STOP.
- Renderer/copy layer only. MUST-NOT-TOUCH: `gpu_agent/scoring.py`, `gpu_agent/report.py`, all brains' prompt modules, `gpu_agent/narrator/prompt.py`, `gpu_agent/evals/*`, `fixtures/evals/*`, `fixtures/narrator/*`, `registry/`, `.claude/skills/run-cycle/SKILL.md`. All four pins (F6, narrator, scoring replay, F83) must stay green untouched.
- Banned-word lint (`story_render.lint_story_copy`) applies to EVERY emitted page; `site_build` aborts on violations (existing pattern).
- Inline self-contained `<script>` allowed on Explore pages (spec §2/§5 user-approved extension); no external assets, no fetch.
- Every chart carries a `Source:` line. Every page: breadcrumb "← today's story" + one-line tie-back under the title.
- Worktree `.worktrees/f101c-explore`, branch `f101c-explore`. Suite green at every commit. Question-stop rule verbatim. Never touch root `store/`; smoke on a COPY.
- Wall-clock isolation: `today` threaded as a parameter everywhere.

**Verified facts (2026-07-23):** wiki pages = front-matter parseable by `gpu_agent/wiki/page.py` (`WikiPage` @:11, `dump_page` @:26 — a `load_page`-style counterpart exists in the same module; read it first) over `store/wiki/entity/<slug>.md`. Standalone findings `store/findings/*.json` carry `{id, statement, evidence[{source,url,date,tier}], asOf, indicatorId, side, polarityDemand, polaritySupply, entity, observedAt, impact{targets,...}, confidence}`. Finding `entity` values need an alias map: `{"nvda": "nvidia", "intc": "intel"}` + casefold (observed: nvidia 60, market 27, amd 26, multi 24, memory 7, NVDA 5, intel 5, coreweave 4, tsmc 3, meta 2, AMD 2, intc 1). Series read via `agenda.read_series`; monthly records via `gap_chart._monthly_records`; chips/labels via `story_model._CHIP_DEFS`; scenes render via `story_render._scene_html(scene)`; story artifacts via `narrator.store.StoryStore` (post-B). `build_site(category_id, store_dir, work_dir, plain_path, out_dir, price_fn=None, today=None)` @site_build.py:22.

**Fixture note:** all tasks extend `tests/dashboard/fixtures`-style tmp stores via `tests/dashboard/test_story_model._store` and add: 2 wiki entity files, 3 standalone findings (one demand-side, one supply-side, one `entity: "NVDA"` alias case), and 2 story artifacts (one narrated, one fellBack) — built once in Task 1's `tests/dashboard/test_explore_fixtures.py` helper `_explore_store(tmp_path)` and imported by every later test file.

---

### Task 1: Shared scaffold + link-integrity gate (`explore_render.py` core)

**Files:**
- Create: `gpu_agent/dashboard/explore_render.py`, `tests/dashboard/test_explore_fixtures.py` (the `_explore_store` helper), `tests/dashboard/test_explore_scaffold.py`
- Verify precondition (Step 0) then branch.

**Interfaces:**
- `page_scaffold(title: str, tieback: str, body: str, depth: int) -> str` — wraps body with `site_render.page(...)`, prepending `<nav class="xp-crumb"><a href="{'../' * (depth-1) or ''}index.html">← today's story</a></nav>` and `<p class="xp-tieback">Behind the verdict: {tieback}</p>`. (depth: 1 = `<cat>/history.html`, 2 = `<cat>/story/x.html` etc.)
- `check_links(pages: dict[str, str]) -> list[str]` — `pages` maps emitted RELATIVE paths (e.g. `"chips.merchant-gpu/findings/index.html"`) to HTML. Extracts every internal `href` (skip `http(s)://`, `#...`, `mailto:`), resolves it against the page's directory (strip `#fragment` and `?query`), and reports each target not in `pages` (root `index.html`/`style.css` included by the caller). Empty = pass.
- `EXPLORE_CSS: str` (`.xp-*` rules; appended to the stylesheet in Task 7).

- [ ] **Step 0:** verify the Phase B merge precondition (Global Constraints). Create worktree + branch.
- [ ] **Step 1: Failing tests**

```python
# tests/dashboard/test_explore_scaffold.py
from gpu_agent.dashboard.explore_render import page_scaffold, check_links


def test_scaffold_has_crumb_and_tieback():
    html = page_scaffold("Findings", "every piece of evidence", "<p>x</p>", depth=2)
    assert "← today" in html and "../index.html" in html
    assert "Behind the verdict: every piece of evidence" in html


def test_check_links_catches_dead_href():
    pages = {"c/index.html": '<a href="findings/index.html">f</a>',
             "c/findings/index.html": '<a href="../index.html">b</a>'
                                       '<a href="../history.html#m-2026-07">h</a>'}
    errs = check_links(pages)
    assert len(errs) == 1 and "history.html" in errs[0]
    pages["c/history.html"] = "<p>ok</p>"
    assert check_links(pages) == []


def test_check_links_ignores_external_and_fragments():
    pages = {"c/a.html": '<a href="https://x.example/y">e</a><a href="#top">t</a>'}
    assert check_links(pages) == []
```

Also write `_explore_store(tmp_path)` in `test_explore_fixtures.py`: calls `_store(tmp_path)`, then adds `store/wiki/entity/{nvidia.md,tsmc.md}` (front-matter via `wiki.page.dump_page` + 2-paragraph markdown bodies with a `## heading` and a `- list`), `store/findings/{fa,fb,fc}.json` (fa: `side:"demand"`, entity `"nvidia"`; fb: `side:"supply"`, entity `"tsmc"`, `polaritySupply:-1`; fc: entity `"NVDA"` alias), and two story artifacts via `StoryStore` (2026-07-22 narrated "Yesterday's H", 2026-07-21 fellBack) — reuse `tests/narrator/test_store._art`.

- [ ] **Step 2:** run → module-not-found FAIL. **Step 3:** implement (href extraction via `re.findall(r'href="([^"]+)"', ...)`; resolve with `posixpath.normpath(posixpath.join(posixpath.dirname(page), href.split("#")[0].split("?")[0]))`). **Step 4:** run → PASS. **Step 5:** commit `feat(f101c): explore scaffold + link-integrity gate`.

---

### Task 2: Explore data assembly (`explore_model.py`)

**Files:**
- Create: `gpu_agent/dashboard/explore_model.py`
- Test: `tests/dashboard/test_explore_model.py`

**Interfaces (all pure reads, `store_root: Path`):**
- `load_findings(store_root) -> list[dict]` — every `store/findings/*.json` (skip unparseable), sorted newest-first by `observedAt` or `asOf`; each dict gains `entitySlug` via `_ALIAS = {"nvda": "nvidia", "intc": "intel"}` + casefold.
- `split_by_side(findings) -> {"demand": [...], "supply": [...], "other": [...]}` (`side` field; missing → other).
- `entity_roles(findings) -> dict[slug, str]` — per entity: majority side → `"where the supply bottleneck lives" if supply and any polaritySupply < 0 else "a supply-side player"` / `"a demand driver"` / `"a market participant"` (mixed/other).
- `load_entities(store_root) -> list[dict]` — per `store/wiki/entity/*.md`: `{slug, title, front: WikiPage-dict, body_md}` using the wiki module's loader (read `gpu_agent/wiki/page.py` first; do not re-implement parsing).
- `series_groups() -> list[{key, label, indicatorIds}]` — the fixed KPI-framework grouping: `gap-price` ["gpuRentalOnDemand","gpuRental1yr","gpuSpotPrice"] "The price of the gap" / `demand` ["hyperscalerCapexRevision","tokenEconomics","marginalBuyerFinancing"] "Demand gauges" / `supply` ["odmMonthlyAiRevenue","pkgCapacityOrderSpread"] "Supply arriving" / `relief` ["hbmSupplyCapex"] "Relief ahead". Plus `SERIES_MEANING: dict[indicatorId, str]` one-liners ("falls when supply catches up", …) and `ENTITY_SERIES = {"tsmc": ["pkgCapacityOrderSpread"]}`.
- `verdict_timeline(cat_dir) -> {"gap": <build_gap_data over ALL months (limit=120)>, "months": [{key, label, headline, rating, direction, constraint, dims: {name: {rating, direction}}}]}` — headline per month via the Phase A `_HEADLINES` gap-word logic month-over-month.
- `story_index(store_root, category_id) -> list[{date, headline, fellBack}]` — every artifact, newest first (via `StoryStore`).
- `markdown_to_html(md: str) -> str` — minimal, safe: escape HTML first (`render.esc`), then `## `→`<h2>`/`### `→`<h3>`, `**x**`→`<b>`, `- ` blocks→`<ul><li>`, blank-line→`<p>` breaks, `[t](https://u)`→anchor (https only). Nothing else — no raw HTML passthrough.

- [ ] **Step 1: Failing tests** (using `_explore_store`):

```python
# tests/dashboard/test_explore_model.py  — representative core (write all)
import datetime as dt
from gpu_agent.dashboard import explore_model as xm
from tests.dashboard.test_explore_fixtures import _explore_store


def test_findings_load_alias_and_sides(tmp_path):
    st = _explore_store(tmp_path)
    fs = xm.load_findings(st)
    assert {f["entitySlug"] for f in fs} >= {"nvidia", "tsmc"}   # NVDA folded in
    sides = xm.split_by_side(fs)
    assert sides["demand"] and sides["supply"]


def test_entity_roles(tmp_path):
    roles = xm.entity_roles(xm.load_findings(_explore_store(tmp_path)))
    assert roles["tsmc"] == "where the supply bottleneck lives"
    assert roles["nvidia"] == "a demand driver"


def test_entities_and_markdown(tmp_path):
    ents = xm.load_entities(_explore_store(tmp_path))
    assert {e["slug"] for e in ents} == {"nvidia", "tsmc"}
    html = xm.markdown_to_html("## Head\n\n**bold** <script>x</script>\n\n- a\n- b")
    assert "<h2>Head</h2>" in html and "<b>bold</b>" in html
    assert "<li>a</li>" in html and "<script>" not in html


def test_verdict_timeline_and_story_index(tmp_path):
    st = _explore_store(tmp_path)
    tl = xm.verdict_timeline(st / "chips.merchant-gpu")
    assert len(tl["months"]) == 2 and tl["months"][-1]["headline"]
    idx = xm.story_index(st, "chips.merchant-gpu")
    assert idx[0]["date"] == "2026-07-22" and idx[1]["fellBack"] is True
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement per Interfaces (import `_HEADLINES`/gap logic from `story_model`/`gap_chart`, `StoryStore` from narrator). **Step 4:** run → PASS. **Step 5:** commit `feat(f101c): explore data assembly`.

---

### Task 3: Story archive pages

**Files:**
- Modify: `gpu_agent/dashboard/explore_render.py`
- Test: `tests/dashboard/test_explore_story_pages.py`

**Interfaces:**
- `render_story_day(artifact_model: dict, date: str) -> str` — takes the SAME model dict `read_story_artifact` produces for that date (Task consumes `story_model.read_story_artifact` pointed at an arbitrary date — add an optional `story_date: str | None = None` parameter to it in this task, default preserving today-behavior) and renders: scaffold(depth=2) + dated headline + deck + the scenes via `story_render._scene_html` + evidence blob/panel scripts. Fallback/missing days: the notice page ("No narrated entry this day — the page ran on assembled data.").
- `render_story_index(entries: list[{date, headline, fellBack}]) -> str` — newest-first list, fellBack rows marked "(assembled)".

- [ ] **Step 1: Failing tests** — narrated day page contains its headline + `_scene_html` output + `id="ev-data"`; same scene HTML on permalink as front page (contract assert: `_scene_html(scene)` substring present in both); fellBack date renders the notice; index lists both days with the marker; all pages lint-clean.
- [ ] **Step 2:** run → FAIL. **Step 3:** implement (+ the `story_date` parameter on `read_story_artifact`, test included that today-behavior is unchanged). **Step 4:** PASS. **Step 5:** commit `feat(f101c): story archive permalinks + index`.

---

### Task 4: Findings page + filter script

**Files:**
- Modify: `gpu_agent/dashboard/explore_render.py`
- Test: `tests/dashboard/test_explore_findings.py`

**Interfaces:**
- `render_findings_page(findings, sides, today) -> str` — scaffold(depth=2); two top groups ("Evidence demand is growing" / "Evidence supply is (or isn't) catching up", `other` folded under a muted third), each finding a `<article class="xp-find" data-dim="..." data-entity="..." data-tier="..." data-date="...">` card: statement, dimension tags (from `impact.targets`), entity, date, evidence source links (https only, `esc`'d). One self-contained `<script>`: reads `location.hash` params (`#dim=...&entity=...`), applies them, and wires `<select>`/date inputs to toggle `hidden` on non-matching cards; a live count line.
- Filter contract (tested server-side): every card carries the four `data-*` attributes; the script string contains `location.hash`, `hidden`, and no external refs.

- [ ] **Step 1: Failing tests** — groups render in order with the fixture findings under the right group; alias finding appears under nvidia; `data-dim`/`data-entity` present; script self-contained (`<script>` count == 1 for the filter, `http` absent inside it); lint-clean.
- [ ] **Step 2–4:** implement → PASS. **Step 5:** commit `feat(f101c): question-grouped findings browser + client filter`.

---

### Task 5: Series + entities pages

**Files:**
- Modify: `gpu_agent/dashboard/explore_render.py`
- Test: `tests/dashboard/test_explore_series_entities.py`

**Interfaces:**
- `render_series_page(series: dict[id, rows], today) -> str` — sections per `series_groups()` order; per indicator: `<h3 id="s-<indicatorId>">` (KPI chips link here), full-history chart (`gap_chart.spark_svg(values, 640, 120)` is acceptable as the line; label axis-least), latest value + unit, `_CHIP_DEFS` description, `SERIES_MEANING` line, source table (unique `source.title` + date rows). Empty series → "no data yet" row, never a crash.
- `render_entity_page(entity: dict, role: str, findings: list, series: dict, today) -> str` — scaffold(depth=2); role line under the title; `markdown_to_html(body_md)`; "What we've observed" = that entity's findings (cards like Task 4, no filter script); owned-series chart(s) via `ENTITY_SERIES`.
- `render_entities_index(entities, roles) -> str` — grouped supply chain / buyers / makers / other by role string.

- [ ] **Step 1: Failing tests** — series page: group headings in order, `id="s-gpuRentalOnDemand"` anchor, meaning lines, a source table row; entity page: role line ("where the supply bottleneck lives" for tsmc), rendered `<h2>` from markdown, the tsmc finding card, no `<script>`; index groups both fixtures; all lint-clean.
- [ ] **Step 2–4:** implement → PASS. **Step 5:** commit `feat(f101c): series + entity pages`.

---

### Task 6: History page (verdict timeline)

**Files:**
- Modify: `gpu_agent/dashboard/explore_render.py` (+ a `render_timeline_svg` in `gap_chart.py`)
- Test: `tests/dashboard/test_explore_history.py`

**Interfaces:**
- `gap_chart.render_timeline_svg(gap_data, month_headlines: list[str]) -> str` — the gap chart at full width/all months with each month's headline as a pinned label with leader line (reuse `_scale`; alternate label rows to avoid overlap).
- `render_history_page(timeline, today) -> str` — scaffold(depth=1); the timeline SVG + `Source:` line; per month a `<details id="m-<key>">` with the six dimension ratings/directions + binding constraint; link to `appendix.html`.

- [ ] **Step 1: Failing tests** — SVG contains both fixture months' headlines; `<details id="m-2026-07">` present with dimension names; appendix link resolves; lint-clean. **Steps 2–4:** implement → PASS. **Step 5:** commit `feat(f101c): verdict-timeline history page`.

---

### Task 7: Site-build emission + narrative-first wiring + gate hookup

**Files:**
- Modify: `gpu_agent/dashboard/site_build.py`, `gpu_agent/dashboard/story_render.py` (link targets only), `gpu_agent/dashboard/story_model.py` (panel `explore` hrefs only)
- Test: `tests/dashboard/test_site_build.py` (append), `tests/dashboard/test_explore_wiring.py`

**Changes:**
1. `build_site` assembles the explore models and emits: `story/index.html`, `story/<date>.html` (every artifact), `findings/index.html`, `series/index.html`, `entities/index.html`, `entities/<slug>.html`, `history.html`. Stylesheet += `EXPLORE_CSS`. Summary dict gains `explore_pages: int`.
2. **Narrative-first wiring:** Explore band tiles → the five routes; evidence panel `explore` values become `../findings/index.html#dim=<dim>&entity=<slug>` (from the claim's finding; falls back to plain findings index) — set in `story_model` where evidence entries are built (both assembler and artifact paths); KPI chips wrap in/link to `series/index.html#s-<indicatorId>`; archive chips + "story archive →" → `story/` routes; the gap chart "the gap, this week" label links to `history.html`; entity titles appearing in scene paragraphs become links (word-boundary match on `load_entities` titles, first occurrence per scene, applied server-side in `_scene_html` via an `entity_links: dict[title, href]` optional parameter — default None keeps old behavior).
3. `check_links` runs over ALL emitted pages at the end of `build_site`; violations → `ValueError` (mirrors lint aborts). Root `index.html` + stylesheets included in the page map.
4. **Old-test reconciliation (enumerated):** `test_build_site_index_is_story`'s CSS assert gains `.xp-` presence; any Phase A test asserting Explore tiles href `appendix.html` → new routes; any test asserting panel `explore == "appendix.html"` → the new hash-href form. Failures outside this list: question-stop.

- [ ] **Step 1: Failing tests** — build on `_explore_store`: all seven page families exist on disk; `summary["explore_pages"] >= 8`; the front index links `findings/index.html`; a panel evidence entry's `explore` carries `#dim=`; scene prose contains an `<a` around a fixture entity title; `check_links` failure path (monkeypatch a dead href) raises.
- [ ] **Step 2–4:** implement + reconcile enumerated tests → dashboard suite green. **Step 5:** commit `feat(f101c): emit explore pages, narrative-first wiring, link gate`.

---

### Task 8: Close-out — smoke on store copy, full suite, sentinel

- [ ] **Step 1:** `mkdir -p ../../work/f101c-smoke && cp -r ../../store ../../work/f101c-smoke/store`; build via CLI against the copy; open + verify by eye/grep: 23 entity pages emitted, findings page groups populated (real side split), series page shows all 9 with source tables, history timeline spans all months with headlines, story pages match however many artifacts exist (possibly few — fine), link gate passes, every page lint-clean. Record counts.
- [ ] **Step 2:** full suite `../../.venv/Scripts/python -m pytest -q` → green; `git diff --stat fixtures/ registry/ gpu_agent/evals gpu_agent/narrator/prompt.py .claude/skills/run-cycle` → EMPTY.
- [ ] **Step 3:** sentinel `.superpowers/handoffs/f101c-explore-DONE.md` (summary, commits, smoke counts, deferred items, "STOP before merge — only the user merges").
- [ ] **Step 4:** final commit, explicit paths.

---

## Self-Review

1. **Spec coverage:** §1 governing principle → Task 1 scaffold (crumb/tieback) + Task 7 wiring (pre-filtered panel hrefs, entity links in prose, KPI anchors) — every entry path itemized; §3.1 → T3; §3.2 → T4 (side grouping, hash pre-filter, growth note deferred until >1MB — recorded as a follow-up in the sentinel, not built: YAGNI); §3.3 → T5; §3.4 → T5 (role line via T2 `entity_roles`); §3.5 → T6; §4 wiring → T7; §5 link gate → T1+T7, lint → every render test, scripting bounds → T4 contract; §6 tests → per-task + T7 gate hookup + T3 same-scene contract. Precondition (§ scope) → T1 Step 0 + Global Constraints.
2. **Placeholders:** none; compressed steps name exact assertions and exact behaviors. T4/T5/T6 render internals left to the implementer ARE bounded by tested contracts (attributes, ids, group order, lint) — acceptable per right-sizing; no "add appropriate X" language present.
3. **Type consistency:** `page_scaffold(title, tieback, body, depth)` T1→T3-T6; `check_links(pages: dict[str,str])` T1→T7; `_explore_store` T1→all; `load_findings→entitySlug` T2→T4/T5/T7; `series_groups()/SERIES_MEANING/ENTITY_SERIES` T2→T5; `verdict_timeline` T2→T6; `story_index` T2→T3/T7; `read_story_artifact(..., story_date=None)` T3 only (backward-compatible default tested); `render_timeline_svg(gap_data, month_headlines)` T6.
