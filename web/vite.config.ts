import { copyFile, mkdir, readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vitest/config'

/**
 * Ship MapLibre's web worker and everything it imports.
 *
 * MapLibre resolves the worker at runtime as `new URL('./maplibre-gl-worker.mjs',
 * import.meta.url)`, which Vite cannot see and so never emits. In development
 * the dev server happens to serve it out of node_modules, so the gap appears
 * only in a production build. Vector tiles and glyphs are parsed in that
 * worker and nothing else is, so the map renders raster hillshade with white
 * oceans and no labels at all, and reports no error while doing it.
 *
 * The worker imports a shared chunk, so this follows its relative imports and
 * fails the build if any of them is missing. A dependency upgrade that adds a
 * third file breaks the build rather than shipping a map that half works.
 */
function maplibreWorker(): Plugin {
  const entry = 'maplibre-gl-worker.mjs'
  return {
    name: 'copy-maplibre-worker',
    apply: 'build',
    async writeBundle(options) {
      // Resolved through the package's exports map, which publishes ./dist/*
      // but no CJS main, so resolving the package root fails.
      const require = createRequire(import.meta.url)
      // Beside the bundle, not at the output root: the runtime URL is resolved
      // against the chunk's own location, which is assets/.
      const outDir = join(options.dir ?? 'dist', 'assets')
      await mkdir(outDir, { recursive: true })

      const pending = [entry]
      const copied = new Set<string>()
      while (pending.length > 0) {
        const name = pending.pop()!
        if (copied.has(name)) continue
        copied.add(name)

        const source = require.resolve(`maplibre-gl/dist/${name}`)
        // Rejects if it has moved or been renamed, which is the point.
        const code = await readFile(source, 'utf8')
        await copyFile(source, join(outDir, name))

        for (const match of code.matchAll(/from\s*["']\.\/([\w.-]+\.mjs)["']/g)) {
          pending.push(match[1]!)
        }
      }
      this.info(`shipped ${[...copied].sort().join(', ')}`)
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), maplibreWorker()],
  // MapLibre ships a web worker the dep optimizer cannot pre-bundle.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // e2e/*.spec.ts belongs to Playwright, not Vitest.
    exclude: ['node_modules/**', 'e2e/**'],
  },
})
