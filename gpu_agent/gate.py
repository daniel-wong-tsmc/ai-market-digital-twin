from __future__ import annotations
import re
from gpu_agent.schema.finding import Finding, Kind
from gpu_agent.schema.scorecard import Scorecard
from gpu_agent.config import min_distinct_publishers
from gpu_agent.publisher import collapsed_publisher_set

_ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")

# F127 — excerpt length cap. Posture doc §2, DECIDED 2026-08-22: an excerpt is
# "at most two sentences or about 50 words". That "or" is read literally — an
# excerpt is rejected only when it breaks BOTH limits. Measured over all 644
# committed excerpts, nothing breaks both, while a hard 50-word cap alone would
# have rejected a real 70-word one-sentence 10-Q quote. The absolute cap is the
# backstop that stops a run-on (which counts as one sentence) from walking past
# the gate at any length.
EXCERPT_MAX_WORDS = 50
EXCERPT_MAX_SENTENCES = 2
EXCERPT_ABSOLUTE_MAX_WORDS = 100

# A sentence end is terminal punctuation followed by end-of-text, or by whitespace
# and then the start of a new sentence: an optional opening quote or bracket, then
# a capital or a digit. Requiring the capital is what stops an abbreviation the list
# does not know ("the Fed. raised", "Rev. was up", "3 mn. units") from being read as
# a sentence end — real prose capitalises after a full stop, abbreviations do not.
_SENTENCE_END = re.compile(r"[.!?]+(?=\s+[\"'“‘(\[]?[A-Z0-9]|\s*$)")

# A token carrying a period INSIDE it is an acronym, a pair of initials or a
# numbered label ("A.I.", "Ph.D.", "J.H.", "2.1."), never a sentence end. Letters
# and ordinals only — a decimal amount ("$6.7B.") may legitimately end a sentence.
_INTERNAL_PERIOD = re.compile(r"^[a-z]+(?:\.[a-z]+)+\.$|^\d+(?:\.\d+)+\.$")

# Tokens that end in "." without ending a sentence. Financial prose only needs a
# short list; anything missed makes the counter count HIGH, so keep it current.
_ABBREVIATIONS = frozenset({
    "u.s.", "u.k.", "e.u.", "u.s.a.",
    "inc.", "corp.", "co.", "ltd.", "llc.", "plc.", "gmbh.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.",
    "vs.", "etc.", "e.g.", "i.e.", "cf.", "al.",
    "no.", "fig.", "approx.", "est.", "avg.", "yr.", "qtr.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.",
    "sept.", "sep.", "oct.", "nov.", "dec.",
})


# Period/quarter labels: "Q3.", "H1.", "1H.", "FY26.", "CY2026.". Financial prose is
# full of these and a static list cannot cover the fiscal-year forms. Note this also
# swallows a genuine sentence that happens to END on such a label ("...grew in Q3.
# Margins held."), which under-counts — the safe direction.
_PERIOD_LABEL = re.compile(r"^(?:fy|cy|q|h)\d+\.$|^\d+[hq]\.$")


def _count_words(text: str) -> int:
    """Word count the way the posture doc measured it: whitespace split."""
    return len(text.split())


def _count_sentences(text: str) -> int:
    """Count sentences, biased to UNDER-count.

    Under-counting lets a long excerpt through; over-counting rejects a real one,
    so every judgement call here is made in the first direction. The count is only
    ever consulted for an excerpt already over EXCERPT_MAX_WORDS, and
    EXCERPT_ABSOLUTE_MAX_WORDS backstops genuine bulk, so leniency is cheap.

    Three rules keep it there: a decimal point is never a terminator (the lookahead
    needs whitespace after the dot); a terminator only counts when a capital or a
    digit follows it, which is what stops an abbreviation the list does not know
    ("the Fed. raised", "Rev. was up") from reading as a full stop; and a token with
    a period inside it is an acronym or a numbered label, never a sentence end.

    It is NOT infallible, and the claim to check before tightening it is this one:
    an abbreviation that is unlisted AND followed by a capitalised word still counts
    as a sentence end, over-counting by one. That is why the gate requires BOTH
    limits to be broken rather than trusting this number on its own.
    """
    folded = " ".join(text.split())
    count = 0
    for match in _SENTENCE_END.finditer(folded):
        # Walk back to the start of the token this terminator ends, rather than
        # re-slicing and re-splitting the whole prefix on every match.
        start = folded.rfind(" ", 0, match.end()) + 1
        last = folded[start:match.end()].lower().strip("\"'([{<")
        if not last:
            continue
        if (last in _ABBREVIATIONS or _PERIOD_LABEL.match(last)
                or _INTERNAL_PERIOD.match(last)):
            continue
        # A single character before the punctuation: an initial, or the tail of
        # "U.S." once the earlier dot has already been consumed.
        if len(last.rstrip(".!?")) <= 1:
            continue
        count += 1
    return max(count, 1)

def _future_dated(date: str, as_of: str) -> bool:
    """Grain-aware vintage compare: truncate the evidence date to asOf's grain
    (month 'YYYY-MM' or day 'YYYY-MM-DD') and compare lexically."""
    g = len(as_of)
    return bool(as_of) and date[:g] > as_of

def excerpt_length_violations(fid: str, excerpt: str) -> list[str]:
    """F127 — the excerpt length cap, as one callable rule.

    Public so that a caller wanting to check a bare excerpt (a store audit, a
    review script) uses the same rule `check_finding` applies, rather than a
    second copy of it that can drift.

    An excerpt is rejected when it breaks BOTH decided limits, or when it breaks
    the absolute backstop on its own. Over the backstop reports only that, since
    the two messages would say the same thing twice.

    A non-string excerpt is not this rule's business to complain about — the schema
    already requires a string — so it is passed over rather than crashing an audit.
    """
    if not isinstance(excerpt, str):
        return []
    words = _count_words(excerpt)
    if words > EXCERPT_ABSOLUTE_MAX_WORDS:
        return [f"{fid}: excerpt too long ({words} words > "
                f"{EXCERPT_ABSOLUTE_MAX_WORDS} absolute cap)"]
    sentences = _count_sentences(excerpt)
    if words > EXCERPT_MAX_WORDS and sentences > EXCERPT_MAX_SENTENCES:
        return [f"{fid}: excerpt too long ({words} words > {EXCERPT_MAX_WORDS} "
                f"and {sentences} sentences > {EXCERPT_MAX_SENTENCES})"]
    return []


def check_finding(f: Finding, *, valid_targets: frozenset[str] | None = None) -> list[str]:
    errors: list[str] = []
    if f.kind == Kind.measured and f.value is None:
        errors.append(f"{f.id}: measured finding missing value")
    if f.kind != Kind.measured and f.value is not None:
        errors.append(f"{f.id}: non-measured finding has invented value")
    if f.kind in (Kind.measured, Kind.observed) and not f.evidence:
        errors.append(f"{f.id}: {f.kind.value} finding missing evidence")   # F2a
    if not f.why.strip():
        errors.append(f"{f.id}: missing why")
    if f.kind == Kind.hypothesis:
        if not f.reasoning:
            errors.append(f"{f.id}: hypothesis missing reasoning")
        if f.confidence.level == "high":
            errors.append(f"{f.id}: hypothesis confidence capped at medium")
    # F2e — headline protection at finding level (contract v1.3: >=N distinct publishers
    # unlock high confidence — docs/migrations/2026-07-contract-v1.3.md). Contract v1.4 (F72):
    # distinctness is counted over COLLAPSED publisher identities (collapsed_publisher_set),
    # so a single wire story syndicated across several netlocs can no longer clear the bar.
    if f.evidence and all(e.tier == "secondary" for e in f.evidence) and f.confidence.level == "high":
        n = min_distinct_publishers()
        publishers = collapsed_publisher_set(f.evidence)
        if len(publishers) < n:
            errors.append(f"{f.id}: secondary-only evidence cannot support high confidence "
                          f"({len(publishers)} distinct publishers < {n})")
    # F8 — price is an overlay: a level without a baseline is not momentum
    if f.side == "price":
        if f.trend == "unknown" and (f.polarityDemand != 0 or f.polaritySupply != 0):
            errors.append(f"{f.id}: static price level (trend unknown) must carry polarity 0")
    elif f.polarityDemand == 0 and f.polaritySupply == 0:
        errors.append(f"{f.id}: finding affects neither demand nor supply track")
    # F17 — vintage honesty
    if not _ISO_PREFIX.match(f.observedAt or ""):
        errors.append(f"{f.id}: observedAt not ISO (YYYY-MM-DD...)")
    for e in f.evidence:
        if not _ISO_PREFIX.match(e.date or ""):
            errors.append(f"{f.id}: evidence date not ISO (YYYY-MM-DD): {e.date!r}")
        elif _future_dated(e.date, f.asOf):
            errors.append(f"{f.id}: future-dated evidence {e.date} vs asOf {f.asOf}")
        errors.extend(excerpt_length_violations(f.id, e.excerpt))   # F127
    # F21 — impact quality
    if not f.impact.targets:
        errors.append(f"{f.id}: impact.targets empty")
    if not f.impact.mechanism.strip():
        errors.append(f"{f.id}: impact.mechanism empty")
    if valid_targets is not None:
        for t in f.impact.targets:
            if t not in valid_targets:
                errors.append(f"{f.id}: impact target '{t}' not in taxonomy")
    return errors


_POSITIVE = {"Very strong", "Strong"}
_NEGATIVE = {"Weak", "Very weak"}
_ANCHOR_TOL = 0.15   # F36: was 0.5 — "Very strong" at anchor -0.49 is not judgment room

def _rating_consistent_with_anchor(rating: str, anchor: float) -> bool:
    if rating in _POSITIVE:
        return anchor > -_ANCHOR_TOL
    if rating in _NEGATIVE:
        return anchor < _ANCHOR_TOL
    return True  # "Mixed" is always allowed

def check_scorecard(sc: Scorecard) -> list[str]:
    errors: list[str] = []
    for f in sc.findings:
        errors.extend(check_finding(f))
    known = {f.id for f in sc.findings}
    for dim, r in sc.dimensionRatings.items():
        if not r.findingIds:
            errors.append(f"{dim}: rating cites no findings")
        for fid in r.findingIds:
            if fid not in known:
                errors.append(f"{dim}: cites unknown finding {fid}")
        anchor = sc.demandSupply.anchors.get(dim)
        if anchor is not None and not _rating_consistent_with_anchor(r.rating, anchor):
            errors.append(f"{dim}: rating {r.rating} contradicts anchor a={anchor:.2f}")
    for f in sc.findings:
        for e in f.evidence:
            if e.source == "AI Market State dashboard" or "market-state.json" in e.url:
                errors.append(f"{f.id}: evidence self-references the dashboard output")
    return errors


class GateError(Exception):
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))
