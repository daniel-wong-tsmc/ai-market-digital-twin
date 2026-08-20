# F119 + F120 Report Quality Pair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the brief's above-fold 88-line promise true with a second honest fold (F119), and block any render whose assembled above-fold text carries an off-allowlist all-caps token (F120).

**Architecture:** Both changes live in `gpu_agent/report.py::render_report` and `render_quick_glance`. F119 extends the existing deterministic shrink loop with one more lever (QUICK GLANCE Tier 2/3 fold + full rows echoed into the appendix). F120 adds one `reader.lint_acronyms` pass over the final above-fold string, raising `ValueError` on a hit.

**Tech Stack:** Python 3 (shared root venv `../../.venv/Scripts/python`), pytest, pydantic models already in `gpu_agent/change.py` / `gpu_agent/thesis.py`.

**Spec:** `docs/superpowers/specs/2026-08-20-report-quality-pair-design.md`

## Global Constraints

- Renderer-only: touch `gpu_agent/report.py` and `tests/` only.
- All pins byte-untouched and green: `tests/test_evals_baseline_pin.py`, F83 fingerprint, narrator prompt pin, scoring-v1 replay. A reddened pin = STOP + question-stop.
- Never touch `store/`, `site/`, `web/`, run-cycle SKILL.md.
- Under-budget renders and every `change=None` render stay byte-identical (F119's fold only fires inside the over-budget branch; F120 adds no text).
- Exec-facing added prose (the fold summary lines) must pass `reader.lint_acronyms` and the no-jargon rule.
- Per-item commits: Task 1 = F119, Task 2 = F120, each independently revertible.
- Full suite green before DONE: `../../.venv/Scripts/python -m pytest -q` (~2547 passed, 6 skips in a worktree).

---

### Task 1: F119 — QUICK GLANCE Tier 2/3 fold as the second shrink lever

**Files:**
- Modify: `gpu_agent/report.py` (`render_quick_glance` ~line 827; budget loop ~line 1083)
- Test: `tests/test_report_change_first.py` (append new tests)

**Interfaces:**
- Consumes: `render_quick_glance(state, change, registry)` (existing), the budget loop over `top[3]`/`top[4]`, `appendix` list (index 0 = divider, index 1 = full THE CALLS on the change-first path).
- Produces: `render_quick_glance(state, change=None, registry=None, fold_detail=False)`; `_glance_fold_line(label, rows_moved) -> str` is internal only. Task 2 relies on nothing new from Task 1 beyond `render_report` still returning `str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_report_change_first.py`)

```python
# ── F119: second shrink lever — QUICK GLANCE Tier 2/3 fold ──────────────────

def _big_book(n=17):
    from gpu_agent.thesis import ThesisBook, ThesisEntry
    entries = [ThesisEntry(
        id=f"t{i}", title=f"call t{i}", statement="s", lens="demand",
        status="registered", conviction="medium",
        lastVerdict=("strengthened" if i == 0 else "reaffirmed"),
        lastDirection=0, streak=2, mechanism="m", falsifiableTrigger="trigger",
        sensitivity="s", createdAsOf="2026-06", lastChangedAsOf="2026-07-08",
        lastJudgedAsOf="2026-07-08") for i in range(n)]
    return ThesisBook(categoryId="chips.merchant-gpu", entries=entries)


def _wide_state():
    # A state vector wide enough (prices + scarcity + money rows) that the top half
    # still overshoots the 88-line budget after ranked calls bottom out at top_k == 1.
    from gpu_agent.change import PriceCell, MetricCell
    st = build_state(_sc())
    st.prices = [PriceCell(model=m, usdPerGpuHour=2.5, asOfColumn="2026-07-08")
                 for m in ("B200", "H100", "H200", "GB200")]
    st.metrics = {
        "leadTimes": MetricCell(indicatorId="leadTimes", statement="36 weeks",
                                tier="scarcity"),
        "S10": MetricCell(indicatorId="S10", statement="inventory lean",
                          tier="scarcity"),
        "vendorRevenueGuidance": MetricCell(indicatorId="vendorRevenueGuidance",
                                            value=45.0, unit="USD_B", tier="money"),
        "rpoBacklog": MetricCell(indicatorId="rpoBacklog", value=90.0, unit="USD_B",
                                 tier="money"),
        "grossMargin": MetricCell(indicatorId="grossMargin", value=71.0, unit="pct",
                                  tier="money"),
    }
    return st


def test_f119_fold_brings_overshooting_page_within_budget():
    from gpu_agent.report import _ABOVE_FOLD_BUDGET
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=_wide_state(), thesis_book=_big_book())
    above, appendix_part = out.split(reader.APPENDIX_DIVIDER, 1)
    assert len(above.splitlines()) <= _ABOVE_FOLD_BUDGET
    # the fold marker sits above the fold; Tier 1 verdict rows never fold
    assert "full rows below the divider" in above
    assert "Momentum rating" in above
    # Tier 2/3 detail rows are gone from the top half...
    assert "B200 rental" not in above
    # ...but the full QUICK GLANCE rows are guaranteed in the appendix
    assert "QUICK GLANCE" in appendix_part
    assert "B200 rental" in appendix_part
    assert "Tier 3 — Money" in appendix_part


def test_f119_fold_lines_pass_acronym_lint():
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=_wide_state(), thesis_book=_big_book())
    assert reader.lint_acronyms(out.split(reader.APPENDIX_DIVIDER)[0]) == []


def test_f119_under_budget_page_never_folds():
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=build_state(_sc()))
    assert "full rows below the divider" not in out
    # and the appendix carries no duplicated QUICK GLANCE when nothing folded
    assert out.split(reader.APPENDIX_DIVIDER)[1].count("QUICK GLANCE") == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair && ../../.venv/Scripts/python -m pytest tests/test_report_change_first.py -q -k f119`
Expected: FAIL — `test_f119_fold_brings_overshooting_page_within_budget` overshoots the budget / lacks the fold marker; `test_f119_under_budget_page_never_folds` may already pass (that is fine — it is the byte-identity guard).

- [ ] **Step 3: Implement the fold**

In `gpu_agent/report.py`, replace `render_quick_glance`'s signature and Tier 2/3 blocks:

```python
def render_quick_glance(state, change=None, registry=None, fold_detail=False) -> str:
    """QUICK GLANCE (D8) — three tiers, each row its move arrow + (money) an age tag. Tier 1
    verdict: the six ratings + demand/supply momentum. Tier 2 scarcity: rental price (feed) +
    lead times + packaging/HBM. Tier 3 money: revenue guidance + backlog + gross margin,
    age-tagged (they move on earnings). Above the fold — passes reader.lint_acronyms. Share
    price is excluded (spec §5.6).

    F119 (user-approved 2026-08-20): ``fold_detail=True`` is the budget loop's second
    shrink lever — Tier 2 and Tier 3 each collapse to one honest summary line (count
    tracked, count moved, pointer to the appendix); Tier 1 never folds. The default is
    byte-identical to before the flag existed."""
    lines = ["QUICK GLANCE"]

    lines.append("  Tier 1 — Verdict")
    d_arrow = _glance_arrow(change, "index:demand")
    s_arrow = _glance_arrow(change, "index:supply")
    lines.append(f"    Demand momentum {_momentum_word(state.demand)} {d_arrow}"
                 f"    Supply momentum {_momentum_word(state.supply)} {s_arrow}")
    for dim, cell in state.dimensions.items():
        arrow = _glance_arrow(change, f"dim:{dim}")
        label = reader.DIM_LABEL.get(dim, dim)
        lines.append(f"    {label:<24} {cell.rating} {arrow}")

    scarcity_keys = ([f"price:{p.model}" for p in state.prices]
                     + [f"metric:{iid}" for iid, c in state.metrics.items()
                        if c.tier == "scarcity"])
    money_keys = [f"metric:{iid}" for iid, c in state.metrics.items()
                  if c.tier == "money"]

    if fold_detail:
        lines.append(_glance_fold_line("Tier 2 — Scarcity", scarcity_keys, change))
        lines.append(_glance_fold_line("Tier 3 — Money", money_keys, change))
        return "\n".join(lines)

    lines.append("  Tier 2 — Scarcity")
    for p in state.prices:
        arrow = _glance_arrow(change, f"price:{p.model}")
        lines.append(f"    {p.model + ' rental':<24} ${p.usdPerGpuHour:g}/GPU-hr {arrow}")
    for iid, cell in state.metrics.items():
        if cell.tier != "scarcity":
            continue
        arrow = _glance_arrow(change, f"metric:{iid}")
        lines.append(f"    {reader.indicator_label(iid, registry):<24} {_metric_display(cell)} {arrow}")

    lines.append("  Tier 3 — Money")
    for iid, cell in state.metrics.items():
        if cell.tier != "money":
            continue
        arrow = _glance_arrow(change, f"metric:{iid}")
        age = _age_tag(state.asOf, cell.observedAt)
        age_str = f"  ({age})" if age else ""
        lines.append(f"    {reader.indicator_label(iid, registry):<24} "
                     f"{_metric_display(cell)} {arrow}{age_str}")

    return "\n".join(lines)
```

Add the helper directly above `render_quick_glance`:

```python
def _glance_fold_line(label: str, keys: list[str], change) -> str:
    """One honest summary line for a folded glance tier (F119): how many rows it
    tracks, how many moved (nearest-horizon arrow != unchanged), and where the full
    rows live. Exec-plain; passes reader.lint_acronyms."""
    moved = sum(1 for k in keys
                if _glance_arrow(change, k) != _CHANGE_ARROW["same"])
    return (f"  {label}: {len(keys)} tracked, {moved} moved — "
            f"full rows below the divider")
```

Then extend the budget loop in `render_report` (after the existing `while ... k > 1` loop, still inside `if change is not None:`):

```python
        # F119 second lever (user-approved 2026-08-20): ranked calls are at their
        # floor — fold QUICK GLANCE Tier 2/3 to one summary line each and echo the
        # full rows into the appendix (right after the full THE CALLS block) so the
        # fold line's promise is true. If the page is STILL over budget after both
        # levers bottom out, ship over budget (user-accepted 2026-07-13 stopgap,
        # re-confirmed 2026-08-20).
        if (state is not None
                and len(body.split(reader.APPENDIX_DIVIDER)[0].splitlines())
                > _ABOVE_FOLD_BUDGET):
            top[3] = render_quick_glance(state, change, registry, fold_detail=True)
            appendix.insert(2, render_quick_glance(state, change, registry))
            body = "\n\n".join(s for s in top + appendix if s)
```

- [ ] **Step 4: Run the new tests, then the report test files**

Run: `cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair && ../../.venv/Scripts/python -m pytest tests/test_report_change_first.py tests/test_cli_report.py tests/test_report_contract.py tests/test_brief_report.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit (F119 alone)**

```bash
cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair
git log --oneline -1   # concurrent-instance guard: HEAD must be your own last commit
git add gpu_agent/report.py tests/test_report_change_first.py docs/superpowers/specs/2026-08-20-report-quality-pair-design.md docs/superpowers/plans/2026-08-20-report-quality-pair.md
git commit -m "feat(report): F119 second shrink lever — fold QUICK GLANCE Tier 2/3 when ranked calls bottom out (user-approved Option B)"
```

---

### Task 2: F120 — block on off-allowlist acronyms in the assembled above-fold text

**Files:**
- Modify: `gpu_agent/report.py` (end of `render_report`, before `return body`)
- Test: `tests/test_report_change_first.py` (append new tests)

**Interfaces:**
- Consumes: `reader.lint_acronyms(text) -> list[str]`, `reader.APPENDIX_DIVIDER`, the final `body` string from Task 1's loop.
- Produces: `render_report` now raises `ValueError` (message contains each offending token and the string `registry/acronyms.json`) when the above-fold half carries an off-allowlist all-caps token. Return type unchanged (`str`) on the clean path.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_report_change_first.py`)

```python
# ── F120: assembled above-fold acronym lint blocks the render ────────────────

def _book_with_title(title):
    from gpu_agent.thesis import ThesisBook, ThesisEntry
    return ThesisBook(categoryId="chips.merchant-gpu", entries=[ThesisEntry(
        id="x1", title=title, statement="s", lens="demand", status="registered",
        conviction="high", lastVerdict="strengthened", lastDirection=0, streak=2,
        mechanism="m", falsifiableTrigger="trigger", sensitivity="s",
        createdAsOf="2026-06", lastChangedAsOf="2026-07-08",
        lastJudgedAsOf="2026-07-08")])


def test_f120_novel_acronym_in_live_title_blocks_render_legacy_path():
    import pytest
    book = _book_with_title("ZORPX9 accelerators reset the market")
    with pytest.raises(ValueError) as exc:
        render_report(_sc(), None, _reg(), render_ts="fixed", thesis_book=book)
    assert "ZORPX9" in str(exc.value)
    assert "registry/acronyms.json" in str(exc.value)


def test_f120_novel_acronym_blocks_change_first_path_too():
    import pytest
    book = _book_with_title("ZORPX9 accelerators reset the market")
    st = build_state(_sc())
    with pytest.raises(ValueError, match="ZORPX9"):
        render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                      state=st, thesis_book=book)


def test_f120_allowlisted_tokens_still_render():
    # DAILY/monthly clean renders keep working — the whole existing suite is the
    # broad green check; this is the targeted one.
    book = _book_with_title("HBM supply stays tight into 2027")
    out = render_report(_sc(), None, _reg(), render_ts="fixed", thesis_book=book)
    assert "HBM supply stays tight" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair && ../../.venv/Scripts/python -m pytest tests/test_report_change_first.py -q -k f120`
Expected: the two blocking tests FAIL (`DID NOT RAISE ValueError`); the allowlisted one passes.

- [ ] **Step 3: Implement the block**

In `render_report`, immediately before `return body` (after the F119 loop so it lints exactly what ships):

```python
    # F120 (user-approved 2026-08-20, BLOCK): one final acronym lint over the fully
    # assembled above-fold text. Per-section lint runs at write time, but live thesis
    # titles and finding statements substitute in afterwards — this is the last gate
    # before the executive page ships. Recovery: add real terms to
    # registry/acronyms.json ("allowed") and re-render from saved artifacts.
    offenders = reader.lint_acronyms(body.split(reader.APPENDIX_DIVIDER)[0])
    if offenders:
        raise ValueError(
            "brief blocked before render: unknown all-caps token(s) above the "
            f"appendix divider: {', '.join(offenders)} — if these are real terms, "
            "add them to registry/acronyms.json (\"allowed\") and re-render; the "
            "saved run data is untouched.")
    return body
```

- [ ] **Step 4: Run the F120 tests, then the full suite**

Run: `cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair && ../../.venv/Scripts/python -m pytest tests/test_report_change_first.py -q -k f120`
Expected: PASS.
Then: `cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair && ../../.venv/Scripts/python -m pytest -q`
Expected: ~2547 passed, 6 skipped, 0 failed. If any test reddens because its fixture legitimately feeds an off-allowlist token above the fold, fix that test fixture (test-only). If a PIN reddens: STOP — question-stop, never re-record.

- [ ] **Step 5: Commit (F120 alone)**

```bash
cd C:/Users/danie/random_for_fun/.worktrees/report-quality-pair
git log --oneline -1   # concurrent-instance guard
git add gpu_agent/report.py tests/test_report_change_first.py
git commit -m "feat(report): F120 final above-fold acronym lint — block render on off-allowlist tokens (user-approved Option A)"
```

---

### Task 3: Review, verify, hand off

- [ ] Run `superpowers:requesting-code-review` over the branch diff; address findings (per-item follow-up commits if needed).
- [ ] Run `superpowers:verification-before-completion`: full suite output captured fresh (`../../.venv/Scripts/python -m pytest -q`), pins confirmed green and byte-untouched (`git diff main --stat` shows only report.py, tests, docs, sentinel).
- [ ] Write `.superpowers/handoffs/report-quality-pair-DONE.md` (branch, commits, test counts, AFK/approval provenance, explicitly: NOT merged — user merges).
