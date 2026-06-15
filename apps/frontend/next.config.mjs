/** @type {import('next').NextConfig} */

// The browser only ever talks to the frontend's own origin. Next proxies
// /api/* to the backend server-side, so there is no cross-origin request and
// therefore no CORS (and the backend needs no public domain / allowlist).
//
// BACKEND_ORIGIN is a SERVER-side var (not NEXT_PUBLIC) — used by the Next
// server, never shipped to the browser. On Railway set it to the backend's
// private address, e.g. http://backend.railway.internal:8080 (no public hop),
// or its public URL. Defaults to localhost for `next dev`.
const BACKEND_ORIGIN = (process.env.BACKEND_ORIGIN || 'http://localhost:8080').replace(/\/+$/, '')

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${BACKEND_ORIGIN}/api/:path*` },
    ]
  },
}

export default nextConfig
