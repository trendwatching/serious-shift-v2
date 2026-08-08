import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'

/**
 * The app is a client-rendered SPA that the Rust backend serves alongside
 * /api/*. Nothing here needs a Node server at runtime, which is why this build
 * emits a plain static bundle and why it replaced Next: Next was only ever the
 * build tool here (no SSR, no server components, no API routes, a hand-rolled
 * router) and cost ~870 KB of chunks to be one.
 *
 * `outDir: 'out'` keeps the backend's STATIC_DIR, the Dockerfile COPY and the
 * Playwright config pointing at the same path they already did.
 */
/**
 * Preload the two faces the first screen actually paints in.
 *
 * @fontsource ships `font-display: swap`, so a face that arrives after first
 * paint re-lays the text it covers. On the homepage that showed as the four
 * sphere badges twitching as Urbanist landed. Preloading fetches them at
 * highest priority alongside the CSS instead of after the first glyph needs
 * them, so the swap has usually already happened by the time anything is on
 * screen.
 *
 * Latin subsets only, and only the two families above the fold: preloading a
 * face nobody paints costs the same bandwidth as one they do. Suez One is the
 * shift-page title and is deliberately not here.
 *
 * The filenames are content-hashed, so they are read out of the bundle rather
 * than written down — a hard-coded name would 404 silently on the next build.
 */
function preloadCriticalFonts() {
  let hrefs = []
  return {
    name: 'preload-critical-fonts',
    apply: 'build',
    generateBundle(_options, bundle) {
      hrefs = Object.keys(bundle)
        .filter((file) => /(urbanist|nunito-sans)-latin-wght-normal-.*\.woff2$/.test(file))
        .map((file) => `/${file}`)
    },
    transformIndexHtml() {
      return hrefs.map((href) => ({
        tag: 'link',
        attrs: { rel: 'preload', as: 'font', type: 'font/woff2', href, crossorigin: '' },
        injectTo: 'head-prepend',
      }))
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwind(), preloadCriticalFonts()],
  build: {
    outDir: 'out',
    emptyOutDir: true,
    // The design leans on large background photographs; inlining anything but
    // the smallest icons would push them into the JS bundle.
    assetsInlineLimit: 2048,
  },
  server: {
    port: 3000,
    // Dev only. In production the backend serves the bundle and /api/* from
    // one origin, so there is no proxy and no CORS on the hot path.
    proxy: {
      '/api': {
        target: process.env.BACKEND_ORIGIN || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  // Same proxy as dev, so a PRODUCTION build can be exercised locally against
  // real data — which is the only way to see the preloads and the real chunking,
  // neither of which the dev server emits.
  preview: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.BACKEND_ORIGIN || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
