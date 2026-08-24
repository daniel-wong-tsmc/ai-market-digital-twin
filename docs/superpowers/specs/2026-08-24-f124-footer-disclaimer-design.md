# F124 — footer disclaimer on every public page

**Status:** design agreed by the implementing agent (AFK-default — no human was
available). Decisions and their rationale: `.superpowers/sdd/2026-08-24-f124-footer-disclaimer/QUESTIONS.md`.
**Authority:** `docs/fix-backlog.md` F124 and `docs/publishing-posture.md` §4.
**Branch:** `f124-footer-disclaimer`, off main `f53d2df`.

## 1. The problem

`docs/publishing-posture.md` §4 sets out the real exposure: the site publishes a
daily market read, it is built and pushed from a GitHub account whose name
contains the user's employer, and a stranger can reasonably guess who is behind
it. The posture doc's answer, decided with the user on 2026-08-22, is a standing
disclaimer in the footer of every public page. It also records the honest status:
no disclaimer of any kind appears on the site today. This lane adds it.

## 2. The wording — approved, verbatim, not to be rephrased

> Independent personal project. The analysis here is one individual's own work,
> produced from public sources. It is not affiliated with, endorsed by, or
> representative of any employer, and it is not investment advice.

Four sentences, plain ASCII, no smart quotes, no em dashes. Any change to a
single character is a change to approved copy and needs the user.

## 3. What "every public page" means here

Two publishing surfaces, and they share no runtime.

**The static builder.** `gpu_agent/dashboard/site_build.py` writes every file
under `site/`. Every HTML file it writes goes through one shell function,
`page(title, body, depth)` in `gpu_agent/dashboard/site_render.py` — verified by
reading the imports: `brief_render.py`, `explore_render.py` and
`story_render.py` all call it and nothing in the builder emits HTML any other
way. One edit there covers, today:

| Page | Emitted by |
| --- | --- |
| root redirect `index.html` | `render_index_redirect` |
| `<cat>/appendix.html` | `render_appendix` |
| `<cat>/how/{alert,demand,supply,gap,featured}.html` | `render_how_*` |
| `<cat>/story/index.html` and one page per story day | `render_story_index`, `render_story_day` |
| `<cat>/findings/index.html` | `render_findings_page` |
| `<cat>/series/index.html` | `render_series_page` |
| `<cat>/entities/index.html` and one dossier per entity | `render_entities_index`, `render_entity_page` |
| `<cat>/history.html` | `render_history_page` |
| the executive brief | `render_brief` |

and any page a later lane adds, at no extra cost.

**The React app.** `site/<cat>/index.html` is the compiled `web/` app — a
committed build input the site builder deliberately never overwrites. It has
three states, and the footer is reached in only one of them:

- ready — renders `<Footer>`;
- loading — early return, no footer;
- load failed — early return, no footer.

All three get the disclaimer. So does the no-scripting fallback baked into
`web/index.html`, which is what a reader with scripting off and what a
link-preview crawler actually read.

**Out of scope:** `gpu_agent/dashboard/render.py::render_html`. It builds
`docs/dashboard.html`, which the site builder never emits and Cloudflare never
serves. Not a public page.

## 4. Design

### 4.1 One literal per language, pinned to each other

`gpu_agent/dashboard/site_render.py` gains a module-level `DISCLAIMER`
constant. `web/src/components/Disclaimer.tsx` gains a `DISCLAIMER` constant and
a `<Disclaimer/>` component that renders it.

Two copies of the text is a drift risk, so a test closes it: the web suite reads
the Python source, pulls the literal out of it, and asserts the TypeScript
constant equals it character for character. The repo already does exactly this
in `web/src/__tests__/page-states.test.tsx`, which lifts caption copy out of
`gpu_agent/dashboard/bullets.py` rather than re-typing it.

The alternative — a shared data file — would mean touching the dashboard
payload, and this lane is forbidden any schema change.

### 4.2 Static pages

`page()` appends, immediately before `</body>`:

```html
<footer class="disclaimer">Independent personal project. …</footer>
```

`SITE_CSS` gains a `.disclaimer` rule: small, muted, hairline rule above,
generous top margin. The stylesheet is concatenated once in `site_build.py` and
written to both `site/style.css` and `site/<cat>/style.css`, so the rule reaches
every page through the link the shell already writes.

The story page keeps its existing `<footer class="st-foot">` build credit and
gains the disclaimer footer after it. Two `<footer>` elements, valid HTML,
saying two different things.

### 4.3 The React app

`Footer.tsx` renders `<Disclaimer/>` after its link nav. `App.tsx` renders
`<Disclaimer/>` inside the loading shell and the failure shell too. `app.css`
styles `.disclaimer` to match the static pages: small, muted, ruled off.

### 4.4 The no-scripting fallback

`web/index.html`'s `<noscript>` block gains the disclaimer as its closing
paragraph, and `noscript.test.ts`'s exact-text pin is extended to match.

That pin exists to stop a *verdict* being baked into a file the daily cycle
never rewrites — a verdict there goes stale the moment the reading changes. The
disclaimer is fixed policy text; it goes stale only if the policy changes, and
the policy is a committed document. The suite's separate "states no verdict of
its own" assertion is untouched and still passes.

## 5. What must not move

No dashboard schema change — the disclaimer is presentation only and never
enters `dashboard.json`. No protected pin moves: the F6 evals baseline
(`tests/test_evals_baseline_pin.py`), the narrator prompt pin, the F83
run-cycle fingerprint, and the scoring replay pin all sit upstream of rendering
and are verified unmoved before the branch is called done.

`site/` is **not** regenerated in this lane — the root store is mid-cycle. The
committed built pages still carry no disclaimer when this branch lands; the
next real site build emits it. This is a merger action, recorded in the handoff.

## 6. Testing

- **Python.** A test asserting `page()` output contains the exact approved
  sentence; a test asserting the constant is the approved string character for
  character; a builder-level test that walks every HTML file `build_site`
  emits into a scratch directory and asserts every one carries the disclaimer —
  so a future page added without it fails the suite.
- **Web.** `Disclaimer` renders the exact text; `Footer` includes it; the app
  shows it while loading and after a load failure as well as when ready; the
  cross-language test pinning the TS constant to the Python one; the updated
  noscript pin.
- **Gates.** Full `pytest -q`, `npm --prefix web test`, `npm --prefix web run
  build`.
