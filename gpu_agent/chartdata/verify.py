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
import json
import re
from pathlib import Path
from typing import Callable, Optional

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
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]*>", re.S)


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
    """
    failures: list[str] = []
    cache: dict[str, object] = {}

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
