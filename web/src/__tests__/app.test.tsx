/** The whole page, composed, against the real committed payload. */
import {render, screen, waitFor} from '@testing-library/react';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {App} from '../App';
import {readGolden} from './fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

function serve(payload: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ok: true, status: 200, json: async () => payload})),
  );
}

describe('the page', () => {
  it('reads the day s file and leads with the verdict', async () => {
    serve(readGolden());
    render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );
    await waitFor(() =>
      expect(screen.getByRole('heading', {level: 1})).toHaveTextContent(
        'Getting closer. The challenger had a good quarter.',
      ),
    );
    expect(screen.getByText(/Merchant GPU/)).toBeInTheDocument();
    expect(
      screen.getByText('Reading for Wednesday 5 August 2026'),
    ).toBeInTheDocument();
  });

  it('says so plainly when the file will not load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ok: false, status: 500, json: async () => ({})})),
    );
    render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/could not be loaded/i);
  });

  it('refuses to render a payload that breaks the contract', async () => {
    const broken = readGolden();
    (broken.verdict as {chip: {direction: string}}).chip.direction = 'sideways';
    serve(broken);
    render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/direction/);
    expect(screen.queryByRole('heading', {level: 1})).toBeNull();
  });
});
