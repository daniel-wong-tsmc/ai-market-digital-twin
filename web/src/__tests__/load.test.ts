import {afterEach, describe, expect, it, vi} from 'vitest';
import {
  DEFAULT_DATA_URL,
  isStale,
  loadDashboard,
  plainDate,
  plainDateWithWeekday,
  countSources,
} from '../load';
import {readGolden} from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('how old the reading is', () => {
  it('is fresh on the day it was written', () => {
    expect(isStale('2026-08-05', '08/05/2026 09:00:00')).toBe(false);
  });

  it('is still fresh two days later — a weekend gap is normal', () => {
    expect(isStale('2026-08-05', '08/07/2026 09:00:00')).toBe(false);
  });

  it('is stale on the third day', () => {
    expect(isStale('2026-08-05', '08/08/2026 09:00:00')).toBe(true);
  });

  it('never calls a reading stale when the page date makes no sense', () => {
    expect(isStale('2026-08-05', 'not a date')).toBe(false);
  });
});

describe('dates in plain English', () => {
  it('writes a source date the way a person would', () => {
    expect(plainDate('2026-08-04')).toBe('4 August 2026');
  });

  it('leaves a missing date empty rather than inventing one', () => {
    expect(plainDate(null)).toBeNull();
  });

  it('names the weekday for the masthead', () => {
    expect(plainDateWithWeekday('2026-08-05')).toBe('Wednesday 5 August 2026');
  });
});

describe('counting what a statement rests on', () => {
  it('counts the published sources under an assessment, not the assessment', () => {
    expect(
      countSources([
        {
          assessment: true,
          basedOn: [
            {title: 'a', outlet: 'a', url: null, date: null, tier: null},
            {title: 'b', outlet: 'b', url: null, date: null, tier: null},
          ],
        },
      ]),
    ).toBe(2);
  });
});

describe('loading the day s reading', () => {
  it('reads the file the daily run writes and reports freshness', async () => {
    const payload = readGolden();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ok: true, status: 200, json: async () => payload})),
    );
    const {data, stale} = await loadDashboard();
    expect(fetch).toHaveBeenCalledWith(DEFAULT_DATA_URL, {cache: 'no-cache'});
    expect(data.asOf).toBe('2026-08-05');
    expect(typeof stale).toBe('boolean');
  });

  it('says plainly when the file cannot be read', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ok: false, status: 404, json: async () => ({})})),
    );
    await expect(loadDashboard()).rejects.toThrow(/could not be read just now/);
  });

  it('refuses a file that does not match the contract', async () => {
    const broken = readGolden();
    delete (broken.verdict as Record<string, unknown>).soWhat;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ok: true, status: 200, json: async () => broken})),
    );
    await expect(loadDashboard()).rejects.toThrow(/soWhat/);
  });
});

describe('the masthead name', () => {
  it('reads the category id back in plain words', async () => {
    const {mastheadName} = await import('../App');
    expect(mastheadName('chips.merchant-gpu')).toEqual({
      name: 'Merchant GPU',
      group: 'chips',
    });
  });
});

describe('freshness is judged on the data file, not on the page', () => {
  /**
   * FINAL REVIEW, Important 2. This used to compare the reading's date
   * against `document.lastModified` — the HTML page's own timestamp. But the
   * page file is a committed input that changes only when someone runs
   * `npm run build` by hand, while the data file is rewritten by every daily
   * run. If an export failed (it is deliberately swallowed so a bad export
   * cannot stop the cycle), yesterday's data file stayed put and the page
   * served an old verdict as today's reading with this warning never firing.
   */
  function stubFetch(lastModified: string | null) {
    const payload = readGolden(); // asOf 2026-08-05
    const fn = vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: {get: (name: string) => (name === 'Last-Modified' ? lastModified : null)},
      json: async () => payload,
    }));
    vi.stubGlobal('fetch', fn);
  }

  it('calls the reading stale when the data file is days older than the page is being read', async () => {
    // The bite: `document.lastModified` in a test run is right now, which
    // would make this look fresh. Only the data file's own stamp says
    // otherwise, and it is the one that must be believed.
    stubFetch('Mon, 17 Aug 2026 09:00:00 GMT');
    const {stale} = await loadDashboard();
    expect(stale).toBe(true);
  });

  it('calls the reading fresh when the data file was written the same day', async () => {
    stubFetch('Wed, 05 Aug 2026 09:00:00 GMT');
    const {stale} = await loadDashboard();
    expect(stale).toBe(false);
  });

  it('does not claim staleness when the server sends no timestamp at all', async () => {
    stubFetch(null);
    const {stale} = await loadDashboard();
    expect(stale).toBe(false);
  });
});

describe('what the reader is told when the file cannot be read', () => {
  it('says it in plain English, with no file path and no status code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ok: false, status: 404, json: async () => ({})})),
    );
    await expect(loadDashboard()).rejects.toThrow(
      'The file it comes from could not be read just now. Please try again in a few minutes.',
    );
    const message = await loadDashboard().catch((e: Error) => e.message);
    expect(message).not.toMatch(/404/);
    expect(message).not.toMatch(/dashboard\.json/);
    expect(message).not.toMatch(/\.\//);
  });
});
