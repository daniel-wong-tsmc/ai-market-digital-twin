/**
 * The one control the whole page uses to answer "where did that come from?".
 *
 * A small superscript marker sits after a statement. It is a real button, so it
 * works from the keyboard and reads out to screen readers. Pressing it opens
 * Astryx's Popover, which lists each source with its outlet and date. Every web
 * address opens in a new tab; a source with no web address is shown as plain
 * text rather than a link that goes nowhere.
 *
 * A reference is one of two things, and the difference matters: a published
 * fact we can point at, or our own judgement — which says so, and then lists
 * the published facts it rests on.
 */
import {Popover} from '@astryxdesign/core/Popover';
import {Link} from '@astryxdesign/core/Link';
import {countSources, isAssessment, plainDate} from '../load';
import type {Ref, Source} from '../load';

function SourceLine({source}: {source: Source}) {
  const when = plainDate(source.date);
  // The exporter often repeats the outlet as the title; say it once.
  const outlet = source.outlet && source.outlet !== source.title ? source.outlet : null;
  const trail = [outlet, when].filter(Boolean).join(' · ');
  return (
    <li className="srcline">
      {source.url ? (
        <Link href={source.url} isExternalLink className="srclink">
          {source.title}
        </Link>
      ) : (
        <span className="srclink">{source.title}</span>
      )}
      {trail ? <span className="srcmeta">{trail}</span> : null}
    </li>
  );
}

function RefLines({refs}: {refs: Ref[]}) {
  return (
    <>
      {refs.map((ref, i) =>
        isAssessment(ref) ? (
          <li className="srcjudgement" key={i}>
            <p className="srcjudgement-head">Our assessment, based on:</p>
            <ul className="srclist">
              <RefLines refs={ref.basedOn} />
            </ul>
          </li>
        ) : (
          <SourceLine source={ref} key={i} />
        ),
      )}
    </>
  );
}

export interface SourceMarkProps {
  refs: Ref[];
  /** Names the statement in the button's label, e.g. "the verdict". */
  about?: string;
}

export function SourceMark({refs, about}: SourceMarkProps) {
  if (refs.length === 0) return null;
  const count = countSources(refs);
  const thing = count === 1 ? 'source' : 'sources';
  const label = `Show the ${count} ${thing} behind ${about ?? 'this'}`;

  return (
    <Popover
      label="Where this comes from"
      placement="below"
      alignment="start"
      width={340}
      className="srcpop"
      content={
        <div className="srcpop-body">
          <p className="srcpop-head">Where this comes from</p>
          <ul className="srclist">
            <RefLines refs={refs} />
          </ul>
        </div>
      }
    >
      <sup className="srcmark-wrap">
        <button type="button" className="srcmark" aria-label={label}>
          {count}
        </button>
      </sup>
    </Popover>
  );
}
