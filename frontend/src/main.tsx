import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Scan } from './pages/Scan'
import { Log } from './pages/Log'
import { Trends } from './pages/Trends'
import { Profile } from './pages/Profile'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Scan /> },
      { path: 'scan', element: <Scan /> },
      { path: 'log', element: <Log /> },
      { path: 'trends', element: <Trends /> },
      { path: 'profile', element: <Profile /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
