"""F134: NVIDIA quarterly Data Center revenue fetcher.

Mirrors gpu_agent/chartdata/fetchers/amd_dc_revenue.py -- same two-step
landing-page/discover shape, same returned point dict, same "raise rather
than guess" error handling. NVIDIA's investor site differs from AMD's in
three ways that forced real divergences, each settled by a user ruling on
2026-09-01 and each pinned by a test in
tests/test_chartdata_nvda_fetcher.py:

1. THE LANDING PAGE IS A DIFFERENT PAGE. AMD's quarterly-results page is
   server-rendered and lists every quarter's press release. NVIDIA's
   equivalent (investor.nvidia.com/financial-info/quarterly-results/) is a
   JavaScript shell: the quarter list is drawn in the browser by a Q4 Inc
   widget from a JSON feed, so the HTML a fetcher receives contains ZERO
   press-release links. registry/chart-series.json therefore points
   sourceUrl at NVIDIA's *financial-reports* page instead, which IS
   server-rendered and carries a "Latest Report" block linking to the
   current quarter's release (saved copy:
   fixtures/chartdata/nvda-ir-financial-reports-landing.html).

   Caveat worth knowing: NVIDIA's own HTML shows that block is hand-edited
   by their IR staff each quarter ("Earnings - After PR crosses: Update
   with PR Title"), so it can lag an actual print. The F112(a) staleness
   guard in fetch.py refuses to append a quarter older than the newest one
   stored, so the failure mode is "the chart updates late", never "the
   chart shows the wrong quarter".

2. THERE IS NO EXACT FIGURE TO READ. AMD publishes a segment table with
   Data Center revenue in exact millions. NVIDIA publishes no such row in
   any table in the release; the figure exists only in the release's prose
   subtitle, already rounded by NVIDIA to one decimal place in billions
   ("Data Center revenue of $89.0 billion, up 117% from a year ago"). We
   take NVIDIA's published rounding verbatim -- the series unit is already
   US$ billions, so nothing is converted, scaled or inferred. A figure
   stated in any other unit raises rather than being converted.

   Consequence: ONE point per release. AMD's three-column table backfills
   the prior and year-ago quarters for free; NVIDIA's history has to
   accumulate one quarter at a time going forward.

3. FISCAL YEAR != CALENDAR YEAR, AND THE LABEL FOLLOWS THE CALENDAR.
   NVIDIA's fiscal quarters end in April, July, October and January, and
   NVIDIA numbers them a year ahead -- the quarter ending 2026-07-26 is
   NVIDIA's "second quarter fiscal 2027". This fetcher labels a quarter by
   the CALENDAR quarter its period ends in, exactly as the AMD fetcher
   does, so that quarter charts as 2026-Q3. That keeps the AMD and NVIDIA
   series aligned in real time and honestly comparable; the cost is that a
   reader who follows NVIDIA sees "Q3" where the headlines said "Q2".

This file only reads strings and returns data -- it must never touch the
network itself, so tests can feed it fixtures with no I/O of any kind.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin

from gpu_agent.chartdata.fetch import ParseFailed

# The "Latest Report" mashup module on NVIDIA's financial-reports page. Its
# news half (`module-financial-mashup_news`) holds the headline, the bullet
# summary and the "Read More" link to the quarter's press release; its
# other half lists documents. Scoping to the news half means the documents
# half's links can never be picked up instead.
_MASHUP_MARKER = 'class="module module-embed module-financial-mashup"'
_NEWS_MARKER = "module-financial-mashup_news"
_LINKS_MARKER = "module_links"
_HREF_RE = re.compile(r'<a\s[^>]*href="([^"]+)"', re.IGNORECASE)

_MONTH_TO_QUARTER = {
    "January": 1, "February": 1, "March": 1,
    "April": 2, "May": 2, "June": 2,
    "July": 3, "August": 3, "September": 3,
    "October": 4, "November": 4, "December": 4,
}
_MONTH_TO_NUMBER = {name: i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# "Data Center revenue of $89.0 billion, up 117% from a year ago" -- NVIDIA's
# standing subtitle format on every quarterly release. The unit word is
# captured, never assumed, so a release that switched to millions fails
# loudly instead of being silently mis-scaled by a factor of 1000.
_DC_FIGURE_RE = re.compile(
    r"Data Center revenue of \$\s*([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)",
    re.IGNORECASE)
_EXPECTED_UNIT_WORD = "billion"

# "...revenue for the second quarter ended July 26, 2026, of $96.2 billion..."
_QUARTER_END_RE = re.compile(
    r"quarter ended\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", re.IGNORECASE)

# NVIDIA's newsroom stamps the publication date in a semantic element rather
# than a meta tag (there is no published_time meta on these pages, which is
# the one place the AMD parser's shape could not be reused verbatim).
_ARTICLE_DATE_RE = re.compile(
    r'class="article-date"[^>]*>\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})',
    re.IGNORECASE)

_CANONICAL_URL_RE = re.compile(
    r'(?:rel="canonical" href|property="og:url" content)="([^"]+)"')
_TITLE_RE = re.compile(r"<title>([^<]+)</title>")

_UNIT = "US$ billions"


def _canonical_month(month_name: str) -> str:
    """NVIDIA's own casing is title case; be tolerant, but only of casing --
    an unrecognized month is an error, never a guess."""
    return month_name.strip().capitalize()


def _quarter_label(month_name: str, year: str) -> str:
    q = _MONTH_TO_QUARTER.get(_canonical_month(month_name))
    if q is None:
        raise ParseFailed(f"unrecognized month name in quarter-end date: {month_name!r}")
    return f"{year}-Q{q}"


def _iso_date(month_name: str, day: str, year: str) -> str:
    month = _MONTH_TO_NUMBER.get(_canonical_month(month_name))
    if month is None:
        raise ParseFailed(f"unrecognized month name in publication date: {month_name!r}")
    return f"{year}-{month:02d}-{int(day):02d}"


def discover(landing_html: str, landing_url: str) -> str:
    """NVIDIA's financial-reports LANDING page HTML -> the absolute URL of
    the current quarter's earnings press release on nvidianews.nvidia.com.

    Anchors on the structure of the "Latest Report" mashup module rather
    than on this quarter's title or a byte offset, so it keeps working as
    NVIDIA replaces the block each quarter. Raises ParseFailed if the block,
    its links container, or a usable href is missing -- it never guesses at
    a URL, and it never returns a Mustache placeholder from a page that only
    half-rendered.
    """
    block_idx = landing_html.find(_MASHUP_MARKER)
    if block_idx == -1:
        raise ParseFailed(
            "could not find the 'Latest Report' block "
            f"({_MASHUP_MARKER!r}) on the landing page -- NVIDIA's "
            "landing-page markup may have changed, or sourceUrl may be "
            "pointing at the JavaScript-rendered quarterly-results page, "
            "whose served HTML carries no links at all")

    # Bound the search to this module, so a later module's links can never
    # be mistaken for the press release.
    next_idx = landing_html.find('class="module module-', block_idx + 1)
    block = landing_html[block_idx:next_idx if next_idx != -1 else len(landing_html)]

    news_idx = block.find(_NEWS_MARKER)
    if news_idx == -1:
        raise ParseFailed(
            f"the 'Latest Report' block has no {_NEWS_MARKER!r} section -- "
            "NVIDIA's landing-page markup may have changed")

    links_idx = block.find(_LINKS_MARKER, news_idx)
    if links_idx == -1:
        raise ParseFailed(
            "found the 'Latest Report' news section but no "
            f"{_LINKS_MARKER!r} container inside it -- NVIDIA may not have "
            "posted this quarter's press-release link yet")

    match = _HREF_RE.search(block, links_idx)
    if not match:
        raise ParseFailed(
            "found the 'Latest Report' links container but no link inside "
            "it -- NVIDIA may not have posted this quarter's press release yet")

    href = html.unescape(match.group(1)).strip()
    if "{{" in href or "}}" in href:
        # An unrendered Mustache template placeholder. urljoin would turn
        # this into a plausible-looking absolute URL, so refuse it here.
        raise ParseFailed(
            f"the 'Latest Report' link is an unrendered template placeholder "
            f"({href!r}) -- NVIDIA's page did not finish rendering server-side")
    if not href:
        raise ParseFailed("the 'Latest Report' link has an empty href")

    return urljoin(landing_url, href)


def parse(html_text: str) -> list[dict]:
    """NVIDIA press-release HTML -> a single-element list
    [{'period', 'value', 'unit', 'publishedAt', 'sourceUrl', 'title'}] for
    the quarter the release reports.

    One point, not several: NVIDIA states Data Center revenue exactly once,
    in prose, and the figures beside it are percentage comparisons rather
    than prior-quarter absolutes. Raises ParseFailed on any markup shape
    this parser doesn't recognize -- never returns a guessed or partial
    result, and never converts a figure into the series' unit.
    """
    figure_match = _DC_FIGURE_RE.search(html_text)
    if not figure_match:
        raise ParseFailed(
            "could not find NVIDIA's 'Data Center revenue of $N billion' "
            "line in the release -- the subtitle wording may have changed. "
            "NVIDIA publishes this figure in prose only; there is no table "
            "row to fall back to")

    raw_value, unit_word = figure_match.group(1), figure_match.group(2).lower()
    if unit_word != _EXPECTED_UNIT_WORD:
        raise ParseFailed(
            f"NVIDIA stated Data Center revenue in {unit_word!r}, but this "
            f"series' unit is {_UNIT!r} and figures are never converted -- "
            "a person needs to look at this release")

    try:
        # Verbatim: NVIDIA's own published rounding, parsed as written. The
        # comma strip handles a hypothetical "$1,000.0 billion" only.
        value = float(raw_value.replace(",", ""))
    except ValueError as e:
        raise ParseFailed(f"unparseable Data Center revenue figure {raw_value!r}") from e

    quarter_match = _QUARTER_END_RE.search(html_text)
    if not quarter_match:
        raise ParseFailed(
            "could not find the 'quarter ended <Month DD, YYYY>' phrase -- "
            "without it there is no trustworthy way to label the quarter")
    period = _quarter_label(quarter_match.group(1), quarter_match.group(3))

    date_match = _ARTICLE_DATE_RE.search(html_text)
    if not date_match:
        raise ParseFailed(
            "could not find the release's article-date element -- NVIDIA's "
            "newsroom carries no published_time meta tag to fall back to")
    published_at = _iso_date(*date_match.groups())

    url_match = _CANONICAL_URL_RE.search(html_text)
    source_url = url_match.group(1) if url_match else ""

    title_match = _TITLE_RE.search(html_text)
    title = title_match.group(1).split(" | ")[0].strip() if title_match else ""

    return [{
        "period": period,
        "value": value,
        "unit": _UNIT,
        "publishedAt": published_at,
        "sourceUrl": source_url,
        "title": title,
    }]
