import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  TrendingUp, LayoutDashboard, ListVideo, Scissors,
  Shield, LogOut, Plus
} from 'lucide-react'
import { authStore } from '../store/auth'

const NAV_ITEMS = [
  { path: '/dashboard', label: '대시보드', icon: LayoutDashboard },
  { path: '/jobs', label: '롱폼 작업', icon: ListVideo },
  { path: '/shorts', label: '쇼츠 생성', icon: Scissors },
]

/**
 * [UI 개선]
 * - 기존에 text-gray-*(Tailwind 기본 회색)를 쓰던 부분을 전부 text-navy-400
 *   계열로 통일했습니다. gray와 navy는 색상 계열 자체가 달라서(gray는 순수
 *   무채색, navy는 파란빛이 도는 톤) 섞어 쓰면 사이트 전체 톤이 미묘하게
 *   어긋나 보이는 원인이었습니다.
 * - 사이드바 로고/네비 항목 글자 크기를 한 단계 키우고, 활성 항목의 강조를
 *   더 명확하게(좌측 바 추가) 했습니다.
 */
export default function Layout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const user = authStore.getUser()
  const isAdmin = authStore.isAdmin()

  const handleLogout = () => {
    authStore.clearToken()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex bg-navy-950">
      {/* 사이드바 */}
      <aside className="w-64 bg-navy-800 flex flex-col border-r border-navy-700">
        <div className="flex items-center gap-2.5 px-6 py-6 border-b border-navy-700">
          <TrendingUp className="text-accent-gold" size={26} />
          <span className="font-bold text-base">주식 영상 자동화</span>
        </div>
        <nav className="flex-1 px-3 py-5 space-y-1.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = location.pathname.startsWith(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`relative flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition ${
                  active
                    ? 'bg-accent-cyan/15 text-accent-cyan font-semibold'
                    : 'text-navy-400 hover:bg-navy-700 hover:text-white'
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-accent-cyan rounded-r-full" />
                )}
                <Icon size={19} />
                {item.label}
              </Link>
            )
          })}
          {isAdmin && (
            <Link
              to="/admin"
              className={`relative flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition ${
                location.pathname.startsWith('/admin')
                  ? 'bg-accent-cyan/15 text-accent-cyan font-semibold'
                  : 'text-navy-400 hover:bg-navy-700 hover:text-white'
              }`}
            >
              {location.pathname.startsWith('/admin') && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-accent-cyan rounded-r-full" />
              )}
              <Shield size={19} />
              관리자
            </Link>
          )}
        </nav>
        <div className="px-3 pb-5">
          <Link
            to="/jobs/new"
            className="flex items-center justify-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg py-3 text-sm hover:opacity-90 transition mb-4 shadow-glow-cyan"
          >
            <Plus size={17} />
            새 영상 만들기
          </Link>
          <div className="flex items-center justify-between px-2 py-3 border-t border-navy-700">
            <div className="text-sm">
              <div className="font-semibold text-white">{user?.username}</div>
              <div className="text-xs text-navy-400 mt-0.5">{user?.role}</div>
            </div>
            <button
              onClick={handleLogout}
              className="text-navy-400 hover:text-accent-red transition p-1.5 hover:bg-navy-700 rounded-lg"
              title="로그아웃"
            >
              <LogOut size={19} />
            </button>
          </div>
        </div>
      </aside>
      {/* 메인 컨텐츠 */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">{children}</div>
      </main>
    </div>
  )
}
