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

/**
 * The second committed payload: identical in every way except that its first
 * bullet carries a real chart. The golden payload's three bullets are all
 * chart-less, so on its own it never walks a `chart` object — the whole chart
 * shape had no committed cross-check against the schema, and a single drifted
 * key there would have failed validation for a whole day's payload.
 */
export const chartGoldenPath = resolve(
  repoRoot,
  'fixtures/dashboard/golden-dashboard-with-chart.json',
);

/** A fresh copy each call, so a test that breaks it cannot leak into the next. */
export function readGolden(): Record<string, unknown> {
  return JSON.parse(readFileSync(goldenPath, 'utf8')) as Record<string, unknown>;
}

/** As `readGolden`, for the chart-bearing payload. */
export function readChartGolden(): Record<string, unknown> {
  return JSON.parse(readFileSync(chartGoldenPath, 'utf8')) as Record<string, unknown>;
}
