/**
 * Zone 6 — "Known issues": the binding constraints and weak-and-worsening
 * dimensions still open, tracked cycle over cycle, plus a quiet record of
 * the ones that have since cleared.
 *
 * F110 review precedent, carried forward for F115: an empty section — heading
 * and all — reads as a broken page, not as honest silence. So when there is
 * nothing open and nothing resolved, this renders nothing at all, not even
 * the "Known issues" heading. `readGolden()`'s committed `issues` are
 * `{open: [], resolved: []}` today — that is this rule's live case, not a
 * hypothetical one.
 *
 * Reuses the page's existing conventions rather than inventing new ones:
 * `SourceMark` for the source badge on the reasoning line (the F113 pattern
 * `Bullets.tsx` established), and the same `.chip` / `.vmeta`-style meta row
 * `Verdict.tsx` and `Dimensions.tsx` already use for a coloured status word
 * next to a plain-English date.
 */
import {SourceMark} from './SourceMark';
import {plainDate} from '../load';
import type {IssueHistoryEntry, IssueOpen, IssueResolved, Issues as IssuesData} from '../load';

/** The colour a status chip takes. `not-assessed` is deliberately NOT one of
 *  the three "we have a fresh read" tones — it gets its own muted look so it
 *  can never be mistaken for a real assessment (spec: "never a fresh-looking
 *  chip"). */
const STATUS_TONE: Record<IssueOpen['status'], string> = {
  improved: 'good',
  worsened: 'serious',
  unchanged: 'flat',
  'not-assessed': 'muted',
};

/** The word the chip says. `not-assessed` says exactly this string, verbatim
 *  — the payload's own status names are for classes, not for reader copy. */
const STATUS_LABEL: Record<IssueOpen['status'], string> = {
  improved: 'Improved',
  worsened: 'Worsened',
  unchanged: 'No change',
  'not-assessed': 'Not assessed this cycle',
};

/** "2026-08-05" as "Aug 2026" — the tenure line's "tracked since" month. */
function monthYear(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  return new Intl.DateTimeFormat('en-GB', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${match[0]}T00:00:00Z`));
}

/**
 * Splits a sentence into everything-but-the-last-word and the last word, so
 * the source badge can be glued to that last word inside one `nowrap` span
 * (the same layout problem `Bullets.tsx`'s `splitLastWord` solves for the
 * "what changed" bullets, and the same fix: without it the badge is free to
 * wrap onto a line of its own, reading as a stray number rather than a
 * footnote marker).
 */
function splitLastWord(text: string): [string, string] {
  const trimmed = text.trimEnd();
  const cut = trimmed.lastIndexOf(' ');
  if (cut === -1) return ['', trimmed];
  return [trimmed.slice(0, cut + 1), trimmed.slice(cut + 1)];
}

function HistoryStrip({history}: {history: IssueHistoryEntry[]}) {
  return (
    <div className="issue-history" aria-hidden="true">
      {history.map((entry, i) => (
        <span key={i} className={`tick tick-${entry.status}`} title={entry.asOf} />
      ))}
    </div>
  );
}

function OpenRow({issue}: {issue: IssueOpen}) {
  const [head, lastWord] = splitLastWord(issue.reasoning);
  return (
    <article className="issue">
      <div className="issue-head">
        <h3 className="issue-title">{issue.title}</h3>
        <div className="issue-meta">
          <span className={`chip ${STATUS_TONE[issue.status]}`}>
            {STATUS_LABEL[issue.status]}
          </span>
          <span className="sep" aria-hidden="true">
            ·
          </span>
          <span className="m">{plainDate(issue.assessedAsOf)}</span>
        </div>
      </div>
      <p className="issue-tenure">
        tracked since {monthYear(issue.trackedSince)} &middot; worsened{' '}
        {issue.worsenedCount} of last {issue.checkCount} checks
      </p>
      <p className="issue-reasoning">
        {head}
        <span className="nowrap-end">
          {lastWord}
          <SourceMark refs={issue.sources} about={issue.title} />
        </span>
      </p>
      <HistoryStrip history={issue.history} />
    </article>
  );
}

function ResolvedRow({issue}: {issue: IssueResolved}) {
  return (
    <li className="issue-resolved-row">
      <span className="issue-title">{issue.title}</span>
      <span className="m">{plainDate(issue.resolvedAsOf)}</span>
      <p>{issue.finalNote}</p>
    </li>
  );
}

export interface IssuesProps {
  issues: IssuesData;
}

export function Issues({issues}: IssuesProps) {
  // F110 review precedent: nothing open AND nothing resolved means no
  // section at all, not an empty heading over nothing.
  if (issues.open.length === 0 && issues.resolved.length === 0) return null;

  return (
    <section className="zone" id="issues">
      <div className="zone-head">
        <h2>Known issues</h2>
      </div>
      {issues.open.length > 0 ? (
        <div className="issues-list">
          {issues.open.map((issue) => (
            <OpenRow issue={issue} key={issue.id} />
          ))}
        </div>
      ) : null}
      {issues.resolved.length > 0 ? (
        <details className="issues-resolved">
          <summary>Resolved</summary>
          <ul>
            {issues.resolved.map((issue) => (
              <ResolvedRow issue={issue} key={issue.id} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
