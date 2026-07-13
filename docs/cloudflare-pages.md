# Cloudflare Pages hosting (F95)

The site is pre-rendered into `site/` and committed; Pages serves the folder as-is.

## One-time setup (operator)

1. Cloudflare dashboard -> Workers & Pages -> Create -> Pages -> Connect to Git.
2. Pick this GitHub repo (private is fine; the SITE becomes public, the repo does not).
3. Production branch: `main`. Build command: (leave empty). Build output directory: `site`.
4. Deploy. Every push to main auto-deploys in under a minute.

## Launch gates (user decisions — settle BEFORE the first deploy; spec §7.5)

- [ ] The standing "repo rename before TSMC-branded exposure" decision (the page carries a
      FOR TSMC section once F65 lands, and the exec framing is TSMC-specific).
- [ ] The `<project>.pages.dev` subdomain name (part of the same exposure decision).

Until both boxes are ticked, building and committing `site/` is fine — just do not connect
the Pages project.
