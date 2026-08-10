import { useState, useEffect } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { TrendingUp, Lock, User, Sparkles } from 'lucide-react'
import { authApi } from '../api/auth'
import { authStore } from '../store/auth'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // 이미 로그인된 사용자가 /login 페이지 접속 시 자동 이동
  useEffect(() => {
    if (authStore.isAuthenticated()) {
      const nextFromQuery = new URLSearchParams(location.search).get('next')
      const nextPath = location.state?.from || nextFromQuery
      const target = nextPath?.startsWith('/') ? nextPath : '/dashboard'
      navigate(target, { replace: true })
    }
  }, [navigate, location])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await authApi.login(username, password)
      if (!data || !data.token) {
        throw new Error('응답 데이터에 로그인 토큰이 존재하지 않습니다.')
      }
      authStore.setToken(data.token)
      authStore.setUser({ username: data.username, role: data.role })

      const nextFromQuery = new URLSearchParams(location.search).get('next')
      const nextPath = location.state?.from || nextFromQuery
      const target = nextPath?.startsWith('/') ? nextPath : '/dashboard'

      // 페이지 전체 상태 갱신 및 토큰 즉시 반영을 위한 안전 이동
      window.location.href = target
    } catch (err) {
      console.error('로그인 실패:', err)
      setError(err.response?.data?.message || '아이디 또는 비밀번호가 올바르지 않습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md">
        {/* 상단 브랜딩 타이틀 */}
        <div className="flex flex-col items-center mb-8 text-center">
          <div className="w-14 h-14 rounded-2xl bg-cyan-600 text-white flex items-center justify-center shadow-lg shadow-cyan-600/30 mb-3">
            <TrendingUp size={32} />
          </div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">AI 주식 영상 자동화 파이프라인</h1>
          <p className="text-xs font-semibold text-slate-500 mt-1">고품질 리포트 & 비디오 콘텐츠 생성 시스템</p>
        </div>

        {/* 로그인 폼 카드 */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl p-8 shadow-xl border border-slate-200 space-y-5">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="text-lg font-black text-slate-900">로그인</h2>
            <p className="text-xs font-semibold text-slate-500 mt-0.5">계정 정보를 입력하여 접속하세요.</p>
          </div>

          {error && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs font-bold text-rose-700">
              ⚠️ {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-extrabold text-slate-700 mb-1.5">아이디</label>
            <div className="relative">
              <User className="absolute left-3.5 top-3.5 text-slate-400" size={18} />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="아이디 입력"
                className="w-full bg-slate-50 border border-slate-300 rounded-xl pl-10 pr-4 py-3 text-sm font-bold text-slate-900 focus:outline-none focus:bg-white focus:border-cyan-600 focus:ring-4 focus:ring-cyan-500/10 transition"
                required
                autoFocus
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-extrabold text-slate-700 mb-1.5">비밀번호</label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-3.5 text-slate-400" size={18} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="비밀번호 입력"
                className="w-full bg-slate-50 border border-slate-300 rounded-xl pl-10 pr-4 py-3 text-sm font-bold text-slate-900 focus:outline-none focus:bg-white focus:border-cyan-600 focus:ring-4 focus:ring-cyan-500/10 transition"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-cyan-600 hover:bg-cyan-700 text-white font-black text-sm rounded-xl py-3.5 transition shadow-lg shadow-cyan-600/25 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? '로그인 처리 중...' : '시스템 로그인'}
          </button>

          <p className="text-center text-xs font-semibold text-slate-500 pt-2">
            아직 계정이 없으신가요?{' '}
            <Link to="/register" className="text-cyan-700 font-bold hover:underline">
              회원가입 신청
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
