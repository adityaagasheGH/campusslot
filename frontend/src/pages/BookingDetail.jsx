import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useSession } from '../auth.js'
import { formatStamp } from '../time.js'
import { ErrorNote, Link, Spinner, StatusBadge, When, statusLabel } from '../ui.jsx'
import { canCancel, canCheckIn, useBookingActions } from './MyBookings.jsx'

export default function BookingDetail({ id }) {
  const session = useSession()
  const [b, setB] = useState(null)
  const [error, setError] = useState(null)
  const actions = useBookingActions(setB)
  useEffect(() => { api('GET', `/bookings/${id}`).then(setB, setError) }, [id])

  if (error) return <div className="page narrow-page"><ErrorNote error={error} /><Link to="/my-bookings">Back to my bookings</Link></div>
  if (!b) return <div className="page"><Spinner /></div>
  const own = b.userId === session.user.userId

  return (
    <div className="page narrow-page">
      <Link to={own ? '/my-bookings' : '/manage/bookings'} className="back">← Back</Link>
      <div className="detail-head">
        <h1>{b.facilityName}</h1>
        <StatusBadge status={b.status} />
      </div>
      <dl className="facts card">
        <dt>When</dt><dd><When booking={b} /></dd>
        <dt>Purpose</dt><dd>{b.purpose}</dd>
        <dt>People</dt><dd>{b.people}</dd>
        <dt>Booked by</dt><dd>{b.userName} ({b.userEmail})</dd>
        {b.rejectReason && <><dt>Reason</dt><dd>{b.rejectReason}</dd></>}
        <dt>Booking ID</dt><dd><code>{b.bookingId}</code></dd>
      </dl>
      <ErrorNote error={actions.error} onDismiss={() => actions.setError(null)} />
      {own && (
        <div className="actions">
          {canCheckIn(b) && <button className="btn btn-primary" disabled={!!actions.busy} onClick={() => actions.run(b, 'check-in')}>Check in</button>}
          {canCancel(b) && <button className="btn" disabled={!!actions.busy} onClick={() => actions.run(b, 'cancel')}>Cancel booking</button>}
        </div>
      )}
      <h2 className="section-title">History</h2>
      <ol className="timeline">
        {b.history.map((h, i) => (
          <li key={i}>
            <span className="tl-when">{formatStamp(h.at)}</span>
            <span className="tl-what">
              {h.from ? <>{statusLabel(h.from)} → <b>{statusLabel(h.to)}</b></> : <>Created as <b>{statusLabel(h.to)}</b></>}
              <span className="muted"> by {h.by}</span>
              {h.note && <span className="tl-note">{h.note}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
