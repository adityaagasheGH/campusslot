// CampusSlot uses one fixed time zone: India Standard Time.
const TZ = 'Asia/Kolkata'

export function todayIST() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date())
}

export function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function daysBetween(a, b) {
  return Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 86400000)
}

export const hhmm = (t) => `${t.slice(0, 2)}:${t.slice(2)}`

export function instant(date, time) {
  return new Date(`${date}T${time.slice(0, 2)}:${time.slice(2)}:00+05:30`)
}

export function formatDate(iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) {
  return new Date(iso + 'T12:00:00Z').toLocaleDateString('en-IN', { ...opts, timeZone: 'UTC' })
}

export function formatStamp(isoStamp) {
  return new Date(isoStamp).toLocaleString('en-IN', {
    timeZone: TZ, day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}
