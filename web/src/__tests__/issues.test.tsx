/**
 * Zone 6 — "Known issues": the constraints and weak-and-worsening dimensions
 * we are still tracking, plus a quiet collapsed record of the ones that have
 * since cleared.
 *
 * F110 review precedent, carried into F115: if there is nothing open and
 * nothing resolved, the whole section — heading included — must not appear.
 * An empty heading over nothing reads as a broken page, not as honest
 * silence, so `readGolden()` (whose committed `issues` are `{open: [],
 * resolved: []}` today) is the exact case that precedent guards, and it is
 * exercised here as-is rather than only through a hand-built empty payload.
 */
import {render, screen, within} from '@testing-library/react';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {Issues} from '../components/Issues';
import {parseDashboard} from '../load';
import type {Issues as IssuesData, IssueHistoryEntry} from '../load';
import {readGolden} from './fixtures';

function draw(ui: React.ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

/** The `.issue` row that carries this title, as an `HTMLElement` --
 *  `Element.closest` is typed to return plain `Element`, which `within()`
 *  and `toHaveClass`/`toHaveAttribute` don't accept. */
function issueRow(title: string): HTMLElement {
  return screen.getByText(title).closest('.issue') as HTMLElement;
}

/** 15 history entries cycling through all four statuses, oldest first, so a
 *  single issue's strip alone proves every tick class renders. */
function makeHistory(): IssueHistoryEntry[] {
  const statuses: IssueHistoryEntry['status'][] = [
    'improved',
    'worsened',
    'unchanged',
    'not-assessed',
  ];
  return Array.from({length: 15}, (_, i) => ({
    asOf: `2026-0${(i % 9) + 1}-0${(i % 8) + 1}`,
    status: statuses[i % statuses.length],
  }));
}

const OPEN_ASSESSED: IssuesData['open'][number] = {
  id: 'hbm-allocation',
  title: 'HBM allocation still binds Q3 output',
  status: 'worsened',
  assessedAsOf: '2026-08-05',
  // Production shape: `trackedSince` carries the scorecard's own `asOf`,
  // which is always month-only ("2026-08"), never a full date.
  trackedSince: '2026-05',
  worsenedCount: 6,
  checkCount: 15,
  reasoning:
    'Packaging capacity remains the tightest link, and three vendors pushed delivery dates back this cycle.',
  sources: [
    {title: 'HBM supply note', outlet: 'TrendForce', url: 'https://example.com/hbm', date: '2026-08-04', tier: 'primary'},
  ],
  history: makeHistory(),
};

const OPEN_NOT_ASSESSED: IssuesData['open'][number] = {
  id: 'foundry-yield',
  title: 'Advanced node yield below plan',
  status: 'not-assessed',
  assessedAsOf: '2026-08-05',
  trackedSince: '2026-06',
  worsenedCount: 2,
  checkCount: 9,
  reasoning: 'No fresh public data was published on this since the last cycle.',
  sources: [],
  history: makeHistory().slice(0, 9),
};

const RESOLVED_ONE: IssuesData['resolved'][number] = {
  id: 'export-licensing',
  title: 'Export licensing delays',
  resolvedAsOf: '2026-07-20',
  finalNote: 'Three straight checks showed licensing turnaround back under two weeks.',
};

const FULL: IssuesData = {
  open: [OPEN_ASSESSED, OPEN_NOT_ASSESSED],
  resolved: [RESOLVED_ONE],
};

describe('known issues: nothing to say renders nothing at all', () => {
  it('renders no "Known issues" heading (or anything else) when open and resolved are both empty', () => {
    const {issues} = parseDashboard(readGolden());
    expect(issues.open).toHaveLength(0);
    expect(issues.resolved).toHaveLength(0);
    draw(<Issues issues={issues} />);
    expect(screen.queryByText('Known issues')).toBeNull();
    expect(document.querySelector('.zone#issues')).toBeNull();
    expect(document.querySelector('.issue')).toBeNull();
    expect(document.querySelector('details')).toBeNull();
  });
});

describe('known issues: open rows', () => {
  it('renders the heading and one row per open issue, with its title', () => {
    draw(<Issues issues={FULL} />);
    expect(screen.getByText('Known issues')).toBeInTheDocument();
    expect(screen.getByText(OPEN_ASSESSED.title)).toBeInTheDocument();
    expect(screen.getByText(OPEN_NOT_ASSESSED.title)).toBeInTheDocument();
  });

  it('shows the assessed status chip, dated', () => {
    draw(<Issues issues={FULL} />);
    const row = issueRow(OPEN_ASSESSED.title);
    expect(within(row).getByText('Worsened')).toBeInTheDocument();
    expect(within(row).getByText('5 August 2026')).toBeInTheDocument();
  });

  it('shows the not-assessed chip with the exact muted text, never a fresh-looking chip', () => {
    draw(<Issues issues={FULL} />);
    const chip = screen.getByText('Not assessed this cycle');
    expect(chip).toBeInTheDocument();
    expect(chip.className).toMatch(/\bmuted\b/);
    // Not any of the "fresh" tones a real assessment gets.
    expect(chip.className).not.toMatch(/\b(good|serious|flat)\b/);
  });

  it('renders the exact tenure line from a production-shaped month-only trackedSince', () => {
    draw(<Issues issues={FULL} />);
    expect(
      screen.getByText('tracked since May 2026 · worsened 6 of last 15 checks'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('tracked since Jun 2026 · worsened 2 of last 9 checks'),
    ).toBeInTheDocument();
  });

  it('also accepts a full YYYY-MM-DD trackedSince (back-compat, not the production shape)', () => {
    const fullDateIssue: IssuesData['open'][number] = {
      ...OPEN_ASSESSED,
      id: 'full-date-issue',
      title: 'Full date tenure issue',
      trackedSince: '2026-05-01',
    };
    draw(<Issues issues={{open: [fullDateIssue], resolved: []}} />);
    expect(
      screen.getByText('tracked since May 2026 · worsened 6 of last 15 checks'),
    ).toBeInTheDocument();
  });

  it('renders the reasoning text with a source badge inline at the end', () => {
    draw(<Issues issues={FULL} />);
    const row = issueRow(OPEN_ASSESSED.title);
    expect(within(row).getByText(/Packaging capacity remains the tightest link/)).toBeInTheDocument();
    expect(within(row).getByRole('button', {name: /source/i})).toBeInTheDocument();
  });

  it('does not render a source badge when an issue carries no sources', () => {
    draw(<Issues issues={FULL} />);
    const row = issueRow(OPEN_NOT_ASSESSED.title);
    expect(within(row).queryByRole('button', {name: /source/i})).toBeNull();
  });

  it('renders one tick per history entry, each with a per-status class and the date in its title', () => {
    draw(<Issues issues={FULL} />);
    const row = issueRow(OPEN_ASSESSED.title);
    const ticks = row.querySelectorAll('.tick');
    expect(ticks).toHaveLength(15);
    OPEN_ASSESSED.history.forEach((entry, i) => {
      expect(ticks[i]).toHaveClass(`tick-${entry.status}`);
      expect(ticks[i]).toHaveAttribute('title', entry.asOf);
    });
  });

  it('exercises all four tick status classes across the row', () => {
    draw(<Issues issues={FULL} />);
    const row = issueRow(OPEN_ASSESSED.title);
    for (const cls of ['tick-improved', 'tick-worsened', 'tick-unchanged', 'tick-not-assessed']) {
      expect(row.querySelectorAll(`.${cls}`).length).toBeGreaterThan(0);
    }
  });
});

describe('known issues: resolved', () => {
  it('renders a collapsed <details> block titled "Resolved" listing title, close date, and final note', () => {
    draw(<Issues issues={FULL} />);
    const details = screen.getByText('Resolved').closest('details') as HTMLElement;
    expect(details).toBeInTheDocument();
    expect(details).not.toHaveAttribute('open');
    expect(within(details).getByText(RESOLVED_ONE.title)).toBeInTheDocument();
    expect(within(details).getByText('20 July 2026')).toBeInTheDocument();
    expect(within(details).getByText(RESOLVED_ONE.finalNote)).toBeInTheDocument();
  });

  it('renders no resolved <details> block when there are no resolved issues', () => {
    draw(<Issues issues={{open: [OPEN_ASSESSED], resolved: []}} />);
    expect(screen.queryByText('Resolved')).toBeNull();
    expect(document.querySelector('details')).toBeNull();
  });

  it('still renders the heading when open is empty but resolved is not', () => {
    draw(<Issues issues={{open: [], resolved: [RESOLVED_ONE]}} />);
    expect(screen.getByText('Known issues')).toBeInTheDocument();
    expect(screen.getByText('Resolved')).toBeInTheDocument();
  });
});
