/**
 * The panel a dimension row slides open: the reasoning on the left, and
 * direction / how-sure-we-are / evidence on the right (mock lines 588-611,
 * `.why-wrap` / `.why` / `.why-body` / `.why-side`).
 *
 * Evidence reuses `SourceMark` -- the one control the rest of the page
 * already uses for "where did that come from?" -- rather than a hand-rolled
 * link list.
 *
 * Panel content stays mounted at all times, so the mock's own
 * `grid-template-rows: 0fr` -> `1fr` transition (app.css `.why-wrap`)
 * animates on BOTH open and close, matching the approved visual contract
 * exactly. What changes when the row is closed is reachability, not
 * presence: the wrapper gets `inert` (removes it from the tab order and the
 * accessibility tree in one step, supported by every evergreen browser) plus
 * `aria-hidden="true"` as a belt-and-braces fallback for assistive
 * technology that predates `inert` support. Without this, the mock's
 * CSS-only collapse (0fr height, `overflow: hidden`, no `hidden`/
 * `aria-hidden`/`display:none`) leaves real evidence links in the tab order
 * and the accessibility tree while they are clipped to zero height on
 * screen -- a keyboard or screen-reader user tabbing through a closed row
 * would land on invisible links. `inert` + `aria-hidden` closes that gap
 * without giving up the mounted-content animation.
 *
 * FINAL REVIEW, Important 5: each of the three blocks is omitted entirely --
 * heading and all -- when it has nothing in it. The exporter deliberately
 * sends an empty reasoning when a dimension's whole rationale is a single
 * sentence (there is honestly nothing to add beyond the row itself), and
 * that used to render as the heading "Why we say that" over blank space,
 * which reads as a broken page rather than an honest silence. Same for an
 * empty confidence line and an empty evidence list.
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
      inert={open ? undefined : true}
      aria-hidden={open ? undefined : true}
    >
      <div className="why">
        {dimension.reasoning ? (
          <div className="why-body">
            <h3>Why we say that</h3>
            <p>{dimension.reasoning}</p>
          </div>
        ) : null}
        <div className="why-side">
          <div className="why-block">
            <span className="k">Direction</span>
            <span className="v">{DIRECTION_PHRASE[dimension.direction]}</span>
          </div>
          {dimension.confidence ? (
            <div className="why-block">
              <span className="k">How sure we are</span>
              <span className="v">{dimension.confidence}</span>
            </div>
          ) : null}
          {dimension.evidence.length > 0 ? (
            <div className="why-block">
              <span className="k">Top evidence</span>
              <SourceMark refs={dimension.evidence} about={dimension.plainName} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
