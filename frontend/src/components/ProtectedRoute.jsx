import { Navigate } from 'react-router-dom'
import { authStore } from '../store/auth'

export default function ProtectedRoute({ children, adminOnly = false }) {
  if (!authStore.isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  if (adminOnly && !authStore.isAdmin()) {
    return <Navigate to="/dashboard" replace />
  }
  return children
}
