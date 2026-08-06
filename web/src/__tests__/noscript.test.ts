/**
 * The block a reader sees with scripting turned off — and what a link-preview
 * crawler or a search engine reads out of the static file.
 *
 * It must never state a verdict. The verdict lives in `data/dashboard.json`,
 * which the daily cycle rewrites; this HTML file only changes when someone
 * rebuilds the app by hand, and no Node runs in the daily cycle. A verdict
 * sentence baked in here therefore goes stale the moment the reading changes,
 * and then confidently tells people the opposite of what the page's own data
 * says. That is the exact failure this whole feature exists to prevent.
 *
 * So the rule is structural, not a spelling check: the no-scripting block says
 * what the page is for, and points at where the current answer lives. Nothing
 * else. The text is pinned exactly, so ANY added sentence -- a verdict above
 * all -- turns this red.
 */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe, expect, it} from 'vitest';
import {readGolden} from './fixtures';
import {parseDashboard} from '../load';

// Vitest runs with `web/` as its root, same as ./fixtures.
const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

/** The no-scripting block's visible words, whitespace flattened. */
function noscriptText(): string {
  const match = /<noscript>([\s\S]*?)<\/noscript>/.exec(html);
  if (!match) throw new Error('index.html has no <noscript> block at all');
  return match[1]
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const EXPECTED =
  "This page needs scripting turned on to show today's reading. " +
  'The question this page answers: Is supply catching up to demand? ' +
  "Today's answer is not written into this file, so it cannot be shown " +
  'here. The story archive has the latest reading in full.';

describe('the no-scripting fallback', () => {
  it('says exactly what it is meant to say, and nothing more', () => {
    expect(noscriptText()).toBe(EXPECTED);
  });

  it('states no verdict of its own', () => {
    const text = noscriptText();
    const {verdict} = parseDashboard(readGolden());
    // Every part of a real verdict, taken from the data contract itself --
    // the answer, the direction chip, how sure we are, the "so what" line.
    // The question is deliberately absent from this list: asking it is fine,
    // answering it here is not.
    for (const claim of [
      verdict.answer,
      verdict.chip.label,
      verdict.confidence,
      verdict.soWhat,
    ]) {
      expect(text).not.toContain(claim);
    }
  });

  it('still points the reader at the page that does have the answer', () => {
    expect(html).toContain('<a href="story/">');
  });
});
