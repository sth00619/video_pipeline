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
      <aside className="w-60 bg-navy-800 flex flex-col border-r border-navy-700">
        <div className="flex items-center gap-2 px-6 py-5 border-b border-navy-700">
          <TrendingUp className="text-accent-gold" size={24} />
          <span className="font-bold text-sm">주식 영상 자동화</span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = location.pathname.startsWith(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition ${
                  active
                    ? 'bg-accent-cyan/15 text-accent-cyan font-medium'
                    : 'text-gray-400 hover:bg-navy-700 hover:text-white'
                }`}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            )
          })}

          {isAdmin && (
            <Link
              to="/admin"
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition ${
                location.pathname.startsWith('/admin')
                  ? 'bg-accent-cyan/15 text-accent-cyan font-medium'
                  : 'text-gray-400 hover:bg-navy-700 hover:text-white'
              }`}
            >
              <Shield size={18} />
              관리자
            </Link>
          )}
        </nav>

        <div className="px-3 pb-4">
          <Link
            to="/jobs/new"
            className="flex items-center justify-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg py-2.5 text-sm hover:opacity-90 transition mb-3"
          >
            <Plus size={16} />
            새 영상 만들기
          </Link>

          <div className="flex items-center justify-between px-2 py-2 border-t border-navy-700 pt-3">
            <div className="text-sm">
              <div className="font-medium">{user?.username}</div>
              <div className="text-xs text-gray-500">{user?.role}</div>
            </div>
            <button
              onClick={handleLogout}
              className="text-gray-400 hover:text-accent-red transition"
              title="로그아웃"
            >
              <LogOut size={18} />
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
