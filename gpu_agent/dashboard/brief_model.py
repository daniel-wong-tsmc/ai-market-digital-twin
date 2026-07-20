"""F97 Executive Brief page model — pure projection from store artifacts.

No LLM, no network, no wall-clock: `today` is always a parameter."""
from __future__ import annotations

import json
import re
from pathlib import Path

_MONTHLY_RE = re.compile(r"^(\d{4}-\d{2})-v(\d+)\.json$")
_CONVICTION_ORDER = {"high": 0, "medium": 1, "low": 2}

RATING_ORDINAL = {"weak": 0.0, "mixed": 1.0, "moderate": 1.0,
                  "strong": 2.0, "very strong": 3.0}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dimension_rating_history(cat_dir, limit=12):
    cat_dir = Path(cat_dir)
    try:
        paths = list(cat_dir.iterdir())
    except OSError:
        return {}
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in paths for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))[-limit:]
    hist = {}
    for _, _, p in revs:
        art = _read_json(p) or {}
        ratings = art.get("dimensionRatings")
        if not isinstance(ratings, dict):
            continue
        for name, r in ratings.items():
            if not isinstance(r, dict):
                continue
            word = (r.get("rating") or "").strip().lower()
            hist.setdefault(name, []).append(RATING_ORDINAL.get(word, 1.0))
    return hist


def _dict_findings(art):
    raw = (art or {}).get("findings")
    return [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []


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


_TILE_CODE_SUFFIX = re.compile(r"\s*\([DSPX]\d{1,2}\)\s*$")


def _indicator_labels():
    # F98: plain-English tile labels come from the indicator registry's own
    # `label` field. IndicatorRegistry.indicators is a dict of RAW dicts (not
    # model objects), so this reads v.get("label"), not v.label. Never allowed
    # to raise: any registry-load problem just means no label overrides.
    # Several registry labels append the internal doctrine code, e.g.
    # "Marginal-buyer financing conditions (X5)"; strip that trailing code so
    # the exec-facing tile shows plain English and the exec-copy register lint
    # (lint_tile_labels) does not reject it the first time such an indicator
    # becomes an agenda occupant.
    try:
        from gpu_agent.config import REGISTRY_PATH
        from gpu_agent.registry.indicators import IndicatorRegistry
        reg = IndicatorRegistry.load(REGISTRY_PATH)
        return {k: _TILE_CODE_SUFFIX.sub("", v.get("label")).strip()
                for k, v in reg.indicators.items() if v.get("label")}
    except Exception:
        return {}

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-v(\d+)\.json$")
_ATTENTION = {"green": "calm", "yellow": "watch", "orange": "elevated",
              "red": "critical"}
_GLYPHS = {"strengthened": "▲", "weakened": "▼", "reaffirmed": "◆"}
_ABBREV = {"e.g", "i.e", "vs", "inc", "corp", "ltd", "co", "mr", "mrs", "dr",
           "st", "no", "etc", "jr", "sr", "approx", "fig", "u.s", "u.k", "u.n"}


def _first_sentence(text):
    text = (text or "").strip()
    for i, ch in enumerate(text):
        if ch != ".":
            continue
        if i + 1 != len(text) and text[i + 1] != " ":
            continue
        # skip abbreviation dots: a single uppercase letter (initialism like "U.S.")…
        if i >= 1 and text[i - 1].isupper() and (i < 2 or not text[i - 2].isalpha()):
            continue
        # …or a known abbreviation token ending at this period
        tail = text[max(0, i - 6):i].lower().split()
        if tail and tail[-1] in _ABBREV:
            continue
        return text[:i + 1]
    return text


def first_n_sentences(text, n=2):
    text = (text or "").strip()
    out, rest = [], text
    for _ in range(n):
        s = _first_sentence(rest)
        if not s:
            break
        out.append(s)
        rest = rest[len(s):].strip()
        if not rest:
            break
    return " ".join(out)


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


def chart_series(cat_dir, limit=12):
    cat_dir = Path(cat_dir)
    try:
        paths = list(cat_dir.iterdir())
    except OSError:
        return {"labels": [], "demand": [], "supply": []}
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in paths for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))[-limit:]
    labels, demand, supply = [], [], []
    for as_of, rev, p in revs:
        art = _read_json(p) or {}
        ds = art.get("demandSupply")
        ds = ds if isinstance(ds, dict) else {}
        labels.append(f"{as_of}-v{rev}")
        demand.append(float(ds.get("dmiContribution") or 0.0))
        supply.append(float(ds.get("smiContribution") or 0.0))
    return {"labels": labels, "demand": demand, "supply": supply}


def signal_strip(cat_dir, limit=7):
    cat_dir = Path(cat_dir)
    try:
        paths = list(cat_dir.iterdir())
    except OSError:
        return []
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in paths
                   for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))
    out = []
    if len(revs) >= 2:
        prior_ids = set()
        entries = []
        for _, _, p in revs:
            findings = _dict_findings(_read_json(p))
            e = _strip_entry(findings, prior_ids)
            if e is not None:
                entries.append(e)
            prior_ids = {f.get("id") for f in findings}
        out = entries[::-1][:limit]
    else:
        dailies = sorted((p for p in paths if _DAILY_RE.match(p.name)),
                         key=lambda p: p.name, reverse=True)[:limit]
        for p in dailies:
            findings = _dict_findings(_read_json(p))
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
    findings = _dict_findings(latest)

    slots = load_slots()
    wanted = {i for s in slots for i in s["indicators"]}
    series = read_series(store_root / "series", wanted)
    labels = _indicator_labels()
    occupants = select_occupants(slots, findings, series,
                                 _dict_findings(prior), today, labels)

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
    ratings = latest.get("dimensionRatings")
    dstat = latest.get("dimensionStatus")
    if not isinstance(ratings, dict):
        ratings = {}
    if not isinstance(dstat, dict):
        dstat = {}
    for name, r in ratings.items():
        if not isinstance(r, dict):
            continue
        conf = r.get("confidence")
        conf_level = conf.get("level") if isinstance(conf, dict) else ""
        ds = dstat.get(name)
        capped = bool(ds.get("confidenceCap")) if isinstance(ds, dict) else False
        dims.append({"name": name, "rating": r.get("rating") or "—",
                     "direction": r.get("direction") or "steady",
                     "confidence": conf_level or "",
                     "sentence": _first_sentence(r.get("rationale")),
                     "capped": capped})

    observed = sorted((f.get("observedAt") or "")[:10] for f in findings
                      if f.get("observedAt"))
    primary = 0
    for f in findings:
        ev = f.get("evidence")
        if isinstance(ev, list) and any(
                isinstance(e, dict) and e.get("tier") == "primary" for e in ev):
            primary += 1

    return {
        "category_id": category_id, "category_label": "Merchant GPU",
        "month_label": f"{_MONTHS[int(month) - 1]} {year}" if as_of else "",
        "revision": rev, "narrative": latest.get("narrative") or "",
        "brief_two": first_n_sentences(latest.get("narrative") or "", 2),
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
                    "source": o.candidate.source_name, "was": o.was_label,
                    "delta_line": o.candidate.delta_line}
                   for o in occupants],
        "tsmc": read_implication_lines(store_root, category_id, as_of),
        "calls": {"rows": call_rows, "total": total, "provisional": prov},
        "strip": signal_strip(cat_dir),
        "chart": chart_series(cat_dir),
        "dimensions": dims,
        "evidence": {"n": len(findings),
                     "median": observed[len(observed) // 2] if observed else "",
                     "oldest": observed[0] if observed else "",
                     "primary": primary},
        "counterweights": counterweight_ids(book),
    }
