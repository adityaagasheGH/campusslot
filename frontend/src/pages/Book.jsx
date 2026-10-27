import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { navigate } from '../router.js'
import { addDays, formatDate, hhmm, todayIST } from '../time.js'
import { ErrorNote, Link, Note, Spinner, TYPE_LABEL } from '../ui.jsx'

const MAX_SLOTS = 4
const STATE_LABEL = { available: 'Available', taken: 'Taken', yours: 'Yours', past: 'Past' }

export default function Book({ query }) {
  const [facilities, setFacilities] = useState(null)
  const [error, setError] = useState(null)
  const today = todayIST()
  const date = query.date && query.date >= today && query.date <= addDays(today, 14) ? query.date : today
  const facilityId = query.facility || facilities?.[0]?.id

  useEffect(() => {
    api('GET', '/facilities').then((d) => setFacilities(d.facilities), setError)
  }, [])

  const go = (patch) => {
    const q = new URLSearchParams({ facility: facilityId, date, ...patch })
    navigate(`/?${q}`, { replace: true })
  }

  if (error) return <div className="page"><ErrorNote error={error} /></div>
  if (!facilities) return <div className="page"><Spinner /></div>
  const facility = facilities.find((f) => f.id === facilityId) || facilities[0]

  return (
    <div className="page book">
      <aside className="facility-list" aria-label="Facilities">
        <h2 className="section-title">Facilities</h2>
        {facilities.map((f) => (
          <button key={f.id} className={`facility-card${f.id === facility?.id ? ' selected' : ''}`} onClick={() => go({ facility: f.id })}>
            <span className="facility-name">{f.name}</span>
            <span className="facility-meta">{TYPE_LABEL[f.type]} · up to {f.capacity}</span>
            {f.requiresApproval && <span className="tag">Needs approval</span>}
          </button>
        ))}
      </aside>
      {facility ? (
        <Timetable key={facility.id + date} facility={facility} date={date} today={today} onDate={(d) => go({ date: d })} />
      ) : (
        <Note>No facilities are open for booking yet.</Note>
      )}
    </div>
  )
}

function Timetable({ facility, date, today, onDate }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState([])
  const [conflict, setConflict] = useState([])
  const [booked, setBooked] = useState(null)

  const load = useCallback(() => {
    return api('GET', `/facilities/${facility.id}/availability`, undefined, { date }).then(setData, setError)
  }, [facility.id, date])

  useEffect(() => { load() }, [load])

  function toggle(slot) {
    if (slot.state !== 'available') return
    setConflict([])
    setError(null)
    setBooked(null)
    const times = data.slots.map((s) => s.time)
    const i = times.indexOf(slot.time)
    if (selected.includes(slot.time)) {
      // Deselecting an end keeps the run; deselecting the middle restarts from here.
      const idx = selected.map((t) => times.indexOf(t))
      if (i === idx[0] || i === idx[idx.length - 1]) setSelected(selected.filter((t) => t !== slot.time))
      else setSelected([slot.time])
      return
    }
    const idx = selected.map((t) => times.indexOf(t))
    const adjacent = idx.length && (i === idx[0] - 1 || i === idx[idx.length - 1] + 1)
    if (adjacent && selected.length < MAX_SLOTS) setSelected([...selected, slot.time].sort())
    else setSelected([slot.time])
  }

  const days = Array.from({ length: 15 }, (_, i) => addDays(today, i))
  const end = selected.length ? data.slots.find((s) => s.time === selected[selected.length - 1]).end : null

  return (
    <section className="timetable" aria-label={`${facility.name} timetable`}>
      <div className="tt-head">
        <div>
          <h1>{facility.name}</h1>
          <p className="muted">
            {facility.location && <>{facility.location} · </>}
            Open {facility.open}–{facility.close} · {facility.slotMinutes}-minute slots · up to {facility.capacity} people
          </p>
          {facility.description && <p className="desc">{facility.description}</p>}
        </div>
      </div>

      <div className="date-strip" role="tablist" aria-label="Date">
        {days.map((d) => (
          <button key={d} role="tab" aria-selected={d === date} className={`date-chip${d === date ? ' active' : ''}`} onClick={() => onDate(d)}>
            <span className="dow">{d === today ? 'Today' : formatDate(d, { weekday: 'short' })}</span>
            <span className="dom">{formatDate(d, { day: 'numeric', month: 'short' })}</span>
          </button>
        ))}
      </div>

      {facility.requiresApproval && (
        <Note tone="warn">Requests for {facility.name} are held as <b>Pending</b> until the facility office approves them.</Note>
      )}
      <ErrorNote error={error} onDismiss={() => setError(null)} />

      {!data ? <Spinner label="Loading slots" /> : (
        <>
          <div className="legend" aria-hidden="true">
            {Object.entries(STATE_LABEL).map(([k, v]) => <span key={k}><i className={`swatch slot-${k}`} />{v}</span>)}
            <span><i className="swatch slot-selected" />Selected</span>
          </div>
          <div className="slot-grid">
            {data.slots.map((s) => {
              const cls = ['slot', `slot-${s.state}`]
              if (selected.includes(s.time)) cls.push('slot-selected')
              if (conflict.includes(s.time)) cls.push('slot-conflict')
              return (
                <button
                  key={s.time}
                  className={cls.join(' ')}
                  disabled={s.state !== 'available'}
                  aria-pressed={selected.includes(s.time)}
                  onClick={() => toggle(s)}
                  title={`${hhmm(s.time)}–${hhmm(s.end)} ${STATE_LABEL[s.state]}`}
                >
                  <span className="slot-time">{hhmm(s.time)}</span>
                  <span className="slot-state">{conflict.includes(s.time) ? 'Just taken' : STATE_LABEL[s.state]}</span>
                </button>
              )
            })}
          </div>
          {booked && (
            <Note tone="ok">
              {booked.status === 'PENDING'
                ? <>Request sent. The facility office will approve or reject it; you can follow it in <Link to="/my-bookings">My bookings</Link>.</>
                : <>Booked {facility.name}, {formatDate(booked.date)} {hhmm(booked.startTime)}–{hhmm(booked.endTime)}. Remember to check in when you arrive. <Link to={`/bookings/${booked.bookingId}`}>View booking</Link></>}
            </Note>
          )}
          {selected.length > 0 && (
            <BookingForm
              facility={facility} date={date} slots={selected} end={end}
              onDone={(b) => { setSelected([]); setBooked(b); load() }}
              onConflict={(taken, err) => { setConflict(taken); setSelected([]); setError(err); load() }}
            />
          )}
          {!selected.length && !booked && data.slots.some((s) => s.state === 'available') && (
            <p className="hint">Pick a free slot to start. You can select up to {MAX_SLOTS} slots in a row.</p>
          )}
        </>
      )}
    </section>
  )
}

function BookingForm({ facility, date, slots, end, onDone, onConflict }) {
  const [purpose, setPurpose] = useState('')
  const [people, setPeople] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDone(await api('POST', '/bookings', { facilityId: facility.id, date, slots, purpose, people: Number(people) }))
    } catch (err) {
      if (err.details?.reason === 'SLOT_TAKEN') onConflict(err.details.takenSlots || [], err)
      else setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="booking-form card" onSubmit={submit}>
      <div className="booking-summary">
        <strong>{formatDate(date)} · {hhmm(slots[0])}–{hhmm(end)}</strong>
        <span className="muted">{slots.length} slot{slots.length > 1 ? 's' : ''} at {facility.name}</span>
      </div>
      <ErrorNote error={error} />
      <div className="form-row">
        <label className="field grow">
          <span>Purpose</span>
          <input value={purpose} onChange={(e) => setPurpose(e.target.value)} minLength={3} maxLength={200} required placeholder="e.g. DBMS project meeting" />
        </label>
        <label className="field narrow">
          <span>People</span>
          <input type="number" min={1} max={facility.capacity} value={people} onChange={(e) => setPeople(e.target.value)} required />
        </label>
      </div>
      <button className="btn btn-primary" disabled={busy}>
        {busy ? 'Booking…' : facility.requiresApproval ? 'Request booking' : 'Book now'}
      </button>
    </form>
  )
}
