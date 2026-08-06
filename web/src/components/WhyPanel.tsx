/**
 * The panel a dimension row slides open: the reasoning on the left, and
 * direction / how-sure-we-are / evidence on the right (mock lines 588-611,
 * `.why-wrap` / `.why` / `.why-body` / `.why-side`).
 *
 * Evidence reuses `SourceMark` -- the one control the rest of the page
 * already uses for "where did that come from?" -- rather than a hand-rolled
 * link list.
 *
 * Panel content is only mounted into the DOM while `open` is true. The
 * mock's own CSS-only technique (`grid-template-rows: 0fr`) keeps the
 * collapsed content in the DOM at zero visual height, which is not actually
 * hidden from assistive technology -- a screen reader can still land on
 * text nobody can see. Removing it from the DOM when closed is what makes
 * "collapsed" mean the same thing visually and to assistive technology.
 */
import {SourceMark} from './SourceMark';
import type {Dimension} from '../load';

/** The mock spells the direction out in words in two places on a row: here,
 *  and again next to the rating word. Both read from this one map so they
 *  can never say different things. */
export const DIRECTION_PHRASE: Record<Dimension['direction'], string> = {
  improving: 'Getting stronger',
  worsening: 'Moving the wrong way',
  flat: 'No better, no worse',
};

export interface WhyPanelProps {
  dimension: Dimension;
  /** id placed on the sliding wrapper; the row button's `aria-controls` points here. */
  id: string;
  /** id of the row button that labels this region. */
  btnId: string;
  open: boolean;
}

export function WhyPanel({dimension, id, btnId, open}: WhyPanelProps) {
  return (
    <div
      className="why-wrap"
      id={id}
      role="region"
      aria-labelledby={btnId}
      data-open={open || undefined}
    >
      {open ? (
        <div className="why">
          <div className="why-body">
            <h3>Why we say that</h3>
            <p>{dimension.reasoning}</p>
          </div>
          <div className="why-side">
            <div className="why-block">
              <span className="k">Direction</span>
              <span className="v">{DIRECTION_PHRASE[dimension.direction]}</span>
            </div>
            <div className="why-block">
              <span className="k">How sure we are</span>
              <span className="v">{dimension.confidence}</span>
            </div>
            <div className="why-block">
              <span className="k">Top evidence</span>
              <SourceMark refs={dimension.evidence} about={dimension.plainName} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
