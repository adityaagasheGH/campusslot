// A very small history router: enough for a dozen pages, no dependency.
import { useSyncExternalStore } from 'react'

const listeners = new Set()
const subscribe = (l) => {
  listeners.add(l)
  window.addEventListener('popstate', l)
  return () => {
    listeners.delete(l)
    window.removeEventListener('popstate', l)
  }
}
const snapshot = () => window.location.pathname + window.location.search

export function navigate(to, { replace = false } = {}) {
  if (to === snapshot()) return
  window.history[replace ? 'replaceState' : 'pushState'](null, '', to)
  for (const l of listeners) l()
  if (!replace) window.scrollTo(0, 0)
}

export function useLocation() {
  const href = useSyncExternalStore(subscribe, snapshot)
  const url = new URL(href, window.location.origin)
  return { path: url.pathname, query: Object.fromEntries(url.searchParams) }
}

export function match(pattern, path) {
  const keys = []
  const rx = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => (keys.push(k), '([^/]+)')) + '/?$')
  const m = path.match(rx)
  return m && Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))
}
