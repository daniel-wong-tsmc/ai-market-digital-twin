# F124 footer disclaimer — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the approved independence disclaimer in the footer of every page the site builder emits and every state of the React app.

**Architecture:** One `DISCLAIMER` literal per language. On the Python side it goes into `page()`, the single HTML shell every builder page already funnels through, so all 50+ emitted pages and every future page get it from one edit. On the TypeScript side a small `<Disclaimer/>` component is rendered by `Footer` and by the app's loading and failure shells, and the same sentence is added to the no-scripting fallback. A cross-language test reads the Python source and pins the TypeScript constant to it so the two copies cannot drift.

**Tech Stack:** Python 3 (pytest), React 18 + TypeScript + Vite (vitest, @testing-library/react).

**Spec:** `docs/superpowers/specs/2026-08-24-f124-footer-disclaimer-design.md`

## Global Constraints

- The disclaimer text is APPROVED VERBATIM. Exactly, in plain ASCII: `Independent personal project. The analysis here is one individual's own work, produced from public sources. It is not affiliated with, endorsed by, or representative of any employer, and it is not investment advice.`
- No dashboard schema change. The text never enters `dashboard.json` or `web/schema/dashboard.schema.json`.
- No protected pin may move: F6 evals baseline (`tests/test_evals_baseline_pin.py`), narrator prompt pin, F83 run-cycle fingerprint, scoring replay pin.
- Do NOT regenerate `site/`. The root store is mid-cycle; the committed built pages stay as they are.
- Python tests run from the worktree root as `../../.venv/Scripts/python -m pytest -q`. Never create a venv.
- Web tests: `npm --prefix web test`. Build: `npm --prefix web run build`.
- Stage files explicitly by name. Never `git add -A`. Run `git log --oneline -1` immediately before every commit.

---

### Task 1: The disclaimer in the static page shell

**Files:**
- Modify: `gpu_agent/dashboard/site_render.py` (add `DISCLAIMER`, `_DISCLAIMER_HTML`, extend `SITE_CSS`, extend `page()`)
- Test: `tests/dashboard/test_site_render.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `gpu_agent.dashboard.site_render.DISCLAIMER: str` — the approved sentence, plain text, no markup. Task 4 reads this literal out of the source file.

- [ ] **Step 1: Write the failing tests**

Append to `tests/dashboard/test_site_render.py`:

```python
from gpu_agent.dashboard.site_render import DISCLAIMER

APPROVED = (
    "Independent personal project. The analysis here is one individual's own "
    "work, produced from public sources. It is not affiliated with, endorsed "
    "by, or representative of any employer, and it is not investment advice."
)


def test_disclaimer_is_the_approved_wording_character_for_character():
    # docs/publishing-posture.md section 4, decided 2026-08-22. Approved
    # verbatim: changing a character here is changing approved copy.
    assert DISCLAIMER == APPROVED


def test_every_shell_page_carries_the_disclaimer_in_its_footer():
    html = page("Any page", "<p>body</p>")
    assert '<footer class="disclaimer">' in html
    assert APPROVED in html
    # In the footer, i.e. last thing in the body -- not floating in the head.
    assert html.index('<footer class="disclaimer">') > html.index("<body>")
    assert html.index(APPROVED) < html.index("</body>")


def test_the_disclaimer_is_styled_rather_than_left_as_bare_text():
    assert ".disclaimer" in SITE_CSS
```

Add `DISCLAIMER` and `SITE_CSS` to the existing `from gpu_agent.dashboard.site_render import (...)` line rather than importing twice.

- [ ] **Step 2: Run them and watch them fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_site_render.py -q`
Expected: FAIL — `ImportError: cannot import name 'DISCLAIMER'`.

- [ ] **Step 3: Implement**

In `gpu_agent/dashboard/site_render.py`, after the `_TILE_SIDES` line:

```python
# F124 -- the standing independence disclaimer, docs/publishing-posture.md
# section 4. Wording APPROVED VERBATIM by the user, interactive, 2026-08-22:
# do not reword, re-punctuate or "tidy" it. The React app carries the same
# sentence in web/src/components/Disclaimer.tsx and a test pins the two
# together, so an edit here without an edit there turns the web suite red.
DISCLAIMER = (
    "Independent personal project. The analysis here is one individual's own "
    "work, produced from public sources. It is not affiliated with, endorsed "
    "by, or representative of any employer, and it is not investment advice."
)

_DISCLAIMER_HTML = f'<footer class="disclaimer">{esc(DISCLAIMER)}</footer>'
```

Append to the end of the `SITE_CSS` string, before its closing `"""`:

```
.disclaimer { margin: 3rem 0 0; padding-top: 1rem; border-top: 1px solid var(--line);
              color: var(--muted); font-size: .8rem; line-height: 1.5; }
```

And in `page()`, change the body line so the footer is the last thing in `<body>`:

```python
            f"</head>\n<body>\n{body}\n{_DISCLAIMER_HTML}\n</body>\n</html>\n")
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_site_render.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add gpu_agent/dashboard/site_render.py tests/dashboard/test_site_render.py
git commit -m "feat(F124): approved disclaimer in the static page shell"
```

---

### Task 2: Prove it reaches every page the builder emits

A shell test proves one page. This proves the whole emitted set, and fails if a later lane adds a page outside the shell.

**Files:**
- Test: `tests/dashboard/test_site_build.py`

**Interfaces:**
- Consumes: `gpu_agent.dashboard.site_render.DISCLAIMER` from Task 1.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/dashboard/test_site_build.py`:

```python
def test_every_emitted_html_page_carries_the_disclaimer(tmp_path):
    """F124: not "the shell has it" but "every file on disk has it".

    If a later lane adds a page that renders its own HTML instead of going
    through site_render.page(), this is the test that catches it.
    """
    from gpu_agent.dashboard.site_render import DISCLAIMER

    _build(tmp_path)
    pages = sorted((tmp_path / "site").rglob("*.html"))
    # The committed React app is not staged into a scratch build, so every
    # .html here is one this builder wrote.
    assert len(pages) > 20, f"suspiciously few pages built: {len(pages)}"
    missing = [str(p) for p in pages if DISCLAIMER not in p.read_text(encoding="utf-8")]
    assert missing == []
```

- [ ] **Step 2: Run it**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_site_build.py -q`
Expected: PASS, because Task 1 already routed every page through the shell. If it FAILS, a renderer bypasses `page()` — find it and route it through the shell rather than pasting the footer a second time.

- [ ] **Step 3: Run the whole Python suite for regressions**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: PASS. One or two skips are expected in a worktree (price-scrape data lives in the root checkout). If a copy-lint or acronym-lint test trips on the disclaimer, STOP and record it as a blocker rather than rewording approved copy.

- [ ] **Step 4: Commit**

```bash
git log --oneline -1
git add tests/dashboard/test_site_build.py
git commit -m "test(F124): every emitted site page carries the disclaimer"
```

---

### Task 3: The React `Disclaimer` component, in the footer and in every app state

**Files:**
- Create: `web/src/components/Disclaimer.tsx`
- Modify: `web/src/components/Footer.tsx`
- Modify: `web/src/App.tsx` (loading shell and failure shell)
- Modify: `web/src/app.css`
- Test: `web/src/__tests__/disclaimer.test.tsx` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `export const DISCLAIMER: string` and `export function Disclaimer(): JSX.Element` from `web/src/components/Disclaimer.tsx`. Task 4 imports `DISCLAIMER` from this module.

- [ ] **Step 1: Write the failing test**

Create `web/src/__tests__/disclaimer.test.tsx`:

```tsx
/**
 * F124 -- the standing independence disclaimer.
 *
 * docs/publishing-posture.md section 4 says it appears in the footer of every
 * public page. The app is one page with three states, so "every page" means
 * every state: a reader who lands on a page that failed to load still needs to
 * know whose work this is and whose it is not.
 */
import {render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Disclaimer, DISCLAIMER} from '../components/Disclaimer';
import {Footer} from '../components/Footer';
import {App} from '../App';
import {readGolden} from './fixtures';

const APPROVED =
  "Independent personal project. The analysis here is one individual's own " +
  'work, produced from public sources. It is not affiliated with, endorsed ' +
  'by, or representative of any employer, and it is not investment advice.';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the disclaimer', () => {
  it('says the approved wording, character for character', () => {
    expect(DISCLAIMER).toBe(APPROVED);
  });

  it('renders as text a reader can see', () => {
    render(<Disclaimer />);
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is part of the footer', () => {
    render(<Footer links={[{label: 'Story', href: 'story/'}]} />);
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page while it is still loading', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    render(<App />);
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page when the reading could not be loaded', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('offline')));
    render(<App />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(APPROVED)).toBeInTheDocument();
  });

  it('is on the page once the reading has loaded', async () => {
    const payload = readGolden();
    vi.stubGlobal('fetch', () =>
      Promise.resolve({ok: true, json: () => Promise.resolve(payload)} as Response),
    );
    render(<App />);
    expect(await screen.findByText(APPROVED)).toBeInTheDocument();
  });
});
```

Note: match how the other suites stub `fetch` and read the golden payload — copy the `serve()` helper's shape from `web/src/__tests__/page-states.test.tsx` if `readGolden()` returns something the loader needs wrapped differently.

- [ ] **Step 2: Run it and watch it fail**

Run: `npm --prefix web test -- disclaimer`
Expected: FAIL — cannot resolve `../components/Disclaimer`.

- [ ] **Step 3: Create the component**

`web/src/components/Disclaimer.tsx`:

```tsx
/**
 * F124 -- the standing independence disclaimer, docs/publishing-posture.md
 * section 4. Wording APPROVED VERBATIM by the user, interactive, 2026-08-22:
 * do not reword, re-punctuate or "tidy" it.
 *
 * The static site builder carries the same sentence in
 * gpu_agent/dashboard/site_render.py; src/__tests__/copy-pins.test.ts reads
 * that file and fails if the two ever drift apart.
 */
export const DISCLAIMER =
  "Independent personal project. The analysis here is one individual's own " +
  'work, produced from public sources. It is not affiliated with, endorsed ' +
  'by, or representative of any employer, and it is not investment advice.';

export function Disclaimer() {
  return <p className="disclaimer">{DISCLAIMER}</p>;
}
```

- [ ] **Step 4: Render it in the footer**

In `web/src/components/Footer.tsx`, import `{Disclaimer}` from `./Disclaimer` and add `<Disclaimer />` after the `</nav>`, still inside `<footer>`.

- [ ] **Step 5: Render it in the other two states**

In `web/src/App.tsx`, import `{Disclaimer}` from `./components/Disclaimer` and add `<Disclaimer />` as the last child of the loading `<div className="shell">` and of the failure `<div className="shell">`.

- [ ] **Step 6: Style it**

Append to `web/src/app.css`, matching the static pages — small, muted, ruled off:

```css
/* F124 -- the standing independence disclaimer. Quiet fine print: it is a
   standing notice, not part of the day's reading. */
.disclaimer {
  margin: 2rem 0 0;
  padding-top: 1rem;
  border-top: 1px solid var(--line, #ddd);
  font-size: 0.75rem;
  line-height: 1.5;
  opacity: 0.7;
}
```

Use whatever line/muted token `app.css` already defines rather than inventing one; check `web/src/tokens.css` first, since `tokens.test.ts` guards that file.

- [ ] **Step 7: Run the test and watch it pass**

Run: `npm --prefix web test -- disclaimer`
Expected: PASS, all six.

- [ ] **Step 8: Commit**

```bash
git log --oneline -1
git add web/src/components/Disclaimer.tsx web/src/components/Footer.tsx web/src/App.tsx web/src/app.css web/src/__tests__/disclaimer.test.tsx
git commit -m "feat(F124): approved disclaimer in the React footer and every app state"
```

---

### Task 4: Pin the two copies of the wording to each other

**Files:**
- Test: `web/src/__tests__/copy-pins.test.ts` (create)

**Interfaces:**
- Consumes: `DISCLAIMER` from `web/src/components/Disclaimer.tsx` (Task 3) and the `DISCLAIMER = (...)` literal in `gpu_agent/dashboard/site_render.py` (Task 1).
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `web/src/__tests__/copy-pins.test.ts`:

```ts
/**
 * The disclaimer exists twice -- once in Python for the built pages, once in
 * TypeScript for the app -- because the two share no runtime and this lane may
 * not add a data file to carry it. Two copies drift. This test is what stops
 * them: it reads the Python source, lifts the literal out, and demands the two
 * match character for character.
 *
 * Same trick as page-states.test.tsx, which reads its caption copy out of
 * gpu_agent/dashboard/bullets.py rather than re-typing it.
 */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe, expect, it} from 'vitest';
import {DISCLAIMER} from '../components/Disclaimer';

// Vitest runs with `web/` as its root, same as ./fixtures.
const repoRoot = resolve(process.cwd(), '..');

/** The DISCLAIMER literal as the Python site builder actually holds it. */
function pythonDisclaimer(): string {
  const py = readFileSync(
    resolve(repoRoot, 'gpu_agent/dashboard/site_render.py'),
    'utf8',
  );
  const block = /^DISCLAIMER = \(\n([\s\S]*?)^\)$/m.exec(py);
  if (!block) {
    throw new Error(
      'no DISCLAIMER = ( ... ) literal in gpu_agent/dashboard/site_render.py. ' +
        'If it moved or changed shape, update this test -- do not delete it.',
    );
  }
  // Python implicit string concatenation: join the quoted chunks in order.
  const parts = block[1].match(/"([^"]*)"/g);
  if (!parts) throw new Error('DISCLAIMER literal held no double-quoted strings');
  return parts.map((p) => p.slice(1, -1)).join('');
}

describe('the disclaimer wording', () => {
  it('is identical in the site builder and in the app', () => {
    expect(DISCLAIMER).toBe(pythonDisclaimer());
  });
});
```

- [ ] **Step 2: Run it**

Run: `npm --prefix web test -- copy-pins`
Expected: PASS. If it fails on the regex, adjust the pattern to the literal's real shape in `site_render.py` — do not weaken the equality assertion.

- [ ] **Step 3: Commit**

```bash
git log --oneline -1
git add web/src/__tests__/copy-pins.test.ts
git commit -m "test(F124): pin the app's disclaimer wording to the builder's"
```

---

### Task 5: The no-scripting fallback

A reader with scripting off, and every link-preview crawler, reads `web/index.html` as a static file and never runs the app.

**Files:**
- Modify: `web/index.html`
- Modify: `web/src/__tests__/noscript.test.ts` (the pinned `EXPECTED` string)

**Interfaces:**
- Consumes: the approved wording.
- Produces: nothing.

- [ ] **Step 1: Update the pin first, so it fails**

In `web/src/__tests__/noscript.test.ts`, extend `EXPECTED`:

```ts
const EXPECTED =
  "This page needs scripting turned on to show today's reading. " +
  'The question this page answers: Is supply catching up to demand? ' +
  "Today's answer is not written into this file, so it cannot be shown " +
  'here. The story archive has the latest reading in full. ' +
  "Independent personal project. The analysis here is one individual's own " +
  'work, produced from public sources. It is not affiliated with, endorsed ' +
  'by, or representative of any employer, and it is not investment advice.';
```

Also extend the file's header comment to say why the pin grew: the pin exists to keep a *verdict* out of a file the daily cycle never rewrites; the disclaimer is standing policy text, so it is safe here in a way a verdict is not.

- [ ] **Step 2: Run it and watch it fail**

Run: `npm --prefix web test -- noscript`
Expected: FAIL — the received text ends at "in full."

- [ ] **Step 3: Add the paragraph**

In `web/index.html`, as the last child of `<div class="noscript">`:

```html
        <p class="disclaimer">
          Independent personal project. The analysis here is one individual's
          own work, produced from public sources. It is not affiliated with,
          endorsed by, or representative of any employer, and it is not
          investment advice.
        </p>
```

The test flattens whitespace, so the line wrapping above is fine. Also add a `.disclaimer` rule to the inline `<style>` block in the head — that block is all the styling a no-scripting reader gets:

```css
      .noscript .disclaimer {
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #ddd;
        font-size: 0.8rem;
        color: #666;
      }
```

- [ ] **Step 4: Run the noscript suite**

Run: `npm --prefix web test -- noscript`
Expected: PASS, all three — including "states no verdict of its own", which must not have been touched.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add web/index.html web/src/__tests__/noscript.test.ts
git commit -m "feat(F124): disclaimer in the no-scripting fallback"
```

---

### Task 6: Full gates, backlog tick, handoff

**Files:**
- Modify: `docs/fix-backlog.md` (the F124 checkbox line only)
- Create: `.superpowers/handoffs/f124-footer-disclaimer-DONE.md` **at the ROOT checkout**, `C:\Users\danie\random_for_fun\.superpowers\handoffs\` — not in the worktree.

- [ ] **Step 1: Run every gate and keep the output**

```bash
../../.venv/Scripts/python -m pytest -q
npm --prefix web test
npm --prefix web run build
```

Expected: all green. Python skips limited to the price-scrape tests that need root-checkout data.

`npm run build` writes into `web/dist/`. Do NOT copy its output into `site/` — this lane does not rebuild the live site.

- [ ] **Step 2: Prove the protected pins did not move**

```bash
../../.venv/Scripts/python -m pytest -q tests/test_evals_baseline_pin.py
git status --short
git diff --stat main
```

Expected: the pin test passes and `git diff --stat main` names only the files this plan touches — no baseline, prompt, fingerprint or replay file among them. If any pin file appears, STOP and record a blocker.

- [ ] **Step 3: Tick the backlog**

In `docs/fix-backlog.md`, change the F124 line's `- [ ]` to `- [x]`. That line and nothing else.

- [ ] **Step 4: Commit**

```bash
git log --oneline -1
git add docs/fix-backlog.md
git commit -m "docs(F124): tick the footer-disclaimer backlog item"
```

- [ ] **Step 5: Write the handoff at the ROOT checkout**

`C:\Users\danie\random_for_fun\.superpowers\handoffs\f124-footer-disclaimer-DONE.md`, covering: date, branch and commit hashes, the three test results with real numbers, the page set the footer now covers, the pins verified unmoved, every AFK-default decision from `QUESTIONS.md`, and the merger's job — **rebuild `site/` after merge** (`npm --prefix web run build` plus the `site` CLI verb) so the live pages actually carry the disclaimer, because this lane deliberately did not regenerate them.

Do not commit, merge, or push from this task beyond the branch commits above.
