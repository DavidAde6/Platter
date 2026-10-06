import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { PublicAccessGate } from './PublicAccessGate'
import './PublicAccessGate.css'

const router = createBrowserRouter([
  {
    path: '*',
    element: <PublicAccessGate />,
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
