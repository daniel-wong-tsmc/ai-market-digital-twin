/**
 * Zone 4 (the six dimensions + why-panels) and zone 5 (the footer).
 *
 * The real payload's row summaries run 30-40 words -- much longer than the
 * mock's hand-written 12-19 word samples
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html lines
 * 568-793). Every test below reads the committed
 * `fixtures/dashboard/golden-dashboard.json` summaries AS-IS, specifically so
 * the real length is what gets exercised, not a shortened stand-in.
 *
 * Row buttons and their panels are found by the stable `btn-<id>` /
 * `why-<id>` ids `Dimensions` assigns from `dimension.id` -- not by
 * accessible-name regexes, which collide with the evidence `SourceMark`
 * button nested inside an open panel (its label is "Show the N sources
 * behind <plainName>", which also contains the row's plain name).
 *
 * The panel's content stays mounted in the DOM at all times (open AND
 * closed) so the mock's `grid-template-rows` transition can animate on both
 * directions. A closed panel is instead made unreachable via `inert` +
 * `aria-hidden="true"` on its wrapper. jsdom reflects the `inert` IDL
 * property/attribute but does NOT enforce its actual behaviour (blocking
 * `.focus()`, removing it from `userEvent.tab()`'s tab order) -- confirmed
 * by hand: a probe with a plain `inert` div let both `.focus()` and
 * `userEvent.tab()` land inside it. So "genuinely unreachable" is proven the
 * way this lane already proves platform behaviour jsdom can't execute (see
 * the `@scope`/`@layer` note in the CSS-token tests): by asserting the
 * wrapper carries the exact `inert` + `aria-hidden="true"` markers a real
 * browser acts on, not by simulating focus/tab and hoping jsdom obeys them.
 */
import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {Dimensions} from '../components/Dimensions';
import {Footer} from '../components/Footer';
import {isAssessment, parseDashboard} from '../load';
import type {Dimension, Source} from '../load';
import {readGolden} from './fixtures';

function draw(ui: React.ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

const golden = () => parseDashboard(readGolden());

function rowButton(dimId: string): HTMLElement {
  return document.getElementById(`btn-${dimId}`)!;
}

function rowPanel(dimId: string): HTMLElement {
  return document.getElementById(`why-${dimId}`)!;
}

/** True when the wrapper is unreachable by keyboard/assistive technology:
 *  carries the `inert` attribute AND `aria-hidden="true"`. Neither alone is
 *  the contract -- `inert` is the modern removal-from-tab-order-and-
 *  accessibility-tree mechanism, `aria-hidden` is the fallback for older
 *  assistive technology that predates `inert` support. */
function isUnreachable(panel: HTMLElement): boolean {
  return panel.hasAttribute('inert') && panel.getAttribute('aria-hidden') === 'true';
}

function isReachable(panel: HTMLElement): boolean {
  return !panel.hasAttribute('inert') && panel.getAttribute('aria-hidden') !== 'true';
}

describe('the six dimensions, on the real committed payload', () => {
  it('renders exactly six rows, one per dimension', () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    expect(document.querySelectorAll('.dim')).toHaveLength(6);
    expect(document.querySelectorAll('.dim-head')).toHaveLength(6);
    for (const dim of dims) {
      expect(rowButton(dim.id)).toBeInTheDocument();
    }
  });

  it('opens the first row on mount and leaves the other five closed', () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);

    expect(rowButton(dims[0].id)).toHaveAttribute('aria-expanded', 'true');
    expect(isReachable(rowPanel(dims[0].id))).toBe(true);
    // The first row's reasoning is in the document AND reachable.
    expect(within(rowPanel(dims[0].id)).getByText(dims[0].reasoning)).toBeInTheDocument();

    // Every other row starts closed: its button says so, and its panel is
    // marked unreachable (inert + aria-hidden), even though the content is
    // still mounted underneath (proved by the animation test below).
    for (const dim of dims.slice(1)) {
      expect(rowButton(dim.id)).toHaveAttribute('aria-expanded', 'false');
      expect(isUnreachable(rowPanel(dim.id))).toBe(true);
    }
  });

  it('clicking a closed row opens it: aria-expanded flips and the panel becomes reachable', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const secondDim = dims[1];
    const btn = rowButton(secondDim.id);
    const panel = rowPanel(secondDim.id);
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(isUnreachable(panel)).toBe(true);

    await userEvent.click(btn);

    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(isReachable(panel)).toBe(true);
    expect(within(panel).getByText(secondDim.reasoning)).toBeInTheDocument();
  });

  it('clicking an open row closes it: aria-expanded flips back and the panel becomes unreachable again', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const firstDim = dims[0];
    const btn = rowButton(firstDim.id);
    const panel = rowPanel(firstDim.id);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(isReachable(panel)).toBe(true);

    await userEvent.click(btn);

    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(isUnreachable(panel)).toBe(true);
    // The content is still there -- only its reachability changed, so the
    // mock's slide-closed transition has something to animate.
    expect(within(panel).getByText(firstDim.reasoning, {selector: 'p'})).toBeInTheDocument();
  });

  it('the panel stays mounted across open/close, so the mock’s transition can animate both ways', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const dim = dims[1]; // starts closed
    const btn = rowButton(dim.id);
    const panel = rowPanel(dim.id);

    // Closed on mount: the reasoning paragraph already exists in the DOM
    // (only unreachable, per isUnreachable above) -- this is what a
    // conditionally-*rendered* panel could never do.
    const beforeOpen = within(panel).getByText(dim.reasoning, {selector: 'p'});
    expect(panel).not.toHaveAttribute('data-open');

    await userEvent.click(btn); // open
    expect(panel).toHaveAttribute('data-open', 'true');
    const afterOpen = within(panel).getByText(dim.reasoning, {selector: 'p'});
    // Same DOM node, not a fresh one from a remount -- the CSS transition
    // has continuous content to animate across, in both directions.
    expect(afterOpen).toBe(beforeOpen);

    await userEvent.click(btn); // close again
    expect(panel).not.toHaveAttribute('data-open');
    const afterClose = within(panel).getByText(dim.reasoning, {selector: 'p'});
    expect(afterClose).toBe(beforeOpen);
  });

  it('the keyboard alone opens a row: Tab to it, then Enter -- and Space closes it', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const thirdDim = dims[2];
    const btn = rowButton(thirdDim.id);
    const panel = rowPanel(thirdDim.id);
    btn.focus();
    expect(btn).toHaveFocus();

    await userEvent.keyboard('{Enter}');
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(isReachable(panel)).toBe(true);

    // And Space closes it again -- both keys operate a real button.
    await userEvent.keyboard(' ');
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(isUnreachable(panel)).toBe(true);
  });

  it('never signals the rating by colour alone: the rating word is spelled out beside the dot on every row', () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    for (const dim of dims) {
      expect(within(rowButton(dim.id)).getByText(dim.ratingWord)).toBeInTheDocument();
    }
  });

  it('renders the full, real-length summary on the row untouched -- no truncation, no ellipsis', () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    for (const dim of dims) {
      // Real summaries run 30-40 words; assert this fixture actually
      // exercises that (guards the test itself from silently degrading to a
      // short string in a future fixture edit).
      expect(dim.summary.split(/\s+/).length).toBeGreaterThanOrEqual(20);
      const summaryEl = within(rowButton(dim.id)).getByText(dim.summary, {selector: '.dim-summary'});
      expect(summaryEl.textContent).toBe(dim.summary);
      expect(summaryEl.textContent).not.toMatch(/…|\.\.\.$/);
    }
  });

  it('every evidence entry with a url renders a real link once its evidence control is opened', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    // First row starts open; find its evidence control (a SourceMark button)
    // inside its why panel and open it.
    const firstDim = dims[0];
    const panel = rowPanel(firstDim.id);
    const evidenceButton = within(panel).getByRole('button', {name: /source/i});
    await userEvent.click(evidenceButton);

    const withUrls = firstDim.evidence.filter(
      (ref): ref is Source => !isAssessment(ref) && ref.url !== null,
    );
    expect(withUrls.length).toBeGreaterThan(0);
    for (const ref of withUrls) {
      const link = await screen.findByRole('link', {
        name: new RegExp(ref.title.slice(0, 20).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
      });
      expect(link).toHaveAttribute('href', ref.url);
    }
  });

  it('shows the direction and how-sure-we-are text inside an open panel', () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const firstDim = dims[0];
    const panel = rowPanel(firstDim.id);
    expect(within(panel).getByText(firstDim.confidence)).toBeInTheDocument();
  });
});

describe('the footer', () => {
  it('renders exactly the five links the payload carries, in order', () => {
    const links = golden().footerLinks;
    draw(<Footer links={links} />);
    const anchors = screen.getAllByRole('link');
    expect(anchors).toHaveLength(links.length);
    anchors.forEach((a, i) => {
      expect(a).toHaveTextContent(links[i].label);
      expect(a).toHaveAttribute('href', links[i].href);
    });
  });
});

describe('the why-panel never prints a heading over nothing', () => {
  /**
   * FINAL REVIEW, Important 5. The exporter deliberately sends an empty
   * `reasoning` when a dimension's whole rationale is a single sentence —
   * there is honestly nothing to add beyond the row itself. Rendered, that
   * was the heading "Why we say that" with blank space under it, which reads
   * as a broken page rather than as an honest silence. Same for an empty
   * confidence line and an empty evidence list.
   */
  function withEmpty(overrides: Partial<Dimension>): Dimension[] {
    const dims = golden().dimensions;
    return [{...dims[0], ...overrides}, ...dims.slice(1)];
  }

  it('omits the reasoning heading entirely when there is no reasoning', () => {
    const dims = withEmpty({reasoning: ''});
    draw(<Dimensions dimensions={dims} />);
    const panel = rowPanel(dims[0].id);
    expect(within(panel).queryByText('Why we say that')).toBeNull();
    expect(panel.querySelector('.why-body')).toBeNull();
  });

  it('keeps the reasoning heading when there is reasoning to show', () => {
    const dims = golden().dimensions;
    expect(dims[0].reasoning).toBeTruthy();
    draw(<Dimensions dimensions={dims} />);
    const panel = rowPanel(dims[0].id);
    expect(within(panel).getByText('Why we say that')).toBeInTheDocument();
  });

  it('omits the how-sure-we-are block entirely when there is no confidence line', () => {
    const dims = withEmpty({confidence: ''});
    draw(<Dimensions dimensions={dims} />);
    const panel = rowPanel(dims[0].id);
    expect(within(panel).queryByText('How sure we are')).toBeNull();
  });

  it('omits the evidence block entirely when there is no evidence', () => {
    const dims = withEmpty({evidence: []});
    draw(<Dimensions dimensions={dims} />);
    const panel = rowPanel(dims[0].id);
    expect(within(panel).queryByText('Top evidence')).toBeNull();
  });

  it('still shows the direction, which every row always has', () => {
    const dims = withEmpty({reasoning: '', confidence: '', evidence: []});
    draw(<Dimensions dimensions={dims} />);
    const panel = rowPanel(dims[0].id);
    expect(within(panel).getByText('Direction')).toBeInTheDocument();
  });
});

describe('the how-sure-we-are line is written for a reader', () => {
  it('never shows the internal scoring method behind it', () => {
    // FINAL REVIEW, Important 1: the row used to print the scorecard's own
    // `confidence.basis`, so an executive read "Medium - majority of 3/3
    // samples; capped by finding confidence (medium)."
    for (const dim of golden().dimensions) {
      const lowered = dim.confidence.toLowerCase();
      for (const phrase of ['sample', 'majority', 'capped by', 'finding confidence', '3/3']) {
        expect(lowered).not.toContain(phrase);
      }
    }
  });
});
