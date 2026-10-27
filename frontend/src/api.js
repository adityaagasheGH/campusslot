// API client: finds the API address in /config.json, sends the token, and turns
// error responses into ApiError (which always carries the server's request ID).
import { getToken, signOut } from './auth.js'

let configPromise

function config() {
  configPromise ??= fetch('/config.json', { cache: 'no-store' }).then((r) => {
    if (!r.ok) throw new Error('config.json missing')
    return r.json()
  })
  return configPromise
}

export class ApiError extends Error {
  constructor(status, error = {}) {
    super(error.message || `Request failed (${status})`)
    this.status = status
    this.code = error.code
    this.requestId = error.requestId
    this.details = error
  }
}

export async function api(method, path, body, query) {
  const { apiUrl } = await config()
  const url = new URL(apiUrl.replace(/\/$/, '') + path)
  for (const [k, v] of Object.entries(query || {})) if (v !== '' && v != null) url.searchParams.set(k, v)
  const headers = {}
  const token = getToken()
  if (token) headers.authorization = `Bearer ${token}`
  if (body !== undefined) headers['content-type'] = 'application/json'

  let res
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, { message: 'Cannot reach CampusSlot. Check your connection and try again.' })
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && token) signOut('Your session has ended. Please sign in again.')
    throw new ApiError(res.status, { requestId: res.headers.get('x-request-id'), ...data.error })
  }
  return data
}
