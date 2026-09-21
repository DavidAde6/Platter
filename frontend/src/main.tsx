import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Scan } from './pages/Scan'
import { Log } from './pages/Log'
import { Trends } from './pages/Trends'
import { Profile } from './pages/Profile'
import { Login } from './pages/Login'
import { Signup } from './pages/Signup'
import { EditProfile } from './pages/EditProfile'
import { AuthProvider } from './context/AuthContext'
import { GuestRoute, ProtectedRoute } from './components/ProtectedRoute'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      {
        index: true,
        element: (
          <ProtectedRoute>
            <Scan />
          </ProtectedRoute>
        ),
      },
      {
        path: 'scan',
        element: (
          <ProtectedRoute>
            <Scan />
          </ProtectedRoute>
        ),
      },
      {
        path: 'log',
        element: (
          <ProtectedRoute>
            <Log />
          </ProtectedRoute>
        ),
      },
      {
        path: 'trends',
        element: (
          <ProtectedRoute>
            <Trends />
          </ProtectedRoute>
        ),
      },
      {
        path: 'profile',
        element: (
          <ProtectedRoute>
            <Profile />
          </ProtectedRoute>
        ),
      },
      {
        path: 'profile/edit',
        element: (
          <ProtectedRoute>
            <EditProfile />
          </ProtectedRoute>
        ),
      },
      {
        path: 'login',
        element: (
          <GuestRoute>
            <Login />
          </GuestRoute>
        ),
      },
      {
        path: 'signup',
        element: (
          <GuestRoute>
            <Signup />
          </GuestRoute>
        ),
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
)
