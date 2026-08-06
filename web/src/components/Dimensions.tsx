/**
 * Zone 4 -- the six things we track. Six rows, each a real `<button>` that
 * slides open a why-panel (`WhyPanel`). The first row starts open (mock
 * lines 568-793,
 * docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html).
 *
 * A REAL CONSTRAINT THIS FILE IS BUILT AROUND: the mock's own row summaries
 * are hand-written at 12-19 words. The real payload's summaries run 30-40
 * words -- see `fixtures/dashboard/golden-dashboard.json` -- because an
 * earlier task chose a complete honest sentence over a truncated fragment
 * that would misstate the finding. `.dim-summary` below carries no
 * line-clamp, `text-overflow`, or JS truncation: it just wraps to two or
 * three lines. Cutting it here would reintroduce exactly the defect that was
 * fixed upstream.
 */
import {useState} from 'react';
import {WhyPanel, DIRECTION_PHRASE} from './WhyPanel';
import type {Dimension} from '../load';

/** The dot's colour class. Never the only signal -- the rating word is
 *  always spelled out in text right next to it, on every row. */
const TONE: Record<Dimension['tone'], string> = {
  good: 'good',
  mixed: 'warning',
  bad: 'serious',
};

function ChevronIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        d="M4 6.5 8 10.5 12 6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DimRow({dimension, defaultOpen}: {dimension: Dimension; defaultOpen: boolean}) {
  const [open, setOpen] = useState(defaultOpen);
  const btnId = `btn-${dimension.id}`;
  const panelId = `why-${dimension.id}`;

  return (
    <div className="dim">
      <button
        className="dim-head"
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        id={btnId}
        onClick={() => setOpen((was) => !was)}
      >
        <span className={`light ${TONE[dimension.tone]}`} aria-hidden="true" />
        <span className="dim-main">
          <span className="dim-label">{dimension.plainName}</span>
          <span className="dim-summary">{dimension.summary}</span>
        </span>
        <span className="dim-rating">
          {dimension.ratingWord}
          <span className="dim-dirn">{DIRECTION_PHRASE[dimension.direction]}</span>
        </span>
        <span className="chev" aria-hidden="true">
          <ChevronIcon />
        </span>
      </button>
      <WhyPanel dimension={dimension} id={panelId} btnId={btnId} open={open} />
    </div>
  );
}

export interface DimensionsProps {
  dimensions: Dimension[];
}

export function Dimensions({dimensions}: DimensionsProps) {
  return (
    <div className="dims">
      {dimensions.map((dimension, i) => (
        <DimRow dimension={dimension} defaultOpen={i === 0} key={dimension.id} />
      ))}
    </div>
  );
}
