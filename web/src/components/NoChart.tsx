/**
 * The honest-omission panel — the mock's dashed "No chart." box
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html lines
 * 549-553), rendered when a bullet's `noChartReason` is set instead of a
 * `chart`.
 *
 * THIS IS NOT A FALLBACK. On today's real committed payload
 * (fixtures/dashboard/golden-dashboard.json) all three bullets carry a
 * reason, never a chart — the Python side (gpu_agent/dashboard/bullets.py)
 * refuses to draw estimated data, internal scores, or numbers it cannot
 * name in plain English. This is the ONLY case real readers see today, so
 * it renders no `<svg>` at all — a dashed frame around plain, readable text,
 * never an empty chart shell.
 */
export interface NoChartProps {
  reason: string;
}

/**
 * The reason strings from gpu_agent/dashboard/bullets.py all open with the
 * short sentence "No chart." followed by the plain-English explanation. Split
 * them apart so the panel can echo the mock's two-line layout (a bold "No
 * chart." lead, then the muted why line) without inventing new copy.
 */
function splitReason(reason: string): [headline: string, rest: string] {
  const stop = reason.indexOf('. ');
  if (stop === -1) return [reason, ''];
  return [reason.slice(0, stop + 1), reason.slice(stop + 2)];
}

export function NoChart({reason}: NoChartProps) {
  const [headline, rest] = splitReason(reason);
  return (
    <figure className="mini">
      <div className="mini-plot empty">
        <p>{headline}</p>
        {rest ? <p className="why-none">{rest}</p> : null}
      </div>
    </figure>
  );
}
