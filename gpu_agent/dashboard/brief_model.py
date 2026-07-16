"""F97 Executive Brief page model — pure projection from store artifacts.

No LLM, no network, no wall-clock: `today` is always a parameter."""
from __future__ import annotations

import json
import re
from pathlib import Path

_MONTHLY_RE = re.compile(r"^(\d{4}-\d{2})-v(\d+)\.json$")
_CONVICTION_ORDER = {"high": 0, "medium": 1, "low": 2}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_monthly(cat_dir):
    cat_dir = Path(cat_dir)
    revs = []
    try:
        entries = list(cat_dir.iterdir())
    except OSError:
        entries = []
    for p in entries:
        m = _MONTHLY_RE.match(p.name)
        if m:
            revs.append((m.group(1), int(m.group(2)), p))
    if not revs:
        return None, None, "", 0
    revs.sort(key=lambda t: (t[0], t[1]))
    as_of, rev, latest_path = revs[-1]
    latest = _read_json(latest_path) or {}
    prior = None
    if len(revs) > 1 and revs[-2][0] == as_of:
        prior = _read_json(revs[-2][2])
    return latest, prior, as_of, rev


def read_thesis_book(store_root, category_id):
    art = _read_json(Path(store_root) / "theses" / category_id / "book.json")
    if not isinstance(art, dict):
        return []
    entries = art.get("entries")
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def _neg_streak(e):
    s = e.get("streak")
    return -s if isinstance(s, (int, float)) else 0


def select_calls(entries, cap=7):
    total = len(entries)
    prov = sum(1 for e in entries if e.get("status") == "provisional")
    ordered = sorted(entries, key=lambda e: (
        0 if e.get("status") == "registered" else 1,
        _CONVICTION_ORDER.get(e.get("conviction"), 3),
        _neg_streak(e),
        e.get("title") or ""))
    return ordered[:cap], total, prov


def read_implication_lines(store_root, category_id, as_of):
    d = Path(store_root) / "implications" / category_id
    art = _read_json(d / f"{as_of}.json")
    if art is None:
        try:
            candidates = sorted(p for p in d.iterdir() if p.suffix == ".json")
        except OSError:
            return []
        art = _read_json(candidates[-1]) if candidates else None
    if not isinstance(art, dict):
        return []
    lines = art.get("lines")
    if not isinstance(lines, list):
        return []
    out = []
    for ln in lines:
        if isinstance(ln, dict) and (ln.get("watchItem") or ln.get("text")):
            out.append({"text": ln.get("watchItem") or ln.get("text"),
                        "dims": list(ln.get("dimensions") or []),
                        "thesis_ids": list(ln.get("thesisIds") or []),
                        "finding_ids": list(ln.get("findingIds") or [])})
    return out


def last_signal_check(store_root, cat_dir):
    log = _read_json(Path(store_root) / "cycle-log.json")
    stamp = log.get("capturedAt") if isinstance(log, dict) else ""
    if stamp:
        return stamp[:10]
    latest, _, _, _ = latest_monthly(cat_dir)
    findings = (latest or {}).get("findings")
    if not isinstance(findings, list):
        findings = []
    stamps = [(f.get("capturedAt") or "")[:10] for f in findings if isinstance(f, dict)]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else ""


import datetime as _dt

from .agenda import load_slots, read_series, select_occupants

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-v(\d+)\.json$")
_ATTENTION = {"green": "calm", "yellow": "watch", "orange": "elevated",
              "red": "critical"}
_GLYPHS = {"strengthened": "▲", "weakened": "▼", "reaffirmed": "◆"}


def _first_sentence(text):
    text = (text or "").strip()
    for i, ch in enumerate(text):
        if ch == "." and (i + 1 == len(text) or text[i + 1] == " "):
            return text[:i + 1]
    return text


def _strip_entry(findings, prior_ids):
    fresh = [f for f in findings if f.get("id") not in prior_ids]
    if not fresh:
        return None
    top = max(fresh, key=lambda f: (int(f.get("magnitude") or 0),
                                    f.get("observedAt") or "", f.get("id") or ""))
    dates = [(f.get("capturedAt") or "")[:10] for f in fresh]
    src = next((e.get("source") for e in (top.get("evidence") or [])
                if e.get("source")), "")
    return {"date": max(d for d in dates if d) if any(dates) else "",
            "text": _first_sentence(top.get("statement")), "source": src}


def signal_strip(cat_dir, limit=7):
    cat_dir = Path(cat_dir)
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in cat_dir.iterdir()
                   for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))
    out = []
    if len(revs) >= 2:
        prior_ids = set()
        entries = []
        for _, _, p in revs:
            findings = (_read_json(p) or {}).get("findings") or []
            e = _strip_entry(findings, prior_ids)
            if e is not None:
                entries.append(e)
            prior_ids = {f.get("id") for f in findings}
        out = entries[::-1][:limit]
    else:
        dailies = sorted((p for p in cat_dir.iterdir() if _DAILY_RE.match(p.name)),
                         key=lambda p: p.name, reverse=True)[:limit]
        for p in dailies:
            findings = (_read_json(p) or {}).get("findings") or []
            e = _strip_entry(findings, set())
            if e is not None:
                out.append(e)
    return out


def counterweight_ids(entries):
    out = {}
    for e in entries:
        if e.get("lens") != "risk":
            continue
        for fid in (e.get("evidenceFindingIds") or e.get("findingIds") or []):
            out[fid] = e.get("title") or ""
    return out


def _attention_state(store_root, category_id):
    try:
        from .build import build_model
        model, _ = build_model(category_id, str(Path(store_root) / category_id),
                               "work", None, generated_at="")
        a = model["alert"]
        return {"word": _ATTENTION.get(a["color"], "calm"),
                "css": _ATTENTION.get(a["color"], "calm"),
                "raw_word": _ATTENTION.get(a["raw"], "calm"),
                "lagging": a["raw"] != a["color"]}
    except Exception:
        return {"word": "calm", "css": "calm", "raw_word": "calm",
                "lagging": False}


def build_brief_model(category_id, store_dir, today, price_fn=None):
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    latest, prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    status = latest.get("categoryStatus") or {}
    year, month = (as_of.split("-") + ["1"])[:2]
    findings = latest.get("findings") or []

    slots = load_slots()
    wanted = {i for s in slots for i in s["indicators"]}
    series = read_series(store_root / "series", wanted)
    occupants = select_occupants(slots, findings, series,
                                 (prior or {}).get("findings") or [], today)

    book = read_thesis_book(store_root, category_id)
    rows, total, prov = select_calls(book)
    call_rows = [{"title": e.get("title") or "", "lens": e.get("lens") or "",
                  "conviction": e.get("conviction") or "",
                  "verdict": e.get("lastVerdict") or "not yet judged",
                  "glyph": _GLYPHS.get(e.get("lastVerdict") or "", ""),
                  "streak": int(e.get("streak") or 0),
                  "trigger": e.get("falsifiableTrigger") or ""} for e in rows]

    check = last_signal_check(store_root, cat_dir)
    stale = False
    if check:
        y, mo, d = (int(x) for x in check.split("-"))
        stale = (today - _dt.date(y, mo, d)).days > 3

    dims = []
    ratings = latest.get("dimensionRatings") or {}
    dstat = latest.get("dimensionStatus") or {}
    for name, r in ratings.items():
        dims.append({"name": name, "rating": r.get("rating") or "—",
                     "direction": r.get("direction") or "steady",
                     "confidence": (r.get("confidence") or {}).get("level") or "",
                     "sentence": _first_sentence(r.get("rationale")),
                     "capped": bool((dstat.get(name) or {}).get("confidenceCap"))})

    observed = sorted((f.get("observedAt") or "")[:10] for f in findings
                      if f.get("observedAt"))
    primary = sum(1 for f in findings if any(
        e.get("tier") == "primary" for e in (f.get("evidence") or [])))

    return {
        "category_id": category_id, "category_label": "Merchant GPU",
        "month_label": f"{_MONTHS[int(month) - 1]} {year}" if as_of else "",
        "revision": rev, "narrative": latest.get("narrative") or "",
        "status": {"rating": status.get("rating") or "—",
                   "direction": status.get("direction") or "",
                   "reason": _first_sentence(status.get("reason")),
                   "constraint": status.get("constraintLabel") or ""},
        "attention": _attention_state(store_root, category_id),
        "last_check": check, "stale": stale,
        "agenda": [{"slot_label": o.slot_label, "metric_label": o.candidate.label,
                    "display": o.candidate.display,
                    "trend_word": o.candidate.trend_word,
                    "as_of": o.candidate.observed_at,
                    "source": o.candidate.source_name, "was": o.was_label}
                   for o in occupants],
        "tsmc": read_implication_lines(store_root, category_id, as_of),
        "calls": {"rows": call_rows, "total": total, "provisional": prov},
        "strip": signal_strip(cat_dir),
        "dimensions": dims,
        "evidence": {"n": len(findings),
                     "median": observed[len(observed) // 2] if observed else "",
                     "oldest": observed[0] if observed else "",
                     "primary": primary},
        "counterweights": counterweight_ids(book),
    }
