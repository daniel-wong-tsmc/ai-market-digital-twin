import type {Cause} from '../load';

/**
 * The one sentence each reason for not drawing a chart is allowed to say.
 *
 * These four strings are READER-FACING COPY, approved by the user — the first
 * three verbatim from the design spec (§6.2,
 * docs/superpowers/specs/2026-08-06-f113-chart-researcher-design.md), the
 * fourth from the user's own wording when `no-plain-name` was added (F113 Task
 * 1, commit 7f99726) because labelling those bullets "too sparse" was a
 * statement the code itself knew to be false. DO NOT reword any of them, and
 * do not add a plural or "and the rest" variant, without asking first.
 *
 * The `Record<Cause, string>` type is the guard: adding a fifth cause code to
 * `load.ts` without writing its sentence stops the build rather than shipping
 * a bullet with no explanation.
 */
export const CAUSE_LEAD: Record<Cause, string> = {
  'no-published-number': 'No published number behind this yet.',
  'estimate-only': "The only number we hold is our own estimate, so we don't draw it.",
  'too-sparse': 'Too few published readings yet to draw honestly.',
  'no-plain-name': 'We have the numbers, but no plain-English name for what they measure yet.',
};

/**
 * The honest-omission panel — the mock's dashed box
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html lines
 * 549-553).
 *
 * THIS IS NOT A FALLBACK, and it is no longer the every-day case either.
 * F113 §6.1 reserves the dashed frame for the MIXED state: some of the day's
 * bullets carry real charts and this one deliberately does not, so the gap in
 * the row is information — the reader can see we had the chance to draw
 * something and chose not to. When NO bullet has a chart, three identical
 * dashed boxes stop carrying that meaning and just read as a broken page, so
 * `Bullets` drops the panel entirely and prints one quiet line instead.
 *
 * Two lines of text, never an `<svg>`:
 *  - `lead` — the sentence for this bullet, picked by `Bullets` (normally the
 *    cause's `CAUSE_LEAD` line; the payload's own sentence when an earlier
 *    bullet already used that cause's line, so the page never repeats itself).
 *  - `detail` — the payload's extra specifics, or `null` when the lead already
 *    IS the payload sentence and printing it twice would be the very
 *    repetition we are avoiding.
 *
 * The bare "No chart." label the mock opened with is gone (user decision,
 * 2026-08-07): the cause sentence is the lead now, and "No chart." repeated
 * once per chartless bullet was the same duplication in a different shirt.
 */
export interface NoChartProps {
  lead: string;
  detail: string | null;
  cause: Cause;
}

export function NoChart({lead, detail, cause}: NoChartProps) {
  return (
    <figure className="mini">
      {/* Keeps the mock's own `mini-plot empty` class names (the mock is the
       * token authority) and adds `nochart-panel` as the name the layout rules
       * are written in terms of. `data-cause` carries the machine-readable
       * code into the DOM so a screenshot review can tell WHICH honesty gate
       * fired without reading the payload. */}
      <div className="mini-plot empty nochart-panel" data-cause={cause}>
        <p className="nochart-lead">{lead}</p>
        {detail ? <p className="why-none">{detail}</p> : null}
      </div>
    </figure>
  );
}
