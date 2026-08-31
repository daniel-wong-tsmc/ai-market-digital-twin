from __future__ import annotations
import pathlib
import re
from typing import Optional
from pydantic import BaseModel
from gpu_agent.schema.finding import Finding
from gpu_agent.wiki.page import WikiPage, dump_page, load_page
from gpu_agent.wiki.log import WikiLog, LogEvent, Observation, StateChange

_ALLOWED_HEADER_FIELDS = {"title", "category", "status", "crossRefs"}
_ALLOWED_PAGE_TYPES = {"entity", "theme"}
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PageNotFound(KeyError):
    """Raised when a wiki page id is not present."""


class DuplicatePage(ValueError):
    """Raised when create_page targets an existing page."""


class FindingNotGated(ValueError):
    """Raised when append_observation references a finding absent from the FindingStore."""


class ResolvedObservation(BaseModel):
    asOf: str
    finding: Finding


class WindowView(BaseModel):
    page: WikiPage
    body: str
    observations: list[ResolvedObservation]


class IndexEntry(BaseModel):
    id: str
    type: str
    title: str
    category: Optional[str]
    status: str
    state: str
    trajectory: str
    salience: float
    lastUpdatedAsOf: str
    observationCount: int
    oneLine: str


class PageDelta(BaseModel):
    id: str
    title: str
    newFindingIds: list[str] = []
    stateTransition: Optional[dict] = None


class IndexMove(BaseModel):
    id: str
    oldState: str
    newState: str
    oldTrajectory: str
    newTrajectory: str
    oldSalience: float
    newSalience: float


class WikiDiff(BaseModel):
    new_pages: list[PageDelta] = []
    changed_pages: list[PageDelta] = []
    quiet_pages: list[str] = []
    index_moves: list[IndexMove] = []


class WikiStore:
    """LLM-wiki thread store: living markdown pages + an append-only log."""

    def __init__(self, root, finding_store):
        self.root = pathlib.Path(root)
        self.findings = finding_store
        self.log = WikiLog(self.root / "log.jsonl")

    # --- persistence helpers ---
    def _page_path(self, page_id: str) -> pathlib.Path:
        ptype, _, slug = page_id.partition(":")
        # F41b: ptype/slug become path segments below; an unvalidated slug (e.g. "../escape")
        # can walk out of self.root. Only the two known page types and a safe slug shape
        # (lowercase alnum + internal dashes, matching what wiki/ingest.py's slug() ever
        # produces) are allowed.
        if ptype not in _ALLOWED_PAGE_TYPES or not _SAFE_SLUG.match(slug):
            raise ValueError(f"unsafe page id: {page_id!r}")
        return self.root / ptype / f"{slug}.md"

    def _read(self, page_id: str) -> tuple[WikiPage, str]:
        path = self._page_path(page_id)
        if not path.exists():
            raise PageNotFound(page_id)
        return load_page(path.read_text(encoding="utf-8"))

    def _write(self, page: WikiPage, body: str) -> None:
        path = self._page_path(page.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_page(page, body), encoding="utf-8")

    # --- mutate ---
    def create_page(self, id, type, title, category=None, *, as_of, body="") -> WikiPage:
        if self._page_path(id).exists():
            raise DuplicatePage(id)
        page = WikiPage(id=id, type=type, title=title, category=category,
                        createdAsOf=as_of, lastUpdatedAsOf=as_of)
        self._write(page, body)
        self.log.append(asOf=as_of, kind="create-page", pageId=id)
        return page

    def update_header(self, page_id, *, as_of, **fields) -> WikiPage:
        bad = set(fields) - _ALLOWED_HEADER_FIELDS
        if bad:
            raise ValueError(f"update_header: disallowed fields {sorted(bad)}")
        page, body = self._read(page_id)
        changed = [f"{k}: {getattr(page, k)} -> {fields[k]}"
                  for k in sorted(fields) if getattr(page, k) != fields[k]]
        page = page.model_copy(update={**fields, "lastUpdatedAsOf": as_of})
        self._write(page, body)
        if changed:
            # F30: promotions (and any other header edit) leave a log event instead of
            # mutating silently.
            self.log.append(asOf=as_of, kind="header-change", pageId=page_id,
                            detail=", ".join(changed))
        return page

    def append_observation(self, page_id, finding_id, *, as_of) -> WikiPage:
        page, body = self._read(page_id)
        if not self.findings.exists(finding_id):
            raise FindingNotGated(finding_id)
        page = page.model_copy(update={"lastUpdatedAsOf": as_of})
        self._write(page, body)
        self.log.append(asOf=as_of, kind="append-observation",
                        pageId=page_id, findingId=finding_id)
        return page

    def record_state(self, page_id, *, as_of, state, trajectory, salience, finding_id=None) -> WikiPage:
        page, body = self._read(page_id)
        page = page.model_copy(update={"state": state, "trajectory": trajectory,
                                       "salience": salience, "lastUpdatedAsOf": as_of})
        self._write(page, body)
        self.log.append(asOf=as_of, kind="state-change", pageId=page_id,
                        findingId=finding_id, state=state, trajectory=trajectory,
                        salience=salience)
        return page

    def set_body(self, page_id, body, *, as_of) -> WikiPage:
        """Replace a page's curated markdown body, bumping lastUpdatedAsOf. Idempotent:
        an unchanged body is not rewritten. Raises PageNotFound. No log event (body edits
        are not temporal observations; the ingest run's event covers them)."""
        page, current_body = self._read(page_id)
        if body == current_body:
            return page
        page = page.model_copy(update={"lastUpdatedAsOf": as_of})
        self._write(page, body)
        return page

    def log_append(self, event: LogEvent) -> None:
        self.log.append_event(event)

    def _events_for(self, page_id, kind) -> list[LogEvent]:
        # F25: the per-page index avoids scanning the whole log per page.
        evs = [e for e in self.log.events_for_page(page_id) if e.kind == kind]
        return sorted(evs, key=lambda e: (e.asOf, e.seq))

    def _body(self, page_id: str) -> str:
        """The page's markdown body (no observation resolution). Raises PageNotFound."""
        return self._read(page_id)[1]

    def observations(self, page_id) -> list[Observation]:
        self._read(page_id)  # raises PageNotFound if absent
        return [Observation(asOf=e.asOf, findingId=e.findingId)
                for e in self._events_for(page_id, "append-observation")]

    def seq_watermark(self, as_of) -> int:
        """Where a run that reported up to `as_of` leaves the notebook (F135): one past the
        highest sequence number among events at or before that period label.

        Deliberately NOT the raw event count. `diff` bounds its window with
        `e.asOf <= as_of`, so an event already stamped with a LATER label is outside this
        run's window; counting it here would also put it behind the next run's watermark
        and it would never be reported by anyone."""
        seqs = [e.seq for e in self.log.read() if e.asOf <= as_of]
        return max(seqs) + 1 if seqs else 0

    def observations_since(self, page_id, since_seq, *, up_to_as_of=None) -> list[Observation]:
        """The page's observations numbered `since_seq` or higher (F135). The sequence
        twin of the period-label window `observations()` callers used to slice by hand —
        needed because within one month every observation carries the same label."""
        self._read(page_id)  # raises PageNotFound if absent
        return [Observation(asOf=e.asOf, findingId=e.findingId)
                for e in self._events_for(page_id, "append-observation")
                if e.seq >= since_seq and (up_to_as_of is None or e.asOf <= up_to_as_of)]

    def state_history(self, page_id) -> list[StateChange]:
        self._read(page_id)
        return [StateChange(asOf=e.asOf, state=e.state, trajectory=e.trajectory,
                            salience=e.salience, findingId=e.findingId)
                for e in self._events_for(page_id, "state-change")]

    def window(self, page_id, n) -> WindowView:
        page, body = self._read(page_id)
        all_obs = self.observations(page_id)
        recent = all_obs[-n:] if n > 0 else []
        resolved = [ResolvedObservation(asOf=o.asOf, finding=self.findings.get(o.findingId))
                    for o in recent]
        return WindowView(page=page, body=body, observations=resolved)

    def index(self) -> list[IndexEntry]:
        entries: list[IndexEntry] = []
        for ptype in ("entity", "theme"):
            d = self.root / ptype
            if not d.exists():
                continue
            for path in d.glob("*.md"):
                page, _ = load_page(path.read_text(encoding="utf-8"))
                count = len(self._events_for(page.id, "append-observation"))
                one = f"{page.title} — {page.state or 'no-state'} ({page.trajectory or 'n/a'})"
                entries.append(IndexEntry(
                    id=page.id, type=page.type, title=page.title, category=page.category,
                    status=page.status, state=page.state, trajectory=page.trajectory,
                    salience=page.salience, lastUpdatedAsOf=page.lastUpdatedAsOf,
                    observationCount=count, oneLine=one))
        return sorted(entries, key=lambda e: ((e.category or ""), e.id))

    def _state_at(self, events, on_or_before):
        sc = [e for e in events if e.kind == "state-change" and e.asOf <= on_or_before]
        if not sc:
            return None
        last = sorted(sc, key=lambda e: (e.asOf, e.seq))[-1]
        return {"state": last.state, "trajectory": last.trajectory, "salience": last.salience}

    def _state_before_seq(self, events, seq):
        """The page's state as it stood at sequence number `seq` — i.e. the last
        state-change recorded strictly before it (F135). The period-label variant above
        cannot answer this: within one month every event carries the same label."""
        sc = [e for e in events if e.kind == "state-change" and e.seq < seq]
        if not sc:
            return None
        last = sorted(sc, key=lambda e: e.seq)[-1]
        return {"state": last.state, "trajectory": last.trajectory, "salience": last.salience}

    def _title_or(self, page_id):
        try:
            return self.get_page(page_id).title
        except PageNotFound:
            return page_id

    def diff(self, as_of, prev_as_of, *, since_seq=None) -> WikiDiff:
        """Pages that appeared or changed inside a window.

        Two ways to name the window:

        - By PERIOD LABEL (the original): "after `prev_as_of`, up to `as_of`". Correct only
          when the two labels differ. Because every event carries the scorecard's period
          label and that label is the month, two runs in one month ask an empty question —
          the F135 defect.
        - By SEQUENCE (`since_seq`, F135): "every event numbered `since_seq` or higher".
          `since_seq` is the notebook's event count at the end of the previous run, taken
          from that run's marker. This works within a single month and needs nothing new
          on disk in the notebook itself.

        `prev_as_of` is still accepted (and still names the prior scorecard for display and
        for the caller's scoring) when `since_seq` is given; it just no longer picks the
        window."""
        by_page: dict[str, list] = {}
        for e in self.log.read():
            if e.pageId:
                by_page.setdefault(e.pageId, []).append(e)
        result = WikiDiff()
        for pid, evs in sorted(by_page.items()):
            evs = sorted(evs, key=lambda e: (e.asOf, e.seq))
            existed_now = any(e.asOf <= as_of for e in evs)
            if not existed_now:
                continue
            if since_seq is None:
                existed_prev = any(e.asOf <= prev_as_of for e in evs)
                window = [e for e in evs if prev_as_of < e.asOf <= as_of]
                prev_state_fn = lambda evs=evs: self._state_at(evs, prev_as_of)
            else:
                existed_prev = any(e.seq < since_seq for e in evs)
                window = [e for e in evs if e.seq >= since_seq and e.asOf <= as_of]
                prev_state_fn = lambda evs=evs: self._state_before_seq(evs, since_seq)
            new_findings = [e.findingId for e in window
                            if e.kind == "append-observation" and e.findingId]
            now_state = self._state_at(evs, as_of) or {}
            title = self._title_or(pid)
            if not existed_prev:
                trans = {"from": "", "to": now_state.get("state", "")} if now_state else None
                result.new_pages.append(PageDelta(id=pid, title=title,
                                                newFindingIds=new_findings, stateTransition=trans))
                continue
            if not window:
                result.quiet_pages.append(pid)
                continue
            prev_state = prev_state_fn() or {}
            trans = None
            if prev_state.get("state") != now_state.get("state"):
                trans = {"from": prev_state.get("state", ""), "to": now_state.get("state", "")}
            result.changed_pages.append(PageDelta(id=pid, title=title,
                                                newFindingIds=new_findings, stateTransition=trans))
            if prev_state != now_state and now_state:
                result.index_moves.append(IndexMove(
                    id=pid,
                    oldState=prev_state.get("state", ""), newState=now_state.get("state", ""),
                    oldTrajectory=prev_state.get("trajectory", ""), newTrajectory=now_state.get("trajectory", ""),
                    oldSalience=prev_state.get("salience", 0.0), newSalience=now_state.get("salience", 0.0)))
        result.index_moves.sort(key=lambda m: abs(m.newSalience - m.oldSalience), reverse=True)
        return result

    # --- read ---
    def get_page(self, page_id) -> WikiPage:
        return self._read(page_id)[0]
