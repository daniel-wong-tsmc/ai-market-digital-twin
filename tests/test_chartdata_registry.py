"""F110 Task 3: curated chart-series registry.

Loader must never touch the network and must reject malformed entries
loudly (ValueError) rather than silently rendering an unproven estimate
as a small chart.
"""
from __future__ import annotations

import json

import pytest

from gpu_agent.chartdata.registry import ChartSeries, load_chart_series

REGISTRY_PATH = "registry/chart-series.json"


def test_load_chart_series_returns_three_entries():
    series = load_chart_series(REGISTRY_PATH)
    assert set(series) == {
        "amdDataCenterRevenue",
        "nvdaDataCenterRevenue",
        "gpuSpotPrice",
    }
    for entry in series.values():
        assert isinstance(entry, ChartSeries)


def test_amd_entry_fields_match_brief():
    series = load_chart_series(REGISTRY_PATH)
    amd = series["amdDataCenterRevenue"]
    assert amd.cadence == "quarterly"
    assert amd.quality == "hard-fact"
    assert amd.topicTags == ("amdDataCenter", "amd")
    assert amd.form == "columns"
    assert amd.unit == "US$ billions"
    assert amd.fetcher == "amd_dc_revenue"
    assert amd.sourceName == "AMD investor relations"
    assert amd.sourceUrl == "https://ir.amd.com/financial-information/quarterly-results"


def test_nvda_entry_is_wired_to_its_fetcher():
    """F134 (user rulings 2026-09-01): NVIDIA finally has a fetcher, and its
    sourceUrl points at the FINANCIAL-REPORTS page rather than the
    quarterly-results page. That is not cosmetic -- the quarterly-results
    page renders its quarter list in the browser, so the HTML a fetcher
    receives from it carries no press-release links at all and no discoverer
    could ever work against it."""
    series = load_chart_series(REGISTRY_PATH)
    nvda = series["nvdaDataCenterRevenue"]
    assert nvda.cadence == "quarterly"
    assert nvda.quality == "hard-fact"
    assert nvda.topicTags == ("nvidia", "nvidiaDataCenter")
    assert nvda.form == "columns"
    assert nvda.unit == "US$ billions"
    assert nvda.fetcher == "nvda_dc_revenue"
    assert nvda.sourceUrl == ("https://investor.nvidia.com/financial-info/"
                              "financial-reports/default.aspx")


def test_gpu_spot_price_is_estimate_and_never_chartable():
    series = load_chart_series(REGISTRY_PATH)
    spot = series["gpuSpotPrice"]
    assert spot.cadence == "monthly"
    assert spot.quality == "estimate"
    assert spot.topicTags == ("gpuSpotPrice",)
    assert spot.form == "line"
    assert spot.unit == "US$"
    assert spot.fetcher is None
    # This is the whole point of this series: an estimate must never be
    # drawn as a small chart, because a small chart reads as fact.
    assert spot.chartable is False


# ── F131: earningsKey scopes a quarterly series to its own company ────────
#
# Without it the fetch scheduler tested every quarterly series against every
# company's print date, so AMD's chart woke up during NVIDIA's earnings week.
# User ruling 2026-08-31: an explicit key on the entry, matched against the
# manifest's earningsDates keys.

def test_quarterly_entries_carry_their_own_earnings_key():
    series = load_chart_series(REGISTRY_PATH)
    assert series["amdDataCenterRevenue"].earningsKey == "amd"
    assert series["nvdaDataCenterRevenue"].earningsKey == "nvidia"


def test_monthly_entry_needs_no_earnings_key():
    """gpuSpotPrice is never scheduled off an earnings date -- price-sync
    owns it -- so it carries no key."""
    series = load_chart_series(REGISTRY_PATH)
    assert series["gpuSpotPrice"].earningsKey is None


def test_quarterly_entry_without_an_earnings_key_raises_value_error(tmp_path):
    """Loudly, at load time. A quarterly series with no key would match no
    print date at all and go silently never-due -- which is precisely the
    failure mode F131 was filed for. Better to refuse to load."""
    bad = {
        "series": [
            {
                "id": "broken",
                "name": "Broken series",
                "sourceName": "Nowhere",
                "sourceUrl": "https://example.com",
                "cadence": "quarterly",
                "quality": "hard-fact",
                "topicTags": ["broken"],
                "form": "columns",
                "unit": "USD",
                "fetcher": None,
                # "earningsKey" deliberately omitted
            }
        ]
    }
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="earningsKey"):
        load_chart_series(str(bad_path))


def _entry(**overrides) -> dict:
    base = {
        "id": "broken", "name": "Broken series", "sourceName": "Nowhere",
        "sourceUrl": "https://example.com", "cadence": "quarterly",
        "quality": "hard-fact", "topicTags": ["broken"], "form": "columns",
        "unit": "USD", "fetcher": None, "earningsKey": "amd",
    }
    base.update(overrides)
    return base


def test_monthly_entry_carrying_an_earnings_key_raises_value_error(tmp_path):
    """A monthly series is never scheduled off an earnings date, so a key on
    one is a mistake -- and a silent one, since nothing would ever read it."""
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps({"series": [
        _entry(cadence="monthly", form="line", earningsKey="amd")]}), encoding="utf-8")
    with pytest.raises(ValueError, match="earningsKey"):
        load_chart_series(str(bad_path))


def test_empty_string_earnings_key_raises_value_error(tmp_path):
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps({"series": [_entry(earningsKey="")]}),
                        encoding="utf-8")
    with pytest.raises(ValueError, match="earningsKey"):
        load_chart_series(str(bad_path))


def test_non_string_earnings_key_raises_value_error(tmp_path):
    bad = {
        "series": [
            {
                "id": "broken",
                "name": "Broken series",
                "sourceName": "Nowhere",
                "sourceUrl": "https://example.com",
                "cadence": "quarterly",
                "quality": "hard-fact",
                "topicTags": ["broken"],
                "form": "columns",
                "unit": "USD",
                "fetcher": None,
                "earningsKey": 7,
            }
        ]
    }
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="earningsKey"):
        load_chart_series(str(bad_path))


def test_hard_fact_entries_are_chartable():
    series = load_chart_series(REGISTRY_PATH)
    assert series["amdDataCenterRevenue"].chartable is True
    assert series["nvdaDataCenterRevenue"].chartable is True


def test_chartable_is_a_derived_property_not_a_stored_field():
    # Prove chartable truly derives from quality, rather than being an
    # independently-settable field that could drift out of sync.
    fact = ChartSeries(
        id="x", name="X", sourceName="S", sourceUrl="https://example.com",
        cadence="monthly", quality="hard-fact", topicTags=("x",),
        form="line", unit="USD", fetcher=None,
    )
    estimate = ChartSeries(
        id="y", name="Y", sourceName="S", sourceUrl="https://example.com",
        cadence="monthly", quality="estimate", topicTags=("y",),
        form="line", unit="USD", fetcher=None,
    )
    assert fact.chartable is True
    assert estimate.chartable is False
    # chartable is a property, not a constructor argument: passing it in
    # would be a TypeError, proving it cannot be set independently of
    # quality.
    with pytest.raises(TypeError):
        ChartSeries(
            id="z", name="Z", sourceName="S", sourceUrl="https://example.com",
            cadence="monthly", quality="hard-fact", topicTags=("z",),
            form="line", unit="USD", fetcher=None, chartable=False,
        )


def test_missing_quality_field_raises_value_error(tmp_path):
    bad = {
        "series": [
            {
                "id": "broken",
                "name": "Broken series",
                "sourceName": "Nowhere",
                "sourceUrl": "https://example.com",
                "cadence": "monthly",
                # "quality" deliberately omitted
                "topicTags": ["broken"],
                "form": "line",
                "unit": "USD",
                "fetcher": None,
            }
        ]
    }
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_chart_series(str(bad_path))


def test_invalid_quality_value_raises_value_error(tmp_path):
    bad = {
        "series": [
            {
                "id": "broken",
                "name": "Broken series",
                "sourceName": "Nowhere",
                "sourceUrl": "https://example.com",
                "cadence": "monthly",
                "quality": "not-a-real-quality",
                "topicTags": ["broken"],
                "form": "line",
                "unit": "USD",
                "fetcher": None,
            }
        ]
    }
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_chart_series(str(bad_path))


def test_invalid_form_value_raises_value_error(tmp_path):
    bad = {
        "series": [
            {
                "id": "broken",
                "name": "Broken series",
                "sourceName": "Nowhere",
                "sourceUrl": "https://example.com",
                "cadence": "monthly",
                "quality": "hard-fact",
                "topicTags": ["broken"],
                "form": "pie",  # not in the columns|bars|line enum
                "unit": "USD",
                "fetcher": None,
            }
        ]
    }
    bad_path = tmp_path / "chart-series.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_chart_series(str(bad_path))
