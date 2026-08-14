/**
 * The one data file the page reads, and the runtime check that guards it.
 *
 * The types below mirror `web/schema/dashboard.schema.json`. The schema is the
 * contract; if the two ever drift, the contract test goes red.
 */

/** A published source we can point at. */
export interface Source {
  title: string;
  outlet: string;
  url: string | null;
  date: string | null;
  tier: 'primary' | 'secondary' | null;
}

/** Our own judgement, and the published sources it rests on. */
export interface Assessment {
  assessment: true;
  basedOn: Ref[];
}

export type Ref = Source | Assessment;

export interface Chip {
  label: string;
  direction: 'narrowing' | 'widening' | 'flat';
}

export interface VerdictData {
  question: string;
  answer: string;
  chip: Chip;
  confidence: string;
  soWhat: string;
  sources: Ref[];
}

export interface GapPoint {
  date: string;
  demand: number;
  supply: number;
}

export interface Annotation {
  date: string;
  label: string;
}

export interface GapChart {
  points: GapPoint[];
  annotation: Annotation;
  caption: string;
  sources: Ref[];
}

export interface ChartPoint {
  label: string;
  value: number;
  hollow: boolean;
  sourceUrl: string | null;
}

export interface Chart {
  form: 'columns' | 'bars' | 'line';
  title: string;
  caption: string;
  unit: string;
  points: ChartPoint[];
  source: Ref;
  /** True only for a chart drawn from today's same-day chart research
   * (quarantined, single-source, verified) -- never for a curated or
   * findings-fallback chart. */
  researched: boolean;
}

/**
 * Why a bullet has no chart, machine-readable. These four cover every
 * honesty-gate branch in `gpu_agent/dashboard/bullets.py`'s
 * `_fallback_reason`:
 *  - 'no-published-number': nothing is tracked for this at all.
 *  - 'estimate-only': the number we track is our own estimate, never a
 *    published figure.
 *  - 'no-plain-name': we hold real, published numbers, but can't yet say
 *    what they measure in plain English (an unnameable raw unit, or a
 *    nameable one with no narrator-supplied title yet).
 *  - 'too-sparse': we hold real, published, plainly-named numbers, but not
 *    enough of a track record yet to draw without misleading.
 * A fourth code (2026-08-07, follow-up to Task 1 review) was added because
 * the original three-code mapping put `no-plain-name`'s two branches under
 * `too-sparse`, which is false of them -- neither is a density problem.
 */
export type Cause = 'no-published-number' | 'estimate-only' | 'no-plain-name' | 'too-sparse';

export interface NoChartReason {
  reason: string;
  cause: Cause;
}

export interface Bullet {
  date: string;
  text: string;
  storyHref: string;
  chart: Chart | null;
  noChartReason: NoChartReason | null;
  sources: Ref[];
}

export interface Dimension {
  id: string;
  plainName: string;
  ratingWord: string;
  tone: 'bad' | 'mixed' | 'good';
  direction: 'improving' | 'worsening' | 'flat';
  confidence: string;
  summary: string;
  reasoning: string;
  evidence: Ref[];
}

export interface FooterLink {
  label: string;
  href: string;
}

/** F115: one entry of an open issue's short trend -- last <= 15, oldest first. */
export interface IssueHistoryEntry {
  asOf: string;
  status: 'improved' | 'worsened' | 'unchanged' | 'not-assessed';
}

/** F115: a binding constraint or a weak-and-worsening dimension still open. */
export interface IssueOpen {
  id: string;
  title: string;
  status: 'improved' | 'worsened' | 'unchanged' | 'not-assessed';
  assessedAsOf: string;
  trackedSince: string;
  worsenedCount: number;
  checkCount: number;
  reasoning: string;
  sources: Ref[];
  history: IssueHistoryEntry[];
}

/** F115: an issue that has since cleared (improved for enough straight checks). */
export interface IssueResolved {
  id: string;
  title: string;
  resolvedAsOf: string;
  finalNote: string;
}

export interface Issues {
  open: IssueOpen[];
  resolved: IssueResolved[];
}

export interface Dashboard {
  schemaVersion: '1.2';
  categoryId: string;
  asOf: string;
  verdict: VerdictData;
  gapChart: GapChart;
  bullets: Bullet[];
  dimensions: Dimension[];
  footerLinks: FooterLink[];
  issues: Issues;
}

/** True when this reference is our own judgement rather than a published fact. */
export function isAssessment(ref: Ref): ref is Assessment {
  return (ref as Assessment).assessment === true;
}

/** How many published sources sit behind a reference, however deeply nested. */
export function countSources(refs: Ref[]): number {
  return refs.reduce(
    (total, ref) => total + (isAssessment(ref) ? countSources(ref.basedOn) : 1),
    0,
  );
}

// --- the runtime check ------------------------------------------------------

class ShapeError extends Error {}

function fail(where: string, why: string): never {
  throw new ShapeError(`dashboard.json: ${where} ${why}`);
}

function obj(value: unknown, where: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(where, 'is not an object');
  }
  return value as Record<string, unknown>;
}

function str(record: Record<string, unknown>, key: string, where: string): string {
  const value = record[key];
  if (typeof value !== 'string') fail(`${where}.${key}`, 'is not text');
  return value;
}

function nullableStr(
  record: Record<string, unknown>,
  key: string,
  where: string,
): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== 'string') fail(`${where}.${key}`, 'is not text or empty');
  return value;
}

function num(record: Record<string, unknown>, key: string, where: string): number {
  const value = record[key];
  if (typeof value !== 'number' || Number.isNaN(value)) {
    fail(`${where}.${key}`, 'is not a number');
  }
  return value;
}

function bool(record: Record<string, unknown>, key: string, where: string): boolean {
  const value = record[key];
  if (typeof value !== 'boolean') fail(`${where}.${key}`, 'is not true or false');
  return value;
}

function oneOf<T extends string>(
  record: Record<string, unknown>,
  key: string,
  allowed: readonly T[],
  where: string,
): T {
  const value = record[key];
  if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
    fail(`${where}.${key}`, `is not one of ${allowed.join(', ')}`);
  }
  return value as T;
}

function list(record: Record<string, unknown>, key: string, where: string): unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) fail(`${where}.${key}`, 'is not a list');
  return value;
}

function parseRef(raw: unknown, where: string): Ref {
  const record = obj(raw, where);
  if ('assessment' in record) {
    if (record.assessment !== true) {
      fail(`${where}: source reference`, 'is marked as an assessment but not set to true');
    }
    return {
      assessment: true,
      basedOn: list(record, 'basedOn', where).map((item, i) =>
        parseRef(item, `${where}.basedOn[${i}]`),
      ),
    };
  }
  if (!('title' in record) || !('url' in record)) {
    fail(`${where}: source reference`, 'is neither a published source nor an assessment');
  }
  return {
    title: str(record, 'title', where),
    outlet: str(record, 'outlet', where),
    url: nullableStr(record, 'url', where),
    date: nullableStr(record, 'date', where),
    tier:
      record.tier === null
        ? null
        : oneOf(record, 'tier', ['primary', 'secondary'] as const, where),
  };
}

function parseRefs(record: Record<string, unknown>, key: string, where: string): Ref[] {
  return list(record, key, where).map((item, i) =>
    parseRef(item, `${where}.${key}[${i}]`),
  );
}

function parseVerdict(raw: unknown): VerdictData {
  const v = obj(raw, 'verdict');
  const chip = obj(v.chip, 'verdict.chip');
  return {
    question: str(v, 'question', 'verdict'),
    answer: str(v, 'answer', 'verdict'),
    chip: {
      label: str(chip, 'label', 'verdict.chip'),
      direction: oneOf(
        chip,
        'direction',
        ['narrowing', 'widening', 'flat'] as const,
        'verdict.chip',
      ),
    },
    confidence: str(v, 'confidence', 'verdict'),
    soWhat: str(v, 'soWhat', 'verdict'),
    sources: parseRefs(v, 'sources', 'verdict'),
  };
}

function parseChart(raw: unknown, where: string): Chart {
  const c = obj(raw, where);
  return {
    form: oneOf(c, 'form', ['columns', 'bars', 'line'] as const, where),
    title: str(c, 'title', where),
    caption: str(c, 'caption', where),
    unit: str(c, 'unit', where),
    points: list(c, 'points', where).map((item, i) => {
      const p = obj(item, `${where}.points[${i}]`);
      return {
        label: str(p, 'label', `${where}.points[${i}]`),
        value: num(p, 'value', `${where}.points[${i}]`),
        hollow: bool(p, 'hollow', `${where}.points[${i}]`),
        sourceUrl: nullableStr(p, 'sourceUrl', `${where}.points[${i}]`),
      };
    }),
    source: parseRef(c.source, `${where}.source`),
    // Optional at the schema level ("researched defaults allowed") -- every
    // chart this cycle's Python side emits sets it explicitly, but an
    // absent key still means "not researched", never a parse failure.
    researched: c.researched === undefined ? false : bool(c, 'researched', where),
  };
}

const CAUSES = ['no-published-number', 'estimate-only', 'no-plain-name', 'too-sparse'] as const;

function parseNoChartReason(raw: unknown, where: string): NoChartReason {
  const r = obj(raw, where);
  return {
    reason: str(r, 'reason', where),
    cause: oneOf(r, 'cause', CAUSES, where),
  };
}

function parseBullet(raw: unknown, where: string): Bullet {
  const b = obj(raw, where);
  const chart = b.chart === null ? null : parseChart(b.chart, `${where}.chart`);
  const noChartReason =
    b.noChartReason === null
      ? null
      : parseNoChartReason(b.noChartReason, `${where}.noChartReason`);
  if (chart === null && noChartReason === null) {
    fail(`${where}`, 'has no chart and no reason why not');
  }
  if (chart !== null && noChartReason !== null) {
    fail(`${where}`, 'has both a chart and a reason for having none');
  }
  return {
    date: str(b, 'date', where),
    text: str(b, 'text', where),
    storyHref: str(b, 'storyHref', where),
    chart,
    noChartReason,
    sources: parseRefs(b, 'sources', where),
  };
}

function parseDimension(raw: unknown, where: string): Dimension {
  const d = obj(raw, where);
  return {
    id: str(d, 'id', where),
    plainName: str(d, 'plainName', where),
    ratingWord: str(d, 'ratingWord', where),
    tone: oneOf(d, 'tone', ['bad', 'mixed', 'good'] as const, where),
    direction: oneOf(d, 'direction', ['improving', 'worsening', 'flat'] as const, where),
    confidence: str(d, 'confidence', where),
    summary: str(d, 'summary', where),
    reasoning: str(d, 'reasoning', where),
    evidence: parseRefs(d, 'evidence', where),
  };
}

function parseGapChart(raw: unknown): GapChart {
  const g = obj(raw, 'gapChart');
  const annotation = obj(g.annotation, 'gapChart.annotation');
  return {
    points: list(g, 'points', 'gapChart').map((item, i) => {
      const p = obj(item, `gapChart.points[${i}]`);
      return {
        date: str(p, 'date', `gapChart.points[${i}]`),
        demand: num(p, 'demand', `gapChart.points[${i}]`),
        supply: num(p, 'supply', `gapChart.points[${i}]`),
      };
    }),
    annotation: {
      date: str(annotation, 'date', 'gapChart.annotation'),
      label: str(annotation, 'label', 'gapChart.annotation'),
    },
    caption: str(g, 'caption', 'gapChart'),
    sources: parseRefs(g, 'sources', 'gapChart'),
  };
}

const ISSUE_STATUSES = ['improved', 'worsened', 'unchanged', 'not-assessed'] as const;

function parseIssueHistoryEntry(raw: unknown, where: string): IssueHistoryEntry {
  const h = obj(raw, where);
  return {
    asOf: str(h, 'asOf', where),
    status: oneOf(h, 'status', ISSUE_STATUSES, where),
  };
}

function parseIssueOpen(raw: unknown, where: string): IssueOpen {
  const i = obj(raw, where);
  return {
    id: str(i, 'id', where),
    title: str(i, 'title', where),
    status: oneOf(i, 'status', ISSUE_STATUSES, where),
    assessedAsOf: str(i, 'assessedAsOf', where),
    trackedSince: str(i, 'trackedSince', where),
    worsenedCount: num(i, 'worsenedCount', where),
    checkCount: num(i, 'checkCount', where),
    reasoning: str(i, 'reasoning', where),
    sources: parseRefs(i, 'sources', where),
    history: list(i, 'history', where).map((item, idx) =>
      parseIssueHistoryEntry(item, `${where}.history[${idx}]`),
    ),
  };
}

function parseIssueResolved(raw: unknown, where: string): IssueResolved {
  const i = obj(raw, where);
  return {
    id: str(i, 'id', where),
    title: str(i, 'title', where),
    resolvedAsOf: str(i, 'resolvedAsOf', where),
    finalNote: str(i, 'finalNote', where),
  };
}

function parseIssues(raw: unknown): Issues {
  const i = obj(raw, 'issues');
  return {
    open: list(i, 'open', 'issues').map((item, idx) => parseIssueOpen(item, `issues.open[${idx}]`)),
    resolved: list(i, 'resolved', 'issues').map((item, idx) =>
      parseIssueResolved(item, `issues.resolved[${idx}]`),
    ),
  };
}

/**
 * Check a raw payload and hand back a typed dashboard, or throw saying exactly
 * which field is wrong. The page never renders anything it has not checked.
 */
export function parseDashboard(raw: unknown): Dashboard {
  const d = obj(raw, 'payload');
  if (d.schemaVersion !== '1.2') {
    fail('schemaVersion', `is "${String(d.schemaVersion)}", not the expected "1.2"`);
  }
  const bullets = list(d, 'bullets', 'payload');
  if (bullets.length !== 3) {
    fail('bullets', `has ${bullets.length} entries, not the expected 3`);
  }
  const dimensions = list(d, 'dimensions', 'payload');
  if (dimensions.length !== 6) {
    fail('dimensions', `has ${dimensions.length} entries, not the expected 6`);
  }
  return {
    schemaVersion: '1.2',
    categoryId: str(d, 'categoryId', 'payload'),
    asOf: str(d, 'asOf', 'payload'),
    verdict: parseVerdict(d.verdict),
    gapChart: parseGapChart(d.gapChart),
    bullets: bullets.map((item, i) => parseBullet(item, `bullets[${i}]`)),
    dimensions: dimensions.map((item, i) => parseDimension(item, `dimensions[${i}]`)),
    footerLinks: list(d, 'footerLinks', 'payload').map((item, i) => {
      const f = obj(item, `footerLinks[${i}]`);
      return {
        label: str(f, 'label', `footerLinks[${i}]`),
        href: str(f, 'href', `footerLinks[${i}]`),
      };
    }),
    issues: parseIssues(d.issues),
  };
}

// --- freshness --------------------------------------------------------------

const DAY_MS = 24 * 60 * 60 * 1000;
/** Two days is the grace period: a weekend gap is normal, longer is not. */
export const STALE_AFTER_DAYS = 2;

function dayNumber(year: number, month: number, day: number): number {
  return Date.UTC(year, month, day) / DAY_MS;
}

/** The calendar day a plain "2026-08-05" string refers to. */
function asOfDay(asOf: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(asOf);
  if (!match) return null;
  return dayNumber(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

/**
 * Is this reading older than the file it came out of?
 *
 * The page has no clock of its own it can trust, so it compares the reading's
 * own date against when the DATA FILE was last written — the `Last-Modified`
 * stamp the server sends back with it.
 *
 * FINAL REVIEW, Important 2: this used to compare against
 * `document.lastModified`, the HTML page's own timestamp. That file is a
 * committed input that only changes when someone runs `npm run build` by
 * hand, while the data file is rewritten by every daily run. So if an export
 * ever failed (it is deliberately swallowed so a bad export cannot stop the
 * cycle), yesterday's data file stayed put and the page served an old verdict
 * as today's reading with this warning never firing. The data file's own
 * timestamp is the only one that moves when the reading does.
 */
export function isStale(asOf: string, dataLastModified: string): boolean {
  const readingDay = asOfDay(asOf);
  if (readingDay === null) return false;
  const built = new Date(dataLastModified);
  if (Number.isNaN(built.getTime())) return false;
  const builtDay = dayNumber(built.getFullYear(), built.getMonth(), built.getDate());
  return builtDay - readingDay > STALE_AFTER_DAYS;
}

/** Where the daily run drops the file, relative to the page that reads it. */
export const DEFAULT_DATA_URL = './data/dashboard.json';

/** Fetch the day's reading and say whether it has gone stale. */
export async function loadDashboard(
  url: string = DEFAULT_DATA_URL,
): Promise<{data: Dashboard; stale: boolean}> {
  const response = await fetch(url, {cache: 'no-cache'});
  if (!response.ok) {
    // FINAL REVIEW, Minor 8: a reader was being shown the file path and the
    // status code. Neither means anything to them, and neither is something
    // they can act on. Say plainly what happened and what to do.
    throw new Error(
      'The file it comes from could not be read just now. Please try again in a few minutes.',
    );
  }
  const data = parseDashboard(await response.json());
  // The stamp on the DATA file, not on the page — see `isStale`.
  const dataLastModified = response.headers?.get('Last-Modified') ?? '';
  return {data, stale: isStale(data.asOf, dataLastModified)};
}

/** "2026-08-04" as "4 August 2026". Returns null for a missing date. */
export function plainDate(date: string | null): string | null {
  if (!date) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!match) return date;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${match[0]}T00:00:00Z`));
}

/** "2026-08-05" as "Wednesday 5 August 2026", for the masthead. */
export function plainDateWithWeekday(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!match) return date;
  // The mock writes it without a comma: "Wednesday 5 August 2026".
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
    .format(new Date(`${match[0]}T00:00:00Z`))
    .replace(',', '');
}
