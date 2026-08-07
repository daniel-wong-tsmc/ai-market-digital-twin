"""gpu_agent/chartdata/verify.py -- F113 Task 4: the deterministic verifier
and the quarantine store.

This module is the TRUST GATE of F113. A research agent can be wrong, lazy or
credulous, so nothing it hands back is believed on its word: for every claimed
data point we fetch the page the agent said the number came from, reduce it to
the text a reader would actually see, and re-find the number there. If a
single point cannot be re-found, the WHOLE candidate is rejected -- there are
no partial charts (spec section 4).

Three properties this module must never lose:

1. **Same numeric truth as the rest of the repo.** The rounding tolerance is
   NOT re-implemented here. `numeric_tokens` / `supported` are imported from
   `gpu_agent.numeric_tokens` -- the shared tokenizer module that the F66
   citation audit (`gpu_agent/citation_audit.py`, which imports these very
   names on its line 36) and the F14 wiki gate both use. Importing from that
   module rather than re-exporting through `citation_audit` keeps this a leaf
   dependency and leaves the audit module untouched; it is the same single
   source of numeric truth either way.

2. **Never blocks the cycle.** `accept_research` NEVER raises and the CLI
   handler always exits 0. An unreachable page, a malformed answer file, a
   store with no story in it -- all of them degrade to "this candidate is
   rejected", never to a crashed daily run.

3. **Quarantine, not registry.** Verified candidates are written to
   `store/<cat>/research-series/`, which is deliberately separate from the
   human-curated `registry/chart-series.json`. This module adds NO writer to
   that registry, and never will: promotion is a human edit (spec section 5).

Records written here carry NO wall-clock field. The story date IS the
timestamp, so a rerun of the same cycle produces byte-identical bytes.
"""
from __future__ import annotations

import decimal
import html as _html
import ipaddress
import json
import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from gpu_agent.chartdata.fetch import _default_fetch_html
from gpu_agent.chartdata.research import CandidateSeries
from gpu_agent.dashboard.export_json import _latest_story
from gpu_agent.numeric_tokens import numeric_tokens, supported
from gpu_agent.wiki.ingest import slug

# The honest give-up answer the research prompt asks for (research_prompt.py).
_NO_SERIES_TOKEN = "NO-SERIES-FOUND"

# `bullet-<n>.json` -- the SAME numbering emit_research uses for its prompts.
_ANSWER_RE = re.compile(r"^bullet-(\d+)\.json$")

# Script and style bodies are not text a reader ever sees: analytics blobs,
# ad tags and build metadata are full of numbers that would otherwise be
# usable as fake backing for a claimed point. Dropped body-and-all, before
# tags are stripped.
#
# The closing tag is OPTIONAL (`|$`): an UNCLOSED `<script>` used to defeat
# the exclusion entirely and leak its numbers back into the pool (review
# finding). An unclosed script runs to the end of the document, so that is
# exactly what is dropped. The alternation is ordered close-tag-first and the
# body is lazy, so a properly closed block still ends at its own `</script>`
# and later page text survives untouched.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|$)", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]*>", re.S)

# `sourceUrl` is written by an LLM, not by the human-curated registry F110's
# fetcher was fed from, and the default fetcher is a bare `urlopen`. Anything
# that is not plain http(s) -- `file://`, `ftp://`, a bare `example.test/x`
# with no scheme at all -- would let a candidate be "verified" against content
# the research agent effectively chose. Checked BEFORE any fetch.
_ALLOWED_SCHEMES = ("http", "https")

# Hostnames that resolve to somewhere only THIS machine can reach. The reader
# is handed the source URL as a link, so a "verified" chart citing one of
# these would send them to a page nobody but the machine that built the page
# can open -- and the fetch that "proved" the number would have been answered
# by local infrastructure (a dev server, a cloud instance's metadata service)
# rather than by a publisher. Review finding: the scheme was filtered, the
# host was not.
_DENIED_HOST_NAMES = ("localhost",)


def _host(url: str | None) -> str:
    """The hostname a URL points at, lower-cased, port and 'www.' removed.

    Mirrors `gpu_agent.dashboard.bullets._outlet_from_url` -- same idea, same
    'www.' stripping, so 'www.trendforce.com' and 'trendforce.com' count as
    one publisher on both sides of the fence. It reads `.hostname` rather
    than `.netloc` on purpose: `.hostname` drops the port and any
    `user@` prefix and lower-cases the result, and this copy is used to make
    a SECURITY decision, where 'http://user@LOCALHOST:8080/' must not slip
    past a check for the literal text 'localhost'.

    Returns "" for anything without a host, which is itself a rejection.
    """
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    host = host.strip().strip("[]").lower()
    return host[4:] if host.startswith("www.") else host


def _unreachable_host_reason(host: str) -> str | None:
    """Why this host must never be handed to a reader as a source link, or
    None if it is an ordinary public hostname.

    Covers `localhost`, loopback (`127.*`, `::1`), link-local -- including the
    cloud metadata address `169.254.169.254` -- and the private ranges
    (`10.*`, `192.168.*`, `172.16-31.*`, IPv6 `fc00::/7`, `fe80::/10`).
    Numeric literals are classified by the standard library's `ipaddress`
    rather than by pattern-matching text, so the IPv6 spellings and the
    IPv4-mapped forms are covered by the same three lines.
    """
    if not host:
        return "source URL has no hostname"
    if host in _DENIED_HOST_NAMES or host.endswith(".localhost"):
        return f"{host} is this machine, not a publisher"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not a numeric address. A real registrable hostname can never be all
        # digits (no TLD is numeric), so an all-digit host is an integer-form
        # IP address dressed up to dodge the check above -- refuse it.
        if host.isdigit():
            return f"{host} is not a real hostname"
        return None
    if (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_reserved or ip.is_unspecified):
        return f"{host} is not a publicly reachable address"
    return None


def page_text(raw_html: str) -> str:
    """The visible text of a page: script/style bodies removed, tags replaced
    by spaces (never by nothing -- `<td>6.7</td><td>1</td>` must not fuse into
    `6.71`), HTML entities decoded."""
    without_code = _SCRIPT_STYLE_RE.sub(" ", raw_html or "")
    without_tags = _TAG_RE.sub(" ", without_code)
    return _html.unescape(without_tags)


def _value_tokens(value: float) -> set[str]:
    """The numeric token(s) a claimed `value` must be backed by, produced with
    the SAME tokenizer the page side uses so both sides are normalised
    identically (commas stripped, sign dropped, exponent expanded).

    `str(value)` first so 12500.0 stays "12500.0" rather than degrading to
    scientific notation, and `format(..., 'f')` so a genuinely huge value
    still renders as plain decimal digits.
    """
    try:
        plain = format(decimal.Decimal(str(value)), "f")
    except (decimal.InvalidOperation, ValueError):  # pragma: no cover -- pydantic
        # already guarantees a float here; belt and braces.
        plain = str(value)
    return numeric_tokens(plain)


def verify_candidate(cand: CandidateSeries,
                     fetch_html: Callable[[str], str]) -> tuple[bool, list[str]]:
    """Re-find every claimed point in the page it says it came from.

    All-or-nothing: returns `(True, [])` only when EVERY point is re-found.
    One miss makes the whole candidate false, with one human-readable failure
    line per failing point (`"point 3: 8.1 not found at <url>"`).

    Pages are fetched at most once each and cached for the call, so a series
    whose points share one source page costs one fetch, not N.

    A `fetch_html` that raises is not an error here -- that point is reported
    unreachable and the candidate is rejected. Nothing escapes this function.

    A candidate with NO points is rejected outright, and `pair=True` requires
    at least two (review finding, Critical): `CandidateSeries` only enforces
    its 3-point floor when `pair` is False, so `{"pair": true, "points": []}`
    validates -- and looping over nothing used to return "pass", making
    all-or-nothing hold only vacuously and letting a record that survived ZERO
    checks reach the trust store. Two is what spec section 3's "clearly-labelled
    comparison pair" means; one number is not a comparison.

    The URLs are checked BEFORE anything is fetched, and a candidate that
    fails there is rejected without a single request going out:

    - the scheme must be http/https (above);
    - the host must be one the reader could actually open -- never
      `localhost`, a loopback, link-local or private address (review
      finding: the scheme was filtered but the host was not, so a
      "verified" chart could link readers at a page only the build machine
      can reach);
    - every point must share ONE host. This is what makes the page's
      "Found today -- single source: <name>." caption true. Nothing else
      enforced it: a candidate whose points came from two different
      publishers was captioned as one source, counted as one source, and
      linked to just one of them. The numbers were all genuinely re-found,
      so nothing false was ever charted -- but the ATTRIBUTION overstated,
      and this lane's one new reader-facing claim has to hold. This is not
      a new rule, it is the label the spec already mandates made true.
    """
    failures: list[str] = []
    cache: dict[str, object] = {}

    if not cand.points:
        return False, ["candidate has no points: nothing to verify"]
    if cand.pair and len(cand.points) < 2:
        return False, [f"pair candidate needs 2 points to compare, "
                       f"got {len(cand.points)}"]

    hosts: list[str] = []
    for i, point in enumerate(cand.points, start=1):
        url = point.sourceUrl
        scheme = url.split(":", 1)[0].lower() if ":" in url else ""
        if scheme not in _ALLOWED_SCHEMES:
            failures.append(f"point {i}: source must be an http/https URL, "
                            f"got {url!r}")
            continue
        host = _host(url)
        reason = _unreachable_host_reason(host)
        if reason is not None:
            failures.append(f"point {i}: {reason} ({url})")
            continue
        hosts.append(host)
    if failures:
        return False, failures

    distinct = sorted(set(hosts))
    if len(distinct) > 1:
        return False, [f"a researched series must come from ONE source, but "
                       f"its points span {len(distinct)} sites: "
                       f"{', '.join(distinct)}"]

    for i, point in enumerate(cand.points, start=1):
        url = point.sourceUrl
        if url not in cache:
            try:
                cache[url] = numeric_tokens(page_text(fetch_html(url)))
            except Exception as e:  # noqa: BLE001 -- deliberate: an unreachable
                # source is a rejection, never a crashed cycle.
                cache[url] = f"{type(e).__name__}: {e}"
        pool = cache[url]
        if isinstance(pool, str):
            failures.append(f"point {i}: {url} unreachable ({pool})")
            continue
        tokens = _value_tokens(point.value)
        if not tokens or not any(supported(t, pool) for t in tokens):
            shown = format(decimal.Decimal(str(point.value)), "f")
            failures.append(f"point {i}: {shown} not found at {url}")

    return (not failures), failures


def _story_date(cat_dir: Path) -> str:
    story = _latest_story(cat_dir / "story")
    date = (story.get("storyDate") or "").strip()
    if not date:
        raise ValueError("latest story artifact carries no storyDate")
    return date


def _is_no_series(text: str) -> bool:
    """The honest give-up answer, whether the agent wrote the bare token or a
    JSON string containing it. Recognising it is what keeps an honest "I found
    nothing" out of the rejected pile."""
    stripped = text.strip()
    if stripped == _NO_SERIES_TOKEN:
        return True
    try:
        parsed = json.loads(stripped)
    except ValueError:
        return False
    return isinstance(parsed, str) and parsed.strip() == _NO_SERIES_TOKEN


def _answer_files(work_dir: str) -> list[tuple[int, Path]]:
    """`<work>/chart-research/bullet-<n>.json`, in bullet order. Prompt files
    (`bullet-<n>-prompt.txt`) and anything else in the directory are ignored."""
    d = Path(work_dir) / "chart-research"
    out: list[tuple[int, Path]] = []
    if not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        m = _ANSWER_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    out.sort(key=lambda t: t[0])
    return out


def accept_research(category_id: str, store_dir: str, work_dir: str,
                    fetch_html: Optional[Callable[[str], str]] = None) -> dict:
    """Verify this cycle's research answers and quarantine the survivors.

    Returns `{'accepted': [path, ...], 'rejected': [{'file', 'failures'}, ...],
    'missing': [path, ...]}` -- `missing` being the honest NO-SERIES-FOUND
    answers, which are a correct outcome and not an error.

    NEVER raises. Any failure at any level (a store with no story, an
    unreadable answer file, a source page that will not load) becomes a
    rejection entry, because a verifier that can strand a cycle is worse than
    no verifier at all.

    Append-only: a target path that already exists is a REJECTION with a clear
    message, never a silent overwrite. The written record is the candidate
    verbatim plus `bulletIndex`, taken from the `bullet-<n>.json` filename it
    came from -- Task 5 matches an accepted candidate back to its bullet
    through that field, and a missing one renders identically to "no series
    found", i.e. an invisible failure. It is set on every persisted record.
    """
    accepted: list[str] = []
    rejected: list[dict] = []
    missing: list[str] = []

    try:
        fetcher = fetch_html or _default_fetch_html
        answers = _answer_files(work_dir)
        if not answers:
            return {"accepted": accepted, "rejected": rejected, "missing": missing}

        cat_dir = Path(store_dir) / category_id
        try:
            story_date = _story_date(cat_dir)
        except Exception as e:  # noqa: BLE001 -- no story means no filename to
            # write under; every candidate is rejected, the cycle continues.
            for _, path in answers:
                rejected.append({"file": str(path),
                                 "failures": [f"cannot resolve story date: "
                                              f"{type(e).__name__}: {e}"]})
            return {"accepted": accepted, "rejected": rejected, "missing": missing}

        out_dir = cat_dir / "research-series"

        for index, path in answers:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                rejected.append({"file": str(path),
                                 "failures": [f"unreadable answer file: {e}"]})
                continue

            if _is_no_series(text):
                missing.append(str(path))
                continue

            try:
                cand = CandidateSeries.model_validate_json(text)
            except Exception as e:  # noqa: BLE001 -- a malformed or schema-
                # violating answer is a rejection, not a crash.
                rejected.append({"file": str(path),
                                 "failures": [f"unusable candidate: "
                                              f"{type(e).__name__}: {e}"]})
                continue

            ok, failures = verify_candidate(cand, fetcher)
            if not ok:
                rejected.append({"file": str(path), "failures": failures})
                continue

            try:
                name = f"{story_date}-{slug(cand.seriesName)}.json"
            except ValueError as e:
                rejected.append({"file": str(path),
                                 "failures": [f"unusable seriesName: {e}"]})
                continue

            target = out_dir / name
            if target.exists():
                rejected.append({"file": str(path),
                                 "failures": [f"quarantine file already exists, "
                                              f"refusing to overwrite: {target}"]})
                continue

            record = cand.model_copy(update={"bulletIndex": index})
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                target.write_text(record.model_dump_json(indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
            except OSError as e:
                rejected.append({"file": str(path),
                                 "failures": [f"could not write {target}: {e}"]})
                continue
            accepted.append(str(target))

        return {"accepted": accepted, "rejected": rejected, "missing": missing}
    except Exception as e:  # noqa: BLE001 -- deliberate outer net: see docstring.
        rejected.append({"file": "*", "failures": [f"{type(e).__name__}: {e}"]})
        return {"accepted": accepted, "rejected": rejected, "missing": missing}
