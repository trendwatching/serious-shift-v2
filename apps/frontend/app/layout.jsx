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

// Recover a tab that was open across a deploy.
//
// The whole app is one lazily-imported chunk (`dynamic(() => import('./Spa'))`),
// and every chunk filename carries a content hash. A deploy therefore replaces
// `958.<hash>.js` with a new name and deletes the old one. index.html is
// `no-cache`, so a *fresh* load always gets the current names — but a tab that
// was already open keeps the previous webpack runtime in memory, and the first
// client-side navigation asks for a chunk that now 404s. The import rejects,
// nothing renders, and the page the reader was on goes blank. It looks exactly
// like the site breaking, which is how it was reported.
//
// A chunk 404 has one correct response: fetch the current index.html and start
// again. The reload is guarded by a sessionStorage key so a genuinely missing
// chunk — a bad build, rather than a superseded one — cannot loop.
const RELOAD_ON_STALE_CHUNK = `(function(){try{
  var KEY = 'ss:chunk-reloaded';
  var stale = function(m){
    m = String(m || '');
    return m.indexOf('ChunkLoadError') > -1
        || m.indexOf('Loading chunk') > -1
        || m.indexOf('Importing a module script failed') > -1
        || m.indexOf('error loading dynamically imported module') > -1;
  };
  var recover = function(){
    if (sessionStorage.getItem(KEY)) return;      // already tried — let it fail visibly
    sessionStorage.setItem(KEY, '1');
    window.location.reload();
  };
  window.addEventListener('error', function(e){
    if (e && e.target && e.target.tagName === 'SCRIPT') return recover();  // 404 on a chunk
    if (e && stale(e.message)) recover();
  }, true);
  window.addEventListener('unhandledrejection', function(e){
    var r = e && e.reason;
    if (stale(r && (r.message || r))) recover();
  });
  // A load that got all the way through is proof the bundle is current, so the
  // guard is cleared and the next deploy gets its own single retry.
  window.addEventListener('load', function(){
    setTimeout(function(){ sessionStorage.removeItem(KEY); }, 5000);
  });
}catch(e){}})();`

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${urbanist.variable} ${suez.variable} ${nunito.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: LEGACY_HASH_REDIRECT }} />
        <script dangerouslySetInnerHTML={{ __html: RELOAD_ON_STALE_CHUNK }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
