import { Camera, Compass, Heart, Menu, Sparkles } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { previewSteps } from './previewData'

const mobileLinks = [
  { path: '/preview/scan', label: 'Scan', icon: Camera },
  { path: '/preview/discover', label: 'Discover', icon: Compass },
  { path: '/preview/swaps', label: 'Make it yours', icon: Sparkles },
  { path: '/preview/remember', label: 'Remember', icon: Heart },
]

export function PreviewLayout() {
  return (
    <div className="preview-shell">
      <header className="preview-header">
        <NavLink className="preview-brand" to="/preview/scan" aria-label="Platter preview home">
          <span className="preview-brand__mark" aria-hidden="true"><span /></span>
          <span>Platter</span>
        </NavLink>
        <nav className="preview-header__nav" aria-label="Preview navigation">
          {previewSteps.slice(0, 3).map((step) => (
            <NavLink key={step.path} to={step.path} className={({ isActive }) => `preview-header__link${isActive ? ' is-active' : ''}`}>
              {step.shortLabel}
            </NavLink>
          ))}
        </nav>
        <button className="preview-menu" type="button" aria-label="Preview navigation menu">
          <Menu aria-hidden="true" />
        </button>
      </header>
      <main className="preview-main"><Outlet /></main>
      <nav className="preview-mobile-nav" aria-label="Preview navigation">
        {mobileLinks.map(({ path, label, icon: Icon }) => (
          <NavLink key={path} to={path} className={({ isActive }) => `preview-mobile-nav__link${isActive ? ' is-active' : ''}`}>
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
