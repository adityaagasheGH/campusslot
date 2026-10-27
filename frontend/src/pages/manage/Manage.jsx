import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api.js'
import { navigate } from '../../router.js'
import { addDays, formatDate, todayIST } from '../../time.js'
import { Empty, ErrorNote, Link, Note, Spinner, STATUSES, StatusBadge, When, statusLabel } from '../../ui.jsx'
import Facilities from './Facilities.jsx'

const TABS = [
  ['approvals', 'Approvals'],
  ['bookings', 'Bookings'],
  ['facilities', 'Facilities'],
  ['reports', 'Utilization'],
  ['operations', 'Operations'],
]

export default function Manage({ path, query }) {
  const tab = path.split('/')[2] || 'approvals'
  const Page = { approvals: Approvals, bookings: Search, facilities: Facilities, reports: Reports, operations: Operations }[tab]
  return (
    <div className="page">
      <h1>Manage</h1>
      <nav className="tabs" aria-label="Manage sections">
        {TABS.map(([id, label]) => (
          <Link key={id} to={`/manage/${id}`} className={id === tab ? 'tab active' : 'tab'} aria-current={id === tab ? 'page' : undefined}>{label}</Link>
        ))}
      </nav>
      {Page ? <Page query={query} /> : <Empty>Unknown section.</Empty>}
    </div>
  )
}

function Approvals() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [rejecting, setRejecting] = useState(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => api('GET', '/admin/approvals').then((d) => setItems(d.bookings), setError), [])
  useEffect(() => { load() }, [load])

  async function decide(b, action) {
    setBusy(true)
    setError(null)
    try {
      await api('POST', `/admin/bookings/${b.bookingId}/${action}`, action === 'reject' ? { reason } : undefined)
      setRejecting(null)
      setReason('')
      await load()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (!items) return error ? <ErrorNote error={error} /> : <Spinner />
  return (
    <section>
      <ErrorNote error={error} onDismiss={() => setError(null)} />
      {!items.length && <Empty>No requests are waiting for approval.</Empty>}
      <ul className="booking-list">
        {items.map((b) => (
          <li key={b.bookingId} className="booking-row approval">
            <div className="booking-main">
              <Link to={`/bookings/${b.bookingId}`} className="booking-title">{b.facilityName}</Link>
              <When booking={b} />
              <span>{b.purpose} · {b.people} people</span>
              <span className="muted">{b.userName} ({b.userEmail})</span>
              {rejecting === b.bookingId && (
                <form className="reject-form" onSubmit={(e) => { e.preventDefault(); decide(b, 'reject') }}>
                  <label className="field grow">
                    <span>Reason for rejecting (shown to the student)</span>
                    <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} minLength={3} maxLength={200} required />
                  </label>
                  <button className="btn btn-danger btn-sm" disabled={busy}>Reject request</button>
                  <button type="button" className="btn-text" onClick={() => setRejecting(null)}>Keep</button>
                </form>
              )}
            </div>
            {rejecting !== b.bookingId && (
              <div className="booking-side">
                <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => decide(b, 'approve')}>Approve</button>
                <button className="btn btn-sm" disabled={busy} onClick={() => { setRejecting(b.bookingId); setReason('') }}>Reject…</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Search({ query }) {
  const [facilities, setFacilities] = useState([])
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const params = { date: query.date || todayIST(), facilityId: query.facilityId || '', status: query.status || '', q: query.q || '' }
  const [q, setQ] = useState(params.q)
  const set = (patch) => navigate(`/manage/bookings?${new URLSearchParams({ ...params, ...patch })}`, { replace: true })

  useEffect(() => { api('GET', '/facilities', undefined, { includeHidden: 1 }).then((d) => setFacilities(d.facilities), setError) }, [])
  useEffect(() => {
    setItems(null)
    api('GET', '/admin/bookings', undefined, params).then((d) => setItems(d.bookings), setError)
  }, [params.date, params.facilityId, params.status, params.q]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); set({ q }) }}>
        <label className="field"><span>Date</span>
          <input type="date" value={params.date} onChange={(e) => e.target.value && set({ date: e.target.value })} />
        </label>
        <label className="field"><span>Facility</span>
          <select value={params.facilityId} onChange={(e) => set({ facilityId: e.target.value })}>
            <option value="">All facilities</option>
            {facilities.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <label className="field"><span>Status</span>
          <select value={params.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="">Any status</option>
            {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </label>
        <label className="field grow"><span>Student</span>
          <input type="search" value={q} placeholder="Name or email" onChange={(e) => setQ(e.target.value)} onBlur={() => q !== params.q && set({ q })} />
        </label>
      </form>
      <ErrorNote error={error} />
      {!items ? <Spinner /> : !items.length ? <Empty>No bookings match on {formatDate(params.date)}.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Time</th><th>Facility</th><th>Student</th><th>Purpose</th><th>People</th><th>Status</th></tr></thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.bookingId}>
                  <td className="nowrap"><Link to={`/bookings/${b.bookingId}`}>{b.startTime.slice(0, 2)}:{b.startTime.slice(2)}–{b.endTime.slice(0, 2)}:{b.endTime.slice(2)}</Link></td>
                  <td>{b.facilityName}</td>
                  <td>{b.userName}<div className="muted small">{b.userEmail}</div></td>
                  <td>{b.purpose}</td>
                  <td className="num">{b.people}</td>
                  <td><StatusBadge status={b.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)

function Reports({ query }) {
  const today = todayIST()
  const from = query.from || addDays(today, -6)
  const to = query.to || today
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const set = (patch) => navigate(`/manage/reports?${new URLSearchParams({ from, to, ...patch })}`, { replace: true })

  useEffect(() => {
    setData(null)
    setError(null)
    api('GET', '/admin/reports/utilization', undefined, { from, to }).then(setData, setError)
  }, [from, to])

  const totals = data && data.facilities.reduce((t, r) => ({
    offered: t.offered + r.offeredHours, booked: t.booked + r.bookedHours, used: t.used + r.usedHours,
    bookings: t.bookings + r.bookings, noShows: t.noShows + r.noShows,
  }), { offered: 0, booked: 0, used: 0, bookings: 0, noShows: 0 })

  return (
    <section>
      <div className="filters">
        <label className="field"><span>From</span><input type="date" value={from} max={to} onChange={(e) => e.target.value && set({ from: e.target.value })} /></label>
        <label className="field"><span>To</span><input type="date" value={to} min={from} onChange={(e) => e.target.value && set({ to: e.target.value })} /></label>
        <div className="quick">
          <button className="btn btn-sm" onClick={() => set({ from: addDays(today, -6), to: today })}>Last 7 days</button>
          <button className="btn btn-sm" onClick={() => set({ from: addDays(today, -29), to: today })}>Last 30 days</button>
        </div>
      </div>
      <ErrorNote error={error} />
      {!data ? (!error && <Spinner />) : (
        <>
          <div className="stats">
            <div className="stat"><span className="stat-label">Hours offered</span><span className="stat-value">{totals.offered.toFixed(0)}</span></div>
            <div className="stat"><span className="stat-label">Hours booked</span><span className="stat-value">{totals.booked.toFixed(1)}</span><span className="stat-sub">{pct(totals.offered ? totals.booked / totals.offered : 0)} of offered</span></div>
            <div className="stat"><span className="stat-label">Hours used</span><span className="stat-value">{totals.used.toFixed(1)}</span><span className="stat-sub">{pct(totals.offered ? totals.used / totals.offered : 0)} of offered</span></div>
            <div className="stat"><span className="stat-label">No-shows</span><span className="stat-value">{totals.noShows}</span><span className="stat-sub">of {totals.bookings} bookings</span></div>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Facility</th><th className="num">Offered h</th><th className="num">Booked h</th><th className="num">Used h</th><th>Booked vs used</th><th className="num">No-show rate</th></tr>
              </thead>
              <tbody>
                {data.facilities.map((r) => (
                  <tr key={r.facilityId}>
                    <td>{r.facilityName}</td>
                    <td className="num">{r.offeredHours}</td>
                    <td className="num">{r.bookedHours}</td>
                    <td className="num">{r.usedHours}</td>
                    <td className="bar-cell">
                      <div className="bar" title={`Booked ${pct(r.bookedPct)}, used ${pct(r.usedPct)}`}>
                        <span className="bar-booked" style={{ width: pct(Math.min(r.bookedPct, 1)) }} />
                        <span className="bar-used" style={{ width: pct(Math.min(r.usedPct, 1)) }} />
                      </div>
                      <span className="bar-label">{pct(r.bookedPct)} / {pct(r.usedPct)}</span>
                    </td>
                    <td className="num">{pct(r.noShowRate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint"><i className="swatch bar-booked" /> booked share of open hours · <i className="swatch bar-used" /> used (checked in). No-show rate = no-shows ÷ bookings that reached their start. Range up to 31 days.</p>
        </>
      )}
    </section>
  )
}

function Operations() {
  const [result, setResult] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api('GET', '/health').then(setHealth, setError) }, [])

  async function sweep() {
    setBusy(true)
    setError(null)
    try { setResult(await api('POST', '/admin/sweep')) } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <section className="narrow-page">
      <div className="card">
        <h2 className="section-title">Lifecycle sweep</h2>
        <p>Runs automatically every 15 minutes. It marks confirmed bookings without a check-in as <b>No-show</b>, expires requests that were never approved, completes finished bookings, and frees slots left behind by failed requests. Running it again changes nothing.</p>
        <button className="btn btn-primary" onClick={sweep} disabled={busy}>{busy ? 'Running…' : 'Run sweep now'}</button>
        <ErrorNote error={error} />
        {result && (
          <Note tone="ok">
            Checked {result.checked} bookings: {result.NO_SHOW.length} no-show, {result.EXPIRED.length} expired, {result.COMPLETED.length} completed,
            {' '}{result.orphanLocksDeleted} orphan lock{result.orphanLocksDeleted === 1 ? '' : 's'} removed.
            {[...result.NO_SHOW, ...result.EXPIRED].length > 0 && (
              <ul>{[...result.NO_SHOW, ...result.EXPIRED].map((d) => <li key={d}>{d}</li>)}</ul>
            )}
          </Note>
        )}
      </div>
      {health && (
        <div className="card">
          <h2 className="section-title">API</h2>
          <p className="muted">Status <b>{health.status}</b> · boto3 {health.boto3}</p>
        </div>
      )}
    </section>
  )
}
