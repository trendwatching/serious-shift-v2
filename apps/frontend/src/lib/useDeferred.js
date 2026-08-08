import { useEffect, useState } from 'react'

/**
 * `true` only once `active` has been true for `delay` milliseconds.
 *
 * Used to decide whether a loading state is worth showing at all. The map API
 * answers in about 30ms, so a skeleton drawn the instant a page mounts is on
 * screen for two frames and then replaced by a differently-shaped page — and
 * that swap IS the stutter. Measured on the sphere page it was 0.39 of layout
 * shift; nobody was waiting for anything, they were watching a skeleton flash.
 *
 * Below the threshold the page renders nothing and then renders itself, which
 * is both shift-free and, at 30ms, indistinguishable from instant. Above it —
 * a cold container, a bad connection — the skeleton appears and earns its
 * place, because by then there is a real wait to communicate.
 */
export function useDeferred(active, delay = 250) {
  const [elapsed, setElapsed] = useState(false)

  useEffect(() => {
    if (!active) {
      setElapsed(false)
      return undefined
    }
    const timer = setTimeout(() => setElapsed(true), delay)
    return () => clearTimeout(timer)
  }, [active, delay])

  return active && elapsed
}
