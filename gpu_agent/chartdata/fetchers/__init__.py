"""F110 Task 4: the fetcher registry.

Maps a ChartSeries.fetcher key (registry/chart-series.json) to a pure
`html_text -> list[dict]` function. Adding a new fetcher (e.g. Nvidia's data
center revenue) means writing a new module here and adding one line below --
gpu_agent/chartdata/fetch.py never needs to change.

DISCOVERERS (fix round 2, user decision) is the optional second half of that
contract: a `fetcher` key whose registry `sourceUrl` is a durable LANDING
page (not the page with the actual figures) maps here to a
`(landing_html, landing_url) -> detail_url` function. `gpu_agent.chartdata
.fetch.run_fetch` looks a key up in DISCOVERERS first; when present, it
fetches the landing page, discovers the detail URL, then fetches AND parses
that. When absent (no entry for a given fetcher key), `sourceUrl` is assumed
to already be the page `FETCHERS[key]` can parse directly -- one-step fetch,
unchanged from before this round.
"""
from __future__ import annotations

from gpu_agent.chartdata.fetchers import amd_dc_revenue

FETCHERS = {
    "amd_dc_revenue": amd_dc_revenue.parse,
}

DISCOVERERS = {
    "amd_dc_revenue": amd_dc_revenue.discover,
}
