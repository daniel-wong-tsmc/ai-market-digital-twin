"""Tests for gpu_agent.manifest — models, loader, and gap computation."""
import datetime as dt
import json
import pytest
from pathlib import Path
from gpu_agent.manifest import (
    CoverageManifest,
    CoverageGap,
    ExpectedSource,
    ManifestLoadError,
    load_manifest,
    compute_coverage_gaps,
    gather_priority,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

MINIMAL_MANIFEST = {
    "version": "1.0",
    "categoryId": "chips.merchant-gpu",
    "asOf": "2026-06",
    "description": "Test manifest",
    "expectedIndicators": [
        {
            "indicatorId": "D2",
            "dimension": "momentum",
            "priority": "required",
            "sourceIds": ["nvda-earnings"],
        }
    ],
    "expectedSources": [
        {
            "id": "nvda-earnings",
            "label": "NVIDIA earnings filings",
            "urlPatterns": ["investor.nvidia.com"],
            "accessMethod": "filing",
            "tier": "primary",
            "costUsd": 0.0,
            "license": "public",
            "refresh": "quarterly",
            "indicators": ["D2"],
        }
    ],
}

PAYWALLED_SOURCE = {
    "id": "trendforce-gpu",
    "label": "TrendForce GPU tracker",
    "urlPatterns": ["trendforce.com"],
    "accessMethod": "licensed-api",
    "tier": "secondary",
    "costUsd": 5000.0,
    "license": "licensed",
    "refresh": "quarterly",
    "indicators": ["market-share-pct"],
    "paywalledNote": "Subscription required.",
}


# ── Model validation tests ───────────────────────────────────────────────────

def test_manifest_loads_valid_json():
    m = CoverageManifest(**MINIMAL_MANIFEST)
    assert m.categoryId == "chips.merchant-gpu"
    assert len(m.expectedIndicators) == 1
    assert len(m.expectedSources) == 1


def test_manifest_rejects_unknown_priority():
    bad = {**MINIMAL_MANIFEST}
    bad["expectedIndicators"] = [
        {**MINIMAL_MANIFEST["expectedIndicators"][0], "priority": "critical"}
    ]
    with pytest.raises(Exception):  # Pydantic ValidationError
        CoverageManifest(**bad)


def test_manifest_rejects_unknown_access_method():
    bad = {**MINIMAL_MANIFEST}
    bad["expectedSources"] = [
        {**MINIMAL_MANIFEST["expectedSources"][0], "accessMethod": "ftp"}
    ]
    with pytest.raises(Exception):
        CoverageManifest(**bad)


# ── load_manifest tests ──────────────────────────────────────────────────────

def test_load_manifest_missing_file():
    with pytest.raises(ManifestLoadError, match="not found"):
        load_manifest("/nonexistent/path/manifest.json")


def test_load_manifest_invalid_json(tmp_path):
    bad_file = tmp_path / "manifest.json"
    bad_file.write_text("not json", encoding="utf-8")
    with pytest.raises(ManifestLoadError, match="invalid JSON"):
        load_manifest(bad_file)


def test_load_manifest_schema_failure(tmp_path):
    bad = {"version": "1.0", "categoryId": "chips.merchant-gpu"}  # missing required fields
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ManifestLoadError, match="schema"):
        load_manifest(f)


def test_load_manifest_valid(tmp_path):
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(MINIMAL_MANIFEST), encoding="utf-8")
    m = load_manifest(f)
    assert m.categoryId == "chips.merchant-gpu"


# ── compute_coverage_gaps tests ──────────────────────────────────────────────

def test_no_gaps_when_all_covered():
    manifest = CoverageManifest(**MINIMAL_MANIFEST)
    blob_urls = ["https://investor.nvidia.com/quarterly-earnings/q1-2026"]
    found = {"D2"}
    gaps = compute_coverage_gaps(manifest, blob_urls, found)
    assert gaps == []


def test_gap_when_source_url_not_matched():
    manifest = CoverageManifest(**MINIMAL_MANIFEST)
    blob_urls = ["https://some-other-site.com/article"]  # no investor.nvidia.com
    found = set()
    gaps = compute_coverage_gaps(manifest, blob_urls, found)
    source_gap = next(g for g in gaps if g.type == "source")
    assert source_gap.id == "nvda-earnings"
    assert source_gap.acquisitionStatus == "not-covered"


def test_gap_when_indicator_not_in_found_set():
    manifest = CoverageManifest(**MINIMAL_MANIFEST)
    blob_urls = ["https://investor.nvidia.com/q1-2026"]  # source covered
    found: set[str] = set()  # but no D2 finding produced
    gaps = compute_coverage_gaps(manifest, blob_urls, found)
    indicator_gap = next((g for g in gaps if g.type == "indicator"), None)
    assert indicator_gap is not None
    assert indicator_gap.id == "D2"
    assert indicator_gap.acquisitionStatus == "not-covered"


def test_paywalled_source_becomes_gap_immediately():
    manifest_data = {
        **MINIMAL_MANIFEST,
        "expectedIndicators": [
            {
                "indicatorId": "market-share-pct",
                "dimension": "moat",
                "priority": "required",
                "sourceIds": ["trendforce-gpu"],
            }
        ],
        "expectedSources": [PAYWALLED_SOURCE],
    }
    manifest = CoverageManifest(**manifest_data)
    gaps = compute_coverage_gaps(manifest, blob_urls=[], found_indicator_ids=set())
    paywalled = next(g for g in gaps if g.id == "trendforce-gpu")
    assert paywalled.acquisitionStatus == "paywalled"
    assert paywalled.type == "source"


def test_real_manifest_indicator_ids_all_resolve_in_registry():
    """Seam guard: every expectedIndicator.indicatorId in the shipped manifest
    must resolve to a real registry indicator. strategicRisk is a DIMENSION,
    not an indicator id; the real ids are exportControlExposure and
    customerConcentration."""
    from gpu_agent.registry.indicators import IndicatorRegistry

    manifest = load_manifest("manifests/chips.merchant-gpu.json")
    reg = IndicatorRegistry.load("registry/indicators.json")
    for entry in manifest.expectedIndicators:
        reg.resolve(entry.indicatorId)  # must not raise


def test_required_vs_preferred_gap_priority():
    manifest_data = {
        **MINIMAL_MANIFEST,
        "expectedIndicators": [
            {"indicatorId": "D2", "dimension": "momentum", "priority": "required",
             "sourceIds": ["nvda-earnings"]},
            {"indicatorId": "grossMargin", "dimension": "unitEconomics", "priority": "preferred",
             "sourceIds": ["nvda-earnings"]},
        ],
    }
    manifest = CoverageManifest(**manifest_data)
    gaps = compute_coverage_gaps(manifest, blob_urls=[], found_indicator_ids=set())
    required_gaps = [g for g in gaps if g.priority == "required"]
    preferred_gaps = [g for g in gaps if g.priority == "preferred"]
    assert len(required_gaps) >= 1
    assert len(preferred_gaps) >= 1


def test_new_indicators_present_in_manifest_and_resolve():
    """The five 4-2 indicators are declared in the shipped manifest and resolve."""
    from gpu_agent.registry.indicators import IndicatorRegistry

    manifest = load_manifest("manifests/chips.merchant-gpu.json")
    reg = IndicatorRegistry.load("registry/indicators.json")
    declared = {e.indicatorId for e in manifest.expectedIndicators}
    for ind in ("rpoBacklog", "vendorRevenueGuidance", "leadTimes", "designWins", "gpuSpotPrice"):
        assert ind in declared, f"{ind} missing from manifest expectedIndicators"
        reg.resolve(ind)  # must not raise


def test_source_inventory_entries_validate_as_source_entries():
    """Every sourceInventory entry in indicators.json (incl. the 5 new) is a valid SourceEntry."""
    import json
    from pathlib import Path
    from gpu_agent.manifest import SourceEntry

    data = json.loads(Path("registry/indicators.json").read_text(encoding="utf-8"))
    inv = data["sourceInventory"]
    for ind in ("rpoBacklog", "vendorRevenueGuidance", "leadTimes", "designWins", "gpuSpotPrice"):
        assert ind in inv, f"{ind} missing from sourceInventory"
    for ind_id, entries in inv.items():
        for entry in entries:
            SourceEntry(**entry)  # must not raise


def test_new_indicators_flagged_as_gaps_when_uncovered():
    """With nothing gathered, the five new indicators are logged as coverage gaps."""
    manifest = load_manifest("manifests/chips.merchant-gpu.json")
    gaps = compute_coverage_gaps(manifest, blob_urls=[], found_indicator_ids=set())
    gap_ids = {g.id for g in gaps if g.type == "indicator"}
    for ind in ("rpoBacklog", "vendorRevenueGuidance", "leadTimes", "designWins", "gpuSpotPrice"):
        assert ind in gap_ids


def test_semianalysis_source_is_paywalled_gap():
    """The SemiAnalysis lead-times source is inventoried as paywalled (labeled, never scraped)."""
    manifest = load_manifest("manifests/chips.merchant-gpu.json")
    gaps = compute_coverage_gaps(manifest, blob_urls=[], found_indicator_ids=set())
    sa = next((g for g in gaps if g.id == "semianalysis"), None)
    assert sa is not None
    assert sa.acquisitionStatus == "paywalled"
    assert sa.type == "source"


# ── Earnings-window cadence (F103 Task 5) ────────────────────────────────────

def test_manifest_round_trips_cadence_earnings_dates_primary_domains():
    """A manifest JSON round-trips and exposes cadence, earningsDates, primaryDomains."""
    data = {
        **MINIMAL_MANIFEST,
        "primaryDomains": ["investor.nvidia.com", "sec.gov"],
        "earningsDates": {"nvidia": "2026-08-26", "amd": "2026-08-04"},
        "expectedSources": [
            {**MINIMAL_MANIFEST["expectedSources"][0], "cadence": "earnings-window"},
        ],
    }
    m = CoverageManifest(**data)
    assert m.primaryDomains == ["investor.nvidia.com", "sec.gov"]
    assert m.earningsDates == {"nvidia": "2026-08-26", "amd": "2026-08-04"}
    assert m.expectedSources[0].cadence == "earnings-window"


def test_manifest_defaults_earnings_dates_and_primary_domains_when_absent():
    m = CoverageManifest(**MINIMAL_MANIFEST)
    assert m.earningsDates == {}
    assert m.primaryDomains == []
    assert m.expectedSources[0].cadence is None


def test_manifest_rejects_unknown_cadence_value():
    bad = {**MINIMAL_MANIFEST}
    bad["expectedSources"] = [
        {**MINIMAL_MANIFEST["expectedSources"][0], "cadence": "daily"}
    ]
    with pytest.raises(Exception):
        CoverageManifest(**bad)


def test_load_manifest_rejects_unknown_cadence_value(tmp_path):
    bad = {**MINIMAL_MANIFEST}
    bad["expectedSources"] = [
        {**MINIMAL_MANIFEST["expectedSources"][0], "cadence": "daily"}
    ]
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ManifestLoadError):
        load_manifest(f)


def test_gather_priority_normal_when_no_cadence():
    source = ExpectedSource(**MINIMAL_MANIFEST["expectedSources"][0])
    manifest = CoverageManifest(**MINIMAL_MANIFEST)
    today = dt.date(2026, 7, 25)
    assert gather_priority(source, manifest, today) == "normal"


def test_gather_priority_heavy_within_earnings_window():
    source = ExpectedSource(**{**MINIMAL_MANIFEST["expectedSources"][0],
                               "cadence": "earnings-window", "earningsKey": "nvidia"})
    manifest = CoverageManifest(**{**MINIMAL_MANIFEST, "earningsDates": {"nvidia": "2026-08-01"}})
    today = dt.date(2026, 7, 25)  # 7 days before 2026-08-01
    assert gather_priority(source, manifest, today) == "heavy"


def test_gather_priority_light_outside_earnings_window():
    source = ExpectedSource(**{**MINIMAL_MANIFEST["expectedSources"][0],
                               "cadence": "earnings-window", "earningsKey": "nvidia"})
    manifest = CoverageManifest(**{**MINIMAL_MANIFEST, "earningsDates": {"nvidia": "2026-10-01"}})
    today = dt.date(2026, 7, 25)
    assert gather_priority(source, manifest, today) == "light"


def test_gather_priority_light_for_weekly_cadence():
    source = ExpectedSource(**{**MINIMAL_MANIFEST["expectedSources"][0], "cadence": "weekly"})
    manifest = CoverageManifest(**{**MINIMAL_MANIFEST, "earningsDates": {"nvidia": "2026-07-25"}})
    today = dt.date(2026, 7, 25)
    assert gather_priority(source, manifest, today) == "light"


def test_gather_priority_light_for_other_vendors_print():
    """F130: one vendor reporting must NOT make another vendor's source heavy.

    Live 2026-08-31: NVIDIA printed 2026-08-26 (5 days out), AMD printed
    2026-08-04 (27 days out). amd-earnings was ranked heavy off NVIDIA's date.
    """
    source = ExpectedSource(**{
        **MINIMAL_MANIFEST["expectedSources"][0],
        "id": "amd-earnings",
        "cadence": "earnings-window",
        "earningsKey": "amd",
    })
    manifest = CoverageManifest(**{
        **MINIMAL_MANIFEST,
        "earningsDates": {"nvidia": "2026-08-26", "amd": "2026-08-04"},
    })
    today = dt.date(2026, 8, 31)
    assert gather_priority(source, manifest, today) == "light"


def test_gather_priority_heavy_only_for_the_vendor_that_just_printed():
    """The same manifest/day: NVIDIA's own source IS heavy (5 days after print)."""
    source = ExpectedSource(**{
        **MINIMAL_MANIFEST["expectedSources"][0],
        "cadence": "earnings-window",
        "earningsKey": "nvidia",
    })
    manifest = CoverageManifest(**{
        **MINIMAL_MANIFEST,
        "earningsDates": {"nvidia": "2026-08-26", "amd": "2026-08-04"},
    })
    today = dt.date(2026, 8, 31)
    assert gather_priority(source, manifest, today) == "heavy"


def test_gather_priority_light_when_no_earnings_key_declared():
    """F130 ruling 3: an earnings-window source with no earningsKey is light --
    it must not ride another vendor's print (e.g. intc-earnings)."""
    source = ExpectedSource(**{
        **MINIMAL_MANIFEST["expectedSources"][0],
        "id": "intc-earnings",
        "cadence": "earnings-window",
    })
    manifest = CoverageManifest(**{
        **MINIMAL_MANIFEST,
        "earningsDates": {"nvidia": "2026-08-26", "amd": "2026-08-04"},
    })
    today = dt.date(2026, 8, 31)
    assert source.earningsKey is None
    assert gather_priority(source, manifest, today) == "light"


def test_gather_priority_light_when_earnings_key_has_no_date():
    """A declared key that the manifest has no date for is also light."""
    source = ExpectedSource(**{
        **MINIMAL_MANIFEST["expectedSources"][0],
        "id": "intc-earnings",
        "cadence": "earnings-window",
        "earningsKey": "intel",
    })
    manifest = CoverageManifest(**{
        **MINIMAL_MANIFEST,
        "earningsDates": {"nvidia": "2026-08-26"},
    })
    today = dt.date(2026, 8, 31)
    assert gather_priority(source, manifest, today) == "light"


def test_gather_priority_window_stays_symmetric_seven_days():
    """F130 ruling 4: the +/-7-day window is a deliberate no-change --
    heavy at exactly 7 days either side of the vendor's own print, light at 8."""
    def _priority(day: int) -> str:
        source = ExpectedSource(**{
            **MINIMAL_MANIFEST["expectedSources"][0],
            "cadence": "earnings-window",
            "earningsKey": "nvidia",
        })
        manifest = CoverageManifest(**{
            **MINIMAL_MANIFEST, "earningsDates": {"nvidia": "2026-08-26"}})
        return gather_priority(source, manifest, dt.date(2026, 8, 26) + dt.timedelta(days=day))

    assert _priority(-7) == "heavy"
    assert _priority(7) == "heavy"
    assert _priority(-8) == "light"
    assert _priority(8) == "light"


def test_real_manifest_earnings_sources_declare_an_earnings_key():
    """The shipped manifest links every earnings-window source to a vendor."""
    m = load_manifest(Path(__file__).parent.parent / "manifests" / "chips.merchant-gpu.json")
    linked = {s.id: s.earningsKey
              for s in m.expectedSources if s.cadence == "earnings-window"}
    assert linked["nvda-earnings"] == "nvidia"
    assert linked["amd-earnings"] == "amd"
    assert linked["nvda-10k-risk-factors"] == "nvidia"


def test_gather_priority_ignores_unparseable_earnings_date():
    source = ExpectedSource(**{**MINIMAL_MANIFEST["expectedSources"][0],
                               "cadence": "earnings-window", "earningsKey": "nvidia"})
    manifest = CoverageManifest(**{**MINIMAL_MANIFEST, "earningsDates": {"nvidia": "not-a-date"}})
    today = dt.date(2026, 7, 25)
    assert gather_priority(source, manifest, today) == "light"


def test_real_manifest_still_validates_with_cadence_fields():
    """The shipped manifest still loads after adding cadence/earningsDates fields."""
    manifest = load_manifest("manifests/chips.merchant-gpu.json")
    for sid in ("nvda-earnings", "amd-earnings", "nvda-10k-risk-factors"):
        src = manifest.source_by_id(sid)
        assert src is not None
        assert src.cadence == "earnings-window"
    assert "nvidia" in manifest.earningsDates
    assert "amd" in manifest.earningsDates
