import apiClient from './client'

export const authApi = {
  login: async (username, password) => {
    const res = await apiClient.post('/auth/login', { username, password })
    return res.data
  },
  register: async (username, password, email) => {
    const res = await apiClient.post('/auth/register', { username, password, email })
    return res.data
  },
  me: async () => {
    const res = await apiClient.get('/auth/me')
    return res.data
  },
}
