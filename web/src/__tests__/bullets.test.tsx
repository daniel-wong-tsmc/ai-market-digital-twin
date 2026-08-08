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
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {Bullets} from '../components/Bullets';
import {MiniChart} from '../components/MiniChart';
import {CAUSE_LEAD, NoChart} from '../components/NoChart';
import {parseDashboard} from '../load';
import type {Bullet, Cause, Chart, NoChartReason} from '../load';
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

/**
 * A chart the exporter built from a series today's researcher found and the
 * deterministic verifier re-checked (F113 Task 5). Everything here is server
 * copy: the "Found today — single source: …" caption is written by
 * gpu_agent/dashboard/bullets.py and arrives in the payload. The web side
 * adds no wording of its own — the tests below hold that line.
 */
const RESEARCHED_CHART: Chart = {
  form: 'line',
  title: 'MediaTek edge AI shipments',
  caption: 'Found today — single source: TrendForce.',
  unit: 'million units',
  points: [
    {label: 'Q1 2026', value: 12, hollow: false, sourceUrl: 'https://example.test/mtk-q1'},
    {label: 'Q2 2026', value: 14.5, hollow: false, sourceUrl: 'https://example.test/mtk-q2'},
    {label: 'Q3 2026', value: 15.2, hollow: false, sourceUrl: 'https://example.test/mtk-q3'},
  ],
  source: {
    title: 'MediaTek edge AI shipments',
    outlet: 'TrendForce',
    url: 'https://example.test/mtk-q1',
    date: '2026-08-04',
    tier: 'secondary',
  },
  researched: true,
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

/** A chartless bullet with its own text, payload reason and cause -- the shape
 * the layout and copy rules are actually about. */
function chartless(text: string, reason: string, cause: Cause): Bullet {
  return {...bulletWith(null, {reason, cause}), text};
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

  it('THE HONESTY POINT: no bullet fakes a chart -- and with every bullet chartless, no dashed box appears at all', () => {
    draw(<Bullets bullets={golden()} />);
    // No bullet renders a chart svg today -- the honest, expected case.
    expect(document.querySelectorAll('.mini-plot svg')).toHaveLength(0);
    for (const bullet of golden()) {
      expect(bullet.noChartReason).not.toBeNull();
    }
    // Rule 1: EVERY bullet chartless -> the dashed panel is gone from the page.
    // Three identical dashed boxes in a row is the exact "this product is
    // broken" look F113 exists to remove.
    expect(document.querySelectorAll('.nochart-panel')).toHaveLength(0);
    expect(document.querySelectorAll('.mini-plot.empty')).toHaveLength(0);
    expect(document.querySelectorAll('figure.mini')).toHaveLength(0);
  });

  it('says the shared reason ONCE, quietly, for the whole group -- never the same sentence three times', () => {
    draw(<Bullets bullets={golden()} />);
    // Today's committed payload: all three bullets chartless, all three the
    // SAME cause, all three carrying the byte-identical reason sentence. The
    // user's decision (interactive, 2026-08-07): print that cause's approved
    // sentence once, under the group, with no per-bullet line.
    const causes = new Set(golden().map((b) => b.noChartReason!.cause));
    expect(causes.size).toBe(1);
    const quiet = document.querySelectorAll('.nochart-quiet');
    expect(quiet).toHaveLength(1);
    expect(quiet[0].textContent).toBe(CAUSE_LEAD['no-published-number']);
    expect(quiet[0].textContent).toBe('No published number behind this yet.');
    // The grouped line belongs to the zone, not to any one bullet's row.
    expect(document.querySelector('.change .nochart-quiet')).toBeNull();
  });

  it('never prints the old bare "No chart." label anywhere', () => {
    draw(<Bullets bullets={golden()} />);
    expect(document.body.textContent).not.toContain('No chart.');
  });

  it('the quiet reason line is real assistive-technology-readable text carrying its cause code', () => {
    draw(<Bullets bullets={golden()} />);
    const quiet = document.querySelector('.nochart-quiet')!;
    expect(quiet).not.toBeNull();
    expect(quiet.textContent!.trim().length).toBeGreaterThan(10);
    expect(quiet.getAttribute('data-cause')).toBe('no-published-number');
  });

  it('gives each bullet a source mark for its own sources', () => {
    draw(<Bullets bullets={golden()} />);
    // 3 bullets from the golden fixture, each with sources -> 3 source buttons
    // (in addition to whichever other marks exist elsewhere on this isolated render).
    const marks = screen.getAllByRole('button', {name: /source/i});
    expect(marks).toHaveLength(3);
  });
});

describe('NoChart — the honest-omission panel (mixed state only)', () => {
  it('renders the dashed panel led by the cause sentence, with the detail under it, and NO svg', () => {
    draw(
      <NoChart
        lead={CAUSE_LEAD['estimate-only']}
        detail="The number we track for this is our own estimate, not a published figure, so we don't draw it."
        cause="estimate-only"
      />,
    );
    const panel = document.querySelector('.nochart-panel')!;
    expect(panel).not.toBeNull();
    // Keeps the mock's own class names -- the mock is the token authority.
    expect(panel).toHaveClass('mini-plot');
    expect(panel).toHaveClass('empty');
    expect(panel.querySelector('svg')).toBeNull();
    expect(panel.textContent).not.toContain('No chart.');
    expect(panel.querySelector('.nochart-lead')!.textContent).toBe(
      "The only number we hold is our own estimate, so we don't draw it.",
    );
    expect(panel.querySelector('.why-none')!.textContent).toContain('our own estimate');
    expect(panel.getAttribute('data-cause')).toBe('estimate-only');
  });

  it('renders only the lead line when there is no extra detail to add', () => {
    draw(<NoChart lead={CAUSE_LEAD['too-sparse']} detail={null} cause="too-sparse" />);
    const panel = document.querySelector('.nochart-panel')!;
    expect(panel.querySelector('.nochart-lead')!.textContent).toBe(
      'Too few published readings yet to draw honestly.',
    );
    expect(panel.querySelector('.why-none')).toBeNull();
  });

  it('never renders an svg regardless of how the text is worded', () => {
    draw(
      <NoChart
        lead={CAUSE_LEAD['no-plain-name']}
        detail="We have real, tracked numbers behind this, but no plain-English name for what they measure yet."
        cause="no-plain-name"
      />,
    );
    expect(document.querySelectorAll('svg')).toHaveLength(0);
  });
});

describe('the four cause codes each get their own approved sentence', () => {
  const EXPECTED: Record<Cause, string> = {
    'no-published-number': 'No published number behind this yet.',
    'estimate-only': "The only number we hold is our own estimate, so we don't draw it.",
    'too-sparse': 'Too few published readings yet to draw honestly.',
    'no-plain-name':
      'We have the numbers, but no plain-English name for what they measure yet.',
  };

  it('maps every cause to its exact approved wording, with no cause left out', () => {
    expect(CAUSE_LEAD).toEqual(EXPECTED);
  });

  it('renders the fourth cause (no-plain-name) end to end, in its own words', () => {
    // The fourth code was added by a user decision after the spec was written,
    // because "too-sparse" was a false label for two branches that have plenty
    // of data and simply no plain-English name for it.
    draw(
      <Bullets
        bullets={[
          bulletWith(COLUMNS_CHART, null),
          bulletWith(
            null,
            noChartReason(
              'We have real, tracked numbers behind this, but no plain-English name for what they measure yet, so we don’t chart them.',
              'no-plain-name',
            ),
          ),
        ]}
      />,
    );
    const panel = document.querySelector('.nochart-panel')!;
    expect(panel.getAttribute('data-cause')).toBe('no-plain-name');
    expect(panel.querySelector('.nochart-lead')!.textContent).toBe(
      'We have the numbers, but no plain-English name for what they measure yet.',
    );
  });
});

describe('rule 1 — when every bullet is chartless', () => {
  it('with DIFFERING causes, each bullet keeps its own quiet line, and all three differ', () => {
    draw(
      <Bullets
        bullets={[
          chartless('Bullet about a rumour.', 'Nobody publishes this yet.', 'no-published-number'),
          chartless('Bullet about our own estimate.', 'Our own estimate only.', 'estimate-only'),
          chartless('Bullet about two readings.', 'Only two readings so far.', 'too-sparse'),
        ]}
      />,
    );
    expect(document.querySelectorAll('.nochart-panel')).toHaveLength(0);
    const quiet = document.querySelectorAll('.nochart-quiet');
    expect(quiet).toHaveLength(3);
    const said = [...quiet].map((n) => n.textContent!);
    expect(new Set(said).size).toBe(3);
    expect(said).toEqual([
      CAUSE_LEAD['no-published-number'],
      CAUSE_LEAD['estimate-only'],
      CAUSE_LEAD['too-sparse'],
    ]);
    // Each line sits inside its own bullet row, under that bullet's text.
    expect(document.querySelectorAll('.change .nochart-quiet')).toHaveLength(3);
    expect(document.body.textContent).not.toContain('No chart.');
  });

  it('gives every chartless row the full-width layout, with no chart column', () => {
    draw(
      <Bullets
        bullets={[
          chartless('One.', 'Reason one.', 'no-published-number'),
          chartless('Two.', 'Reason two.', 'estimate-only'),
        ]}
      />,
    );
    const rows = document.querySelectorAll('.change');
    expect(rows).toHaveLength(2);
    rows.forEach((row) => {
      expect(row).toHaveClass('full');
      expect(row.querySelector('figure.mini')).toBeNull();
    });
  });

  it('with ALL causes the same, says it once for the group and gives no row its own line', () => {
    draw(
      <Bullets
        bullets={[
          chartless('One.', 'Reason one.', 'too-sparse'),
          chartless('Two.', 'Reason two.', 'too-sparse'),
          chartless('Three.', 'Reason three.', 'too-sparse'),
        ]}
      />,
    );
    const quiet = document.querySelectorAll('.nochart-quiet');
    expect(quiet).toHaveLength(1);
    expect(quiet[0].textContent).toBe(CAUSE_LEAD['too-sparse']);
    expect(document.querySelectorAll('.change .nochart-quiet')).toHaveLength(0);
    // Rows still go full width -- the group line replaces the panel, it does
    // not bring the chart column back.
    document.querySelectorAll('.change').forEach((row) => expect(row).toHaveClass('full'));
  });
});

describe('rule 3 — in the all-chartless layouts, no sentence appears twice', () => {
  it('a REPEATED cause falls back to that bullet own payload sentence', () => {
    // Two bullets share `estimate-only`; a third differs, so this is NOT the
    // all-one-cause grouped case. The second of the pair must not echo the
    // lead line verbatim.
    draw(
      <Bullets
        bullets={[
          chartless('First estimate bullet.', 'The memory figure is our own estimate.', 'estimate-only'),
          chartless('Second estimate bullet.', 'The packaging figure is our own estimate too.', 'estimate-only'),
          chartless('A sparse bullet.', 'Only two readings so far.', 'too-sparse'),
        ]}
      />,
    );
    const said = [...document.querySelectorAll('.nochart-quiet')].map((n) => n.textContent!);
    expect(said).toEqual([
      CAUSE_LEAD['estimate-only'],
      'The packaging figure is our own estimate too.',
      CAUSE_LEAD['too-sparse'],
    ]);
    expect(new Set(said).size).toBe(3);
  });

});

describe('the mixed state DOES repeat a shared reason — permitted by decision, not oversight', () => {
  /**
   * READ THIS BEFORE "FIXING" THE TEST BELOW.
   *
   * The realistic case: the exporter builds every reason from a fixed list of
   * canned sentences (gpu_agent/dashboard/bullets.py::_fallback_reason), so two
   * chartless bullets that share a cause normally carry the SAME payload
   * sentence too, word for word. In the mixed state that sentence really does
   * appear twice on the page — once as the first panel's detail line, once as
   * the second panel's lead.
   *
   * That is ALLOWED, by an interactive USER DECISION on 2026-08-07 (not an
   * AFK-default, not an oversight): each dashed panel sits beside a real chart
   * and has to explain itself where it stands, and a repeat separated by real
   * charted content reads nothing like three identical boxes stacked in a row.
   * The all-chartless layouts are the ones that must never repeat, and they
   * don't (see the describe above, and the grouped single line).
   *
   * An earlier version of this test used two hand-written, deliberately
   * DIFFERENT payload sentences, which quietly stepped around the real case and
   * implied the mixed state avoids repetition. It does not. This test now uses
   * the same sentence for both and asserts what actually happens.
   */
  const SAME = 'There isn’t yet enough of a track record to show a trend without being misleading.';

  it('prints the shared payload sentence twice, once per panel, when two bullets share a cause', () => {
    draw(
      <Bullets
        bullets={[
          chartless('First sparse bullet.', SAME, 'too-sparse'),
          bulletWith(COLUMNS_CHART, null),
          chartless('Second sparse bullet.', SAME, 'too-sparse'),
        ]}
      />,
    );
    const panels = document.querySelectorAll('.nochart-panel');
    expect(panels).toHaveLength(2);

    // First panel: the cause's lead line, with the payload sentence as detail.
    expect(panels[0].querySelector('.nochart-lead')!.textContent).toBe(CAUSE_LEAD['too-sparse']);
    expect(panels[0].querySelector('.why-none')!.textContent).toBe(SAME);

    // Second panel: the lead line is NOT echoed -- rule 3's de-duplication
    // still does its job, so the panel leads with the payload sentence and
    // does not then print that same sentence again underneath itself.
    expect(panels[1].querySelector('.nochart-lead')!.textContent).toBe(SAME);
    expect(panels[1].querySelector('.why-none')).toBeNull();
    expect([...panels].filter((p) => p.textContent!.includes(CAUSE_LEAD['too-sparse']))).toHaveLength(1);

    // ...and the ACCEPTED consequence: that shared sentence is on the page
    // twice. Asserted deliberately, so nobody can read this suite as a promise
    // that the mixed state never repeats.
    const shown = [...document.querySelectorAll('.nochart-lead, .why-none')].map((n) => n.textContent!);
    expect(shown.filter((s) => s === SAME)).toHaveLength(2);
  });
});

describe('rule 2 — the mixed state keeps the dashed panel', () => {
  it('puts the dashed panel on the chartless bullet ONLY, beside real charts', () => {
    draw(
      <Bullets
        bullets={[
          bulletWith(COLUMNS_CHART, null),
          chartless('The chartless one.', 'Nobody publishes this yet.', 'no-published-number'),
          bulletWith(BARS_CHART, null),
        ]}
      />,
    );
    const rows = document.querySelectorAll('.change');
    expect(document.querySelectorAll('.nochart-panel')).toHaveLength(1);
    expect(rows[0].querySelector('.nochart-panel')).toBeNull();
    expect(rows[1].querySelector('.nochart-panel')).not.toBeNull();
    expect(rows[2].querySelector('.nochart-panel')).toBeNull();
    // No quiet grouped line in the mixed state -- the panel carries it.
    expect(document.querySelectorAll('.nochart-quiet')).toHaveLength(0);
    // And the charted rows keep their chart column, so no row goes full width.
    rows.forEach((row) => expect(row).not.toHaveClass('full'));
    expect(document.body.textContent).not.toContain('No chart.');
  });
});

describe('rule 4 — the source badge sits at the end of the sentence', () => {
  it('renders the badge inside the sentence-end span, glued to the last word', () => {
    const bullet = chartless(
      'AMD delivered, and it does not add chips this year.',
      'Nobody publishes this yet.',
      'no-published-number',
    );
    draw(<Bullets bullets={[bullet]} />);
    const p = document.querySelector('.change p')!;
    // No line break of any kind can push the badge onto its own line.
    expect(p.querySelector('br')).toBeNull();
    const end = p.lastElementChild as HTMLElement;
    expect(end).not.toBeNull();
    expect(end.tagName).toBe('SPAN');
    expect(end).toHaveClass('nowrap-end');
    // The badge is a SIBLING of the last word inside that one span.
    expect(end.textContent!.startsWith('year.')).toBe(true);
    expect(end.querySelector('button.srcmark')).not.toBeNull();
    // ...and nothing else in the paragraph carries the badge.
    expect(p.querySelectorAll('button.srcmark')).toHaveLength(1);
    // The whole sentence still reads as one continuous string.
    expect(p.textContent!.startsWith('AMD delivered, and it does not add chips this year.')).toBe(true);
  });

  it('the nowrap class is a real style rule, not just a name in the markup', () => {
    const css = readFileSync(resolve(process.cwd(), 'src', 'app.css'), 'utf8');
    const rule = css.match(/\.nowrap-end\s*\{[^}]*\}/);
    expect(rule).not.toBeNull();
    expect(rule![0]).toMatch(/white-space:\s*nowrap/);
  });

  it('switches nowrap back OFF inside the popover, so source titles still wrap', () => {
    // The popover panel is a SIBLING of the badge's wrapper, so it lives inside
    // the nowrap span and inherits from it. Without this reset, opening a
    // source badge would run the titles off the side of a 340px box. jsdom
    // does not do layout, so the rule is proven by reading the stylesheet --
    // and the selector is proven to hit something real by the DOM check below.
    const css = readFileSync(resolve(process.cwd(), 'src', 'app.css'), 'utf8');
    const rule = css.match(/\.nowrap-end\s*>\s*\[popover\]\s*\{[^}]*\}/);
    expect(rule).not.toBeNull();
    expect(rule![0]).toMatch(/white-space:\s*normal/);
  });

  it('the popover panel really is a direct child of the nowrap span, as that reset assumes', () => {
    draw(<Bullets bullets={[chartless('A bullet.', 'Nobody publishes this yet.', 'no-published-number')]} />);
    const span = document.querySelector('span.nowrap-end')!;
    const panel = span.querySelector(':scope > [popover]');
    expect(panel).not.toBeNull();
    // The badge lives in the OTHER child -- the anchor wrapper -- so the
    // display:inline rule and the white-space:normal rule hit different
    // elements and cannot collide.
    expect(panel!.querySelector('button.srcmark')).toBeNull();
    expect(span.querySelector('div:has(.srcmark-wrap)')).not.toBe(panel);
  });

  it('copes with a one-word bullet without losing the badge', () => {
    draw(<Bullets bullets={[chartless('Delayed.', 'Nobody publishes this yet.', 'no-published-number')]} />);
    const end = document.querySelector('.change p')!.lastElementChild as HTMLElement;
    expect(end).toHaveClass('nowrap-end');
    expect(end.textContent!.startsWith('Delayed.')).toBe(true);
    expect(end.querySelector('button.srcmark')).not.toBeNull();
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

describe('a chart found by today’s research says so, in the payload’s own words', () => {
  it('prints the found-today caption exactly as the payload wrote it', () => {
    draw(<MiniChart chart={RESEARCHED_CHART} />);
    const caption = document.querySelector('figure.mini figcaption')!;
    expect(caption.textContent).toContain('Found today — single source: TrendForce.');
    // The chart itself still draws normally -- the label is the only difference.
    expect(document.querySelector('figure.mini svg')).not.toBeNull();
  });

  it('gives it a working link to the single source it rests on', async () => {
    draw(<Bullets bullets={[bulletWith(RESEARCHED_CHART, null)]} />);
    const figure = document.querySelector('figure.mini')!;
    await userEvent.click(figure.querySelector('button.srcmark')!);
    const link = await screen.findByRole('link', {name: /MediaTek edge AI shipments/});
    expect(link).toHaveAttribute('href', 'https://example.test/mtk-q1');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('THE LINE THAT MATTERS: the found-today wording lives on the server, not in the component', () => {
    // If this ever fails, someone has hard-coded reader-facing copy into the
    // web app. The exporter is the single place that decides what a chart
    // claims about itself; a second copy here could drift from it and start
    // saying something the data does not support.
    const tsx = readFileSync(resolve(process.cwd(), 'src', 'components', 'MiniChart.tsx'), 'utf8');
    expect(tsx).not.toContain('Found today');
    expect(tsx).not.toContain('single source');
  });

  it('leaves a non-researched chart exactly as it was -- no label, no extra words', () => {
    draw(<MiniChart chart={COLUMNS_CHART} />);
    const caption = document.querySelector('figure.mini figcaption')!;
    expect(caption.textContent).toContain(COLUMNS_CHART.caption);
    expect(caption.textContent).not.toContain('Found today');
    expect(COLUMNS_CHART.researched).toBe(false);
  });

  it('carries every point’s own source page through to the payload the chart renders', () => {
    // The per-point URLs are what make a researched chart checkable: each
    // number was re-found on that exact page before it was allowed here.
    expect(RESEARCHED_CHART.points.map((p) => p.sourceUrl)).toEqual([
      'https://example.test/mtk-q1',
      'https://example.test/mtk-q2',
      'https://example.test/mtk-q3',
    ]);
    draw(<MiniChart chart={RESEARCHED_CHART} />);
    expect(document.querySelectorAll('.mini-dot')).toHaveLength(RESEARCHED_CHART.points.length);
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
