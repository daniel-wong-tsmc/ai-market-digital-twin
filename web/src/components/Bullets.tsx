/**
 * Zone 3 — "what changed": exactly three dated, plain-English bullets
 * condensing the day's story, each paired with either a small supporting
 * chart (`MiniChart`) or, when there is nothing honest to draw, an explanation
 * — never both, per the schema's own one-of-chart-or-reason rule
 * (`web/schema/dashboard.schema.json`).
 *
 * Ported from the mock's `.change` rows
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html lines
 * 536-563), with the F113 §6 render fixes on top. The fixes exist because the
 * live page on 2026-08-06 showed three identical dashed boxes carrying three
 * identical sentences, which reads as a broken product rather than as honesty.
 *
 * The three layouts this component chooses between, in the order it tests
 * them — the whole zone decides, because none of these can be decided by a
 * bullet looking only at itself:
 *
 *  1. EVERY bullet chartless, ALL the same cause (today's real payload). Every
 *     row goes full width and the shared explanation is printed ONCE, quietly,
 *     under the group. Rationale (user decision, interactive 2026-08-07): the
 *     exporter builds each reason from a fixed list of canned sentences
 *     (`gpu_agent/dashboard/bullets.py::_fallback_reason`), so bullets sharing
 *     a cause normally share the identical wording too — there is no honest
 *     third sentence to reach for, and saying one true thing once beats saying
 *     it three times. The grouped line uses the cause's approved sentence
 *     UNCHANGED; inventing a plural variant would be new reader copy.
 *  2. EVERY bullet chartless, causes DIFFER. Rows still go full width, but
 *     each keeps its own quiet line, because each has something different to
 *     say.
 *  3. MIXED — at least one real chart on the page. Charted bullets keep the
 *     chart column and chartless ones keep the dashed panel, because next to a
 *     real chart the empty slot is meaningful (§6.1).
 *
 * Across all of them, rule §6.2 holds: the same sentence never appears twice
 * on one page. See `pickLines`.
 */
import {MiniChart} from './MiniChart';
import {CAUSE_LEAD, NoChart} from './NoChart';
import {SourceMark} from './SourceMark';
import {shortDate} from './gapMath';
import type {Bullet, Cause} from '../load';

export interface BulletsProps {
  bullets: Bullet[];
}

/**
 * Picks the one sentence each chartless bullet says, in reading order.
 *
 * First bullet of a cause: that cause's approved lead line. A LATER bullet
 * with the same cause would only repeat it, so it says its own payload
 * sentence instead — different words, same truth, nothing invented. Charted
 * bullets get `null`; they say nothing.
 */
function pickLines(bullets: Bullet[]): (string | null)[] {
  const used = new Set<Cause>();
  return bullets.map((bullet) => {
    if (bullet.chart || !bullet.noChartReason) return null;
    const {reason, cause} = bullet.noChartReason;
    if (used.has(cause)) return reason;
    used.add(cause);
    return CAUSE_LEAD[cause];
  });
}

/**
 * Splits a sentence into everything-but-the-last-word and the last word, so
 * the source badge can be glued to that last word inside one `nowrap` span
 * (§6.3). Without this the badge is free to wrap onto a line of its own, where
 * it reads as a stray number rather than as a footnote marker — and the
 * popover library wraps its trigger in a `<div>`, which app.css has to force
 * back to `display: inline` for the same reason.
 */
function splitLastWord(text: string): [string, string] {
  const trimmed = text.trimEnd();
  const cut = trimmed.lastIndexOf(' ');
  if (cut === -1) return ['', trimmed];
  return [trimmed.slice(0, cut + 1), trimmed.slice(cut + 1)];
}

interface RowProps {
  bullet: Bullet;
  /** The sentence chosen for this bullet by `pickLines` (null when charted). */
  line: string | null;
  /** No chart column anywhere on the page: the text spans the row. */
  full: boolean;
  /** This row prints its own quiet line (layout 2, not the grouped layout 1). */
  ownLine: boolean;
}

function BulletRow({bullet, line, full, ownLine}: RowProps) {
  const [head, lastWord] = splitLastWord(bullet.text);
  const reason = bullet.noChartReason;
  return (
    <div className={full ? 'change full' : 'change'}>
      <span className="date">{shortDate(bullet.date)}</span>
      <div className="change-text">
        <p>
          {head}
          <span className="nowrap-end">
            {lastWord}
            <SourceMark refs={bullet.sources} about={bullet.text} />
          </span>
        </p>
        {ownLine && reason ? (
          <p className="nochart-quiet" data-cause={reason.cause}>
            {line}
          </p>
        ) : null}
      </div>
      {bullet.chart ? <MiniChart chart={bullet.chart} /> : null}
      {!bullet.chart && !full && reason ? (
        <NoChart
          lead={line!}
          // When the lead already IS the payload sentence (this bullet's cause
          // was used earlier), repeating it underneath would be the very
          // duplication §6.2 forbids.
          detail={line === reason.reason ? null : reason.reason}
          cause={reason.cause}
        />
      ) : null}
    </div>
  );
}

export function Bullets({bullets}: BulletsProps) {
  const lines = pickLines(bullets);
  const allChartless = bullets.length > 0 && bullets.every((b) => !b.chart);
  const causes = new Set(
    bullets.filter((b) => b.noChartReason).map((b) => b.noChartReason!.cause),
  );
  // Layout 1: nothing charted and one single shared reason for it.
  const grouped = allChartless && causes.size === 1;
  const groupCause = grouped ? [...causes][0] : null;

  return (
    <div className="changed">
      {bullets.map((bullet, i) => (
        <BulletRow
          bullet={bullet}
          line={lines[i]}
          full={allChartless}
          ownLine={allChartless && !grouped}
          key={`${bullet.date}-${i}`}
        />
      ))}
      {groupCause ? (
        <p className="nochart-quiet" data-cause={groupCause}>
          {CAUSE_LEAD[groupCause]}
        </p>
      ) : null}
    </div>
  );
}
