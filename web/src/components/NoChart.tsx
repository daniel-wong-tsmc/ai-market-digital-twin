import type {Cause} from '../load';

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
 *
 * Schema 1.1 (F113 Task 1): the payload now hands this panel two structured
 * fields instead of one pre-formatted sentence -- `reason` (the payload's
 * own plain-English detail) and `cause` (the machine-readable code driving
 * it). This component still renders the same two-line shape the mock
 * defines (a bold "No chart." lead, then the muted why line) using a fixed
 * lead string rather than splitting the payload text apart -- there is no
 * `splitReason` any more. Varying the LEAD line's copy by `cause` is F113
 * Task 2's job (spec §6.2); this task only carries `cause` through so that
 * later work has it to read.
 */
export interface NoChartProps {
  reason: string;
  cause: Cause;
}

export function NoChart({reason, cause}: NoChartProps) {
  return (
    <figure className="mini">
      {/* data-cause: carries the machine-readable code through to the DOM so
       * F113 Task 2's copy-by-cause and layout work has it to key off of;
       * this task renders the same fixed lead + reason line regardless. */}
      <div className="mini-plot empty" data-cause={cause}>
        <p>No chart.</p>
        <p className="why-none">{reason}</p>
      </div>
    </figure>
  );
}
