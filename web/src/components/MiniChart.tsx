/**
 * The small supporting chart beside a "what changed" bullet. Ported from the
 * mock's two worked examples
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html):
 *   - `columns` (AMD quarterly revenue, lines 541-543): thin vertical bars,
 *     first/last points labelled, a hover tooltip per bar.
 *   - `bars` (NVIDIA memory per chip, lines 559-561): horizontal bars with
 *     the label and value written beside each one; a `hollow` point (the
 *     2025 preview that was never built) renders as the mock's pale,
 *     outlined "ghost" bar rather than a solid one.
 * `line` has no worked example in the mock — this category's registered
 * `gpuSpotPrice` series (registry/chart-series.json) already uses it, so a
 * real chart will need it. Built to the same visual language as the other
 * two (same tokens, same hover-tooltip pattern, the same `ghost` treatment
 * for a hollow point) rather than inventing a new one.
 *
 * Every chart carries its own source via `SourceMark`, distinct from the
 * bullet's own `SourceMark` for its prose sources.
 */
import {SourceMark} from './SourceMark';
import {makeValueScale} from './gapMath';
import type {Chart, ChartPoint} from '../load';

export interface MiniChartProps {
  chart: Chart;
}

const VIEW_W = 320;

/** "6.7 USD bn", "1,024 GB" -- the number, formatted with a sensible number
 * of decimals and a thousands separator, followed by the server-supplied
 * plain-English unit. Never a raw float, never the unit omitted. */
function formatChartValue(value: number, unit: string): string {
  const decimals = Number.isInteger(value) ? 0 : 1;
  const num = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
  return unit ? `${num} ${unit}` : num;
}

function ariaDescription(chart: Chart): string {
  const {points, title, unit} = chart;
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return title;
  if (first === last) {
    return `${title}: ${formatChartValue(first.value, unit)} at ${first.label}.`;
  }
  return (
    `${title}: from ${formatChartValue(first.value, unit)} at ${first.label} ` +
    `to ${formatChartValue(last.value, unit)} at ${last.label}.`
  );
}

function barClass(seriesClass: string, point: ChartPoint): string {
  return point.hollow ? `mini-bar ${seriesClass} ghost` : `mini-bar ${seriesClass}`;
}

/** Vertical bars rising from a shared baseline -- the AMD-revenue form. */
function Columns({chart}: {chart: Chart}) {
  const {points, unit} = chart;
  const n = points.length;
  const LEFT = 4;
  const RIGHT = 316;
  const BASE_Y = 124;
  const TOP_Y = 8;
  const PLOT_H = BASE_Y - TOP_Y;
  const slot = (RIGHT - LEFT) / n;
  const barW = slot * 0.62;
  const maxAbs = Math.max(...points.map((p) => Math.abs(p.value)), 1e-9);
  const lastIndex = n - 1;

  return (
    <svg viewBox={`0 0 ${VIEW_W} 152`} role="img" aria-label={ariaDescription(chart)}>
      <line className="mini-base" x1={LEFT} y1={BASE_Y} x2={RIGHT} y2={BASE_Y} />
      {points.map((p, i) => {
        const center = LEFT + slot * (i + 0.5);
        const height = (Math.abs(p.value) / maxAbs) * PLOT_H;
        const barY = BASE_Y - height;
        const tipLeft = center > VIEW_W / 2;
        return (
          <g className="mbar" key={`${p.label}-${i}`}>
            <rect
              className={barClass('dem', p)}
              x={center - barW / 2}
              y={barY}
              width={barW}
              height={Math.max(height, 1)}
              rx={3}
            />
            <rect className="mini-hit" x={center - slot / 2} y={TOP_Y} width={slot} height={PLOT_H} />
            <text
              className="mini-tip"
              x={tipLeft ? VIEW_W - 2 : 2}
              y={12}
              textAnchor={tipLeft ? 'end' : 'start'}
            >
              {p.label} &middot; {formatChartValue(p.value, unit)}
            </text>
            {i === 0 || i === lastIndex ? (
              <text
                className={i === lastIndex ? 'mini-val strong' : 'mini-val'}
                x={center}
                y={barY - 8}
                textAnchor="middle"
              >
                {formatChartValue(p.value, unit)}
              </text>
            ) : null}
          </g>
        );
      })}
      <text className="mini-tick" x={LEFT} y={138} textAnchor="start">
        {points[0]?.label}
      </text>
      <text className="mini-tick" x={RIGHT} y={138} textAnchor="end">
        {points[lastIndex]?.label}
      </text>
    </svg>
  );
}

/** Horizontal bars, one row per point -- the NVIDIA-memory form. A `hollow`
 * point (a design shown once and never built) renders as the mock's pale,
 * outlined "ghost" bar. */
function Bars({chart}: {chart: Chart}) {
  const {points, unit} = chart;
  const ROW_H = 46;
  const TOP_PAD = 8;
  const BAR_MAX_W = 196;
  const maxAbs = Math.max(...points.map((p) => Math.abs(p.value)), 1e-9);
  const viewH = points.length * ROW_H + TOP_PAD * 2;
  const lastIndex = points.length - 1;

  return (
    <svg viewBox={`0 0 ${VIEW_W} ${viewH}`} role="img" aria-label={ariaDescription(chart)}>
      {points.map((p, i) => {
        const rowTop = TOP_PAD + i * ROW_H;
        const tickY = rowTop + 6;
        const barY = rowTop + 14;
        const width = (Math.abs(p.value) / maxAbs) * BAR_MAX_W;
        return (
          <g key={`${p.label}-${i}`}>
            <text className="mini-tick" x={0} y={tickY}>
              {p.label}
            </text>
            <rect
              className={barClass('sup', p)}
              x={0}
              y={barY}
              width={Math.max(width, 1)}
              height={14}
              rx={3}
            />
            <text
              className={i === lastIndex ? 'mini-val strong' : 'mini-val'}
              x={width + 8}
              y={barY + 11}
            >
              {formatChartValue(p.value, unit)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** A single-series sparkline, evenly spaced by point order (points here are
 * named periods like "Q2 2026" or "Jul 2026", not calendar dates -- unlike
 * the zone-2 gap chart, there is no real-date axis to honour). */
function Line({chart}: {chart: Chart}) {
  const {points, unit} = chart;
  const n = points.length;
  const LEFT = 8;
  const RIGHT = 312;
  const TOP = 16;
  const BOTTOM = 116;
  const {scale} = makeValueScale(points.map((p) => p.value), [TOP, BOTTOM]);
  const slot = n > 1 ? (RIGHT - LEFT) / (n - 1) : 0;
  const xs = points.map((_, i) => (n > 1 ? LEFT + slot * i : (LEFT + RIGHT) / 2));
  const ys = points.map((p) => scale(p.value));
  const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');
  const lastIndex = n - 1;

  return (
    <svg viewBox={`0 0 ${VIEW_W} 152`} role="img" aria-label={ariaDescription(chart)}>
      <line className="mini-base" x1={LEFT} y1={BOTTOM} x2={RIGHT} y2={BOTTOM} />
      <path className="mini-line" d={path} />
      {points.map((p, i) => {
        const tipLeft = xs[i] > VIEW_W / 2;
        return (
          <g className="mbar" key={`${p.label}-${i}`}>
            <circle
              className={p.hollow ? 'mini-dot ghost' : 'mini-dot'}
              cx={xs[i]}
              cy={ys[i]}
              r={3.5}
            />
            <rect
              className="mini-hit"
              x={xs[i] - (slot || RIGHT - LEFT) / 2}
              y={TOP - 8}
              width={slot || RIGHT - LEFT}
              height={BOTTOM - TOP + 16}
            />
            <text
              className="mini-tip"
              x={tipLeft ? VIEW_W - 2 : 2}
              y={12}
              textAnchor={tipLeft ? 'end' : 'start'}
            >
              {p.label} &middot; {formatChartValue(p.value, unit)}
            </text>
          </g>
        );
      })}
      <text className="mini-val" x={xs[0]} y={ys[0] - 8} textAnchor="start">
        {formatChartValue(points[0]!.value, unit)}
      </text>
      <text className="mini-val strong" x={xs[lastIndex]} y={ys[lastIndex] - 8} textAnchor="end">
        {formatChartValue(points[lastIndex]!.value, unit)}
      </text>
      <text className="mini-tick" x={LEFT} y={138} textAnchor="start">
        {points[0]?.label}
      </text>
      <text className="mini-tick" x={RIGHT} y={138} textAnchor="end">
        {points[lastIndex]?.label}
      </text>
    </svg>
  );
}

export function MiniChart({chart}: MiniChartProps) {
  if (chart.points.length === 0) return null;

  return (
    <figure className="mini">
      <div className="mini-plot">
        {chart.form === 'columns' ? (
          <Columns chart={chart} />
        ) : chart.form === 'bars' ? (
          <Bars chart={chart} />
        ) : (
          <Line chart={chart} />
        )}
      </div>
      <figcaption>
        {chart.caption}
        <SourceMark refs={[chart.source]} about={chart.title} />
      </figcaption>
    </figure>
  );
}
