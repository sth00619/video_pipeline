const TOKEN_KEY = 'stock_pipeline_token'
const USER_KEY = 'stock_pipeline_user'

export const authStore = {
  getToken() {
    return localStorage.getItem(TOKEN_KEY)
  },
  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token)
  },
  clearToken() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
  getUser() {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  },
  setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  isAuthenticated() {
    return !!this.getToken()
  },
  isAdmin() {
    const user = this.getUser()
    return user?.role === 'ADMIN'
  },
}
