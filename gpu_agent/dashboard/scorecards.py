import json
import re
from pathlib import Path

# Matches both monthly (YYYY-MM-vN.json) and daily (YYYY-MM-DD-vN.json) scorecards.
# The optional day group is greedy, so a daily filename still resolves its full
# YYYY-MM-DD date string rather than being truncated to YYYY-MM.
_DATE_RE = re.compile(r"(\d{4}-\d{2}(?:-\d{2})?)-v(\d+)\.json$")


def _read_json(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return json.load(fh)


def _best_tier(evidence):
    for ev in evidence or []:
        if ev.get("tier") == "primary":
            return "primary"
    return "secondary"


def _source_name(evidence):
    for ev in evidence or []:
        if ev.get("source"):
            return ev["source"]
    return ""


def _norm_finding(f):
    ev = f.get("evidence") or []
    impact = f.get("impact") or {}
    return {
        "id": f.get("id", ""),
        "statement": f.get("statement", ""),
        "observed_at": f.get("observedAt") or f.get("asOf"),
        "magnitude": int(f.get("magnitude") or 0),
        "impact_direction": impact.get("direction", ""),
        "mechanism": impact.get("mechanism", ""),
        "source_name": _source_name(ev),
        "tier": _best_tier(ev),
        "evidence_date": (ev[0].get("date") if ev else None),
    }


def _norm_dimensions(ratings, status):
    dims = {}
    names = set(ratings) | set(status)
    for name in names:
        r = ratings.get(name, {}) or {}
        s = status.get(name, {}) or {}
        dims[name] = {
            "rating": r.get("rating"),
            "direction": r.get("direction"),
            "confidence": (r.get("confidence") or {}).get("level"),
            "rationale": r.get("rationale", ""),
            "evidence_status": s.get("evidenceStatus", "under-supported"),
            "finding_count": int(s.get("findingCount") or 0),
        }
    return dims


def load_scorecards(category_id, store_dir):
    base = Path(store_dir)
    latest = {}  # date -> (version, path); keep highest version per date
    for p in base.glob("*.json"):
        m = _DATE_RE.search(p.name)
        if not m:
            continue
        d_str, ver = m.group(1), int(m.group(2))
        if d_str not in latest or ver > latest[d_str][0]:
            latest[d_str] = (ver, p)
    keys = list(latest)
    # When monthly deep-read scorecards (YYYY-MM) exist they are the current cadence;
    # older intra-month dailies (YYYY-MM-DD) are legacy snapshots — use the monthly grain
    # only, so the whole site (appendix, alert, featured) reads the same deep-read the
    # F97 brief anchors on.
    monthly = [k for k in keys if len(k) == 7]
    if monthly:
        keys = monthly
    files = sorted((k, latest[k][1]) for k in keys)
    records = []
    for as_of, path in files:
        d = _read_json(path)
        ds = d.get("demandSupply", {}) or {}
        cat = d.get("categoryStatus", {}) or {}
        findings = [_norm_finding(f) for f in (d.get("findings") or [])]
        prim = sum(1 for f in findings if f["tier"] == "primary")
        records.append({
            "as_of": d.get("asOf", as_of),
            "rating": cat.get("rating"),
            "direction": cat.get("direction"),
            "bottleneck": cat.get("bottleneck"),
            "reason": cat.get("reason", ""),
            "dmi": float(ds.get("dmiContribution") or 0.0),
            "smi": float(ds.get("smiContribution") or 0.0),
            "sdgi": float(ds.get("sdgi") or 0.0),
            "sdgi_direction": ds.get("sdgiDirection", ""),
            "dimensions": _norm_dimensions(d.get("dimensionRatings", {}) or {},
                                           d.get("dimensionStatus", {}) or {}),
            "findings": findings,
            "sources": d.get("sources", []) or [],
            "findings_count": len(findings),
            "primary_count": prim,
            "secondary_count": len(findings) - prim,
            "sources_count": len(d.get("sources", []) or []),
            "confidence": (d.get("confidence", {}) or {}).get("level"),
        })
    return records


def trend_series(records):
    return {
        "dates": [r["as_of"] for r in records],
        "dmi": [r["dmi"] for r in records],
        "smi": [r["smi"] for r in records],
        "sdgi": [r["sdgi"] for r in records],
    }
