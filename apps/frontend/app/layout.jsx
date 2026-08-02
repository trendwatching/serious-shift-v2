import { Nunito_Sans, Suez_One, Urbanist } from 'next/font/google'

import '../src/index.css'

// Self-hosted, not fetched from fonts.googleapis.com at runtime.
//
// next/font downloads and subsets these at build time and emits them under
// /_next/static — which the backend serves immutable, same-origin. The previous
// <link> to Google's CDN blocked first paint on a third-party round trip on
// every page load, on a site that is otherwise deliberately same-origin, and
// sent every visitor's IP to Google (a GDPR consideration for an EU company).
//
// `display: swap` keeps text visible while a face loads; the CSS fallbacks
// (system-ui / Georgia) already match the design's intent.
const urbanist = Urbanist({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-urbanist',
  display: 'swap',
})
const suez = Suez_One({
  subsets: ['latin'],
  weight: '400',            // Suez One ships 400 only
  variable: '--font-suez',
  display: 'swap',
})
const nunito = Nunito_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '600', '700', '800'],
  variable: '--font-nunito',
  display: 'swap',
})

// Build-time defaults only. The backend rewrites <title>, the description and
// the social tags per route from the live map document (apps/backend/src/seo.rs)
// — a static export cannot know how many shifts there are this week, and this
// file used to claim "eight" while the database held 57.
export const metadata = {
  title: 'Serious Shi(f)t — Everything that is about to change',
  description: 'What is about to change, and who is saying so. A weekly trend map built from sourced evidence.',
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/icon-192.png', type: 'image/png', sizes: '192x192' },
    ],
    apple: '/apple-touch-icon.png',
  },
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',   // let the black bar sit under the notch
  themeColor: '#000000',
}

// Legacy hash routes -> real paths.
//
// The previous site was hash-routed (seriousshift.ai/#/map/society). Every link
// shared or bookmarked before this redesign carries that form, and a fragment
// is never sent to the server — so the redirect has to happen here, inline in
// <head>, before React mounts. Doing it in a component would show the homepage
// first and then jump.
const LEGACY_HASH_REDIRECT = `(function(){try{
  var h = window.location.hash;
  if (h.indexOf('#/') !== 0) return;
  var p = h.slice(1);
  if (p.indexOf('/map/thinkers') === 0) p = '/';   // no equivalent page now
  window.history.replaceState(null, '', p + window.location.search);
}catch(e){}})();`

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${urbanist.variable} ${suez.variable} ${nunito.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: LEGACY_HASH_REDIRECT }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
