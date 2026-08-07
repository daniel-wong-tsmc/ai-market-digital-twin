/**
 * Zone 3 — "what changed": three dated bullets, each with a small supporting
 * chart, OR — when there is nothing honest to draw — the dashed no-chart
 * panel from the mock. On today's real committed payload ALL THREE bullets
 * carry a no-chart reason, not a chart: that is the expected, honest case,
 * not an edge case, so it is proven first and given the most coverage here.
 *
 * Test data:
 *  - The "all three bullets, real dates/text/reasons" tests below read the
 *    committed `fixtures/dashboard/golden-dashboard.json` AS-IS (no invention).
 *  - `golden-dashboard.json` has `chart: null` on every bullet today (task-5's
 *    honesty gate refuses to draw estimated/internal/unnamed numbers), so it
 *    cannot exercise the chart-rendering paths (columns/bars/line, hollow
 *    points). Those are covered with constructed-but-realistic fixtures below,
 *    each labelled with what in it is real and what is built for coverage:
 *      - COLUMNS_CHART restates the exact AMD data-centre-revenue figures
 *        already established in the approved mock
 *        (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html
 *        lines 541-543) and the real registry series
 *        (registry/chart-series.json: amdDataCenterRevenue, form "columns",
 *        unit "USD bn") — values are real, wrapped in a constructed Bullet.
 *      - BARS_CHART restates the exact stacked-memory figures from the same
 *        mock's NVIDIA memory-per-chip illustration (lines 559-561): 1,024GB
 *        (hollow/"ghost" — the 2025 preview, never built), 288GB, 192GB —
 *        values are real, wrapped in a constructed Chart/Bullet since no such
 *        series is registered in registry/chart-series.json yet.
 *      - LINE_CHART is modelled on the real registered `gpuSpotPrice` series
 *        (registry/chart-series.json: form "line", unit "USD") — the id and
 *        unit are real, the monthly price points are constructed since that
 *        series has no fetcher yet (`fetcher: null`) and so no real rows.
 */
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {Bullets} from '../components/Bullets';
import {MiniChart} from '../components/MiniChart';
import {NoChart} from '../components/NoChart';
import {parseDashboard} from '../load';
import type {Bullet, Chart, NoChartReason} from '../load';
import {readGolden} from './fixtures';

function draw(ui: React.ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

const golden = () => parseDashboard(readGolden()).bullets;

const COLUMNS_CHART: Chart = {
  form: 'columns',
  title: 'AMD data-centre revenue',
  caption: 'AMD data-centre revenue by quarter. Source: AMD investor relations.',
  unit: 'USD bn',
  points: [
    {label: 'Q1 2024', value: 2.3, hollow: false, sourceUrl: null},
    {label: 'Q2 2024', value: 2.8, hollow: false, sourceUrl: null},
    {label: 'Q3 2024', value: 3.5, hollow: false, sourceUrl: null},
    {label: 'Q4 2024', value: 3.9, hollow: false, sourceUrl: null},
    {label: 'Q1 2026', value: 5.8, hollow: false, sourceUrl: null},
    {label: 'Q2 2026', value: 6.7, hollow: false, sourceUrl: null},
  ],
  source: {
    title: 'AMD data center revenue',
    outlet: 'AMD investor relations',
    url: 'https://ir.amd.com/financial-information/quarterly-results',
    date: '2026-08-04',
    tier: 'primary',
  },
  researched: false,
};

const BARS_CHART: Chart = {
  form: 'bars',
  title: 'Stacked memory planned per chip',
  caption: 'Stacked memory planned per chip. The pale bar is a design shown once and never built.',
  unit: 'GB',
  points: [
    {label: 'Rubin Ultra, as previewed in 2025', value: 1024, hollow: true, sourceUrl: null},
    {label: 'Rubin, today’s top part', value: 288, hollow: false, sourceUrl: null},
    {label: 'Rubin Ultra, the new plan', value: 192, hollow: false, sourceUrl: null},
  ],
  source: {
    title: '404K Semi-Ai Research',
    outlet: '404K Semi-Ai Research (Substack)',
    url: 'https://404kresearch.substack.com/p/rubin-ultra-hbm-capacity-cut-to-192gb',
    date: '2026-08-04',
    tier: 'secondary',
  },
  researched: false,
};

const LINE_CHART: Chart = {
  form: 'line',
  title: 'GPU rental spot price',
  caption: 'The blended marketplace spot price, tracked monthly.',
  unit: 'USD',
  points: [
    {label: 'Mar 2026', value: 2.4, hollow: false, sourceUrl: null},
    {label: 'Apr 2026', value: 2.2, hollow: false, sourceUrl: null},
    {label: 'May 2026', value: 2.35, hollow: false, sourceUrl: null},
    {label: 'Jun 2026', value: 2.1, hollow: false, sourceUrl: null},
    {label: 'Jul 2026', value: 1.95, hollow: false, sourceUrl: null},
  ],
  source: {
    title: 'GPU rental spot price',
    outlet: 'GPU Category Agent price tracker (blended marketplace estimate)',
    url: null,
    date: '2026-08-01',
    tier: 'secondary',
  },
  researched: false,
};

/** Builds a {reason, cause} pair from a plain sentence, for tests that only
 * care about the reason text and don't exercise cause-specific behaviour. */
function noChartReason(reason: string, cause: NoChartReason['cause'] = 'no-published-number'): NoChartReason {
  return {reason, cause};
}

function bulletWith(chart: Chart | null, reason: NoChartReason | null): Bullet {
  return {
    date: '2026-08-04',
    text: 'A constructed bullet for coverage.',
    storyHref: 'story/2026-08-05.html',
    chart,
    noChartReason: reason,
    sources: [
      {
        title: 'A filing',
        outlet: 'Some outlet',
        url: 'https://example.com/filing',
        date: '2026-08-04',
        tier: 'primary',
      },
    ],
  };
}

describe('the what-changed zone on real committed data', () => {
  it('renders exactly three bullets, dated and worded from the payload', () => {
    draw(<Bullets bullets={golden()} />);
    const rows = document.querySelectorAll('.change');
    expect(rows).toHaveLength(3);
    expect(screen.getByText(/AMD delivered, and it does not add chips this year/)).toBeInTheDocument();
    expect(screen.getByText(/One new buyer has already claimed a slice of 2027/)).toBeInTheDocument();
    expect(screen.getByText(/The way around the packaging queue/)).toBeInTheDocument();
  });

  it('THE HONESTY POINT: all three real bullets render the dashed no-chart panel, never an empty chart frame', () => {
    draw(<Bullets bullets={golden()} />);
    const panels = document.querySelectorAll('.mini-plot.empty');
    expect(panels).toHaveLength(3);
    // No bullet renders a chart svg today -- the honest, expected case.
    expect(document.querySelectorAll('.mini-plot svg')).toHaveLength(0);
    for (const bullet of golden()) {
      expect(bullet.noChartReason).not.toBeNull();
    }
    // "No chart." opens every one of the three real panels.
    expect(screen.getAllByText('No chart.')).toHaveLength(3);
  });

  it('the no-chart reason text is real assistive-technology-readable text, not styling', () => {
    draw(<Bullets bullets={golden()} />);
    const panels = document.querySelectorAll('.mini-plot.empty');
    panels.forEach((panel, i) => {
      const reason = golden()[i].noChartReason!;
      expect(panel.textContent).toContain('No chart.');
      expect(panel.textContent).toContain(reason.reason);
      expect(panel.getAttribute('data-cause')).toBe(reason.cause);
    });
  });

  it('gives each bullet a source mark for its own sources', () => {
    draw(<Bullets bullets={golden()} />);
    // 3 bullets from the golden fixture, each with sources -> 3 source buttons
    // (in addition to whichever other marks exist elsewhere on this isolated render).
    const marks = screen.getAllByRole('button', {name: /source/i});
    expect(marks).toHaveLength(3);
  });
});

describe('NoChart — the honest-omission panel', () => {
  it('renders the dashed panel with the reason, and NO svg', () => {
    draw(
      <NoChart
        reason="The only numbers we track for this are our own estimates, not published facts, so we don't chart them."
        cause="estimate-only"
      />,
    );
    const panel = document.querySelector('.mini-plot.empty')!;
    expect(panel).not.toBeNull();
    expect(panel.querySelector('svg')).toBeNull();
    expect(panel.textContent).toContain('No chart.');
    expect(panel.textContent).toContain('our own estimates');
    expect(panel.getAttribute('data-cause')).toBe('estimate-only');
  });

  it('never renders an svg regardless of how the reason text is worded', () => {
    draw(
      <NoChart
        reason="We don't yet have a plain-English way to describe what this number measures, so we don't draw it."
        cause="too-sparse"
      />,
    );
    expect(document.querySelectorAll('svg')).toHaveLength(0);
  });
});

describe('MiniChart — the three chart forms', () => {
  it('renders the columns form as an svg with one bar per point', () => {
    draw(<MiniChart chart={COLUMNS_CHART} />);
    const svg = document.querySelector('svg')!;
    expect(svg).toBeInTheDocument();
    expect(svg.querySelectorAll('.mini-bar')).toHaveLength(COLUMNS_CHART.points.length);
  });

  it('renders the bars form as an svg with one bar per point', () => {
    draw(<MiniChart chart={BARS_CHART} />);
    const svg = document.querySelector('svg')!;
    expect(svg).toBeInTheDocument();
    expect(svg.querySelectorAll('.mini-bar')).toHaveLength(BARS_CHART.points.length);
  });

  it('renders the line form as an svg with one path and one point marker per point', () => {
    draw(<MiniChart chart={LINE_CHART} />);
    const svg = document.querySelector('svg')!;
    expect(svg).toBeInTheDocument();
    expect(svg.querySelector('path.mini-line')).not.toBeNull();
    expect(svg.querySelectorAll('.mini-dot')).toHaveLength(LINE_CHART.points.length);
  });

  it('a bullet with a chart renders an svg, a caption, and its own source link', async () => {
    const bullet = bulletWith(COLUMNS_CHART, null);
    draw(
      <Bullets
        bullets={[
          bullet,
          bulletWith(null, noChartReason('Reason one.')),
          bulletWith(null, noChartReason('Reason two.')),
        ]}
      />,
    );
    expect(document.querySelector('figure.mini svg')).not.toBeNull();
    expect(screen.getByText(COLUMNS_CHART.caption)).toBeInTheDocument();

    // Open the chart's OWN source mark (inside figure.mini, not the bullet's
    // prose SourceMark) and assert the link carries chart.source.url --
    // proving MiniChart really passes the chart's source through, not the
    // bullet's own sources and not a dropped url. This is the pattern used
    // for the verdict's source mark (verdict.test.tsx:188-198).
    const chartSource = COLUMNS_CHART.source as {title: string; url: string};
    const figure = document.querySelector('figure.mini')!;
    const chartSourceButton = figure.querySelector('button.srcmark')!;
    await userEvent.click(chartSourceButton);
    const link = await screen.findByRole('link', {name: new RegExp(chartSource.title)});
    expect(link).toHaveAttribute('href', chartSource.url);
  });

  it('marks a hollow point as outlined, not filled, with a real CSS class', () => {
    draw(<MiniChart chart={BARS_CHART} />);
    const svg = document.querySelector('svg')!;
    const bars = svg.querySelectorAll('.mini-bar');
    const hollowIndex = BARS_CHART.points.findIndex((p) => p.hollow);
    expect(bars[hollowIndex]).toHaveClass('ghost');
    // And no OTHER bar is marked hollow -- colour/class is not applied blanket.
    bars.forEach((bar, i) => {
      if (i !== hollowIndex) expect(bar).not.toHaveClass('ghost');
    });
  });

  it('never renders the internal index names in a chart title, caption or unit', () => {
    draw(<MiniChart chart={COLUMNS_CHART} />);
    const figure = document.querySelector('figure.mini')!;
    expect(figure.textContent).not.toMatch(/DMI/);
    expect(figure.textContent).not.toMatch(/SMI/);
  });

  it('gives the chart svg a plain-English accessible description', () => {
    draw(<MiniChart chart={LINE_CHART} />);
    const svg = document.querySelector('svg')!;
    expect(svg).toHaveAttribute('role', 'img');
    expect(svg.getAttribute('aria-label')).toBeTruthy();
    expect(svg.getAttribute('aria-label')!.length).toBeGreaterThan(10);
  });

  it('carries the chart source via SourceMark, distinct from the bullet sources', () => {
    draw(<MiniChart chart={COLUMNS_CHART} />);
    // SourceMark renders a real button; the figure caption carries it.
    const figure = document.querySelector('figure.mini')!;
    expect(figure.querySelector('button.srcmark')).not.toBeNull();
  });
});

describe('Bullets — the whole zone', () => {
  it('mixes a charted bullet and a no-chart bullet without crashing, keeping row order', () => {
    const bullets = [
      bulletWith(COLUMNS_CHART, null),
      bulletWith(null, noChartReason(
        'The only numbers we track for this are our own estimates, not published facts, so we don’t chart them.',
        'estimate-only',
      )),
      bulletWith(BARS_CHART, null),
    ];
    draw(<Bullets bullets={bullets} />);
    const rows = document.querySelectorAll('.change');
    expect(rows).toHaveLength(3);
    // Scoped to `.mini-plot` -- a row's own SourceMark popover keeps an
    // (initially hidden) external-link icon svg in the DOM too, which is not
    // what this assertion is about.
    expect(rows[0].querySelector('.mini-plot svg')).not.toBeNull();
    expect(rows[1].querySelector('.mini-plot.empty')).not.toBeNull();
    expect(rows[1].querySelector('.mini-plot svg')).toBeNull();
    expect(rows[2].querySelector('.mini-plot svg')).not.toBeNull();
  });
});
