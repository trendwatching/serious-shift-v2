import React from 'react'
import { BrowserRouter } from './router'
import App from './App'

// Mounts the React app. BrowserRouter gives real, shareable URLs; the backend
// serves index.html for any unmatched path so deep links resolve to the SPA.
export default function Spa() {
  return (
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  )
}
