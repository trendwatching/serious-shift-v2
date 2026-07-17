import { useEffect, useState } from 'react'

/**
 * useTheme — manages dark / light mode.
 *
 * Default: light (the bright "Serious Shi(f)t" look). The dark theme is an
 * opt-in variant. Persisted in localStorage under the key 'ss-theme'.
 *
 * Applies the theme by toggling the 'light' class on <html> (present = light).
 * The index.css `html.light { }` block supplies the bright palette; removing
 * the class falls back to the dark base tokens.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('ss-theme') || 'light'
    } catch {
      return 'light'
    }
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'light') {
      root.classList.add('light')
    } else {
      root.classList.remove('light')
    }
    try {
      localStorage.setItem('ss-theme', theme)
    } catch {
      // localStorage unavailable — theme works but won't persist
    }
  }, [theme])

  const toggle = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))

  return { theme, toggle }
}
