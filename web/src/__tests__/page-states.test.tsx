/**
 * F113 Task 7 Step 4 — the two day-states, rendered as a reader meets them.
 *
 * The other suites test components in isolation. This one mounts the REAL
 * `App` against two whole, schema-valid payloads and asserts only things a
 * person looking at the page would actually see:
 *
 *  (a) an all-chartless day  -> one quiet grouped line, no dashed boxes at all
 *  (b) a day carrying a chart the researcher found -> dashed panels beside the
 *      real chart, the "Found today — single source: …" caption, and a source
 *      link that really points at the page the numbers were re-found on.
 *
 * WHY IT ALSO READS PYTHON: the found-today wording is server copy
 * (`gpu_agent/dashboard/bullets.py`). If this test hard-coded that sentence it
 * would be a second copy free to drift from the real one. Instead it lifts the
 * template out of the exporter's source, so the day the server rewords the
 * caption this test either follows along or fails loudly — it can never quietly
 * assert copy the product no longer ships.
 *
 * NOTE ON WHAT THIS CANNOT PROVE: jsdom computes no layout and paints nothing.
 * Stroke weight, the quiet line's left alignment, dash rendering and popover
 * text wrapping are NOT verified here — those need a real browser.
 */
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {App} from '../App';
import {readChartGolden, readGolden} from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

function serve(payload: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ok: true, status: 200, json: async () => payload})),
  );
}

function mount(payload: unknown) {
  serve(payload);
  render(
    <Theme theme={neutralTheme}>
      <App />
    </Theme>,
  );
}

/** The repo root, from vitest's `web/` working directory. */
const repoRoot = resolve(process.cwd(), '..');

/**
 * Lifts the found-today caption out of the exporter so this test can never
 * assert wording the server has stopped shipping.
 */
function serverCaptionFor(sourceName: string): string {
  const py = readFileSync(
    resolve(repoRoot, 'gpu_agent/dashboard/bullets.py'),
    'utf8',
  );
  const match = py.match(/"caption": f"([^"]*\{source_name\}[^"]*)"/);
  if (!match) {
    throw new Error(
      'Could not find the found-today caption template in ' +
        'gpu_agent/dashboard/bullets.py. If the exporter moved or reworded it, ' +
        'update this helper deliberately — do not delete the check.',
    );
  }
  return match[1].replace('{source_name}', sourceName);
}

/**
 * Payload (b): the committed chart payload, with its chart marked as one
 * today's researcher found, captioned exactly as the exporter would caption
 * it. Everything else — the two chartless sibling bullets, the verdict, the
 * dimensions — is the real committed fixture.
 */
function researchedDayPayload() {
  const payload = readChartGolden();
  const bullets = payload.bullets as Record<string, unknown>[];
  const chart = bullets.find((b) => b.chart)!.chart as Record<string, unknown>;
  const source = chart.source as Record<string, unknown>;
  chart.researched = true;
  chart.caption = serverCaptionFor(String(source.outlet));
  return payload;
}

describe('(a) a day when nothing could be charted', () => {
  it('shows no dashed no-chart box anywhere — three of them read as a broken page', async () => {
    mount(readGolden());
    await screen.findByRole('heading', {level: 1});
    expect(document.querySelectorAll('.nochart-panel')).toHaveLength(0);
    // and no chart was faked to fill the gap either. Charts are the
    // `role="img"` svgs; the plain svgs left over are source-mark icons.
    expect(document.querySelectorAll('.changed svg[role="img"]')).toHaveLength(0);
  });

  it('says the one true reason ONCE, quietly, for the whole group', async () => {
    mount(readGolden());
    await screen.findByRole('heading', {level: 1});
    const quiet = document.querySelectorAll('.changed .nochart-quiet');
    expect(quiet).toHaveLength(1);
    expect(quiet[0].textContent).toBe('No published number behind this yet.');
  });

  it('prints that sentence exactly once on the entire page', async () => {
    mount(readGolden());
    await screen.findByRole('heading', {level: 1});
    const hits = screen.getAllByText('No published number behind this yet.');
    expect(hits).toHaveLength(1);
  });

  it('still shows all three dated bullets, each with its own source mark', async () => {
    mount(readGolden());
    await screen.findByRole('heading', {level: 1});
    const rows = document.querySelectorAll('.changed .change');
    expect(rows).toHaveLength(3);
    rows.forEach((row) => {
      expect(row.querySelector('button.srcmark')).not.toBeNull();
      // full-width layout: no chart column reserved
      expect(row.classList.contains('full')).toBe(true);
    });
  });

  it('never shows the bare "No chart." label the old mock opened with', async () => {
    mount(readGolden());
    await screen.findByRole('heading', {level: 1});
    expect(document.body.textContent).not.toContain('No chart.');
  });
});

describe('(b) a day carrying a chart the researcher found', () => {
  it('labels it "Found today — single source: …" in the exporter’s own words', async () => {
    const payload = researchedDayPayload();
    mount(payload);
    await screen.findByRole('heading', {level: 1});
    const caption = document.querySelector('.changed figure.mini figcaption')!;
    expect(caption.textContent).toContain('Found today — single source:');
    expect(caption.textContent).toContain('AMD investor relations');
  });

  it('the caption it renders is byte-for-byte the sentence the server builds', async () => {
    const expected = serverCaptionFor('AMD investor relations');
    // guards the helper itself: if the regex silently matched nothing useful,
    // this pins what it produced.
    expect(expected).toBe('Found today — single source: AMD investor relations.');
    mount(researchedDayPayload());
    await screen.findByRole('heading', {level: 1});
    const caption = document.querySelector('.changed figure.mini figcaption')!;
    expect(caption.textContent).toContain(expected);
  });

  it('gives the reader a working link to the page the numbers were re-found on', async () => {
    mount(researchedDayPayload());
    await screen.findByRole('heading', {level: 1});
    const figure = document.querySelector('.changed figure.mini')!;
    await userEvent.click(figure.querySelector('button.srcmark')!);
    const link = await screen.findByRole('link', {
      name: /AMD data center revenue/,
    });
    expect(link).toHaveAttribute(
      'href',
      'https://ir.amd.com/financial-information/quarterly-results',
    );
    expect(link).toHaveAttribute('target', '_blank');
    // opening a new tab without this is a known security footgun
    expect(link.getAttribute('rel') ?? '').toContain('noopener');
  });

  it('draws the real chart, and keeps the dashed panel on the bullets beside it', async () => {
    mount(researchedDayPayload());
    await screen.findByRole('heading', {level: 1});
    // exactly one real chart drawn (role="img" is the chart svg; source-mark
    // icons are svgs too and must not be counted as charts)
    expect(
      document.querySelectorAll('.changed figure.mini svg[role="img"]'),
    ).toHaveLength(1);
    // the two chartless siblings keep their dashed boxes -- beside a real
    // chart the empty slot is information, not noise (F113 6.1)
    const panels = document.querySelectorAll('.changed .nochart-panel');
    expect(panels).toHaveLength(2);
    panels.forEach((panel) => {
      expect(panel.querySelector('svg')).toBeNull();
      expect(panel.getAttribute('data-cause')).toBe('no-published-number');
      expect((panel.textContent ?? '').trim().length).toBeGreaterThan(0);
    });
  });

  it('drops the grouped quiet line — this is the mixed state, not the quiet one', async () => {
    mount(researchedDayPayload());
    await screen.findByRole('heading', {level: 1});
    expect(document.querySelectorAll('.changed > .nochart-quiet')).toHaveLength(0);
  });

  it('an ordinary curated chart on the same page says nothing about being found today', async () => {
    // the committed payload is researched:false as shipped
    mount(readChartGolden());
    await screen.findByRole('heading', {level: 1});
    const caption = document.querySelector('.changed figure.mini figcaption')!;
    expect(caption.textContent).not.toContain('Found today');
    expect(caption.textContent).not.toContain('single source');
  });
});
