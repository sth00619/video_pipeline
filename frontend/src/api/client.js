import axios from 'axios'
import { authStore } from '../store/auth'

const apiClient = axios.create({
  baseURL: '/api',
  // Long-form 10–20 minute rendering must not be aborted in the browser.
  timeout: 21600000,
})

apiClient.interceptors.request.use((config) => {
  const token = authStore.getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url || ''
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register')

    // 401 Unauthorized: 로그인 토큰이 만료되었거나 유효하지 않은 경우에만 토큰을 삭제하고 로그인으로 리다이렉트
    if (status === 401 && !isAuthEndpoint) {
      authStore.clearToken()
      if (window.location.pathname !== '/login') {
        const next = window.location.pathname + window.location.search
        window.location.href = `/login?next=${encodeURIComponent(next)}`
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
