/**
 * The accessible alternative to the gap chart's SVG: a plain table with the
 * real value behind every point, tucked under a "Show the numbers" disclosure
 * so it never crowds the chart for a sighted reader who does not need it.
 */
import {plainDate} from '../load';
import type {GapPoint} from '../load';
import {formatSigned} from './gapMath';

export interface NumbersTableProps {
  points: GapPoint[];
}

export function NumbersTable({points}: NumbersTableProps) {
  return (
    <details className="numbers">
      <summary>Show the numbers</summary>
      <table>
        <thead>
          <tr>
            <th>Reading</th>
            <th>Demand</th>
            <th>Supply</th>
            <th>Gap</th>
          </tr>
        </thead>
        <tbody>
          {/*
            A whole-month reading is dated the 1st of its month, so a reading
            taken on the 1st shares that date. The row's position is what is
            unique about it, not the date it shows.
          */}
          {points.map((p, i) => (
            <tr key={`${p.date}-${i}`}>
              <td>{plainDate(p.date)}</td>
              <td>{formatSigned(p.demand)}</td>
              <td>{formatSigned(p.supply)}</td>
              <td>{formatSigned(p.demand - p.supply)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
