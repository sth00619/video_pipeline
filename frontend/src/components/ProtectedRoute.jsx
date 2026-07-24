import { Navigate, useLocation } from 'react-router-dom'
import { authStore } from '../store/auth'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const location = useLocation()

  if (!authStore.isAuthenticated()) {
    // Keep a direct link to an existing job usable after authentication.
    // Without this, opening /longform/:id while logged out always lands on
    // the dashboard and makes previous work appear to be missing.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (adminOnly && !authStore.isAdmin()) {
    return <Navigate to="/dashboard" replace />
  }
  return children
}
