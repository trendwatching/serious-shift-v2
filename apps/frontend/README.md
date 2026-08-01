# frontend — the UI

The Serious Shift trend map: a client-side React SPA (react-router + Tailwind v4),
built to a **static export** and served by the [Rust backend](../backend/README.md)
from the same origin as `/api/*`.

Next.js is a build tool here, not a server — there is no SSR, no server component
and no API route, so `output: 'export'` emits a plain static bundle and the always-on
Node service it used to need is gone. Same origin also means no CORS and no
browser → Next → backend proxy hop.

## Layout

```
app/            Next entry: layout.jsx (document head), page.jsx (mounts the SPA)
src/
  Spa.jsx       <BrowserRouter><App/></BrowserRouter>
  App.jsx       routes
  shift/
    Home.jsx      the swipe deck
    pages.jsx     the three reading views
    sections/     editorial section components (barrel re-export in index.js)
    modules.jsx   {type,data} → component registry (see packages/contracts)
    chrome.jsx    top bar, menu, footer
    useDomains.js the one adapter between /api/map and the UI
    site.js       domains + external links (static config only)
    theme.js      per-domain colour, slug, read-time helpers
  hooks/useData.js  fetches /api/<name>, de-duplicated and cached
```

Routes are real paths (`/map/:domain/:shift/:sub`), so shifts deep-link and unfurl.
The backend serves `index.html` for any unmatched path, which is what makes that work.

## Data

One endpoint: `GET /api/map`. `useDomains` turns that document into the view model;
components never touch the raw JSON. A shift's page composition is its `modules`
array, so adding or reordering a section is a data change, not a code change.

There is no offline copy of the editorial content. If the map can't be loaded the UI
says so (`unavailable`) rather than rendering stale prose as if it were current.

## Run locally

```bash
npm install
npm run dev          # http://localhost:3000, proxies /api to :8080 (dev only)
```

The dev proxy honours `BACKEND_ORIGIN` (default `http://localhost:8080`). To exercise
exactly what production serves, build the bundle and point the backend at it:

```bash
npm run build
STATIC_DIR=$PWD/out cargo run --manifest-path ../backend/Cargo.toml   # :8080
```

## Deploy

Not deployed on its own — `apps/backend/Dockerfile` builds this bundle and copies it
into the backend image. See [DEPLOY-RAILWAY.md](../../DEPLOY-RAILWAY.md).
