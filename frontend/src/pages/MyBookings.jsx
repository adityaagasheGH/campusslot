import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { instant } from '../time.js'
import { Empty, ErrorNote, Link, Spinner, StatusBadge, When } from '../ui.jsx'

const WINDOW = 15 * 60 * 1000

export function canCheckIn(b, now = Date.now()) {
  const start = instant(b.date, b.startTime).getTime()
  return b.status === 'CONFIRMED' && now >= start - WINDOW && now <= start + WINDOW
}

export function canCancel(b, now = Date.now()) {
  return (b.status === 'PENDING' || b.status === 'CONFIRMED') && now < instant(b.date, b.startTime).getTime()
}

export function useBookingActions(onChange) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  async function run(b, action) {
    if (action === 'cancel' && !window.confirm(`Cancel ${b.facilityName} on ${b.date}? The slot will be freed for others.`)) return
    setBusy(b.bookingId + action)
    setError(null)
    try {
      onChange(await api('POST', `/bookings/${b.bookingId}/${action}`))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }
  return { busy, error, setError, run }
}

function BookingRow({ b, actions }) {
  const now = Date.now()
  return (
    <li className="booking-row">
      <div className="booking-main">
        <Link to={`/bookings/${b.bookingId}`} className="booking-title">{b.facilityName}</Link>
        <When booking={b} />
        <span className="muted purpose">{b.purpose}</span>
      </div>
      <div className="booking-side">
        <StatusBadge status={b.status} />
        {actions && canCheckIn(b, now) && (
          <button className="btn btn-primary btn-sm" disabled={!!actions.busy} onClick={() => actions.run(b, 'check-in')}>Check in</button>
        )}
        {actions && canCancel(b, now) && (
          <button className="btn btn-sm" disabled={!!actions.busy} onClick={() => actions.run(b, 'cancel')}>Cancel</button>
        )}
      </div>
    </li>
  )
}

export default function MyBookings() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => api('GET', '/bookings/mine').then(setData, setError), [])
  const actions = useBookingActions(load)
  useEffect(() => { load() }, [load])

  // Re-render every 30 s so Check in appears when its window opens.
  const [, tick] = useState(0)
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 30000); return () => clearInterval(t) }, [])

  if (error) return <div className="page"><ErrorNote error={error} /></div>
  if (!data) return <div className="page"><Spinner /></div>
  return (
    <div className="page narrow-page">
      <h1>My bookings</h1>
      <ErrorNote error={actions.error} onDismiss={() => actions.setError(null)} />
      <h2 className="section-title">Upcoming <span className="count">{data.upcoming.length} of 3 active</span></h2>
      {data.upcoming.length ? (
        <ul className="booking-list">{data.upcoming.map((b) => <BookingRow key={b.bookingId} b={b} actions={actions} />)}</ul>
      ) : (
        <Empty>No upcoming bookings. <Link to="/">Book a slot</Link></Empty>
      )}
      <p className="hint">Check in opens 15 minutes before the start and closes 15 minutes after. Bookings without a check-in are released as no-shows.</p>
      <h2 className="section-title">History</h2>
      {data.past.length ? (
        <ul className="booking-list">{data.past.map((b) => <BookingRow key={b.bookingId} b={b} />)}</ul>
      ) : (
        <Empty>Nothing here yet.</Empty>
      )}
    </div>
  )
}
