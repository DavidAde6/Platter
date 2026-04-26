import './App.css'
import { NavLink, Outlet } from 'react-router-dom'
import {
  UtensilsCrossed,
  Camera,
  LayoutGrid,
  History,
  UserRound,
} from 'lucide-react'

function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">
            <UtensilsCrossed className="brand-icon" />
          </div>
          <span className="brand-text">Platter</span>
        </div>
        <nav className="app-nav">
          <NavLink to="/scan" className={({ isActive }) => (isActive ? 'nav-link nav-link-active' : 'nav-link')}>
            <Camera className="nav-icon" />
            <span>Scan</span>
          </NavLink>
          <NavLink to="/log" className={({ isActive }) => (isActive ? 'nav-link nav-link-active' : 'nav-link')}>
            <History className="nav-icon" />
            <span>Log</span>
          </NavLink>
          <NavLink to="/trends" className={({ isActive }) => (isActive ? 'nav-link nav-link-active' : 'nav-link')}>
            <LayoutGrid className="nav-icon" />
            <span>Trends</span>
          </NavLink>
          <NavLink to="/profile" className={({ isActive }) => (isActive ? 'nav-link nav-link-active' : 'nav-link')}>
            <UserRound className="nav-icon" />
            <span>Profile</span>
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}

export default App
