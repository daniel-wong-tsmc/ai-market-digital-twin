/**
 * Zone 2 — the demand-versus-supply chart. Two lines, a shaded gap between
 * them, an annotation on the widest reading, and a "Show the numbers" table
 * underneath for anyone who cannot (or does not want to) read the picture.
 *
 * THE rule this file exists to get right: every point sits on the horizontal
 * axis by its real calendar date, via `makeDateScale` in ./gapMath — never
 * by its position in the `points` array. The real payload mixes single-day
 * readings taken days apart with whole-month figures a month apart; plotting
 * by index would draw four days and a month-long gap as the same width, and
 * that would show the reader a pattern that is not real.
 */
import {SourceMark} from './SourceMark';
import {NumbersTable} from './NumbersTable';
import {
  dayNumber,
  formatSigned,
  makeDateScale,
  makeValueScale,
  shortDate,
  spacedTickIndices,
  ticks,
} from './gapMath';
import {plainDate} from '../load';
import type {GapChart as GapChartData, GapPoint} from '../load';

export interface GapChartProps {
  data: GapChartData;
}

// The plot's own pixel geometry -- a fixed viewBox, ported from the mock's
// SVG so the chart's proportions match the approved visual contract exactly.
const VIEW_W = 1000;
const VIEW_H = 300;
const PLOT_X0 = 44;
const PLOT_X1 = 860;
const PLOT_Y_TOP = 20;
const PLOT_Y_BOTTOM = 244;
const XTICK_Y = 276;
const HOV_TOP = 12;
const HOV_BOTTOM = 258;
const END_SWATCH_X = 876;
const END_LABEL_X = 886;
// Roughly two label widths at the axis type size: enough room that "1 Jun"
// and its neighbour never touch. Below this, a point goes unlabelled.
const MIN_TICK_GAP = 70;

function ariaDescription(points: GapPoint[]): string {
  const first = points[0];
  const last = points[points.length - 1];
  const demandWord = last.demand >= first.demand ? 'rises' : 'falls';
  const supplyWord = last.supply >= first.supply ? 'rises' : 'falls';
  const firstGap = first.demand - first.supply;
  const lastGap = last.demand - last.supply;
  const gapWord =
    Math.abs(lastGap - firstGap) < 0.05
      ? 'holds roughly steady'
      : lastGap > firstGap
        ? 'widens'
        : 'narrows';
  return (
    `Two lines since ${plainDate(first.date)}. The demand score ${demandWord} from ` +
    `${formatSigned(first.demand)} to ${formatSigned(last.demand)} while the supply score ` +
    `${supplyWord} from ${formatSigned(first.supply)} to ${formatSigned(last.supply)}, so ` +
    `the shaded gap between them ${gapWord}.`
  );
}

export function GapChart({data}: GapChartProps) {
  // Defensive sort by real date -- geometry must be correct even if a future
  // producer ever hands points out of order. This reorders, it never drops,
  // rescales or otherwise touches the reported demand/supply figures.
  const points = [...data.points].sort((a, b) => dayNumber(a.date) - dayNumber(b.date));

  if (points.length === 0) {
    return null;
  }

  const xScale = makeDateScale(
    points.map((p) => p.date),
    [PLOT_X0, PLOT_X1],
  );
  const {scale: yScale, min: yMin, max: yMax} = makeValueScale(
    points.flatMap((p) => [p.demand, p.supply]),
    [PLOT_Y_TOP, PLOT_Y_BOTTOM],
  );

  const xs = points.map((p) => xScale(p.date));
  const demandYs = points.map((p) => yScale(p.demand));
  const supplyYs = points.map((p) => yScale(p.supply));

  const demandPath = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${demandYs[i].toFixed(1)}`).join(' ');
  const supplyPath = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${supplyYs[i].toFixed(1)}`).join(' ');
  const bandForward = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${demandYs[i].toFixed(1)}`).join(' ');
  const bandBack = xs
    .map((x, i) => `L ${x.toFixed(1)} ${supplyYs[i].toFixed(1)}`)
    .reverse()
    .join(' ');
  const gapBandPath = `${bandForward} ${bandBack} Z`;

  const yTicks = ticks(yMin, yMax, 5);
  const zeroInRange = yMin < 0 && yMax > 0;

  const annotationIndex = points.findIndex((p) => p.date === data.annotation.date);

  const lastIndex = points.length - 1;

  return (
    <figure className="chart">
      <div className="chart-legend">
        <span>
          <i className="key dem" aria-hidden="true" /> Demand — what buyers are committing
        </span>
        <span>
          <i className="key sup" aria-hidden="true" /> Supply — what is actually arriving
        </span>
        <span>
          <i className="key gap" aria-hidden="true" /> The gap between them
        </span>
      </div>

      <div className="plot-frame">
        <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} role="img" aria-label={ariaDescription(points)}>
          {yTicks.map((v, i) => (
            <g key={`ytick-${i}`}>
              <line
                className="grid"
                x1={PLOT_X0}
                y1={yScale(v)}
                x2={PLOT_X1}
                y2={yScale(v)}
              />
              <text className="ytick" x={PLOT_X0 - 10} y={yScale(v) + 4}>
                {formatSigned(v, 1)}
              </text>
            </g>
          ))}
          {zeroInRange ? (
            <line className="zero" x1={PLOT_X0} y1={yScale(0)} x2={PLOT_X1} y2={yScale(0)} />
          ) : null}

          {spacedTickIndices(xs, MIN_TICK_GAP).map((i) => (
            <text key={`xtick-${points[i].date}`} className="xtick" x={xs[i]} y={XTICK_Y}>
              {shortDate(points[i].date)}
            </text>
          ))}

          <path className="gapband" d={gapBandPath} />

          {annotationIndex !== -1 ? (
            <g>
              <line
                className="ann-rule"
                x1={xs[annotationIndex]}
                y1={PLOT_Y_TOP - 4}
                x2={xs[annotationIndex]}
                y2={PLOT_Y_BOTTOM + 16}
              />
              <text
                className="ann"
                x={xs[annotationIndex] - 8}
                y={PLOT_Y_TOP - 6}
                textAnchor="end"
              >
                {data.annotation.label}, {shortDate(points[annotationIndex].date)}
              </text>
            </g>
          ) : null}

          <path className="line sup" d={supplyPath} />
          <path className="line dem" d={demandPath} />

          <circle className="dot dem" cx={xs[lastIndex]} cy={demandYs[lastIndex]} r={4.5} />
          <circle className="dot sup" cx={xs[lastIndex]} cy={supplyYs[lastIndex]} r={4.5} />
          <circle className="swatch dem" cx={END_SWATCH_X} cy={demandYs[lastIndex]} r={4} />
          <text className="endlab" x={END_LABEL_X} y={demandYs[lastIndex] - 3}>
            Demand
          </text>
          <text className="endval" x={END_LABEL_X} y={demandYs[lastIndex] + 13}>
            {formatSigned(points[lastIndex].demand)}
          </text>
          <circle className="swatch sup" cx={END_SWATCH_X} cy={supplyYs[lastIndex]} r={4} />
          <text className="endlab" x={END_LABEL_X} y={supplyYs[lastIndex] - 3}>
            Supply
          </text>
          <text className="endval" x={END_LABEL_X} y={supplyYs[lastIndex] + 13}>
            {formatSigned(points[lastIndex].supply)}
          </text>

          {points.map((p, i) => {
            const left = i === 0 ? PLOT_X0 : (xs[i - 1] + xs[i]) / 2;
            const right = i === lastIndex ? PLOT_X1 : (xs[i] + xs[i + 1]) / 2;
            const tipLeft = xs[i] > (PLOT_X0 + PLOT_X1) / 2 ? xs[i] - 212 : xs[i] + 10;
            const gap = p.demand - p.supply;
            return (
              <g className="hov" key={p.date}>
                <rect x={left} y={HOV_TOP} width={Math.max(right - left, 1)} height={HOV_BOTTOM - HOV_TOP} />
                <g className="read">
                  <line className="cross" x1={xs[i]} y1={HOV_TOP} x2={xs[i]} y2={HOV_BOTTOM} />
                  <circle className="dot dem" cx={xs[i]} cy={demandYs[i]} r={4} />
                  <circle className="dot sup" cx={xs[i]} cy={supplyYs[i]} r={4} />
                  <rect className="tipbg" x={tipLeft} y={PLOT_Y_BOTTOM - 40} width={208} height={62} rx={6} />
                  <text className="tip head" x={tipLeft + 14} y={PLOT_Y_BOTTOM - 22}>
                    {plainDate(p.date)}
                  </text>
                  <text className="tip" x={tipLeft + 14} y={PLOT_Y_BOTTOM - 6}>
                    Demand {formatSigned(p.demand)} &middot; Supply {formatSigned(p.supply)}
                  </text>
                  <text className="tip strong" x={tipLeft + 14} y={PLOT_Y_BOTTOM + 10}>
                    Gap {formatSigned(gap)}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
      </div>

      <figcaption>
        {data.caption}
        <SourceMark refs={data.sources} about="the gap chart" />
      </figcaption>

      <NumbersTable points={points} />
    </figure>
  );
}
