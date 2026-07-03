import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { TrendingUp } from 'lucide-react'
import { authApi } from '../api/auth'

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '', email: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await authApi.register(form.username, form.password, form.email)
      setSuccess(true)
      setTimeout(() => navigate('/login'), 1500)
    } catch (err) {
      setError(err.response?.data?.message || '회원가입에 실패했습니다.')
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
          <h2 className="text-lg font-semibold mb-2">회원가입</h2>
          <p className="text-sm text-gray-400 mb-6">영상 작업자 계정을 생성합니다.</p>

          {error && (
            <div className="bg-accent-red/20 border border-accent-red text-accent-red text-sm rounded-lg px-4 py-2 mb-4">
              {error}
            </div>
          )}
          {success && (
            <div className="bg-accent-green/20 border border-accent-green text-accent-green text-sm rounded-lg px-4 py-2 mb-4">
              가입 완료! 로그인 화면으로 이동합니다.
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">아이디</label>
            <input
              name="username"
              type="text"
              value={form.username}
              onChange={handleChange}
              className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
              required
              autoFocus
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">이메일</label>
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
              required
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm text-gray-400 mb-1">비밀번호</label>
            <input
              name="password"
              type="password"
              value={form.password}
              onChange={handleChange}
              className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
              required
              minLength={6}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent-cyan text-navy-950 font-semibold rounded-lg py-2.5 hover:opacity-90 transition disabled:opacity-50"
          >
            {loading ? '가입 중...' : '회원가입'}
          </button>

          <p className="text-center text-sm text-gray-400 mt-4">
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className="text-accent-cyan hover:underline">
              로그인
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
