"""gpu_agent/fetch_policy.py -- F117 + F126: who we may fetch, and who we
must not.

Two different things make a domain one this desk should not read, and they
are NOT the same thing:

`publisher-objection`
    The publisher asked not to be used at all. Posture doc section 3(4).
    Hard refusal: the fetch runner refuses the request outright, and the
    chart verifier rejects a cited point before a single request goes out.
    Nothing on this list is ever fetched or cited again.

`blocks-plain-readers`
    The site turns the verifier's plain automated reader away (HTTP 401,
    403 or 429). This is a technical fact, not a permission problem, so
    it does NOT stop a gatherer reading the page for a claim. It means a
    researched chart point sourced there can never verify, so the
    researcher's brief names the domain and the verifier's failure line
    says "blocked" rather than burying it in "unreachable".

Both kinds live in ONE file, `registry/do-not-fetch.json`, sorted by domain,
because a person looking for "may we read this site?" should have one place
to look. That file is deliberately NOT `registry/licensed-sources.json`,
which means something else entirely (publishers whose material the desk holds
a licence to) and which D6 stopped treating as a refusal list.

Nothing here raises. A missing, unreadable or malformed registry is an EMPTY
registry, and a failed learned-append is swallowed: a policy file that can
strand an unattended cycle is worse than no policy file.

This module is a STDLIB-ONLY LEAF on purpose. The fetch runner
(`gpu_agent.gathering.webreach`, which needs pydantic and subprocess), the
chart verifier and the researcher's prompt builder all import it, and none of
them should drag the others' dependencies along. That is also why the one
host matcher this repo has -- `matching_domain` -- lives here rather than in
the fetch runner: the licensed list and the do-not-fetch list must never
disagree about what "the same site" means.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

DO_NOT_FETCH_REGISTRY = pathlib.Path("registry/do-not-fetch.json")

KIND_OBJECTION = "publisher-objection"
KIND_BLOCKS_READERS = "blocks-plain-readers"
KINDS = (KIND_OBJECTION, KIND_BLOCKS_READERS)

# Written into an entry the verifier learned for itself, so a reader of the
# file can tell it from a line a person typed (which also carries no
# `firstSeenUrl`).
LEARNED_WHY = ("learned automatically: the verifier's plain reader was turned "
               "away (HTTP 401/403/429)")

# Fixed key order for every row written back, so a learned append is a
# one-line diff rather than a whole-file reformat.
_KEY_ORDER = ("domain", "kind", "since", "why", "firstSeenUrl")


def matching_domain(target: str, domains: Iterable[str]) -> str | None:
    """The domain in `domains` that `target`'s host matches -- exact host or
    dot-suffix subdomain -- or None when it matches none of them.

    Reads `parsed.hostname` rather than `parsed.netloc` so a port and any
    `user:pass@` prefix cannot hide the real host (this feeds refusal
    decisions), and returns None for anything that is not a fetchable http(s)
    URL at all -- a free-text search target, a `file://` path, a bare
    `example.test/x` with no scheme.

    `domains` is iterated in sorted order so the answer is deterministic when
    a host could match two listed domains (`b.example.com` and `example.com`);
    the alphabetically first wins, and both are correct answers to "is this
    site listed?".
    """
    try:
        parsed = urlparse(target)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:   # malformed IPv6 literal, e.g. "https://[oops/"
        return None
    if not host:
        return None
    for dom in sorted(d.lower() for d in domains):
        if host == dom or host.endswith("." + dom):
            return dom
    return None


@dataclass(frozen=True)
class DoNotFetchEntry:
    """One domain we must not read, and why. `firstSeenUrl` is set only on an
    entry the verifier learned for itself -- the page that proved the block."""
    domain: str
    kind: str
    since: str
    why: str
    firstSeenUrl: str | None = None


class DoNotFetchRegistry:
    """The loaded do-not-fetch list. Entries are held sorted by domain."""

    def __init__(self, entries: list[DoNotFetchEntry] | None = None) -> None:
        self.entries = sorted(entries or [], key=lambda e: e.domain)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def domains(self, kind: str | None = None) -> list[str]:
        """Listed domains, sorted; `kind=None` means both kinds."""
        return sorted(e.domain for e in self.entries
                      if kind is None or e.kind == kind)

    def match(self, target: str, kind: str | None = None) -> DoNotFetchEntry | None:
        """The entry `target`'s host is listed under, or None. `kind` narrows
        the search to one kind -- which is the whole point of the kinds: a
        `publisher-objection` lookup must not be answered by a
        `blocks-plain-readers` entry, since only the first is a refusal."""
        pool = [e for e in self.entries if kind is None or e.kind == kind]
        dom = matching_domain(target, [e.domain for e in pool])
        if dom is None:
            return None
        return next((e for e in pool if e.domain == dom), None)


def _row(entry: DoNotFetchEntry) -> dict:
    """One entry as it is written back: fixed key order, and `firstSeenUrl`
    omitted entirely (never `null`) when there isn't one."""
    row = {"domain": entry.domain, "kind": entry.kind, "since": entry.since,
           "why": entry.why}
    if entry.firstSeenUrl:
        row["firstSeenUrl"] = entry.firstSeenUrl
    return {k: row[k] for k in _KEY_ORDER if k in row}


def load_do_not_fetch(path=DO_NOT_FETCH_REGISTRY) -> DoNotFetchRegistry:
    """The registry at `path`, or an EMPTY registry when the file is missing,
    unreadable or malformed. Never raises.

    A row with a blank domain or an unrecognised `kind` is DROPPED rather than
    trusted: a typo'd kind must not become a silent third policy.
    """
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DoNotFetchRegistry()
    rows = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return DoNotFetchRegistry()
    out: list[DoNotFetchEntry] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        domain = str(r.get("domain") or "").strip().lower()
        kind = r.get("kind")
        if not domain or kind not in KINDS:
            continue
        first_seen = r.get("firstSeenUrl")
        out.append(DoNotFetchEntry(
            domain=domain, kind=kind,
            since=str(r.get("since") or ""), why=str(r.get("why") or ""),
            firstSeenUrl=str(first_seen) if first_seen else None))
    return DoNotFetchRegistry(out)


def record_blocked_domain(path, domain: str, *, since: str,
                          first_seen_url: str | None = None,
                          why: str | None = None) -> bool:
    """Append `domain` to `path` as a `blocks-plain-readers` entry, keeping the
    file sorted by domain. Returns True when the file changed.

    Returns False and changes nothing when:

    - the domain is already listed under EITHER kind. Idempotence is what makes
      this safe to call on every cycle -- and skipping a domain already listed
      as `publisher-objection` is deliberate: an objection must never be
      quietly downgraded to a mere technical block.
    - the write fails. A read-only checkout, a locked file or a path that is a
      directory must not break a cycle, so the failure is swallowed and the
      caller simply learns nothing this time.

    `since` is supplied by the caller rather than read from the clock: the
    verifier passes the STORY date, so re-running a cycle produces the same
    bytes.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return False
    path = pathlib.Path(path)
    reg = load_do_not_fetch(path)
    if any(e.domain == domain for e in reg.entries):
        return False
    rows = [_row(e) for e in reg.entries]
    rows.append(_row(DoNotFetchEntry(
        domain=domain, kind=KIND_BLOCKS_READERS, since=since,
        why=why or LEARNED_WHY, firstSeenUrl=first_seen_url)))
    rows.sort(key=lambda r: r["domain"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "entries": rows}, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True
