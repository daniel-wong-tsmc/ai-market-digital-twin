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
    assert amd.unit == "USD bn"
    assert amd.fetcher == "amd_dc_revenue"
    assert amd.sourceName == "AMD investor relations"
    assert amd.sourceUrl == "https://ir.amd.com/financial-information/quarterly-results"


def test_nvda_entry_has_no_fetcher_yet():
    series = load_chart_series(REGISTRY_PATH)
    nvda = series["nvdaDataCenterRevenue"]
    assert nvda.cadence == "quarterly"
    assert nvda.quality == "hard-fact"
    assert nvda.topicTags == ("nvidia", "nvidiaDataCenter")
    assert nvda.form == "columns"
    assert nvda.unit == "USD bn"
    assert nvda.fetcher is None


def test_gpu_spot_price_is_estimate_and_never_chartable():
    series = load_chart_series(REGISTRY_PATH)
    spot = series["gpuSpotPrice"]
    assert spot.cadence == "monthly"
    assert spot.quality == "estimate"
    assert spot.topicTags == ("gpuSpotPrice",)
    assert spot.form == "line"
    assert spot.unit == "USD"
    assert spot.fetcher is None
    # This is the whole point of this series: an estimate must never be
    # drawn as a small chart, because a small chart reads as fact.
    assert spot.chartable is False


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
