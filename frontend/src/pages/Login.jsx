import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { TrendingUp } from 'lucide-react'
import { authApi } from '../api/auth'
import { authStore } from '../store/auth'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await authApi.login(username, password)
      authStore.setToken(data.token)
      authStore.setUser({ username: data.username, role: data.role })
      const nextFromQuery = new URLSearchParams(location.search).get('next')
      const nextPath = location.state?.from || nextFromQuery
      // Only allow in-app paths so a crafted login URL cannot redirect users
      // to an external site after authentication.
      navigate(nextPath?.startsWith('/') ? nextPath : '/dashboard', { replace: true })
    } catch (err) {
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy-950">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <TrendingUp className="text-accent-gold" size={32} />
          <h1 className="text-xl font-bold">주식 영상 자동화</h1>
        </div>

        <form onSubmit={handleSubmit} className="bg-navy-800 rounded-xl p-8 shadow-xl">
          <h2 className="text-lg font-semibold mb-6">로그인</h2>

          {error && (
            <div className="bg-accent-red/20 border border-accent-red text-accent-red text-sm rounded-lg px-4 py-2 mb-4">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">아이디</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
              required
              autoFocus
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm text-gray-400 mb-1">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent-cyan text-navy-950 font-semibold rounded-lg py-2.5 hover:opacity-90 transition disabled:opacity-50"
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>

          <p className="text-center text-sm text-gray-400 mt-4">
            계정이 없으신가요?{' '}
            <Link to="/register" className="text-accent-cyan hover:underline">
              회원가입
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
