/// <reference types="vitest/config" />
import {rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {defineConfig, type Plugin} from 'vite';
import react from '@vitejs/plugin-react';

const OUT_DIR = '../site/chips.merchant-gpu';

/**
 * Clear ONLY the bundle folder before a build.
 *
 * The output folder is shared with the Python site renderer, so it can never be
 * emptied wholesale. Without this, every build would leave the previous run's
 * hash-named bundles behind and they would pile up in the repository forever.
 */
function cleanAssets(): Plugin {
  return {
    name: 'clean-assets-only',
    apply: 'build',
    buildStart() {
      rmSync(resolve(import.meta.dirname, OUT_DIR, 'assets'), {
        recursive: true,
        force: true,
      });
    },
  };
}

// The compiled output is committed and served statically from the category page's
// own folder, so every asset URL must be relative -- there is no server to rewrite
// paths and no Node process in the daily run.
export default defineConfig({
  base: './',
  plugins: [react(), cleanAssets()],
  build: {
    // The compiled page IS the category page, so it builds straight into the
    // committed site folder.
    outDir: OUT_DIR,
    // NEVER set this to true. That folder also holds the deep pages the Python
    // renderer writes -- findings/, series/, story/, entities/, history.html --
    // and emptying it would delete a large part of a live site. Stale bundles
    // from an earlier build are cleared by the narrow `clean-assets` plugin
    // below, which only ever touches the assets/ folder.
    emptyOutDir: false,
    assetsDir: 'assets',
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
