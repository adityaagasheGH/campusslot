import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api.js'
import { ErrorNote, Spinner, TYPE_LABEL } from '../../ui.jsx'

const BLANK = {
  id: '', name: '', type: 'study_room', location: '', description: '', capacity: 6,
  open: '08:00', close: '20:00', slotMinutes: 60, requiresApproval: false, hidden: false,
}

export default function Facilities() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // null | 'new' | facility id
  const load = useCallback(() => api('GET', '/facilities', undefined, { includeHidden: 1 }).then((d) => setItems(d.facilities), setError), [])
  useEffect(() => { load() }, [load])

  if (!items) return error ? <ErrorNote error={error} /> : <Spinner />
  const current = editing === 'new' ? BLANK : items.find((f) => f.id === editing)

  return (
    <section>
      <div className="toolbar">
        <span className="muted">{items.length} facilities · {items.filter((f) => f.hidden).length} hidden</span>
        <button className="btn btn-primary btn-sm" onClick={() => setEditing('new')}>Add facility</button>
      </div>
      {current && (
        <FacilityForm key={editing} initial={current} isNew={editing === 'new'}
          onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />
      )}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Name</th><th>Type</th><th className="num">Capacity</th><th>Hours</th><th>Slots</th><th>Approval</th><th>Visible</th><th /></tr></thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.id} className={f.hidden ? 'row-muted' : ''}>
                <td>{f.name}<div className="muted small">{f.location}</div></td>
                <td>{TYPE_LABEL[f.type]}</td>
                <td className="num">{f.capacity}</td>
                <td className="nowrap">{f.open}–{f.close}</td>
                <td>{f.slotMinutes} min</td>
                <td>{f.requiresApproval ? 'Required' : '—'}</td>
                <td>{f.hidden ? 'Hidden' : 'Yes'}</td>
                <td><button className="btn btn-sm" onClick={() => setEditing(f.id)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function FacilityForm({ initial, isNew, onCancel, onSaved }) {
  const [f, setF] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' || k === 'slotMinutes' ? Number(e.target.value) : e.target.value
    setF({ ...f, [k]: v })
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (isNew) await api('POST', '/admin/facilities', f)
      else {
        const { id, ...rest } = f // eslint-disable-line no-unused-vars
        await api('PUT', `/admin/facilities/${initial.id}`, rest)
      }
      onSaved()
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  return (
    <form className="card facility-form" onSubmit={save}>
      <h2 className="section-title">{isNew ? 'Add facility' : `Edit ${initial.name}`}</h2>
      <ErrorNote error={error} />
      <div className="form-grid">
        <label className="field"><span>ID</span>
          <input value={f.id} onChange={set('id')} disabled={!isNew} required pattern="[a-z0-9][a-z0-9\-]{2,39}" title="lowercase letters, digits, dashes" />
        </label>
        <label className="field"><span>Name</span><input value={f.name} onChange={set('name')} required minLength={3} maxLength={60} /></label>
        <label className="field"><span>Type</span>
          <select value={f.type} onChange={set('type')}>{Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </label>
        <label className="field"><span>Capacity</span><input type="number" min={1} max={1000} value={f.capacity} onChange={set('capacity')} required /></label>
        <label className="field"><span>Opens</span><input type="time" step={1800} value={f.open} onChange={set('open')} required /></label>
        <label className="field"><span>Closes</span><input type="time" step={1800} value={f.close} onChange={set('close')} required /></label>
        <label className="field"><span>Slot length</span>
          <select value={f.slotMinutes} onChange={set('slotMinutes')}><option value={30}>30 minutes</option><option value={60}>60 minutes</option></select>
        </label>
        <label className="field"><span>Location</span><input value={f.location} onChange={set('location')} maxLength={80} /></label>
        <label className="field span-2"><span>Description</span><input value={f.description} onChange={set('description')} maxLength={200} /></label>
        <label className="check"><input type="checkbox" checked={f.requiresApproval} onChange={set('requiresApproval')} /> Requests need admin approval</label>
        <label className="check"><input type="checkbox" checked={f.hidden} onChange={set('hidden')} /> Hidden from students</label>
      </div>
      <div className="actions">
        <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
      </div>
      {!isNew && <p className="hint">Changing hours does not move existing bookings.</p>}
    </form>
  )
}
