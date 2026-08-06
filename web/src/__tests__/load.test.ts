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
    await expect(loadDashboard()).rejects.toThrow(/404/);
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
