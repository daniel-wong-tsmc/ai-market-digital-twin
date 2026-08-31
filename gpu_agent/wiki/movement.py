"""gpu_agent/wiki/movement.py — read-only collector for the brief's store-fed sections
(sub-project 4-5b). Assembles WHAT MOVED (ranked material moves) + STORYLINES (page
state/trajectory) from the wiki store as a plain MarketMovement value. No LLM, no store
write (never calls lint())."""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field
from gpu_agent.wiki.lint import score_moves, _contradictions_for, DEFAULT_LINT_CONFIG
from gpu_agent.wiki.lifecycle import partition_canonical


class MovedRow(BaseModel):
    title: str
    findingIds: list[str] = Field(default_factory=list)
    tier: Literal["primary", "secondary"]
    provisional: bool
    newThread: bool
    contradiction: bool
    contradictionNote: str = ""
    stateFrom: Optional[str] = None
    stateTo: Optional[str] = None
    score: float


class StorylineRow(BaseModel):
    title: str
    state: str
    trajectory: str
    lastUpdatedAsOf: str
    salience: float
    provisional: bool


class MarketMovement(BaseModel):
    prevAsOf: Optional[str] = None
    moved: list[MovedRow] = Field(default_factory=list)
    foldedCount: int = 0
    storylines: list[StorylineRow] = Field(default_factory=list)
    # F135. `restart` is the honest state for the first run after the change-tracking fix:
    # there is no earlier run marker to measure from, so this run sets the starting point
    # and the list resumes next cycle. It is NOT "nothing moved" and must not read as it.
    restart: bool = False
    # The calendar date of the run being compared against, when known — so the section can
    # name the actual run instead of the month label that caused the defect.
    prevRunDate: Optional[str] = None


def _moved_row(m, one_by_id) -> MovedRow:
    st = m.factors.stateTransition or {}
    return MovedRow(
        title=one_by_id.get(m.pageId, m.title),
        findingIds=list(m.contributingFindingIds),
        tier="primary" if m.tierMult >= 0.8 else "secondary",
        provisional=(m.status != "registered"),
        newThread=m.factors.newThread,
        contradiction=m.factors.contradiction,
        contradictionNote=m.factors.contradictionNote,
        stateFrom=st.get("from"),
        stateTo=st.get("to"),
        score=m.score)


def _storyline_rows(entries, *, provisional) -> list[StorylineRow]:
    # Row order is a display concern owned by render_storylines (which sorts each group);
    # the collector returns index order (sorted by category, id).
    return [StorylineRow(title=e.title, state=e.state, trajectory=e.trajectory,
                         lastUpdatedAsOf=e.lastUpdatedAsOf, salience=e.salience,
                         provisional=provisional) for e in entries]


def collect_movement(store, *, as_of, prev_as_of, registry, horizons,
                     config=DEFAULT_LINT_CONFIG, since_seq=None, restart=False,
                     prev_run_date=None) -> MarketMovement:
    """Read-only. WHAT MOVED via diff + score_moves (only when there is something to
    compare against); STORYLINES via index + partition_canonical. Never writes (never
    calls lint()).

    Three ways to name the comparison window, in the order they are tried:

    - `restart=True` (F135): no earlier run marker exists, so there is honestly nothing to
      diff against. Returns an empty `moved` list flagged `restart` — the renderer says so
      in plain words rather than implying the market was quiet.
    - `since_seq` (F135, the production path): diff by notebook sequence number, which
      works for two runs inside one calendar month. `prev_as_of` still names the prior
      scorecard for display; it no longer picks the window.
    - `prev_as_of` alone: the original period-label window. Correct only across periods,
      kept for callers that legitimately compare month to month.
    """
    index = store.index()
    one_by_id = {e.id: e.oneLine for e in index}
    moved: list[MovedRow] = []
    folded = 0
    if restart:
        return MarketMovement(prevAsOf=None, moved=[], foldedCount=0, restart=True,
                              storylines=_all_storyline_rows(index))
    if since_seq is not None or prev_as_of is not None:
        diff = store.diff(as_of, prev_as_of, since_seq=since_seq)
        contradictions = _contradictions_for(store, as_of)
        material, dropped = score_moves(store, diff, contradictions, as_of=as_of,
                                        prev_as_of=prev_as_of, registry=registry,
                                        horizons=horizons, config=config,
                                        since_seq=since_seq)
        material.sort(key=lambda m: (-m.score, m.pageId))   # byte-stable tiebreak
        moved = [_moved_row(m, one_by_id) for m in material]
        folded = len(dropped)
    return MarketMovement(prevAsOf=prev_as_of, moved=moved, foldedCount=folded,
                          prevRunDate=prev_run_date,
                          storylines=_all_storyline_rows(index))


def _all_storyline_rows(index) -> list[StorylineRow]:
    registered, provisional = partition_canonical(index)
    return (_storyline_rows(registered, provisional=False)
            + _storyline_rows(provisional, provisional=True))
