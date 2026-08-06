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
import {readGolden, readSchema} from './fixtures';

const schema = readSchema();

function makeValidator() {
  const ajv = new Ajv2020({allErrors: true, strict: false});
  return ajv.compile(schema);
}

const golden = readGolden;

describe('dashboard.json contract', () => {
  it('the golden payload validates against the shared schema', () => {
    const validate = makeValidator();
    const ok = validate(golden());
    expect(validate.errors ?? []).toEqual([]);
    expect(ok).toBe(true);
  });

  it('the golden payload parses into the loader types', () => {
    const data = parseDashboard(golden());
    expect(data.schemaVersion).toBe('1.0');
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
});
