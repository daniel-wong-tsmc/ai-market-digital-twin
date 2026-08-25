/**
 * The disclaimer exists twice — once in Python for the pages the site builder
 * writes, once in TypeScript for this app — because the two share no runtime
 * and the dashboard payload may not grow a field to carry copy (F124 forbids
 * any schema change). Two copies of the same approved sentence will drift. This
 * test is what stops them: it reads the Python source, lifts the literal out of
 * it, and demands the two match character for character.
 *
 * Same trick as `page-states.test.tsx`, which reads its caption copy out of
 * `gpu_agent/dashboard/bullets.py` rather than re-typing it.
 */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe, expect, it} from 'vitest';
import {DISCLAIMER} from '../components/Disclaimer';

/** Vitest runs with `web/` as its root, so the repo root is one level up. */
const repoRoot = resolve(process.cwd(), '..');

/** The DISCLAIMER literal exactly as the site builder holds it. */
function builderDisclaimer(): string {
  const py = readFileSync(
    resolve(repoRoot, 'gpu_agent/dashboard/site_render.py'),
    'utf8',
  );
  const block = /^DISCLAIMER = \(\r?\n([\s\S]*?)^\)$/m.exec(py);
  if (!block) {
    throw new Error(
      'No `DISCLAIMER = ( ... )` literal in gpu_agent/dashboard/site_render.py. ' +
        'If it moved or changed shape, update this helper deliberately — do ' +
        'not delete the check.',
    );
  }
  // Python implicit string concatenation: join the quoted chunks in order.
  const parts = block[1].match(/"([^"]*)"/g);
  if (!parts) {
    throw new Error('The DISCLAIMER literal held no double-quoted strings.');
  }
  return parts.map((part) => part.slice(1, -1)).join('');
}

describe('the disclaimer wording', () => {
  it('is identical in the site builder and in the app', () => {
    expect(DISCLAIMER).toBe(builderDisclaimer());
  });
});
