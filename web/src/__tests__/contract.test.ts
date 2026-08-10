/**
 * The contract test. Two halves that must agree:
 *   1. the committed golden payload validates against the shared JSON schema;
 *   2. the same payload passes the loader's own runtime check and yields the
 *      values the page actually renders.
 * Plus a bite test: a payload broken in one field must be rejected by BOTH.
 */
import Ajv2020 from 'ajv/dist/2020.js';
import {describe, expect, it} from 'vitest';
import {parseDashboard, isAssessment} from '../load';
import {readChartGolden, readGolden, readSchema} from './fixtures';

const schema = readSchema();

function makeValidator() {
  const ajv = new Ajv2020({allErrors: true, strict: false});
  return ajv.compile(schema);
}

const golden = readGolden;
const chartGolden = readChartGolden;

describe('dashboard.json contract', () => {
  it('the golden payload validates against the shared schema', () => {
    const validate = makeValidator();
    const ok = validate(golden());
    expect(validate.errors ?? []).toEqual([]);
    expect(ok).toBe(true);
  });

  it('the golden payload parses into the loader types', () => {
    const data = parseDashboard(golden());
    expect(data.schemaVersion).toBe('1.2');
    expect(data.categoryId).toBe('chips.merchant-gpu');
    expect(data.asOf).toBe('2026-08-05');
    expect(data.verdict.question).toBe('Is supply catching up to demand?');
    expect(data.verdict.chip.direction).toBe('narrowing');
    expect(data.bullets).toHaveLength(3);
    expect(data.dimensions).toHaveLength(6);
    // The verdict is the system's own judgement, not a published fact.
    expect(isAssessment(data.verdict.sources[0])).toBe(true);
  });

  // --- bite tests: each deliberately broken payload must be REJECTED ---

  it('rejects an unknown gap direction', () => {
    const broken = golden();
    (broken.verdict as {chip: {direction: string}}).chip.direction = 'sideways';
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow(/direction/);
  });

  it('rejects a missing verdict answer', () => {
    const broken = golden();
    delete (broken.verdict as Record<string, unknown>).answer;
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow(/answer/);
  });

  it('rejects the wrong number of dimensions', () => {
    const broken = golden();
    (broken.dimensions as unknown[]).pop();
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow(/dimensions/);
  });

  it('rejects a source reference that is neither a source nor an assessment', () => {
    const broken = golden();
    (broken.verdict as {sources: unknown[]}).sources = [{note: 'trust me'}];
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow(/source/i);
  });

  it('rejects the old 1.0 bare-string noChartReason shape (STRICT, no compat branch)', () => {
    const broken = golden();
    (broken.bullets as Array<Record<string, unknown>>)[0].noChartReason = 'No published number.';
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow();
  });

  it('rejects an unknown noChartReason cause', () => {
    const broken = golden();
    const bullet = (broken.bullets as Array<Record<string, unknown>>)[0];
    (bullet.noChartReason as Record<string, unknown>).cause = 'something-else';
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow();
  });
});

/**
 * The chart-bearing payload. The golden fixture's three bullets are all
 * chart-less, so everything above walks past `bullets[].chart` without ever
 * entering it — the chart shape the exporter builds had no committed
 * cross-check against the schema at all. One drifted key there would reject
 * a whole day's payload, and the page would silently keep serving yesterday's.
 */
describe('a payload whose bullet carries a chart', () => {
  it('validates against the shared schema', () => {
    const validate = makeValidator();
    const ok = validate(chartGolden());
    expect(validate.errors ?? []).toEqual([]);
    expect(ok).toBe(true);
  });

  it('parses into the loader types, chart and all', () => {
    const data = parseDashboard(chartGolden());
    const charted = data.bullets.filter((b) => b.chart !== null);
    expect(charted).toHaveLength(1);
    const chart = charted[0].chart!;
    expect(chart.form).toBe('columns');
    expect(chart.title).toBeTruthy();
    expect(chart.unit).toBe('US$ billions');
    expect(chart.points.length).toBeGreaterThan(0);
    expect(chart.points[0].sourceUrl).toMatch(/^https:/);
    // Every charted bullet must still carry no reason for having no chart.
    expect(charted[0].noChartReason).toBeNull();
  });

  it('rejects a chart with a form the schema has never heard of', () => {
    const broken = chartGolden();
    const bullets = broken.bullets as Array<Record<string, unknown>>;
    const chart = bullets.find((b) => b.chart !== null)!.chart as Record<string, unknown>;
    chart.form = 'pie';
    expect(makeValidator()(broken)).toBe(false);
    expect(() => parseDashboard(broken)).toThrow(/form/);
  });
});

/**
 * Shape drift, as opposed to value drift. The checks above would still pass if
 * someone added a field to the TypeScript types that the schema has never heard
 * of, or dropped one the schema requires. This walks what the loader actually
 * produces against what the schema allows, level by level.
 */
describe('the loader and the schema describe the same shape', () => {
  type Node = Record<string, unknown>;
  const defs = (schema as {$defs: Record<string, Node>}).$defs;

  /**
   * Follow a $ref, and flatten a oneOf into the branches it allows. A node can
   * carry both its own properties and a oneOf that narrows a couple of them
   * (the bullet's either-a-chart-or-a-reason rule), so the parent's properties
   * are folded into each branch.
   */
  function branches(node: Node): Node[] {
    if (typeof node.$ref === 'string') {
      return branches(defs[node.$ref.replace('#/$defs/', '')]);
    }
    if (Array.isArray(node.oneOf)) {
      const inner = (node.oneOf as Node[]).flatMap(branches);
      if (!node.properties) return inner;
      // The parent's own property schemas win over the branch's. A branch
      // exists to NARROW a key the parent already declares — the bullet's
      // either-a-chart-or-a-reason rule restates `chart` as bare
      // `{type: "object"}`, which has no properties of its own. Letting that
      // win meant the walk stopped at the chart and never looked inside it,
      // so nothing here ever checked the chart's own shape (found by the
      // final review, together with the fixture that now exercises it).
      return inner.map((b) => ({
        ...node,
        oneOf: undefined,
        properties: {...((b.properties as Node) ?? {}), ...(node.properties as Node)},
        required: [
          ...((node.required as string[] | undefined) ?? []),
          ...((b.required as string[] | undefined) ?? []),
        ],
      }));
    }
    return [node];
  }

  const problems: string[] = [];

  function walk(value: unknown, node: Node, path: string): void {
    if (Array.isArray(value)) {
      const items = node.items as Node | undefined;
      if (items) value.forEach((v, i) => walk(v, items, `${path}[${i}]`));
      return;
    }
    if (typeof value !== 'object' || value === null) return;

    const options = branches(node).filter((b) => b.properties);
    if (options.length === 0) return;

    const keys = Object.keys(value as Node);
    // The value must fit at least one branch: every key known to it, and every
    // key it requires present.
    const fits = options.some((b) => {
      const allowed = Object.keys(b.properties as Node);
      const required = (b.required as string[] | undefined) ?? [];
      return (
        keys.every((k) => allowed.includes(k)) &&
        required.every((k) => keys.includes(k))
      );
    });
    if (!fits) {
      const allowed = options.map((b) => Object.keys(b.properties as Node));
      problems.push(
        `${path}: loader produced {${keys.join(', ')}} — schema allows ${allowed
          .map((a) => `{${a.join(', ')}}`)
          .join(' or ')}`,
      );
      return;
    }
    const branch = options.find((b) =>
      keys.every((k) => Object.keys(b.properties as Node).includes(k)),
    )!;
    for (const [key, child] of Object.entries(value as Node)) {
      const childSchema = (branch.properties as Node)[key] as Node | undefined;
      if (childSchema) walk(child, childSchema, `${path}.${key}`);
    }
  }

  it('produces no field the schema does not know, and none it requires missing', () => {
    problems.length = 0;
    walk(parseDashboard(golden()), schema as Node, 'dashboard');
    expect(problems).toEqual([]);
  });

  it('would notice a field the schema has never heard of', () => {
    // Proves the walk above bites rather than passing vacuously.
    problems.length = 0;
    const data = parseDashboard(golden()) as unknown as Record<string, unknown>;
    (data.verdict as Record<string, unknown>).hunch = 'invented';
    walk(data, schema as Node, 'dashboard');
    expect(problems.join('\n')).toMatch(/hunch/);
  });

  it('walks a chart object too, not only chart-less bullets', () => {
    problems.length = 0;
    const data = parseDashboard(chartGolden());
    expect(data.bullets.some((b) => b.chart !== null)).toBe(true);
    walk(data, schema as Node, 'dashboard');
    expect(problems).toEqual([]);
  });

  it('would notice a chart field the schema has never heard of', () => {
    problems.length = 0;
    const data = parseDashboard(chartGolden()) as unknown as Record<string, unknown>;
    const bullets = data.bullets as Array<Record<string, unknown>>;
    const chart = bullets.find((b) => b.chart !== null)!.chart as Record<string, unknown>;
    chart.flourish = 'invented';
    walk(data, schema as Node, 'dashboard');
    expect(problems.join('\n')).toMatch(/flourish/);
  });

});
