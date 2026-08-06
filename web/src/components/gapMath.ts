/**
 * Pure geometry helpers for the gap chart. Kept apart from the component so
 * the ONE rule that matters — points sit on the horizontal axis by their
 * real calendar date, never by their position in the array — lives in one
 * small, obviously-correct place.
 */

/** A UTC day-count for an ISO "YYYY-MM-DD" (or longer) date string. Two dates
 * that are N calendar days apart always differ by exactly N here, regardless
 * of which two indices they sit at in a points array. */
export function dayNumber(isoDate: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return Number.NaN;
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) / 86_400_000;
}

/**
 * A linear scale from real calendar date to a pixel position, built from the
 * actual min/max date in the series. Every date maps to its true proportional
 * place in that range — this is the one function standing between "seven
 * points rendered" and "seven points rendered in the right place".
 */
export function makeDateScale(
  dates: string[],
  range: [number, number],
): (isoDate: string) => number {
  const days = dates.map(dayNumber);
  const min = Math.min(...days);
  const max = Math.max(...days);
  const span = max - min || 1; // a single-point series still gets a defined scale
  const [x0, x1] = range;
  return (isoDate: string) => {
    const t = (dayNumber(isoDate) - min) / span;
    return x0 + t * (x1 - x0);
  };
}

/** A shared linear scale for two value series plotted on one axis, with a
 * little headroom so the lines and the annotation rule never touch the
 * frame. */
export function makeValueScale(
  values: number[],
  range: [number, number],
): {scale: (v: number) => number; min: number; max: number} {
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const pad = (rawMax - rawMin) * 0.14 || Math.max(Math.abs(rawMax), 1) * 0.2;
  const min = rawMin - pad;
  const max = rawMax + pad;
  const span = max - min || 1;
  const [y0, y1] = range; // y0 = top (pixel), y1 = bottom (pixel)
  return {
    scale: (v: number) => y1 - ((v - min) / span) * (y1 - y0),
    min,
    max,
  };
}

/** N evenly spaced tick values across [min, max], including both ends. */
export function ticks(min: number, max: number, count: number): number[] {
  if (count <= 1) return [min];
  const step = (max - min) / (count - 1);
  return Array.from({length: count}, (_, i) => min + i * step);
}

/** "0.63", "−0.45" -- a real minus sign, never a hyphen, and always the
 * same number of decimal places so the numbers table lines up. */
export function formatSigned(value: number, decimals = 2): string {
  const rounded = Number(value.toFixed(decimals));
  const magnitude = Math.abs(rounded).toFixed(decimals);
  return rounded < 0 ? `−${magnitude}` : magnitude;
}

/** "3 Jul" -- a short calendar label for x-axis ticks and the annotation. */
export function shortDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(`${match[0]}T00:00:00Z`));
}

/**
 * Which points get a date label under the chart.
 *
 * The real reading history bunches up: five single-day readings inside one
 * week, then a month-long jump. Labelling every point printed those five on
 * top of each other and the axis read as gibberish. This keeps the first and
 * last readings -- the two the eye actually looks for -- and then only those
 * in between that sit at least `minGap` apart, so a label always has room.
 *
 * `xs` are the points' horizontal positions, in the order they are drawn.
 */
export function spacedTickIndices(xs: number[], minGap: number): number[] {
  if (xs.length <= 1) return xs.map((_, i) => i);
  const kept = [0];
  for (let i = 1; i < xs.length - 1; i += 1) {
    if (xs[i] - xs[kept[kept.length - 1]] >= minGap) kept.push(i);
  }
  const last = xs.length - 1;
  // The final reading always gets its label, so anything it would collide
  // with gives way -- except the first, which is kept on principle.
  while (kept.length > 1 && xs[last] - xs[kept[kept.length - 1]] < minGap) kept.pop();
  kept.push(last);
  return kept;
}
