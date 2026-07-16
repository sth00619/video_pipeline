import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Clapperboard, LayoutDashboard, ListVideo, LogOut, Plus, Scissors, Shield, TrendingUp } from 'lucide-react'
import { authStore } from '../store/auth'

const NAV_ITEMS = [
  { path: '/dashboard', label: '대시보드', icon: LayoutDashboard },
  { path: '/longform', label: '롱폼 제작실', icon: ListVideo },
  { path: '/shorts', label: '쇼츠 제작실', icon: Scissors },
]

export default function Layout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const user = authStore.getUser()
  const isAdmin = authStore.isAdmin()
  const isActive = (path) => location.pathname === path || location.pathname.startsWith(`${path}/`)

  return (
    <div className="min-h-screen bg-navy-950 text-slate-900">
      <aside className="hidden lg:flex fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-navy-700 flex-col overflow-y-auto">
        <Link to="/dashboard" className="flex items-center gap-3 px-6 py-6 border-b border-navy-700">
          <span className="w-9 h-9 rounded-xl bg-accent-cyan text-white flex items-center justify-center shadow-glow-cyan"><Clapperboard size={19}/></span>
          <span className="font-bold text-[15px] text-slate-900">롱폼 제작실</span>
        </Link>
        <nav className="flex-1 px-3 py-5 space-y-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => <Link key={path} to={path} className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm transition ${isActive(path) ? 'bg-accent-cyan text-white font-semibold shadow-sm' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'}`}><Icon size={18}/>{label}</Link>)}
          {isAdmin && <Link to="/admin" className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm transition ${isActive('/admin') ? 'bg-accent-cyan text-white font-semibold shadow-sm' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'}`}><Shield size={18}/>관리자</Link>}
        </nav>
        <div className="px-4 pb-5 space-y-3">
          <Link to="/longform/new" className="w-full flex items-center justify-center gap-2 rounded-lg bg-accent-cyan hover:opacity-90 text-white py-2.5 text-sm font-semibold"><Plus size={16}/>새 롱폼 작업</Link>
          <div className="rounded-xl bg-slate-50 border border-navy-700 px-3 py-3 flex items-center justify-between"><div><div className="text-sm font-semibold text-slate-900">{user?.username || '사용자'}</div><div className="text-xs text-slate-500 mt-0.5">{user?.role || 'MEMBER'}</div></div><button onClick={() => { authStore.clearToken(); navigate('/login') }} className="text-slate-400 hover:text-accent-red p-1.5" title="로그아웃"><LogOut size={17}/></button></div>
        </div>
      </aside>
      <main className="min-w-0 min-h-screen lg:ml-64">
        <div className="lg:hidden bg-white border-b border-navy-700 px-4 py-3 flex items-center justify-between"><Link to="/dashboard" className="flex items-center gap-2 font-semibold"><TrendingUp className="text-accent-cyan" size={19}/>롱폼 제작실</Link><Link to="/longform/new" className="text-sm rounded-lg bg-accent-cyan text-white px-3 py-2">새 작업</Link></div>
        <div className="p-4 md:p-8">{children}</div>
      </main>
    </div>
  )
}
