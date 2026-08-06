/**
 * Guards the one thing that decides whether the page looks like the approved
 * mock at all: when the mock and Astryx name the same design token, the mock's
 * value must be the one that wins inside the app.
 *
 * Why this needs a test rather than a comment. Astryx does NOT put its tokens
 * on the document root. It puts them on the element the <Theme> provider
 * renders, using:
 *
 *   @layer astryx-theme {
 *     @scope ([data-astryx-theme="neutral"]) to ([data-astryx-theme]) {
 *       :scope { --color-accent: …; }
 *     }
 *   }
 *
 * A custom property is inherited from the NEAREST ancestor that declares it.
 * The whole app lives inside that element, so anything it declares shadows the
 * same name declared on :root — cascade layers never even come into it, because
 * the two declarations are attached to different elements and so never compete.
 *
 * The fix is to declare the mock's tokens on that same element too. Then the two
 * declarations do compete, on equal footing, and the unlayered one (ours) wins.
 *
 * These checks read the real stylesheet Astryx ships, so a future Astryx version
 * that renames a token or moves its declarations will fail here rather than
 * quietly changing how the page looks.
 */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {render} from '@testing-library/react';
import {createElement} from 'react';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';

const here = resolve(process.cwd(), 'src');
const pkg = resolve(process.cwd(), 'node_modules', '@astryxdesign');

/**
 * Comments must go before anything else. These files explain the very rule
 * being checked, and the explanations contain example CSS — which an analyser
 * would happily read as real rules and be fooled by.
 */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

const read = (path: string) => stripComments(readFileSync(path, 'utf8'));

const ourTokens = read(resolve(here, 'tokens.css'));
const ourStyles = read(resolve(here, 'app.css'));
const astryxTheme = read(resolve(pkg, 'theme-neutral/dist/theme.css'));
const astryxBase = read(resolve(pkg, 'core/dist/astryx.css'));

/** Every custom property a stylesheet declares. */
function declaredNames(css: string): Set<string> {
  return new Set(
    [...css.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]),
  );
}

/** The selectors a stylesheet uses to declare one named custom property. */
function selectorsDeclaring(css: string, token: string): string[] {
  const found: string[] = [];
  const needle = new RegExp(`${token}\\s*:`, 'g');
  for (const hit of css.matchAll(needle)) {
    const before = css.slice(0, hit.index);
    // The innermost still-open selector block before this declaration.
    let selector: string | null = null;
    for (const open of before.matchAll(/([^{};]+)\{/g)) selector = open[1];
    if (selector) found.push(selector.trim());
  }
  return found;
}

const COLLIDING = ['--color-accent', '--color-border', '--color-text-secondary', '--color-warning'];

describe('mock tokens versus Astryx tokens', () => {
  it('still collides on exactly the four tokens we have handled', () => {
    const astryx = new Set([
      ...declaredNames(astryxTheme),
      ...declaredNames(astryxBase),
    ]);
    const collisions = [...declaredNames(ourTokens)]
      .filter((name) => astryx.has(name))
      .sort();
    expect(collisions).toEqual([...COLLIDING].sort());
  });

  it('Astryx declares its tokens on the theme element, not on the root', () => {
    // If this ever stops being true the reasoning above changes and the fix
    // below may no longer be needed — so fail loudly rather than drift.
    expect(astryxTheme).toMatch(
      /@scope \(\[data-astryx-theme="neutral"\]\) to \(\[data-astryx-theme\]\)/,
    );
    for (const token of COLLIDING) {
      expect(selectorsDeclaring(astryxTheme, token)).toContain(':scope');
    }
  });

  it('the theme provider really does wrap the app in that element', () => {
    const {container} = render(
      createElement(Theme, {
        theme: neutralTheme,
        children: createElement('p', null, 'x'),
      }),
    );
    const themed = container.querySelector('[data-astryx-theme]');
    expect(themed).not.toBeNull();
    expect(themed!.textContent).toBe('x');
  });

  it('declares every colliding token on that same element, so the mock wins', () => {
    for (const token of COLLIDING) {
      const selectors = selectorsDeclaring(ourTokens, token);
      expect(selectors.length).toBeGreaterThan(0);
      // At least one declaration must reach the themed element. Declaring only
      // on :root would be shadowed by Astryx and the mock's colour would never
      // appear on screen.
      expect(
        selectors.some((selector) => selector.includes('[data-astryx-theme]')),
        `${token} is declared only on ${selectors.join(' / ')} — Astryx's value would win`,
      ).toBe(true);
    }
  });

  it('takes the typeface and the ink back from Astryx too', () => {
    // Astryx styles the theme element itself, and colours headings and
    // paragraphs directly rather than by inheritance. Both have to be reclaimed
    // on that same element or the page renders in Astryx's typeface.
    const onThemeElement = /\[data-astryx-theme\][^{]*\{([^}]*)\}/g;
    const blocks = [...ourStyles.matchAll(onThemeElement)].map((m) => m[1]);
    expect(blocks.join('\n')).toMatch(/font-family:\s*var\(--font-sans\)/);
    expect(blocks.join('\n')).toMatch(/color:\s*var\(--color-text\)/);
    // …and headings/paragraphs told to inherit it rather than keep Astryx's.
    expect(ourStyles).toMatch(
      /\[data-astryx-theme\]\s+:where\(h1[^{]*\{[^}]*font-family:\s*inherit/,
    );
  });

  it('keeps the mock s own values for the colliding tokens', () => {
    // The values are the mock's, verbatim. Astryx's near-black accent must not
    // be what the page uses.
    expect(ourTokens).toMatch(/--color-accent:\s*#1F5FD0/);
    expect(ourTokens).toMatch(/--color-border:\s*#E3E3DF/);
    expect(ourTokens).toMatch(/--color-text-secondary:\s*#55555C/);
    expect(ourTokens).toMatch(/--color-warning:\s*#A16207/);
  });
});
