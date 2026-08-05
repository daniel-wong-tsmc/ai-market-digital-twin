"""F110 Task 4: the fetcher registry.

Maps a ChartSeries.fetcher key (registry/chart-series.json) to a pure
`html_text -> list[dict]` function. Adding a new fetcher (e.g. Nvidia's data
center revenue) means writing a new module here and adding one line below --
gpu_agent/chartdata/fetch.py never needs to change.
"""
from __future__ import annotations

from gpu_agent.chartdata.fetchers import amd_dc_revenue

FETCHERS = {
    "amd_dc_revenue": amd_dc_revenue.parse,
}
