'use client'

import dynamic from 'next/dynamic'

// Client-only: the app is a purely interactive react-router SPA, so there is
// nothing to server-render. `next build` emits it as a static bundle.
const Spa = dynamic(() => import('../src/Spa'), { ssr: false })

export default function Page() {
  return <Spa />
}
