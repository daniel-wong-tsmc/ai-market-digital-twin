/**
 * Zone 3 — "what changed": exactly three dated, plain-English bullets
 * condensing the day's story, each paired with either a small supporting
 * chart (`MiniChart`) or, when there is nothing honest to draw, the dashed
 * no-chart panel (`NoChart`) — never both, per the schema's own
 * one-of-chart-or-reason rule (`web/schema/dashboard.schema.json`).
 *
 * Ported from the mock's `.change` rows
 * (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html lines
 * 536-563).
 */
import {MiniChart} from './MiniChart';
import {NoChart} from './NoChart';
import {SourceMark} from './SourceMark';
import {shortDate} from './gapMath';
import type {Bullet} from '../load';

export interface BulletsProps {
  bullets: Bullet[];
}

function BulletRow({bullet}: {bullet: Bullet}) {
  return (
    <div className="change">
      <span className="date">{shortDate(bullet.date)}</span>
      <p>
        {bullet.text}
        <SourceMark refs={bullet.sources} about={bullet.text} />
      </p>
      {bullet.chart ? (
        <MiniChart chart={bullet.chart} />
      ) : (
        <NoChart reason={bullet.noChartReason!.reason} cause={bullet.noChartReason!.cause} />
      )}
    </div>
  );
}

export function Bullets({bullets}: BulletsProps) {
  return (
    <div className="changed">
      {bullets.map((bullet, i) => (
        <BulletRow bullet={bullet} key={`${bullet.date}-${i}`} />
      ))}
    </div>
  );
}
