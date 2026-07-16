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
    return [e for e in (art.get("entries") or []) if isinstance(e, dict)]


def select_calls(entries, cap=7):
    total = len(entries)
    prov = sum(1 for e in entries if e.get("status") == "provisional")
    ordered = sorted(entries, key=lambda e: (
        0 if e.get("status") == "registered" else 1,
        _CONVICTION_ORDER.get(e.get("conviction"), 3),
        -(e.get("streak") or 0),
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
    out = []
    for ln in art.get("lines") or []:
        if isinstance(ln, dict) and (ln.get("watchItem") or ln.get("text")):
            out.append({"text": ln.get("watchItem") or ln.get("text"),
                        "dims": list(ln.get("dimensions") or []),
                        "thesis_ids": list(ln.get("thesisIds") or []),
                        "finding_ids": list(ln.get("findingIds") or [])})
    return out


def last_signal_check(store_root, cat_dir):
    log = _read_json(Path(store_root) / "cycle-log.json")
    stamp = (log or {}).get("capturedAt") or ""
    if stamp:
        return stamp[:10]
    latest, _, _, _ = latest_monthly(cat_dir)
    stamps = [f.get("capturedAt") or "" for f in (latest or {}).get("findings", [])]
    stamps = [s[:10] for s in stamps if s]
    return max(stamps) if stamps else ""
