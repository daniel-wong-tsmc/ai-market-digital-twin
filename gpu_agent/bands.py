"""gpu_agent/bands.py — the five-word band map (piece 5-2, output surgery).

Pure, deterministic, stdlib-only: maps a raw DMI/SMI-style value in roughly
[-1, 1] to one of five words (accelerating/firm/flat/softening/contracting),
and, given the prior cycle's value, renders the earned "WORD ARROW (was WORD)"
line — words first, no invented magnitudes (charter Part 17). Raw indices move to
the trust footer (docs/superpowers/specs/2026-07-02-thesis-book-design.md §4);
this module is the only place the threshold numbers live, so retuning them
retunes every caller at once.

F136 (2026-08-31): the brief's HEADLINE demand/supply lines no longer use the word
bands. The demand number is a running total that has grown past 4.5, far above the
top band's 0.30 floor, so the banded headline was permanently pinned at
"ACCELERATING = (was ACCELERATING)" and could not report a move of any size.
change_line() below replaced it there — it reports the day-over-day change, so it
carries the same information at any scale and never needs retuning. band_word /
band_with_prior are UNCHANGED and still serve the web dashboard tiles, the
change-detector's band-crossing checks, and the appendix raw-index table, where the
absolute level (not the move) is the point.
"""
from __future__ import annotations

# v1 thresholds — documented, retunable data (spec §4). Ordered descending by
# threshold. The two positive floors are inclusive (>=); the two negative
# floors are exclusive (>) — so -0.05 itself is "softening" (not "flat") and
# -0.30 itself is "contracting" (not "softening"). Anything not caught by these
# four floors is "contracting" — the implicit fifth band, with no floor of its
# own.
BANDS: list[tuple[float, str]] = [
    (0.30, "accelerating"),
    (0.05, "firm"),
    (-0.05, "flat"),
    (-0.30, "softening"),
]

# Ascending rank, worst -> best, derived from BANDS so a retune of the
# thresholds/words above keeps band_with_prior's arrow logic consistent
# automatically.
_WORD_RANK: list[str] = ["contracting"] + [word for _, word in reversed(BANDS)]

_ARROW_ROSE = "▲"
_ARROW_FELL = "▼"
_ARROW_SAME = "="
_ARROW_NO_PRIOR = "·"


def band_word(value: float) -> str:
    """One of accelerating/firm/flat/softening/contracting, lowercase.

    Positive floors are inclusive (>=); negative floors are exclusive (>);
    see BANDS for the exact pinned thresholds.
    """
    for threshold, word in BANDS:
        if threshold >= 0:
            if value >= threshold:
                return word
        elif value > threshold:
            return word
    return "contracting"


def _two_dp(value: float) -> str:
    """Two decimals, with the '-0.00' that a tiny negative would otherwise print
    normalised to '0.00' — a minus sign in front of a zero reads as a real minus."""
    text = f"{value:.2f}"
    return "0.00" if text == "-0.00" else text


def change_line(value: float, prior: float | None) -> str:
    """F136: '4.51, up 0.57 since the last run' — the headline demand/supply wording.

    Why this replaced the word band on the headline. band_with_prior below maps a value
    onto five words whose top band starts at 0.30. The demand number is a running total
    that has grown past 4.5, so every value lands in the top band and the headline was
    permanently pinned at 'ACCELERATING = (was ACCELERATING)' — it could not report a
    move of any size. This line reports the day-over-day change directly, so it carries
    the same information whether the number sits at 0.5, 4.5 or 450, and never needs
    the thresholds retuned. The word bands are unchanged and still serve the dashboard
    tiles and the appendix raw-index table, where the absolute level is the point.

    Two decimals throughout; a move that rounds to 0.00 reads 'unchanged' rather than
    claiming a change the reader cannot see. Plain words only — no acronyms, so it
    passes the above-the-fold reader lint.
    """
    level = _two_dp(value)
    if prior is None:
        return f"{level}, first tracked run — nothing to compare yet"
    delta = value - prior
    if abs(delta) < 0.005:      # rounds to 0.00 at the displayed precision
        return f"{level}, unchanged since the last run"
    direction = "up" if delta > 0 else "down"
    return f"{level}, {direction} {abs(delta):.2f} since the last run"


def band_with_prior(value: float, prior: float | None) -> str:
    """'ACCELERATING ▲ (was FIRM)' style: the current band uppercased, an arrow
    for the move versus the prior cycle's band, and the prior band uppercased.

    Arrow: ▲ if the band rank rose vs prior, ▼ if it fell, = if unchanged, ·
    when there is no prior cycle to compare against (first cycle) — in which
    case the trailing clause reads '(no prior)' instead of '(was WORD)'.
    """
    word = band_word(value)
    if prior is None:
        return f"{word.upper()} {_ARROW_NO_PRIOR} (no prior)"
    prior_word = band_word(prior)
    rank = _WORD_RANK.index(word)
    prior_rank = _WORD_RANK.index(prior_word)
    if rank > prior_rank:
        arrow = _ARROW_ROSE
    elif rank < prior_rank:
        arrow = _ARROW_FELL
    else:
        arrow = _ARROW_SAME
    return f"{word.upper()} {arrow} (was {prior_word.upper()})"
