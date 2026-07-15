# Cloudflare Pages hosting (F95)

The site is pre-rendered into `site/` and committed; Pages serves the folder as-is.

## One-time setup (operator)

1. Cloudflare dashboard -> Workers & Pages -> Create -> Pages -> Connect to Git.
2. Pick the `ai-market-digital-twin` repo (private is fine; the SITE becomes public, the repo does not).
3. Production branch: `main`. Build command: (leave empty). Build output directory: `site`.
4. Deploy. Every push to main auto-deploys in under a minute.

## Launch gates (user decisions — settle BEFORE the first deploy; spec §7.5)

- [x] Repo rename / TSMC-branded-exposure decision — RESOLVED 2026-07-15: the project moved to
      the **private** repo `ai-market-digital-twin` (the site content is public; the repo is not).
- [x] The `<project>.pages.dev` subdomain name — RESOLVED 2026-07-15: `ai-market-digital-twin.pages.dev`.

Both gates are settled. The remaining step is the operator creating the Pages project (steps above)
after this branch merges to `main`, since Pages deploys the `site/` folder from `main`.
