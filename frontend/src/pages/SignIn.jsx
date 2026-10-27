import { useState } from 'react'
import { api } from '../api.js'
import { saveSession, takeNotice } from '../auth.js'
import { ErrorNote, Note } from '../ui.jsx'

export default function SignIn() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice] = useState(takeNotice)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      saveSession(await api('POST', '/auth/sign-in', { email, password }))
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <div className="signin-panel">
        <div className="brand brand-lg"><span className="brand-mark" aria-hidden="true" />CampusSlot</div>
        <p className="lede">Book labs, seminar halls, study rooms and courts by the slot.</p>
        {notice && <Note>{notice}</Note>}
        <ErrorNote error={error} />
        <form onSubmit={submit} className="stack">
          <label className="field">
            <span>Email</span>
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">
            <span>Password</span>
            <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="fine">Accounts are created by the facility office. Ask them if you need one.</p>
      </div>
    </div>
  )
}
