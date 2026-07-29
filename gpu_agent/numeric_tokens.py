"""Shared numeric-token machinery for citation gates (F14 wiki gate, F66 audit).

`numeric_tokens` and `value_renderings` were moved here verbatim from
`gpu_agent/wiki/ingest.py` when F66 grew a second call site. The wiki gate's
behaviour is unchanged: it still compares token to token by EXACT set
membership. `supported` is the F66 addition and is deliberately NOT used by the
wiki gate -- a wiki body quotes figures verbatim, while story prose written for
a non-technical reader rounds by policy.

Leaf module by design: stdlib only, no gpu_agent imports, so both a gate deep
in `wiki/` and a leaf audit module can import it without an import cycle.
"""
from __future__ import annotations

import decimal
import re
from typing import Iterable

_NUMERIC_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numeric_tokens(text: str) -> set[str]:
    """Numeric tokens (>= 2 digits after stripping thousands commas) mentioned in `text`.
    Single-digit tokens (list markers like '1.') are not material and are dropped."""
    out: set[str] = set()
    for m in _NUMERIC_RE.findall(text):
        norm = m.replace(",", "")
        if sum(ch.isdigit() for ch in norm) >= 2:
            out.add(norm)
    return out


def value_renderings(v: float) -> list[str]:
    """Every string form a finding's `value.number` might legitimately be written as.

    Multiple renderings so prose can cite the value however it was written:
    f"{v:g}" degrades to scientific notation for large floats ("7.52e+10"), so the
    integral form str(int(v)) is included whenever v is a whole number.
    """
    out = [str(v), repr(v), f"{v:g}"]
    if float(v).is_integer():
        out.append(str(int(v)))
    return out


def _precision(token: str) -> int:
    """Decimal places the prose author committed to. '7.09' -> 2, '7' -> 0."""
    head, _, frac = token.partition(".")
    return len(frac)


def supported(token: str, allowed: Iterable[str]) -> bool:
    """True when `token` is backed by `allowed`, tolerating honest rounding.

    Exact set membership first (this is what the wiki gate does). Failing that,
    a prose token is supported when some allowed value rounds to it AT THE PROSE
    TOKEN'S OWN DECIMAL PRECISION -- so 7.0931 supports "7.09", "7.1" and "7",
    but not "7.19", "8" or "70.9". Rounding is exact-decimal ROUND_HALF_UP via
    `decimal.Decimal`, never binary float rounding, so "2.45" supports "2.5" and
    "2.5" supports "3" (banker's rounding would give 2).

    Allowed members that are not parseable numbers are skipped, not an error:
    the pool is built by tokenizing free prose and can contain anything.
    """
    allowed = set(allowed)
    if token in allowed:
        return True
    try:
        want = decimal.Decimal(token)
    except decimal.InvalidOperation:
        return False
    quantum = decimal.Decimal(1).scaleb(-_precision(token))
    for cand in allowed:
        try:
            got = decimal.Decimal(cand)
        except decimal.InvalidOperation:
            continue
        try:
            rounded = got.quantize(quantum, rounding=decimal.ROUND_HALF_UP)
        except decimal.InvalidOperation:
            # Value too large to quantize at this precision; it cannot equal `want`
            # at that precision either.
            continue
        if rounded == want:
            return True
    return False
