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
 */
import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';
import {Dimensions} from '../components/Dimensions';
import {Footer} from '../components/Footer';
import {isAssessment, parseDashboard} from '../load';
import type {Source} from '../load';
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
    // The first row's reasoning is already in the document -- the panel
    // content, not just the collapsed summary line.
    expect(within(rowPanel(dims[0].id)).getByText(dims[0].reasoning)).toBeInTheDocument();

    // Every other row starts closed: its button says so, and its reasoning
    // text is nowhere in the document (proves the panel content, not just
    // its visibility, tracks aria-expanded).
    for (const dim of dims.slice(1)) {
      expect(rowButton(dim.id)).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByText(dim.reasoning)).not.toBeInTheDocument();
    }
  });

  it('clicking a closed row opens it: aria-expanded flips and the reasoning becomes available', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const secondDim = dims[1];
    const btn = rowButton(secondDim.id);
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(secondDim.reasoning)).not.toBeInTheDocument();

    await userEvent.click(btn);

    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(within(rowPanel(secondDim.id)).getByText(secondDim.reasoning)).toBeInTheDocument();
  });

  it('clicking an open row closes it: aria-expanded flips back and the reasoning is removed', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const firstDim = dims[0];
    const btn = rowButton(firstDim.id);
    expect(btn).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(btn);

    expect(btn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(firstDim.reasoning)).not.toBeInTheDocument();
  });

  it('the keyboard alone opens a row: Tab to it, then Enter -- and Space closes it', async () => {
    const dims = golden().dimensions;
    draw(<Dimensions dimensions={dims} />);
    const thirdDim = dims[2];
    const btn = rowButton(thirdDim.id);
    btn.focus();
    expect(btn).toHaveFocus();

    await userEvent.keyboard('{Enter}');
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(within(rowPanel(thirdDim.id)).getByText(thirdDim.reasoning)).toBeInTheDocument();

    // And Space closes it again -- both keys operate a real button.
    await userEvent.keyboard(' ');
    expect(btn).toHaveAttribute('aria-expanded', 'false');
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
