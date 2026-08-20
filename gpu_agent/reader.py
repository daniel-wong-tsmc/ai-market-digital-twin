"""gpu_agent/reader.py — the F67 reader contract (spec §2a).

One home for every exec-facing vocabulary rule: the reader is a TSMC executive
with zero knowledge of this repo. Label maps translate internal jargon; the
acronym allowlist (registry/acronyms.json — DATA, edit there) bounds all-caps
tokens; lint_prose enforces the analyst-voice rules on brain-written fields.
Pure functions, no LLM, no network."""
from __future__ import annotations
import json
import re
from pathlib import Path

APPENDIX_DIVIDER = "──────────────────────────── APPENDIX ────────────────────────────"

TIER_LABEL = {
    "primary": "company filing / official post",
    "secondary": "press / analyst report",
}
STATUS_LABEL = {
    "grounded": "well-evidenced",
    "under-supported": "thin evidence",
    "provisional": "early — not yet corroborated",
}

# Six scorecard dimension ids -> exec-plain labels for above-the-fold change/quick-glance
# lines (the DIMENSION RATINGS appendix section keeps the raw ids). All pass lint_acronyms.
DIM_LABEL = {
    "momentum": "Momentum rating",
    "unitEconomics": "Unit economics",
    "competitiveStructure": "Competitive structure",
    "moat": "Moat",
    "bottleneck": "Supply bottleneck",
    "strategicRisk": "Strategic risk",
}

# Brain-prose ban list (spec §2a + stop-slop's filler subset — deterministic slice only).
BANNED_WORDS = (
    "delve", "delves", "crucial", "pivotal", "robust", "landscape",
    "leverage", "leverages", "holistic", "seamless", "utilize", "utilizes",
)
# Finding ids look like `<slug>-<8 hex>-<n>` (see gathering ids in store/findings/).
_FINDING_ID_RE = re.compile(r"\b[a-z0-9][a-z0-9-]*-[0-9a-f]{8}-\d+\b")
_ALLCAPS_RE = re.compile(r"\b[A-Z][A-Z0-9&]+(?:-[A-Z0-9&]+)*\b")
# Sentence split: end punctuation followed by whitespace+capital; decimals survive.
# Common abbreviations (U.S., U.K., e.g., i.e., vs.) are not sentence ends — the F6 eval
# run caught "U.S. GDP" splitting a two-sentence rationale into three and tripping the
# max-2 voice lint. Python lookbehinds are fixed-width, hence one per abbreviation.
_SENT_SPLIT_RE = re.compile(
    r"(?<!\bU\.S\.)(?<!\bU\.K\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)"
    r"(?<=[.!?])\s+(?=[A-Z(\"'0-9])")

_ACRONYMS_PATH = Path("registry/acronyms.json")
_INDICATOR_IDS: frozenset[str] | None = None
_ALLOWED: frozenset[str] | None = None


def _allowed() -> frozenset[str]:
    global _ALLOWED
    if _ALLOWED is None:
        _ALLOWED = frozenset(json.loads(_ACRONYMS_PATH.read_text("utf-8"))["allowed"])
    return _ALLOWED


def _indicator_ids() -> frozenset[str]:
    global _INDICATOR_IDS
    if _INDICATOR_IDS is None:
        raw = json.loads(Path("registry/indicators.json").read_text("utf-8"))
        _INDICATOR_IDS = frozenset(raw.get("indicators", {}))
    return _INDICATOR_IDS


def indicator_label(indicator_id: str, registry) -> str:
    """Human label for an indicator id; falls back to the id (never crashes)."""
    spec = registry.indicators.get(indicator_id) if registry is not None else None
    if isinstance(spec, dict):
        return spec.get("label") or indicator_id
    return indicator_id


def label_ids_in_text(text: str, registry) -> str:
    """Replace whole-token registry indicator ids with their human labels (display only).

    The thesis GATE requires indicator ids in falsifiableTrigger (F54 observable
    heuristic), so the BOOK keeps ids verbatim; this display-layer substitution is what
    lets THE CALLS' "breaks if:" line read like exec prose instead of leaking an id like
    "D6" above reader.APPENDIX_DIVIDER. registry=None or empty text -> unchanged.

    F68e: substitution is a SINGLE re.sub pass over one alternation of every id (longest
    id first, so a longer id can't be prefix-shadowed by a shorter one ending at a
    non-word char, e.g. a hyphen). One pass means the replacement function only ever
    sees matches against the ORIGINAL text — an inserted label is never re-scanned, so a
    future registry label that happens to embed another id's literal token can never be
    re-substituted (no iterative chaining). Do not rewrite this as a loop of per-id
    re.sub calls; that reintroduces the chaining bug this function exists to prevent."""
    if registry is None or not text:
        return text
    ids = [ind_id for ind_id in sorted(registry.indicators, key=len, reverse=True)
           if indicator_label(ind_id, registry) != ind_id]
    if not ids:
        return text
    pattern = re.compile("|".join(rf"\b{re.escape(ind_id)}\b" for ind_id in ids))
    return pattern.sub(lambda m: indicator_label(m.group(0), registry), text)


# F120 round-2 (user-approved 2026-08-20, Option A): the live thesis book's
# falsifiableTrigger texts embed OLD-scheme indicator ids in parentheses right after
# their plain-word labels ("Hyperscaler capex-revision direction (D1)"). Those ids are
# not in today's registry, so label_ids_in_text cannot substitute them and they would
# leak raw above the fold. Deliberately narrow: ONE capital letter + 1-2 digits inside
# parentheses, nothing broader — "(no growth in 2027)" and "(CS-4)" must survive.
_STALE_PAREN_ID_RE = re.compile(r"\s*\(\b([A-Z]\d{1,2})\b\)")


def strip_stale_paren_ids(text: str) -> str:
    """Display-layer strip of leftover parenthesized old-scheme short-id tokens
    (e.g. "(D1)", "(X5)") from a "breaks if" line. The stored book text is never
    touched (the GATE's observable-id requirement lives there, as designed).
    Review fix (2026-08-20): a token on the acronym allowlist (e.g. "(Q3)") is
    sanctioned exec-facing vocabulary, never a stale id — it survives untouched
    (silent deletion of legitimate content would invert the fail-loud posture)."""
    if not text:
        return text
    allowed = _allowed()
    return _STALE_PAREN_ID_RE.sub(
        lambda m: m.group(0) if m.group(1) in allowed else "", text)


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [s for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def lint_acronyms(text: str) -> list[str]:
    """All-caps tokens not on the allowlist (spec §2a) — sorted, deduplicated."""
    allowed = _allowed()
    hits = {t for t in _ALLCAPS_RE.findall(text or "")
            if t.upper() not in allowed and t not in allowed}
    return sorted(hits)


def lint_prose(text: str, field: str, *, max_sentences: int | None = None) -> list[str]:
    """Analyst-voice lint for one brain-written field. Returns violations (empty = clean).
    Checks: indicator ids, finding ids, banned words, sentence cap, off-list acronyms."""
    errs: list[str] = []
    text = text or ""
    lowered = text.lower()
    tokens = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", text))
    for ind in sorted(_indicator_ids() & tokens):
        errs.append(f"{field}: indicator id '{ind}' in exec-facing prose")
    for m in sorted(set(_FINDING_ID_RE.findall(lowered))):
        errs.append(f"{field}: finding id '{m}' in exec-facing prose")
    for w in BANNED_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", lowered):
            errs.append(f"{field}: banned word '{w}'")
    if max_sentences is not None:
        n = len(split_sentences(text))
        if n > max_sentences:
            errs.append(f"{field}: {n} sentences (max {max_sentences})")
    for a in lint_acronyms(text):
        errs.append(f"{field}: acronym '{a}' not on registry/acronyms.json allowlist")
    return errs
