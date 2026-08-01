/** @type {import('next').NextConfig} */

// Static export. The app is a client-side SPA (no SSR, no server components, no
// API routes), so Next is only a build tool here: `next build` emits a static
// bundle into out/ which the Rust backend serves alongside /api/*.
//
// That removes an always-on Node service and the browser -> Next -> backend
// proxy hop, and keeps the API same-origin (no CORS on the hot path).
const isDev = process.env.NODE_ENV === 'development'

const nextConfig = {
  reactStrictMode: true,
  // `next dev` ignores `output`, so this only shapes the production build.
  output: 'export',
  images: { unoptimized: true }, // no Next image server in a static export

  // Dev only: `next dev` has no backend behind it, so proxy /api to the local
  // one. Rewrites are not part of a static export and are ignored by `next
  // build` — in production the Rust binary serves both from one origin.
  ...(isDev && {
    async rewrites() {
      const origin = process.env.BACKEND_ORIGIN || 'http://localhost:8080'
      return [{ source: '/api/:path*', destination: `${origin}/api/:path*` }]
    },
  }),
}

export default nextConfig
