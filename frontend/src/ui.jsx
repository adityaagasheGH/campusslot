import { navigate } from './router.js'
import { formatDate, hhmm } from './time.js'

export function Link({ to, children, className, ...rest }) {
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        navigate(to)
      }}
      {...rest}
    >
      {children}
    </a>
  )
}

const STATUS = {
  PENDING: ['Pending approval', 'warn'],
  CONFIRMED: ['Confirmed', 'ok'],
  CHECKED_IN: ['Checked in', 'accent'],
  COMPLETED: ['Completed', 'muted'],
  CANCELLED: ['Cancelled', 'muted'],
  REJECTED: ['Rejected', 'bad'],
  EXPIRED: ['Expired', 'muted'],
  NO_SHOW: ['No-show', 'bad'],
}
export const STATUSES = Object.keys(STATUS)
export const statusLabel = (s) => STATUS[s]?.[0] ?? s

export function StatusBadge({ status }) {
  const [label, tone] = STATUS[status] || [status, 'muted']
  return <span className={`badge badge-${tone}`}>{label}</span>
}

export function ErrorNote({ error, onDismiss }) {
  if (!error) return null
  return (
    <div className="note note-error" role="alert">
      <div>
        <strong>{error.message}</strong>
        {error.details?.fields && (
          <ul className="field-errors">
            {Object.entries(error.details.fields).map(([k, v]) => <li key={k}><b>{k}</b>: {v}</li>)}
          </ul>
        )}
        {error.requestId && <div className="request-id">Request ID: <code>{error.requestId}</code></div>}
      </div>
      {onDismiss && <button className="btn-text" onClick={onDismiss} aria-label="Dismiss">✕</button>}
    </div>
  )
}

export function Note({ tone = 'info', children }) {
  return <div className={`note note-${tone}`}>{children}</div>
}

export function Spinner({ label = 'Loading' }) {
  return <div className="spinner" role="status"><span className="dot" />{label}…</div>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export const TYPE_LABEL = {
  lab: 'Lab', seminar_hall: 'Seminar hall', study_room: 'Study room', sports_court: 'Sports court', auditorium: 'Auditorium',
}

export function When({ booking }) {
  return (
    <span className="when">
      {formatDate(booking.date)} · {hhmm(booking.startTime)}–{hhmm(booking.endTime)}
    </span>
  )
}
