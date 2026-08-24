/**
 * F124 — the standing independence disclaimer.
 *
 * docs/publishing-posture.md §4 says it appears in the footer of every public
 * page. The app is a single page with three states, so "every page" has to
 * mean every state: someone who lands while it is still loading, or on a page
 * whose reading failed to load, still needs to know whose work this is and
 * whose it is not. The failed state is arguably where it matters most.
 *
 * The wording was approved verbatim with the user on 2026-08-22. It is pinned
 * here character for character on purpose — rewording it is a copy decision
 * that belongs to the user, not a test that can be edited to match.
 */
import {render, screen} from '@testing-library/react';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Disclaimer, DISCLAIMER} from '../components/Disclaimer';
import {Footer} from '../components/Footer';
import {App} from '../App';
import {readGolden} from './fixtures';

const APPROVED =
  "Independent personal project. The analysis here is one individual's own " +
  'work, produced from public sources. It is not affiliated with, endorsed ' +
  'by, or representative of any employer, and it is not investment advice.';

afterEach(() => {
  vi.unstubAllGlobals();
});

function mountApp(fetchImpl: () => Promise<unknown>) {
  vi.stubGlobal('fetch', vi.fn(fetchImpl));
  render(
    <Theme theme={neutralTheme}>
      <App />
    </Theme>,
  );
}

describe('the disclaimer', () => {
  it('says the approved wording, character for character', () => {
    expect(DISCLAIMER).toBe(APPROVED);
  });

  it('renders as words a reader can actually see', () => {
    render(<Disclaimer />);
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is part of the footer', () => {
    render(<Footer links={[{label: 'The story', href: 'story/'}]} />);
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page while the reading is still loading', () => {
    mountApp(() => new Promise(() => {}));
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page when the reading could not be loaded', async () => {
    mountApp(() => Promise.reject(new Error('offline')));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page once the reading has loaded', async () => {
    const payload = readGolden();
    mountApp(async () => ({ok: true, status: 200, json: async () => payload}));
    // Wait for the real footer to arrive, then read it: on the loaded page the
    // disclaimer must be inside the footer, not merely somewhere on the page.
    const footer = await screen.findByRole('contentinfo');
    expect(footer).toHaveTextContent(APPROVED);
  });
});
