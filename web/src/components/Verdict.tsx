/**
 * Zone 1 — the verdict. The first thing anyone reads, and the largest text on
 * the page: a short question, the answer as the headline, then the direction of
 * travel, how sure we are, and what it means.
 */
import {SourceMark} from './SourceMark';
import {plainDate} from '../load';
import type {Chip, VerdictData} from '../load';

/** Green when the gap is closing, red when it is opening, quiet when flat. */
const TONE: Record<Chip['direction'], string> = {
  narrowing: 'good',
  widening: 'serious',
  flat: 'flat',
};

function DirectionIcon({direction}: {direction: Chip['direction']}) {
  // Decorative only — the chip always spells the direction out in words too.
  const path =
    direction === 'narrowing'
      ? 'M2 4.5 6 8.5 10 4.5'
      : direction === 'widening'
        ? 'M2 7.5 6 3.5 10 7.5'
        : 'M2 6h8';
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** A lead is a short phrase like "Not yet." — four words at the outside. */
const LONGEST_LEAD_WORDS = 4;

/**
 * The mock sets the opening phrase of the answer apart. Split on the first full
 * stop so the lead carries the weight, and colour it by the direction the gap is
 * actually moving — never colour on its own, the words say it too.
 *
 * Only a genuine short lead followed by a supporting sentence gets set apart. A
 * one-sentence answer, or one that opens with a long sentence, is left alone:
 * colouring the whole headline would turn emphasis into decoration.
 */
function splitAnswer(answer: string): [lead: string, rest: string] {
  const stop = answer.indexOf('. ');
  if (stop === -1) return ['', answer];
  const lead = answer.slice(0, stop + 1);
  const rest = answer.slice(stop + 1);
  if (rest.trim() === '') return ['', answer];
  if (lead.trim().split(/\s+/).length > LONGEST_LEAD_WORDS) return ['', answer];
  return [lead, rest];
}

export interface VerdictProps {
  verdict: VerdictData;
  asOf: string;
  stale: boolean;
}

export function Verdict({verdict, asOf, stale}: VerdictProps) {
  const [lead, rest] = splitAnswer(verdict.answer);
  const tone = TONE[verdict.chip.direction];

  return (
    <section className="verdict">
      {stale ? (
        <p className="staleban" role="status">
          This reading is from {plainDate(asOf)}. We have not published a newer
          one since.
        </p>
      ) : null}

      <p className="q">{verdict.question}</p>

      <h1>
        {lead ? <span className={`lead ${tone}`}>{lead}</span> : null}
        {rest}
        <SourceMark refs={verdict.sources} about="the verdict" />
      </h1>

      <div className="vmeta">
        <span className={`chip ${tone}`}>
          <DirectionIcon direction={verdict.chip.direction} />
          {verdict.chip.label}
        </span>
        <span className="sep" aria-hidden="true">
          ·
        </span>
        <span className="m">{verdict.confidence}</span>
      </div>

      <p className="sowhat">{verdict.soWhat}</p>
    </section>
  );
}
