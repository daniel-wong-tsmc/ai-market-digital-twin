/**
 * F124 — the standing independence disclaimer, docs/publishing-posture.md §4.
 *
 * The wording is APPROVED VERBATIM by the user, interactive, 2026-08-22. Do not
 * reword it, re-punctuate it, or "tidy" it: it is the line that keeps a public
 * market view from reading as an employer's.
 *
 * The static site builder holds the same sentence in
 * `gpu_agent/dashboard/site_render.py`. The two exist separately because the
 * builder and this app share no runtime and the dashboard payload may not grow
 * a field to carry copy. `src/__tests__/copy-pins.test.ts` reads that Python
 * file and fails if the two ever drift apart.
 */
export const DISCLAIMER =
  "Independent personal project. The analysis here is one individual's own " +
  'work, produced from public sources. It is not affiliated with, endorsed ' +
  'by, or representative of any employer, and it is not investment advice.';

export function Disclaimer() {
  return <p className="disclaimer">{DISCLAIMER}</p>;
}
