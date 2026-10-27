import { useEffect } from 'react'
import { signOut, useSession } from './auth.js'
import { match, navigate, useLocation } from './router.js'
import { Link } from './ui.jsx'
import SignIn from './pages/SignIn.jsx'
import Book from './pages/Book.jsx'
import MyBookings from './pages/MyBookings.jsx'
import BookingDetail from './pages/BookingDetail.jsx'
import Manage from './pages/manage/Manage.jsx'

function NavLink({ to, path, children }) {
  const active = to === '/' ? path === '/' : path.startsWith(to)
  return <Link to={to} className={active ? 'nav-link active' : 'nav-link'} aria-current={active ? 'page' : undefined}>{children}</Link>
}

export default function App() {
  const session = useSession()
  const { path, query } = useLocation()

  useEffect(() => {
    if (!session && path !== '/sign-in') navigate('/sign-in', { replace: true })
    if (session && path === '/sign-in') navigate('/', { replace: true })
  }, [session, path])

  if (!session) return path === '/sign-in' ? <SignIn /> : null

  const isAdmin = session.user.role === 'admin'
  let page
  let params
  if (path === '/') page = <Book query={query} />
  else if (path === '/my-bookings') page = <MyBookings />
  else if ((params = match('/bookings/:id', path))) page = <BookingDetail id={params.id} />
  else if (path.startsWith('/manage') && isAdmin) page = <Manage path={path} query={query} />
  else page = <div className="page"><h1>Page not found</h1><p><Link to="/">Back to booking</Link></p></div>

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand"><span className="brand-mark" aria-hidden="true" />CampusSlot</Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" path={path}>Book</NavLink>
            <NavLink to="/my-bookings" path={path}>My bookings</NavLink>
            {isAdmin && <NavLink to="/manage" path={path}>Manage</NavLink>}
          </nav>
          <div className="who">
            <span className="who-name" title={session.user.email}>{session.user.name}</span>
            {isAdmin && <span className="role-tag">Admin</span>}
            <button className="btn-text" onClick={() => signOut()}>Sign out</button>
          </div>
        </div>
      </header>
      <main>{page}</main>
      <footer className="footer">All times are India Standard Time (IST).</footer>
    </>
  )
}
