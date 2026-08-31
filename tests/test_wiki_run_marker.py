"""F135 — WHAT MOVED must survive two runs inside the same calendar month.

The notebook stamps every event with the scorecard's period label, which is the MONTH
(`2026-08`). The report used to diff "after <prior run's label> up to <this run's label>",
so on every run except the month's first both labels were identical and the window was
empty by construction: 0 moves, everything quiet, however much had actually landed.

The fix (user-decided 2026-08-31): each run records the notebook's sequence number in an
append-only per-category ledger, and WHAT MOVED asks "everything added since sequence N".

Reproduction (the first test below) is the real-world shape: two runs, same month label,
real new observations in between. Under the old month-window question it returns nothing.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil

import pytest

from gpu_agent.registry.horizon import IndicatorHorizons
from gpu_agent.registry.indicators import IndicatorRegistry
from gpu_agent.schema.finding import Confidence, Evidence, Finding, Impact, Kind
from gpu_agent.store import FindingStore
from gpu_agent.wiki.ingest import route_findings
from gpu_agent.wiki.marker import RunMarker, RunMarkerLedger
from gpu_agent.wiki.movement import collect_movement
from gpu_agent.wiki.store import WikiStore

MONTH = "2026-08"


def _store(tmp_path):
    return WikiStore(tmp_path / "wiki", FindingStore(tmp_path / "findings"))


def _reg_hz():
    return (IndicatorRegistry.load("registry/indicators.json"),
            IndicatorHorizons.load("registry/indicators.json"))


def _f(fid, entity, indicator_id, *, as_of=MONTH, magnitude=3, tier="primary"):
    return Finding(
        id=fid, statement="s", kind=Kind.observed, trend="flat", why="w",
        impact=Impact(targets=["x"], direction="negative", mechanism="m"),
        evidence=[Evidence(source="src", url="u", date=as_of, excerpt="e", tier=tier)],
        confidence=Confidence(level="medium", basis="b"), asOf=as_of,
        indicatorId=indicator_id, side="demand", polarityDemand=1, polaritySupply=0,
        magnitude=magnitude, entity=entity, observedAt=as_of, capturedAt=as_of + "-12")


# --------------------------------------------------------------------------- #
# 1. The regression itself
# --------------------------------------------------------------------------- #
def test_same_month_runs_report_moves_when_diffed_by_sequence(tmp_path):
    """Two runs inside one month, real new evidence between them."""
    reg, hz = _reg_hz()
    ws = _store(tmp_path)

    # --- run 1: NVIDIA enters the notebook, registered and rated.
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog")], as_of=MONTH)
    ws.update_header("entity:nvidia", as_of=MONTH, status="registered")
    ws.record_state("entity:nvidia", as_of=MONTH, state="on-track",
                    trajectory="accelerating", salience=0.9)
    marker_after_run_1 = ws.log.count()

    # --- run 2, SAME month label: AMD is a brand-new thread, NVIDIA gets fresh evidence.
    route_findings(ws, [_f("f-amd", "AMD", "rpoBacklog"),
                        _f("f-nv2", "NVDA", "rpoBacklog")], as_of=MONTH)
    ws.update_header("entity:amd", as_of=MONTH, status="registered")
    ws.record_state("entity:amd", as_of=MONTH, state="watch",
                    trajectory="softening", salience=0.8)

    # The old question — "after 2026-08, up to 2026-08" — is empty by construction.
    month_window = collect_movement(ws, as_of=MONTH, prev_as_of=MONTH,
                                    registry=reg, horizons=hz)
    assert month_window.moved == [], "precondition: the month window is empty by definition"

    # The fix: ask for everything added since run 1's marker.
    seq_window = collect_movement(ws, as_of=MONTH, prev_as_of=MONTH,
                                  since_seq=marker_after_run_1, registry=reg, horizons=hz)
    titles = {row.title for row in seq_window.moved}
    assert titles, "run 2 must report the moves that landed after run 1's marker"
    assert any("AMD" in t or "amd" in t.lower() for t in titles), (
        f"AMD is a brand-new thread in run 2 and must be reported; got {titles}")

    # And the citations must come from the sequence window too — a move whose sources
    # all fell outside the window would render as "(sources in history)".
    cited = {fid for row in seq_window.moved for fid in row.findingIds}
    assert "f-amd" in cited
    assert "f-nv1" not in cited, "run 1's evidence is before the marker; it is not new"


def test_new_page_seen_before_the_marker_is_a_change_not_a_new_thread(tmp_path):
    """A page that already existed at the marker must not be re-announced as NEW."""
    reg, hz = _reg_hz()
    ws = _store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog")], as_of=MONTH)
    ws.update_header("entity:nvidia", as_of=MONTH, status="registered")
    ws.record_state("entity:nvidia", as_of=MONTH, state="on-track",
                    trajectory="accelerating", salience=0.9)
    marker = ws.log.count()
    route_findings(ws, [_f("f-nv2", "NVDA", "rpoBacklog")], as_of=MONTH)

    diff = ws.diff(MONTH, MONTH, since_seq=marker)
    assert [p.id for p in diff.new_pages] == []
    assert [p.id for p in diff.changed_pages] == ["entity:nvidia"]
    assert diff.changed_pages[0].newFindingIds == ["f-nv2"]

    mv = collect_movement(ws, as_of=MONTH, prev_as_of=MONTH, since_seq=marker,
                          registry=reg, horizons=hz)
    assert mv.moved and mv.moved[0].newThread is False


def test_collect_movement_never_writes_when_diffing_by_sequence(tmp_path):
    reg, hz = _reg_hz()
    ws = _store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog")], as_of=MONTH)
    marker = ws.log.count()
    route_findings(ws, [_f("f-nv2", "NVDA", "rpoBacklog")], as_of=MONTH)
    before = len(ws.log.read())
    collect_movement(ws, as_of=MONTH, prev_as_of=MONTH, since_seq=marker,
                     registry=reg, horizons=hz)
    assert len(ws.log.read()) == before


def test_month_window_behaviour_is_unchanged_without_a_marker(tmp_path):
    """Back-compat: no since_seq -> the legacy month window, byte-for-byte."""
    reg, hz = _reg_hz()
    ws = _store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of="2026-07")], as_of="2026-07")
    route_findings(ws, [_f("f-nv2", "NVDA", "rpoBacklog")], as_of=MONTH)
    legacy = collect_movement(ws, as_of=MONTH, prev_as_of="2026-07", registry=reg, horizons=hz)
    assert legacy.moved, "the cross-month window still works exactly as before"
    assert legacy.restart is False


# --------------------------------------------------------------------------- #
# 2. The ledger
# --------------------------------------------------------------------------- #
def test_ledger_is_append_only_and_reads_back_in_order(tmp_path):
    ledger = RunMarkerLedger(tmp_path, "chips.merchant-gpu")
    assert ledger.read() == []
    assert ledger.latest() is None

    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=16,
                            wikiSeq=100, storyDate="2026-08-30"))
    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=17,
                            wikiSeq=140, storyDate="2026-08-31"))
    rows = ledger.read()
    assert [r.version for r in rows] == [16, 17]
    assert ledger.latest().wikiSeq == 140
    # append-only: two lines on disk, the first one byte-identical to what was written
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"version":16' in lines[0].replace(" ", "")


def test_ledger_record_is_idempotent_by_as_of_and_version(tmp_path):
    """Re-rendering the same scorecard must not append a second marker."""
    ledger = RunMarkerLedger(tmp_path, "chips.merchant-gpu")
    m = RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=17, wikiSeq=140)
    assert ledger.record(m) is True
    assert ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH,
                                   version=17, wikiSeq=999)) is False
    assert len(ledger.read()) == 1
    assert ledger.latest().wikiSeq == 140, "the first recording wins; no rewrite"


def test_ledger_marker_for_the_previous_run_excludes_this_run(tmp_path):
    ledger = RunMarkerLedger(tmp_path, "chips.merchant-gpu")
    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=16,
                            wikiSeq=100, storyDate="2026-08-30"))
    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=17,
                            wikiSeq=140, storyDate="2026-08-31"))
    prev = ledger.previous(as_of=MONTH, version=17)
    assert prev is not None and prev.wikiSeq == 100
    assert ledger.previous(as_of=MONTH, version=16) is None
    # A run with no marker of its own still gets the newest one below it.
    assert ledger.previous(as_of=MONTH, version=18).wikiSeq == 140


def test_ledger_skips_unreadable_lines_without_sinking_the_report(tmp_path):
    ledger = RunMarkerLedger(tmp_path, "chips.merchant-gpu")
    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=16,
                            wikiSeq=100))
    with ledger.path.open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    ledger.record(RunMarker(categoryId="chips.merchant-gpu", asOf=MONTH, version=17,
                            wikiSeq=140))
    assert [r.version for r in ledger.read()] == [16, 17]


# --------------------------------------------------------------------------- #
# 3. What the reader sees
# --------------------------------------------------------------------------- #
def test_restart_run_says_so_in_plain_words_and_drops_the_vs_tail():
    from gpu_agent.brief import render_what_moved
    from gpu_agent.wiki.movement import MarketMovement
    out = render_what_moved(MarketMovement(prevAsOf=None, moved=[], foldedCount=0,
                                           restart=True, storylines=[]))
    assert "change tracking restarts this run" in out
    assert "this run sets the new starting point" in out
    assert "resumes next cycle" in out
    # Q2, user-decided: no "(vs ...)" tail on the restart run's header.
    assert "(vs " not in out
    # And it must NOT read as "the market was quiet".
    assert "nothing new cleared the materiality bar" not in out
    assert "no material moves" not in out


def test_comparison_point_is_named_by_run_date_when_known():
    from gpu_agent.brief import render_what_moved
    from gpu_agent.wiki.movement import MarketMovement
    out = render_what_moved(MarketMovement(prevAsOf=MONTH, prevRunDate="2026-08-30",
                                           moved=[], foldedCount=0, storylines=[]))
    assert "(vs the 2026-08-30 run)" in out
    # Without a date it still falls back to the period label — no crash, no blank.
    out2 = render_what_moved(MarketMovement(prevAsOf=MONTH, moved=[], foldedCount=0,
                                            storylines=[]))
    assert f"(vs {MONTH})" in out2


# --------------------------------------------------------------------------- #
# 4. End to end through the real report handler
# --------------------------------------------------------------------------- #
FIX_MONTH = "2026-06"
CATEGORY = "chips.merchant-gpu"


def _seed_store(tmp_path):
    """A store with two same-month scorecards (v1 then v2) and a notebook."""
    store = tmp_path / "store"
    cat = store / CATEGORY
    cat.mkdir(parents=True)
    shutil.copy("fixtures/report/legacy-prior.json", cat / f"{FIX_MONTH}-v1.json")
    shutil.copy("fixtures/report/legacy-current.json", cat / f"{FIX_MONTH}-v2.json")
    ws = WikiStore(store / "wiki", FindingStore(store / "findings"))
    return store, ws


def _render(store, version, **over):
    args = argparse.Namespace(
        scorecard=str(store / CATEGORY / f"{FIX_MONTH}-v{version}.json"),
        prior=None, no_prior=False, store=str(store),
        registry="registry/indicators.json", out=None,
        render_ts=f"2026-06-0{version}T00:00:00Z",
    )
    for k, v in over.items():
        setattr(args, k, v)
    buf = io.StringIO()
    from gpu_agent import cli
    with contextlib.redirect_stdout(buf):
        rc = cli._report(args)
    assert rc == 0
    return buf.getvalue()


def _ledger_lines(store):
    p = store / CATEGORY / "run-markers.jsonl"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_report_first_run_restarts_then_second_run_reports_real_moves(tmp_path):
    """The whole point, end to end: two runs, one month, moves actually reported."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    ws.update_header("entity:nvidia", as_of=FIX_MONTH, status="registered")
    ws.record_state("entity:nvidia", as_of=FIX_MONTH, state="on-track",
                    trajectory="accelerating", salience=0.9)

    # Run 1 (v2 against prior v1): no marker on disk yet -> honest restart, marker laid down.
    first = _render(store, 2)
    assert "change tracking restarts this run" in first
    assert len(_ledger_lines(store)) == 1

    # New evidence lands, SAME month label.
    route_findings(ws, [_f("f-amd", "AMD", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    ws.update_header("entity:amd", as_of=FIX_MONTH, status="registered")
    ws.record_state("entity:amd", as_of=FIX_MONTH, state="watch",
                    trajectory="softening", salience=0.8)

    # Run 2: a new scorecard version in the same month — the case that was broken.
    shutil.copy(store / CATEGORY / f"{FIX_MONTH}-v2.json",
                store / CATEGORY / f"{FIX_MONTH}-v3.json")
    second = _render(store, 3)
    assert "change tracking restarts this run" not in second
    what_moved = second.split("WHAT MOVED SINCE LAST RUN", 1)[1].split("\n\n", 1)[0]
    assert "nothing new cleared the materiality bar" not in what_moved, (
        "this is the F135 defect: a same-month run reporting zero moves despite new events")
    assert "amd" in what_moved.lower()
    # It names the run it compared against, not the month.
    assert "(vs the 2026-06-02 run)" in what_moved
    assert len(_ledger_lines(store)) == 2


def test_re_rendering_the_same_scorecard_appends_no_second_marker(tmp_path):
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    a = _render(store, 2)
    lines_after_first = _ledger_lines(store)
    b = _render(store, 2)
    assert _ledger_lines(store) == lines_after_first, "append-only ledger grew on a replay"
    assert a == b, "a $0 replay of the same scorecard must be byte-identical"


def test_no_marker_flag_leaves_the_ledger_untouched(tmp_path):
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    _render(store, 2, no_marker=True)
    assert _ledger_lines(store) == [], "--no-marker must not write to the store"
    assert not (store / CATEGORY / "run-markers.jsonl").exists()


def test_marker_records_the_notebook_position_and_the_run_identity(tmp_path):
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    expected_seq = ws.log.count()
    _render(store, 2)
    row = json.loads(_ledger_lines(store)[0])
    assert row == {"categoryId": CATEGORY, "asOf": FIX_MONTH, "version": 2,
                   "wikiSeq": expected_seq, "storyDate": "2026-06-02"}


def test_no_wiki_store_means_no_ledger_and_no_crash(tmp_path):
    """A store without a notebook renders exactly as before and writes nothing."""
    store = tmp_path / "store"
    cat = store / CATEGORY
    cat.mkdir(parents=True)
    shutil.copy("fixtures/report/legacy-prior.json", cat / f"{FIX_MONTH}-v1.json")
    shutil.copy("fixtures/report/legacy-current.json", cat / f"{FIX_MONTH}-v2.json")
    out = _render(store, 2)
    assert "CATEGORY REPORT" in out
    assert _ledger_lines(store) == []


def test_marker_is_not_recorded_when_the_report_is_never_delivered(tmp_path):
    """A run that dies before the reader sees the report must NOT advance the starting
    point — otherwise the next run begins after those events and nobody ever hears about
    them. --out into a missing directory is the concrete failure."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    with pytest.raises((OSError, FileNotFoundError)):
        _render(store, 2, out=str(tmp_path / "no-such-dir" / "report.txt"))
    assert _ledger_lines(store) == [], (
        "the watermark advanced even though the report was never delivered")


def test_no_prior_render_neither_reads_nor_writes_a_marker(tmp_path):
    """--no-prior is a standalone read of one scorecard, not a cycle run."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    out = _render(store, 2, no_prior=True)
    assert _ledger_lines(store) == [], "--no-prior must not lay down a watermark"
    assert "no prior cycle to compare" in out

    # And it must not have consumed an existing marker either: the real cycle render that
    # follows still sees the restart state and records the marker itself.
    real = _render(store, 2)
    assert "change tracking restarts this run" in real
    assert len(_ledger_lines(store)) == 1


def test_ad_hoc_scorecard_filename_says_so_instead_of_claiming_nothing_moved(tmp_path):
    """An off-convention filename cannot be placed in the run chain. It must not fall back
    to the month window — that prints the very sentence F135 exists to stop."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    ad_hoc = store / CATEGORY / "scratch-copy.json"
    shutil.copy(store / CATEGORY / f"{FIX_MONTH}-v2.json", ad_hoc)
    args = argparse.Namespace(
        scorecard=str(ad_hoc), prior=str(store / CATEGORY / f"{FIX_MONTH}-v1.json"),
        no_prior=False, store=str(store), registry="registry/indicators.json",
        out=None, render_ts="2026-06-02T00:00:00Z")
    buf = io.StringIO()
    from gpu_agent import cli
    with contextlib.redirect_stdout(buf):
        assert cli._report(args) == 0
    out = buf.getvalue()
    assert "nothing new cleared the materiality bar" not in out
    assert "change tracking restarts this run" in out
    assert _ledger_lines(store) == [], "an ad-hoc render must not write a marker"


def test_unwritable_ledger_warns_but_still_delivers_the_report(tmp_path, monkeypatch):
    """A damaged watermark must never cost the executive the report."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)

    def _boom(self, marker):
        raise OSError("disk is read-only")

    monkeypatch.setattr(RunMarkerLedger, "record", _boom)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = _render(store, 2)
    assert "CATEGORY REPORT" in out, "the report must still be delivered"
    assert "could not record the run marker" in err.getvalue()


def test_watermark_ignores_events_stamped_with_a_later_period(tmp_path):
    """The window is bounded by the period label, so the watermark must be too — an event
    already stamped with next month's label is outside this run's window and must not be
    left behind the next run's watermark either."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    in_window = ws.seq_watermark(FIX_MONTH)
    route_findings(ws, [_f("f-next", "AMD", "rpoBacklog", as_of="2026-07")], as_of="2026-07")
    assert ws.seq_watermark(FIX_MONTH) == in_window, (
        "a later-period event must not advance this run's watermark")
    assert ws.seq_watermark("2026-07") > in_window

    _render(store, 2)
    assert json.loads(_ledger_lines(store)[0])["wikiSeq"] == in_window


def test_state_transition_is_reconstructed_from_before_the_marker(tmp_path):
    """The subtlest new function: a page's state as it stood AT the marker, which the
    period-label lookup cannot answer because every event that month shares one label."""
    reg, hz = _reg_hz()
    ws = _store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=MONTH)], as_of=MONTH)
    ws.record_state("entity:nvidia", as_of=MONTH, state="on-track",
                    trajectory="accelerating", salience=0.9)
    marker = ws.log.count()
    route_findings(ws, [_f("f-nv2", "NVDA", "rpoBacklog", as_of=MONTH)], as_of=MONTH)
    ws.record_state("entity:nvidia", as_of=MONTH, state="at-risk",
                    trajectory="softening", salience=0.5)

    diff = ws.diff(MONTH, MONTH, since_seq=marker)
    assert diff.changed_pages[0].stateTransition == {"from": "on-track", "to": "at-risk"}
    move = diff.index_moves[0]
    assert (move.oldState, move.newState) == ("on-track", "at-risk")
    assert (move.oldTrajectory, move.newTrajectory) == ("accelerating", "softening")

    mv = collect_movement(ws, as_of=MONTH, prev_as_of=MONTH, since_seq=marker,
                          registry=reg, horizons=hz)
    row = next(r for r in mv.moved if r.stateFrom)
    assert (row.stateFrom, row.stateTo) == ("on-track", "at-risk")


def test_report_writes_only_the_marker_ledger_into_the_store(tmp_path):
    """Write discipline: the report's one and only store write is the marker line."""
    store, ws = _seed_store(tmp_path)
    route_findings(ws, [_f("f-nv1", "NVDA", "rpoBacklog", as_of=FIX_MONTH)], as_of=FIX_MONTH)
    before = {p: p.stat().st_mtime_ns for p in store.rglob("*") if p.is_file()}
    _render(store, 2)
    after = {p for p in store.rglob("*") if p.is_file()}
    assert after - set(before) == {store / CATEGORY / "run-markers.jsonl"}
    for p, mtime in before.items():
        assert p.stat().st_mtime_ns == mtime, f"report modified an existing store file: {p}"
