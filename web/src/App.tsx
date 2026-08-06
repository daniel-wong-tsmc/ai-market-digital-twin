/**
 * The page. It reads one file, checks it, and renders the zones in order.
 */
import {useEffect, useState} from 'react';
import {Verdict} from './components/Verdict';
import {GapChart} from './components/GapChart';
import {Bullets} from './components/Bullets';
import {Dimensions} from './components/Dimensions';
import {Footer} from './components/Footer';
import {loadDashboard, plainDate, plainDateWithWeekday} from './load';
import type {Dashboard} from './load';

/** Words that are said letter by letter, so they stay in capitals. */
const SPELLED_OUT = new Set(['gpu', 'cpu', 'ai']);

/**
 * "chips.merchant-gpu" reads as "Merchant GPU · chips" — the same wording the
 * rest of the site already uses. Derived from the id rather than written in by
 * hand, so a second category needs no code change.
 */
export function mastheadName(categoryId: string): {name: string; group: string} {
  const [group = '', slug = ''] = categoryId.split('.');
  const name = slug
    .split('-')
    .map((word) =>
      SPELLED_OUT.has(word)
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join(' ');
  return {name, group};
}

type State =
  | {status: 'loading'}
  | {status: 'ready'; data: Dashboard; stale: boolean}
  | {status: 'failed'; message: string};

export function App() {
  const [state, setState] = useState<State>({status: 'loading'});

  useEffect(() => {
    let live = true;
    loadDashboard()
      .then(({data, stale}) => {
        if (live) setState({status: 'ready', data, stale});
      })
      .catch((error: unknown) => {
        if (live) {
          setState({
            status: 'failed',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      live = false;
    };
  }, []);

  if (state.status === 'loading') {
    return (
      <div className="shell">
        <p className="loading">Loading today&rsquo;s reading&hellip;</p>
      </div>
    );
  }

  if (state.status === 'failed') {
    return (
      <div className="shell">
        <p className="loadfail" role="alert">
          Today&rsquo;s reading could not be loaded. {state.message}
        </p>
      </div>
    );
  }

  const {data, stale} = state;
  const {name, group} = mastheadName(data.categoryId);

  return (
    <div className="shell">
      <header className="mast">
        <div className="who">
          {name} <span>&middot; {group}</span>
        </div>
        <div className="when">Reading for {plainDateWithWeekday(data.asOf)}</div>
      </header>

      <Verdict verdict={data.verdict} asOf={data.asOf} stale={stale} />

      <section className="zone" id="gap">
        <div className="zone-head">
          <h2>The gap</h2>
          <span className="note">
            Every reading since {plainDate(data.gapChart.points[0]?.date ?? null)}
          </span>
        </div>
        <GapChart data={data.gapChart} />
      </section>

      <section className="zone" id="changed">
        <div className="zone-head">
          <h2>What changed</h2>
          <span className="note">Three things worth two minutes</span>
        </div>
        <Bullets bullets={data.bullets} />
        {data.bullets[0] ? (
          <a className="readmore" href={data.bullets[0].storyHref}>
            Read the full story &rarr;
          </a>
        ) : null}
      </section>

      <section className="zone" id="dimensions">
        <div className="zone-head">
          <h2>The six things we track</h2>
          <span className="note">
            Green healthy &middot; amber mixed &middot; red strained. Open a row to see why.
          </span>
        </div>
        <Dimensions dimensions={data.dimensions} />
      </section>

      <Footer links={data.footerLinks} />
    </div>
  );
}
