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
          {points.map((p) => (
            <tr key={p.date}>
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
