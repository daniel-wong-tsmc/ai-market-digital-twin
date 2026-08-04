"""Coverage manifest models and gap computation for sub-project C.

Defines:
  CoverageManifest  — the per-category expected-coverage declaration
  CoverageGap       — a not-covered expected item (source or indicator)
  load_manifest()   — typed loader with clear error messages
  compute_coverage_gaps() — pure gap checker (no I/O)
  CoverageRecord    — the durable, self-auditing coverage artifact (F109)
  build_coverage_record() — pure builder for that artifact (no I/O)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


# ── Source entry (also used in per-indicator sourceInventory in indicators.json) ──

class SourceEntry(BaseModel):
    name: str
    accessMethod: Literal["free-web", "filing", "licensed-api", "mcp", "manual"]
    tier: Literal["primary", "secondary"]
    costUsd: float = 0.0
    license: Literal["public", "licensed", "confidential", "unknown"] = "public"
    refresh: Literal["realtime", "daily", "weekly", "quarterly", "annual", "on-demand"]


# ── Manifest components ───────────────────────────────────────────────────────

class ExpectedSource(BaseModel):
    id: str
    label: str
    urlPatterns: list[str] = Field(default_factory=list)
    mirrorPatterns: list[str] = Field(default_factory=list)
    accessMethod: Literal["free-web", "filing", "licensed-api", "mcp", "manual"]
    tier: Literal["primary", "secondary"]
    costUsd: float = 0.0
    license: Literal["public", "licensed", "confidential", "unknown"] = "public"
    refresh: Literal["realtime", "daily", "weekly", "quarterly", "annual", "on-demand"]
    indicators: list[str] = Field(default_factory=list)
    paywalledNote: str | None = None
    cadence: Optional[Literal["earnings-window", "weekly"]] = None

    @property
    def is_paywalled(self) -> bool:
        """True if this source requires a paid license we do not hold."""
        return self.costUsd > 0 or self.accessMethod == "licensed-api"


class ExpectedIndicator(BaseModel):
    indicatorId: str
    dimension: str
    priority: Literal["required", "preferred", "optional"]
    sourceIds: list[str] = Field(default_factory=list)


# F106: the topic-slug tree published in huggingnews.com/SKILL.md v0.0.2. A manifest
# declaring a slug outside this set fails loud at load (typo tripwire). Update this
# copy when the published contract version moves.
HUGGINGNEWS_TAG_SLUGS = frozenset({
    "ai", "ai-fundraising",
    "ai-modeling", "ai-model-releases", "ai-open-models", "ai-research-evals",
    "ai-products", "ai-agents-coding", "ai-enterprise-tools", "ai-generative-media",
    "ai-infrastructure", "ai-compute-chips", "ai-inference-platforms",
    "ai-governance", "ai-policy-regulation", "ai-legal-safety",
    "ai-sector-impact",
})


class CoverageManifest(BaseModel):
    version: str
    categoryId: str
    asOf: str
    description: str = ""
    expectedIndicators: list[ExpectedIndicator] = Field(default_factory=list)
    expectedSources: list[ExpectedSource] = Field(default_factory=list)
    earningsDates: dict[str, str] = Field(default_factory=dict)
    primaryDomains: list[str] = Field(default_factory=list)
    huggingnewsTags: list[str] = Field(default_factory=list)

    @field_validator("huggingnewsTags")
    @classmethod
    def _huggingnews_slugs_known(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in HUGGINGNEWS_TAG_SLUGS]
        if unknown:
            raise ValueError(
                f"unknown huggingnews tag slug(s) {unknown} — valid slugs are the "
                f"published huggingnews.com/SKILL.md tree (see HUGGINGNEWS_TAG_SLUGS)")
        return v

    def source_by_id(self, source_id: str) -> ExpectedSource | None:
        return next((s for s in self.expectedSources if s.id == source_id), None)


# ── Coverage gap ──────────────────────────────────────────────────────────────

class CoverageGap(BaseModel):
    type: Literal["indicator", "source"]
    id: str
    priority: Literal["required", "preferred", "optional"]
    acquisitionStatus: Literal[
        "paywalled", "not-covered", "cap-truncated",
        "manual-upload-required", "mcp-unavailable", "waived"
    ]
    reason: str
    paywalledNote: str | None = None


# ── Coverage override (structured, auditable waiver) ─────────────────────────

class CoverageOverride(BaseModel):
    type: Literal["indicator", "source"]
    id: str
    reason: str          # the auditable free text that used to live in prose
    waivedBy: str         # who/what waived it, e.g. "gather-coordinator 2026-07-02"


# ── Loader ────────────────────────────────────────────────────────────────────

class ManifestLoadError(Exception):
    pass


def load_manifest(path: str | Path) -> CoverageManifest:
    """Load and validate a coverage manifest from a JSON file.

    Raises ManifestLoadError with a plain-language message on:
      - file not found
      - invalid JSON
      - schema validation failure
    """
    p = Path(path)
    if not p.exists():
        raise ManifestLoadError(f"Manifest file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestLoadError(f"Manifest at {p} contains invalid JSON: {exc}") from exc
    try:
        return CoverageManifest(**raw)
    except Exception as exc:
        raise ManifestLoadError(f"Manifest at {p} failed schema validation: {exc}") from exc


def _url_matches(url: str, pattern: str) -> bool:
    """Host-aware: a pattern with no '/' matches when the url's host == pattern or
    endswith '.'+pattern; a pattern with a path keeps today's substring semantics.
    """
    if "/" in pattern:
        return pattern in url
    host = urlparse(url).netloc
    if not host:
        return False
    return host == pattern or host.endswith("." + pattern)


# ── Gather priority (pure — no I/O) ──────────────────────────────────────────

def gather_priority(
    source: ExpectedSource, manifest: CoverageManifest, today: dt.date
) -> str:
    """Return "heavy", "light", or "normal" gather priority for a source.

    - No cadence set → "normal".
    - cadence == "earnings-window" and any manifest.earningsDates value falls
      within +/-7 days of `today` → "heavy".
    - Otherwise (cadence set but not currently in an earnings window,
      including cadence == "weekly") → "light".

    Pure: `today` must be passed in — never reads the real clock.
    """
    if source.cadence is None:
        return "normal"

    if source.cadence == "earnings-window":
        for raw_date in manifest.earningsDates.values():
            try:
                earnings_date = dt.date.fromisoformat(raw_date)
            except ValueError:
                continue
            if abs((earnings_date - today).days) <= 7:
                return "heavy"

    return "light"


# ── Gap computation (pure — no I/O) ──────────────────────────────────────────

def compute_coverage_gaps(
    manifest: CoverageManifest,
    blob_urls: list[str],
    found_indicator_ids: set[str],
    overrides: list[CoverageOverride] | None = None,
) -> list[CoverageGap]:
    """Return a gap record for each expected item not covered by the gather run.

    Args:
        manifest: the loaded CoverageManifest for this category.
        blob_urls: normalized URLs of all blobs the gather collected.
        found_indicator_ids: set of indicatorIds that appear in at least one
            collected blob (i.e., the coordinator matched an on-topic blob to
            this indicator).
        overrides: optional structured, auditable waivers. A gap whose
            (type, id) matches an override is STILL RETURNED but with
            acquisitionStatus="waived" and its reason extended with who/why
            waived it — waived gaps stay visible, never silently dropped.
            An override naming an item that has no gap (already covered)
            changes nothing.

    Returns:
        A list of CoverageGap records. An empty list means full coverage.
    """
    gaps: list[CoverageGap] = []

    # 1. Source coverage pass
    for src in manifest.expectedSources:
        if src.is_paywalled:
            gaps.append(CoverageGap(
                type="source",
                id=src.id,
                priority="required",  # paywalled sources default to required
                acquisitionStatus="paywalled",
                reason=f"Source '{src.label}' requires a paid license (costUsd={src.costUsd}).",
                paywalledNote=src.paywalledNote,
            ))
            continue  # do not attempt URL match for paywalled sources

        patterns = src.urlPatterns + src.mirrorPatterns
        matched = any(
            any(_url_matches(url, pattern) for pattern in patterns)
            for url in blob_urls
        )
        if not matched:
            gaps.append(CoverageGap(
                type="source",
                id=src.id,
                priority="required",
                acquisitionStatus="not-covered",
                reason=(
                    f"Source '{src.label}' was not fetched. "
                    f"URL patterns: {src.urlPatterns}"
                ),
            ))

    # 2. Indicator coverage pass
    for ind in manifest.expectedIndicators:
        # An indicator is covered only if its indicatorId explicitly appears in
        # found_indicator_ids.  Source-URL coverage is necessary but not
        # sufficient: if the gather fetched the source but the coordinator
        # never produced a finding for this indicator, that is still a gap.
        indicator_found = ind.indicatorId in found_indicator_ids

        if indicator_found:
            continue

        gaps.append(CoverageGap(
            type="indicator",
            id=ind.indicatorId,
            priority=ind.priority,
            acquisitionStatus="not-covered",
            reason=(
                f"Indicator '{ind.indicatorId}' (dimension: {ind.dimension}) "
                f"was not covered. Expected sources: {ind.sourceIds}."
            ),
        ))

    # 3. Apply structured overrides: waived gaps stay visible, never dropped.
    if overrides:
        by_key = {(ov.type, ov.id): ov for ov in overrides}
        for i, gap in enumerate(gaps):
            ov = by_key.get((gap.type, gap.id))
            if ov is None:
                continue
            gaps[i] = gap.model_copy(update={
                "acquisitionStatus": "waived",
                "reason": f"waived: {ov.reason} (by {ov.waivedBy}); original: {gap.reason}",
            })

    return gaps


# ── Durable coverage record (F109) ───────────────────────────────────────────

class CoverageRecord(BaseModel):
    """One cycle's coverage verdict, in a form that survives the machine.

    Before F109 the gap list existed only inside a run: `compute_coverage_gaps()`
    had no production caller, and its output was hand-copied into a file under the
    gitignored `work/` tree. This model is what gets committed instead, as
    `store/<categoryId>/coverage-<asOf>.json` — the same shape of tracked sidecar
    the L2 dedup report already uses.

    It is deliberately SELF-AUDITING: `judgedUrls`, `judgedIndicatorIds` and
    `manifestRef` record the exact inputs the verdict was computed over, so the gap
    list can still be checked long after the run's work dir is swept. A gap list you
    cannot re-derive is a claim, not a record.
    """
    schemaVersion: str = "1.0"
    categoryId: str
    asOf: str
    capturedAt: str
    manifestRef: str
    manifestVersion: str
    manifestAsOf: str
    gaps: list[CoverageGap] = Field(default_factory=list)
    gapCounts: dict[str, int] = Field(default_factory=dict)
    judgedUrls: list[str] = Field(default_factory=list)
    judgedIndicatorIds: list[str] = Field(default_factory=list)


def _count_gaps(gaps: list[CoverageGap]) -> dict[str, int]:
    """Precomputed tallies, so a reader never has to re-derive them (and so two
    readers can never disagree about how many gaps a cycle had).

    A waived gap is counted in `total` and in its priority bucket as well as in
    `waived`: waiving records a reason, it never erases the gap.
    """
    return {
        "total": len(gaps),
        "source": sum(1 for g in gaps if g.type == "source"),
        "indicator": sum(1 for g in gaps if g.type == "indicator"),
        "required": sum(1 for g in gaps if g.priority == "required"),
        "preferred": sum(1 for g in gaps if g.priority == "preferred"),
        "optional": sum(1 for g in gaps if g.priority == "optional"),
        "waived": sum(1 for g in gaps if g.acquisitionStatus == "waived"),
        "paywalled": sum(1 for g in gaps if g.acquisitionStatus == "paywalled"),
    }


def build_coverage_record(
    manifest: CoverageManifest,
    category_id: str,
    as_of: str,
    manifest_ref: str,
    fetched_urls: list[str],
    found_indicator_ids: set[str],
    captured_at: str,
    overrides: list[CoverageOverride] | None = None,
) -> CoverageRecord:
    """Build the durable coverage record. Pure — no I/O, no clock.

    `captured_at` is passed in rather than read from the clock so the same inputs
    always produce the same bytes (re-running a cycle's coverage check must not
    show up as a diff).

    Args:
        manifest: the loaded CoverageManifest for this category.
        category_id: the category this record belongs to (the store directory name).
        as_of: the cycle's asOf — also the filename key.
        manifest_ref: the path the manifest was loaded from, recorded verbatim so a
            later reader can find the declaration the verdict was judged against.
        fetched_urls: every URL the gather actually fetched this cycle.
        found_indicator_ids: indicatorIds this cycle actually produced a gated
            finding for. Fetching a source is NOT the same as covering its
            indicator — see compute_coverage_gaps().
        captured_at: ISO-8601 timestamp string for when this record was made.
        overrides: optional structured waivers; waived gaps stay in the list.
    """
    gaps = compute_coverage_gaps(
        manifest, list(fetched_urls), set(found_indicator_ids), overrides=overrides)
    return CoverageRecord(
        categoryId=category_id,
        asOf=as_of,
        capturedAt=captured_at,
        manifestRef=manifest_ref,
        manifestVersion=manifest.version,
        manifestAsOf=manifest.asOf,
        gaps=gaps,
        gapCounts=_count_gaps(gaps),
        judgedUrls=sorted(set(fetched_urls)),
        judgedIndicatorIds=sorted(set(found_indicator_ids)),
    )
