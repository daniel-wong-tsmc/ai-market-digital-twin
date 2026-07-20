"""F100 deep-dive payloads — one per dimension, projected from store artifacts.
Pure, never raises: missing/malformed data degrades to empty."""
from __future__ import annotations

from .brief_model import RATING_ORDINAL  # re-exported

LENS_TO_DIMENSION = {"demand": "momentum", "supply": "bottleneck",
                     "risk": "strategicRisk", "competitive": "competitiveStructure"}
SLOT_TO_DIMENSION = {"demand-durability": "momentum",
                     "binding-constraint": "bottleneck",
                     "customer-mix": "competitiveStructure",
                     "end-market-economics": "unitEconomics",
                     "demand-quality": "strategicRisk"}

_RATING_TONE = {"weak": "bad", "mixed": "neutral", "strong": "good",
                "very strong": "good"}
_DIR_TONE = {"improving": "good", "steady": "neutral", "worsening": "bad"}
# "improving" is good even when the current rating is weak (bottleneck easing).
_GOOD_DIRECTION = {"improving"}


def _findings_by_id(latest):
    out = {}
    for f in (latest.get("findings") or []):
        if isinstance(f, dict) and f.get("id"):
            out[f["id"]] = f
    return out


def build_deepdive_targets(latest, rating_history, book_entries, implication_lines):
    ratings = latest.get("dimensionRatings")
    if not isinstance(ratings, dict):
        return {}
    dstat = latest.get("dimensionStatus")
    dstat = dstat if isinstance(dstat, dict) else {}
    fbi = _findings_by_id(latest)

    # pre-group folded content by dimension
    impl_by_dim = {}
    for ln in (implication_lines or []):
        text = ln.get("text") or ln.get("watchItem")
        for dim in (ln.get("dimensions") or []):
            if text:
                impl_by_dim.setdefault(dim, []).append(text)
    calls_by_dim = {}
    for e in (book_entries or []):
        dim = LENS_TO_DIMENSION.get(e.get("lens"))
        if dim:
            calls_by_dim.setdefault(dim, []).append({
                "title": e.get("title") or "",
                "verdict": e.get("lastVerdict") or "not yet judged",
                "trigger": e.get("falsifiableTrigger") or ""})

    out = {}
    for name, r in ratings.items():
        if not isinstance(r, dict):
            continue
        rating = r.get("rating") or "—"
        direction = r.get("direction") or "steady"
        conf = r.get("confidence")
        conf = conf if isinstance(conf, dict) else {}
        capped = bool(dstat.get(name, {}).get("confidenceCap")) if isinstance(dstat.get(name), dict) else False

        badges = [{"text": rating, "tone": _RATING_TONE.get(rating.lower(), "neutral")},
                  {"text": f"{direction}", "tone": _DIR_TONE.get(direction, "neutral")}]
        if conf.get("level"):
            badges.append({"text": f"{conf['level']} confidence", "tone": "neutral"})
        if capped:
            badges.append({"text": "confidence capped", "tone": "neutral"})

        evidence = []
        for fid in (r.get("findingIds") or [])[:5]:
            f = fbi.get(fid)
            if not isinstance(f, dict):
                continue
            ev0 = next((x for x in (f.get("evidence") or []) if isinstance(x, dict)), {})
            evidence.append({"source": ev0.get("source") or "source",
                             "trend": f.get("trend") or "",
                             "text": f.get("statement") or "",
                             "url": ev0.get("url") or ""})

        calls = calls_by_dim.get(name, [])
        conf_basis = conf.get("basis") or ""
        vote = r.get("voteSpread") or ""
        confidence = " · ".join(x for x in (vote, conf_basis) if x)

        out[name] = {
            "eyebrow": "Dimension" + (" · confidence capped" if capped else ""),
            "title": f"{name} — {rating}, {direction}",
            "badges": badges,
            "why": r.get("rationale") or "",
            "trend": list(rating_history.get(name) or []),
            "trend_good": direction in _GOOD_DIRECTION or rating.lower() in ("strong", "very strong"),
            "evidence": evidence,
            "confidence": confidence,
            "change": calls[0]["trigger"] if calls else "",
            "tsmc": impl_by_dim.get(name, []),
            "calls": calls,
        }
    return out
