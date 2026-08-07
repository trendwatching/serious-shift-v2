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
export default defineConfig({
  plugins: [react(), tailwind()],
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
  preview: { port: 3000 },
})
