import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {beforeEach, describe, expect, it} from 'vitest';
import {parseDashboard} from '../load';
import {Verdict} from '../components/Verdict';
import {SourceMark} from '../components/SourceMark';
import type {Ref} from '../load';
import {readGolden} from './fixtures';

const golden = () => parseDashboard(readGolden());

function draw(ui: React.ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

describe('the verdict zone', () => {
  let data = golden();
  beforeEach(() => {
    data = golden();
  });

  it('makes the answer the single biggest heading on the page', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    const headings = screen.getAllByRole('heading', {level: 1});
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(
      'Getting closer. The challenger had a good quarter.',
    );
  });

  it('asks the question in its own line above the answer', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    const question = screen.getByText('Is supply catching up to demand?');
    const answer = screen.getByRole('heading', {level: 1});
    // The question comes first in reading order.
    expect(
      question.compareDocumentPosition(answer) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows the direction chip and the confidence on one row', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    const chip = screen.getByText('Gap narrowing');
    const confidence = screen.getByText('We are confident in this read');
    expect(chip).toBeInTheDocument();
    expect(confidence).toBeInTheDocument();
    // Same row means the same parent element.
    expect(chip.closest('.vmeta')).not.toBeNull();
    expect(chip.closest('.vmeta')).toBe(confidence.closest('.vmeta'));
  });

  it('spells the direction out in words, never colour alone', () => {
    data.verdict.chip.direction = 'widening';
    data.verdict.chip.label = 'Gap widening';
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    expect(screen.getByText('Gap widening')).toBeInTheDocument();
  });

  it('carries the so-what line', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    expect(
      screen.getByText(/AMD beat its own numbers/, {selector: '.sowhat'}),
    ).toBeInTheDocument();
  });

  it('hides the as-of banner on a fresh reading', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    expect(document.querySelector('.staleban')).toBeNull();
  });

  it('shows the as-of banner when the reading is stale', () => {
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale />);
    const banner = document.querySelector('.staleban')!;
    expect(banner).toHaveAttribute('role', 'status');
    expect(banner).toHaveTextContent('5 August 2026');
    expect(banner).toHaveTextContent(/newer/i);
  });
});

describe('the source mark', () => {
  const published: Ref[] = [
    {
      title: 'AMD reports second quarter 2026 results',
      outlet: 'AMD Investor Relations',
      url: 'https://ir.amd.com/press/q2-2026',
      date: '2026-08-04',
      tier: 'primary',
    },
  ];

  it('keeps the sources out of the way until asked', async () => {
    draw(<SourceMark refs={published} />);
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    // Nothing from the list is reachable before the control is used.
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('opens a real link to the source when clicked', async () => {
    draw(<SourceMark refs={published} />);
    await userEvent.click(screen.getByRole('button'));
    const link = await screen.findByRole('link', {
      name: /AMD reports second quarter 2026 results/,
    });
    expect(link).toHaveAttribute('href', 'https://ir.amd.com/press/q2-2026');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('opens from the keyboard alone', async () => {
    draw(<SourceMark refs={published} />);
    await userEvent.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(
      await screen.findByRole('link', {name: /AMD reports/}),
    ).toBeInTheDocument();
  });

  it('names outlet and date beside each source', async () => {
    draw(<SourceMark refs={published} />);
    await userEvent.click(screen.getByRole('button'));
    expect(
      await screen.findByText(/AMD Investor Relations/),
    ).toBeInTheDocument();
    expect(screen.getByText(/4 August 2026/)).toBeInTheDocument();
  });

  it('marks our own judgement as an assessment and lists what it rests on', async () => {
    const assessed: Ref[] = [{assessment: true, basedOn: published}];
    draw(<SourceMark refs={assessed} />);
    await userEvent.click(screen.getByRole('button'));
    expect(
      await screen.findByText('Our assessment, based on:'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', {name: /AMD reports second quarter 2026/}),
    ).toBeInTheDocument();
  });

  it('does not claim an assessment when the reference is a published fact', async () => {
    draw(<SourceMark refs={published} />);
    await userEvent.click(screen.getByRole('button'));
    await screen.findByRole('link', {name: /AMD reports/});
    expect(screen.queryByText('Our assessment, based on:')).toBeNull();
  });

  it('shows a source with no web address as plain text, not a dead link', async () => {
    const offline: Ref[] = [
      {
        title: 'Quarterly filing, read in print',
        outlet: 'Company filing',
        url: null,
        date: null,
        tier: 'primary',
      },
    ];
    draw(<SourceMark refs={offline} />);
    await userEvent.click(screen.getByRole('button'));
    expect(
      await screen.findByText('Quarterly filing, read in print'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('counts the published sources behind an assessment on the marker', () => {
    const assessed: Ref[] = [
      {assessment: true, basedOn: [...published, ...published, ...published]},
    ];
    draw(<SourceMark refs={assessed} />);
    expect(screen.getByRole('button')).toHaveTextContent('3');
  });

  it('renders nothing at all when there are no sources', () => {
    const {container} = draw(<SourceMark refs={[]} />);
    expect(container.querySelector('button')).toBeNull();
  });
});

describe('the verdict carries its own sources', () => {
  it('puts a source mark on the answer', async () => {
    const data = golden();
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    const mark = screen.getByRole('button', {name: /sources/i});
    await userEvent.click(mark);
    expect(
      await screen.findByText('Our assessment, based on:'),
    ).toBeInTheDocument();
    const link = screen.getByRole('link', {name: /AMD Investor Relations/});
    expect(link).toHaveAttribute('target', '_blank');
  });
});

describe('colouring the answer s opening phrase', () => {
  function answerWith(answer: string, direction = 'widening') {
    const data = golden();
    data.verdict.answer = answer;
    data.verdict.chip.direction = direction as 'narrowing' | 'widening' | 'flat';
    draw(<Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />);
    return screen.getByRole('heading', {level: 1});
  }

  it('sets a genuine short lead apart', () => {
    const h1 = answerWith('Not yet. Buyers are committing faster than the chain can ship.');
    const lead = h1.querySelector('.lead');
    expect(lead).not.toBeNull();
    expect(lead).toHaveTextContent('Not yet.');
    expect(h1).toHaveTextContent(
      'Not yet. Buyers are committing faster than the chain can ship.',
    );
  });

  it('never colours the whole headline when the answer is one sentence', () => {
    const h1 = answerWith('Not yet.');
    expect(h1.querySelector('.lead')).toBeNull();
    expect(h1).toHaveTextContent('Not yet.');
  });

  it('leaves a long opening sentence uncoloured — it is not a lead phrase', () => {
    const long =
      'Supply is still a long way behind what buyers have committed to. The gap is closing.';
    const h1 = answerWith(long);
    expect(h1.querySelector('.lead')).toBeNull();
    expect(h1).toHaveTextContent(long);
  });

  it('copes with an empty answer without colouring anything', () => {
    const h1 = answerWith('');
    expect(h1.querySelector('.lead')).toBeNull();
  });

  it('never lets the lead phrase and the chip disagree', () => {
    // Task 6 makes the opening phrase, the chip and the chart caption come from
    // one computation, so they are guaranteed to agree. This holds the render
    // side to it: the lead's tone is read from the chip's direction and from
    // nowhere else, so the two can never drift apart.
    for (const direction of ['narrowing', 'widening', 'flat'] as const) {
      const data = golden();
      data.verdict.answer = 'Not yet. The gap is still wide.';
      data.verdict.chip.direction = direction;
      const {unmount} = draw(
        <Verdict verdict={data.verdict} asOf={data.asOf} stale={false} />,
      );
      const lead = document.querySelector('h1 .lead')!;
      const chip = document.querySelector('.chip')!;
      const tone = ['good', 'serious', 'flat'].find((t) =>
        lead.classList.contains(t),
      );
      expect(tone, `no tone class for ${direction}`).toBeDefined();
      expect(chip.classList.contains(tone!)).toBe(true);
      unmount();
    }
  });
});

describe('what the source mark says out loud', () => {
  const one: Ref[] = [
    {title: 'A filing', outlet: 'Company', url: null, date: null, tier: null},
  ];

  it('says "1 source", not "1 sources"', () => {
    draw(<SourceMark refs={one} about="the verdict" />);
    expect(screen.getByRole('button')).toHaveAccessibleName(
      'Show the 1 source behind the verdict',
    );
  });

  it('says "sources" when there is more than one', () => {
    draw(<SourceMark refs={[...one, ...one]} about="the verdict" />);
    expect(screen.getByRole('button')).toHaveAccessibleName(
      'Show the 2 sources behind the verdict',
    );
  });

  it('still reads properly with nothing to name it after', () => {
    draw(<SourceMark refs={one} />);
    expect(screen.getByRole('button')).toHaveAccessibleName(
      'Show the 1 source behind this',
    );
  });
});
