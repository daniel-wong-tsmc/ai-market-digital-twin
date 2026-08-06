/**
 * Zone 2 — the demand-versus-supply chart.
 *
 * The one requirement that is easy to get wrong: points sit on the horizontal
 * axis by their REAL DATE, never by their position in the array. The mixed
 * fixture below mirrors the Python exporter's own test data
 * (tests/test_export_json.py::test_gap_chart_points_are_positioned_by_real_date_not_index)
 * — seven real, non-uniformly-spaced dates: four readings two calendar days
 * apart sitting next to two month-wide gaps. A test that only counts seven
 * rendered points would not catch an index-spacing bug; this file proves the
 * actual pixel gaps are proportional to the actual calendar gaps.
 */
import {render, screen} from '@testing-library/react';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {GapChart} from '../components/GapChart';
import {parseDashboard} from '../load';
import type {GapChart as GapChartData, GapPoint} from '../load';
import {readGolden} from './fixtures';

function draw(ui: React.ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

const golden = () => parseDashboard(readGolden()).gapChart;

/** Mirrors _make_mixed_store in tests/test_export_json.py: real dates, real
 * non-uniform gaps -- June/July/August month anchors plus four genuine daily
 * readings clustered in early July. */
const MIXED_POINTS: GapPoint[] = [
  {date: '2026-06-01', demand: 1.0, supply: 0.5},
  {date: '2026-07-01', demand: 1.2, supply: 0.3},
  {date: '2026-07-02', demand: 1.0, supply: 0.4},
  {date: '2026-07-03', demand: 1.1, supply: 0.3},
  {date: '2026-07-05', demand: 1.3, supply: 0.2},
  {date: '2026-07-06', demand: 1.4, supply: 0.1},
  {date: '2026-08-01', demand: 2.0, supply: -0.6},
];

function mixedChart(): GapChartData {
  return {
    points: MIXED_POINTS,
    annotation: {date: '2026-08-01', label: 'Widest gap so far'},
    caption:
      'The gap widened in the latest reading. Demand and supply are each ' +
      "reading's own reported momentum score, not a raw shipment count. " +
      "Some points are a single day's reading; others are a whole month's " +
      'figure, placed at the start of that month.',
    sources: [],
  };
}

describe('the gap chart renders the required forms', () => {
  it('draws an svg with two line paths and one shaded gap path', () => {
    draw(<GapChart data={golden()} />);
    const svg = document.querySelector('svg')!;
    expect(svg).toBeInTheDocument();
    expect(svg.querySelector('path.line.dem')).not.toBeNull();
    expect(svg.querySelector('path.line.sup')).not.toBeNull();
    expect(svg.querySelector('path.gapband')).not.toBeNull();
  });

  it('labels the end of each line in plain English, never the internal names', () => {
    draw(<GapChart data={golden()} />);
    const svg = document.querySelector('svg')!;
    expect(svg.textContent).toContain('Demand');
    expect(svg.textContent).toContain('Supply');
    expect(svg.outerHTML).not.toMatch(/DMI/);
    expect(svg.outerHTML).not.toMatch(/SMI/);
  });

  it('gives the chart a plain-English aria-label naming both series', () => {
    draw(<GapChart data={golden()} />);
    const svg = document.querySelector('svg')!;
    const label = svg.getAttribute('aria-label') ?? '';
    expect(label.toLowerCase()).toMatch(/demand/);
    expect(label.toLowerCase()).toMatch(/supply/);
    expect(label).not.toMatch(/DMI/);
    expect(label).not.toMatch(/SMI/);
  });

  it('never uses colour alone to tell the two lines apart', () => {
    draw(<GapChart data={golden()} />);
    // Each series carries a text label as well as its colour class, in the
    // chart itself, not only in the numbers table underneath.
    const svg = document.querySelector('svg')!;
    expect(svg.textContent).toContain('Demand');
    expect(svg.textContent).toContain('Supply');
    // And the legend spells out which is which in words too.
    expect(screen.getByText(/what buyers are committing/)).toBeInTheDocument();
    expect(screen.getByText(/what is actually arriving/)).toBeInTheDocument();
  });

  it('renders the caption disclosed by the data, not invented copy', () => {
    draw(<GapChart data={golden()} />);
    expect(screen.getByText(golden().caption)).toBeInTheDocument();
  });
});

describe('the gap chart positions points by real calendar date, not array index', () => {
  it('renders one horizontal marker per point', () => {
    draw(<GapChart data={mixedChart()} />);
    const crosses = document.querySelectorAll('.hov .cross');
    expect(crosses).toHaveLength(7);
  });

  it('spaces points proportionally to the real number of days between readings', () => {
    draw(<GapChart data={mixedChart()} />);
    const crosses = Array.from(document.querySelectorAll('.hov .cross'));
    const xs = crosses.map((el) => Number(el.getAttribute('x1')));
    expect(xs).toHaveLength(7);
    // Strictly increasing left to right, in the same order as the data.
    for (let i = 1; i < xs.length; i++) {
      expect(xs[i]).toBeGreaterThan(xs[i - 1]);
    }

    // 2 Jul -> 3 Jul is 1 real day. 1 Jul -> 1 Aug is 31 real days. If the
    // component spaced by array index instead of date, EVERY gap here would
    // be equal (1/6 of the plot width each) -- this must not be even close
    // to true.
    const julToAug = xs[6] - xs[1]; // 2026-07-01 -> 2026-08-01 (31 days)
    const twoToThree = xs[3] - xs[2]; // 2026-07-02 -> 2026-07-03 (1 day)
    const ratio = twoToThree / julToAug;
    const expectedRatio = 1 / 31;
    expect(ratio).toBeGreaterThan(expectedRatio * 0.4);
    expect(ratio).toBeLessThan(expectedRatio * 2.5);

    // The four daily readings (1-2 real days apart each) must sit far closer
    // together than the month-wide June -> July gap.
    const juneToJuly = xs[1] - xs[0]; // 30 real days
    const dailyCluster = xs[5] - xs[2]; // 2026-07-02 -> 2026-07-06 (4 real days)
    expect(dailyCluster).toBeLessThan(juneToJuly * 0.4);

    // And the pixel gaps must not all be equal -- the direct index-spacing bite.
    const gaps = xs.slice(1).map((x, i) => x - xs[i]);
    const distinctGaps = new Set(gaps.map((g) => Math.round(g)));
    expect(distinctGaps.size).toBeGreaterThan(1);
  });

});

describe('the numbers table is the accessible alternative', () => {
  it('renders one row per point with real formatted values', () => {
    draw(<GapChart data={mixedChart()} />);
    const details = document.querySelector('details.numbers')!;
    expect(details).not.toBeNull();
    expect(screen.getByText('Show the numbers')).toBeInTheDocument();
    const rows = details.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(7);
    // Spot check a real row's values, formatted, not raw floats.
    const julySix = Array.from(rows).find((r) => r.textContent?.includes('6 July 2026'))!;
    expect(julySix).toBeTruthy();
    expect(julySix.textContent).toContain('1.40');
    expect(julySix.textContent).toContain('0.10');
  });

  it('never mentions the internal index names', () => {
    draw(<GapChart data={mixedChart()} />);
    const details = document.querySelector('details.numbers')!;
    expect(details.textContent).not.toMatch(/DMI/);
    expect(details.textContent).not.toMatch(/SMI/);
    expect(details.querySelector('thead')!.textContent).toMatch(/Demand/);
    expect(details.querySelector('thead')!.textContent).toMatch(/Supply/);
  });
});

describe('the annotation marker', () => {
  it('marks the annotated reading with its label', () => {
    draw(<GapChart data={mixedChart()} />);
    expect(screen.getByText(/Widest gap so far/)).toBeInTheDocument();
  });
});

describe('the date labels under the chart never collide', () => {
  it('drops labels that would print on top of each other, keeping both ends', () => {
    // The real reading history bunches five days inside one week. Labelling
    // every one of them printed them over each other and the axis read as
    // gibberish -- caught by looking at the built page (Task 12 step 5).
    draw(<GapChart data={mixedChart()} />);
    const labels = Array.from(document.querySelectorAll('text.xtick'));
    const positions = labels.map((el) => Number(el.getAttribute('x')));
    for (let i = 1; i < positions.length; i += 1) {
      expect(positions[i] - positions[i - 1]).toBeGreaterThanOrEqual(70);
    }
    // The first and last readings are the two the eye looks for: both stay.
    expect(labels[0].textContent).toBe('1 Jun');
    expect(labels[labels.length - 1].textContent).toBe('1 Aug');
    expect(labels.length).toBeLessThan(MIXED_POINTS.length);
  });

  it('labels every reading when they are already far enough apart', () => {
    draw(<GapChart data={golden()} />);
    const labels = document.querySelectorAll('text.xtick');
    expect(labels.length).toBeGreaterThan(1);
  });
});
