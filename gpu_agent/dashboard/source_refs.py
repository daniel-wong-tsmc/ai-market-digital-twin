"""Resolve scorecard finding IDs into displayable source references.

Pure functions only: no file I/O, no network, no clock. Callers pass in
already-loaded dicts (a scorecard, or a findings-by-id index) and get back
plain dicts shaped for the dashboard's ``ref`` schema (see
web/schema/dashboard.schema.json): {title, outlet, url, date, tier}.
"""

from __future__ import annotations

VIA_SEPARATOR = " via "


def findings_index(scorecard: dict) -> dict[str, dict]:
    """scorecard['findings'] keyed by id."""
    return {f["id"]: f for f in scorecard.get("findings", [])}


def _ref_from_evidence(evidence: dict) -> dict:
    source = evidence.get("source", "") or ""
    if VIA_SEPARATOR in source:
        title, outlet = source.split(VIA_SEPARATOR, 1)
    else:
        title, outlet = source, source
    return {
        "title": title,
        "outlet": outlet,
        "url": evidence.get("url"),
        "date": evidence.get("date"),
        "tier": evidence.get("tier"),
    }


def refs_for_finding_ids(finding_ids: list[str], findings_by_id: dict[str, dict],
                          max_refs: int = 3) -> list[dict]:
    """Each finding's evidence[] entries -> ref dicts
    {title, outlet, url, date, tier}; deduped by url; primary tier first;
    unknown ids skipped (never raise). title = evidence['excerpt'][:80] is WRONG —
    title comes from evidence['source'] before ' via ', outlet = the ' via ' tail
    or the full source string; url/date/tier copied verbatim."""
    refs = []
    seen_urls = set()
    for fid in finding_ids:
        finding = findings_by_id.get(fid)
        if finding is None:
            continue
        for evidence in finding.get("evidence", []):
            url = evidence.get("url")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            refs.append(_ref_from_evidence(evidence))

    refs.sort(key=lambda r: 0 if r["tier"] == "primary" else 1)
    return refs[:max_refs]


def assessment_ref(based_on: list[dict]) -> dict:
    """{'assessment': True, 'basedOn': based_on} for synthesis sentences."""
    return {"assessment": True, "basedOn": based_on}
