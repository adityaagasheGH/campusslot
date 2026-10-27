// Session held in localStorage: { token, user, exp }. Tokens last 60 minutes.
import { useSyncExternalStore } from 'react'

const KEY = 'campusslot.session'
const listeners = new Set()
let notice = ''

function read() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null')
    return s && s.exp > Date.now() ? s : null
  } catch {
    return null
  }
}

let session = read()

function emit() {
  for (const l of listeners) l()
}

export function saveSession({ token, user, expiresIn }) {
  session = { token, user, exp: Date.now() + expiresIn * 1000 }
  notice = ''
  try { localStorage.setItem(KEY, JSON.stringify(session)) } catch { /* private mode: memory only */ }
  emit()
}

export function signOut(message = '') {
  session = null
  notice = message
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  emit()
}

export function getToken() {
  if (session && session.exp <= Date.now()) signOut('Your session has ended. Please sign in again.')
  return session?.token
}

export function takeNotice() {
  const n = notice
  notice = ''
  return n
}

export function useSession() {
  return useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), () => session)
}
