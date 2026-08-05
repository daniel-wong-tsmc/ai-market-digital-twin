"""F110 Task 4: AMD quarterly Data Center segment revenue fetcher.

Parses AMD's own quarterly-results press release (saved copy at
fixtures/chartdata/amd-ir-q2-2026.html for tests). registry/chart-series.json
deliberately keeps `sourceUrl` pointed at AMD's durable, quarter-independent
landing page (https://ir.amd.com/financial-information/quarterly-results,
saved copy at fixtures/chartdata/amd-ir-quarterly-results-landing.html) --
that is the address shown to readers as "the source" and it never changes.
The landing page itself does NOT carry the revenue figures; it links to a
new detail page every quarter (a new URL each time, e.g. .../detail/1295/
amd-reports-second-quarter-2026-financial-results). `discover()` finds that
quarter's detail-page link on the landing page (user decision, fix round 2:
"follow the link automatically ... keeps working every quarter with nobody
touching it"); `parse()` still only reads the detail page.

AMD publishes a "SELECTED CORPORATE DATA" table with a "Segment and
Disaggregated Revenue Information" section; the "Data Center Segment" row
under "Net Revenue:" gives three-months-ended figures (in USD millions) for
the just-reported quarter, the prior quarter, and the year-ago quarter, each
under a "Month DD, YYYY" column header.

This file only reads strings and returns data -- it must never touch the
network itself, so tests can feed it fixtures with no I/O of any kind.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin

from gpu_agent.chartdata.fetch import ParseFailed

# AMD's landing page lists each quarter's results in document order, newest
# first, inside a `<div class="box quarterly-results" id="...">` block; the
# actual id values (e.g. "2026-9232-results") are internal event ids that do
# NOT reliably encode which quarter is newest, so this anchors on document
# ORDER (first block = newest) rather than parsing the id. Within that first
# block, the earnings-release press release link is the one whose
# `aria-label` starts with "Earnings Release" (as opposed to the Slide
# Presentation / Financial Tables / 10-Q links in the same block).
_QUARTERLY_BLOCK_MARKER = 'class="box quarterly-results"'
_EARNINGS_RELEASE_LINK_RE = re.compile(
    r'<a\s+href="([^"]+)"[^>]*aria-label="Earnings Release[^"]*"', re.IGNORECASE)

_MONTH_TO_QUARTER = {
    "January": 1, "February": 1, "March": 1,
    "April": 2, "May": 2, "June": 2,
    "July": 3, "August": 3, "September": 3,
    "October": 4, "November": 4, "December": 4,
}

_ANCHOR = "Segment and Disaggregated Revenue Information"
_ROW_LABEL = "Data Center Segment"
_NEXT_ROW_LABEL = "Client and Gaming Segment"

_HEADER_DATE_RE = re.compile(
    r"<strong>([A-Za-z]+)\s+\d{1,2},</strong>\s*<br>\s*<strong>(\d{4})</strong>")
_CELL_NUMBER_RE = re.compile(r"<td[^>]*>\s*\$?\s*([\d,]+)\s*</td>")
_PUBLISHED_RE = re.compile(
    r'name="published_time"\s+content="(\d{4}-\d{2}-\d{2})"')
_CANONICAL_URL_RE = re.compile(
    r'(?:rel="canonical" href|property="og:url" content)="([^"]+)"')
_TITLE_RE = re.compile(r"<title>([^<]+)</title>")


def _quarter_label(month_name: str, year: str) -> str:
    q = _MONTH_TO_QUARTER.get(month_name)
    if q is None:
        raise ParseFailed(f"unrecognized month name in header date: {month_name!r}")
    return f"{year}-Q{q}"


def discover(landing_html: str, landing_url: str) -> str:
    """AMD's quarterly-results LANDING page HTML -> the absolute URL of the
    most recent quarter's earnings-release detail page.

    Anchors on structure that survives every quarter (the first
    quarterly-results block in document order, and the "Earnings Release"
    aria-label inside it), not on this-quarter's specific title or a byte
    offset. Raises ParseFailed if no quarterly-results block or no matching
    link is found -- never guesses at a URL.
    """
    first_idx = landing_html.find(_QUARTERLY_BLOCK_MARKER)
    if first_idx == -1:
        raise ParseFailed(
            f"could not find a {_QUARTERLY_BLOCK_MARKER!r} block on the landing "
            "page -- AMD's landing-page markup may have changed")

    # Scope the search to just the FIRST (newest) quarter's block, so an
    # older quarter's earnings-release link is never picked up instead.
    next_idx = landing_html.find(_QUARTERLY_BLOCK_MARKER, first_idx + 1)
    block_end = next_idx if next_idx != -1 else len(landing_html)
    block = landing_html[first_idx:block_end]

    match = _EARNINGS_RELEASE_LINK_RE.search(block)
    if not match:
        raise ParseFailed(
            "found a quarterly-results block on the landing page but no "
            "'Earnings Release ... HTML' link inside it -- AMD's "
            "landing-page markup may have changed")

    href = html.unescape(match.group(1))
    return urljoin(landing_url, href)


def parse(html_text: str) -> list[dict]:
    """AMD press-release HTML -> [{'period', 'value', 'unit', 'publishedAt',
    'sourceUrl', 'title'}, ...] for each Three-Months-Ended column in the
    Data Center Segment revenue row. Raises ParseFailed on any markup shape
    this parser doesn't recognize -- never returns a guessed/partial result."""
    anchor_idx = html_text.find(_ANCHOR)
    if anchor_idx == -1:
        raise ParseFailed(
            f"could not find {_ANCHOR!r} section in the page -- AMD's "
            "results-table markup may have changed")

    header_start = html_text.rfind("Three Months Ended", 0, anchor_idx)
    if header_start == -1:
        raise ParseFailed("could not find the 'Three Months Ended' column headers")
    header_window = html_text[header_start:anchor_idx]
    all_dates = _HEADER_DATE_RE.findall(header_window)
    # Only the first 3 dates are the "Three Months Ended" columns; any dates
    # after that belong to the adjacent "Six Months Ended" columns in the
    # same header block, which are NOT per-quarter figures and must never be
    # zipped in (they'd silently overwrite a quarter's real value with a
    # half-year total under the same quarter label).
    dates = all_dates[:3]
    if len(dates) < 2:
        raise ParseFailed(
            f"expected at least 2 quarter-end column dates, found {len(dates)}")

    row_idx = html_text.find(_ROW_LABEL, anchor_idx)
    if row_idx == -1:
        raise ParseFailed(f"could not find the {_ROW_LABEL!r} revenue row")
    row_end = html_text.find(_NEXT_ROW_LABEL, row_idx)
    if row_end == -1:
        row_end = row_idx + 4000
    row_html = html_text[row_idx:row_end]

    values = [v.replace(",", "") for v in _CELL_NUMBER_RE.findall(row_html)]
    if len(values) < 2:
        raise ParseFailed(
            f"expected at least 2 revenue figures in the {_ROW_LABEL!r} row, "
            f"found {len(values)}")

    published_match = _PUBLISHED_RE.search(html_text)
    if not published_match:
        raise ParseFailed("could not find the page's published_time meta tag")
    published_at = published_match.group(1)

    url_match = _CANONICAL_URL_RE.search(html_text)
    source_url = url_match.group(1) if url_match else ""

    title_match = _TITLE_RE.search(html_text)
    title = title_match.group(1).split(" :: ")[0].strip() if title_match else ""

    n = min(len(dates), len(values))
    points = []
    for (month_name, year), raw_value in zip(dates[:n], values[:n]):
        period = _quarter_label(month_name, year)
        value_bn = round(int(raw_value) / 1000.0, 3)
        points.append({
            "period": period,
            "value": value_bn,
            "unit": "USD bn",
            "publishedAt": published_at,
            "sourceUrl": source_url,
            "title": title,
        })
    return points
