/** Shared access to the committed, schema-valid payload the tests run against. */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

/** Vitest runs with `web/` as its root, so the repo root is one level up. */
const repoRoot = resolve(process.cwd(), '..');

export const schemaPath = resolve(repoRoot, 'web/schema/dashboard.schema.json');
export const goldenPath = resolve(
  repoRoot,
  'fixtures/dashboard/golden-dashboard.json',
);

export function readSchema(): object {
  return JSON.parse(readFileSync(schemaPath, 'utf8')) as object;
}

/** A fresh copy each call, so a test that breaks it cannot leak into the next. */
export function readGolden(): Record<string, unknown> {
  return JSON.parse(readFileSync(goldenPath, 'utf8')) as Record<string, unknown>;
}
