import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Clapperboard, Film, Plus, RefreshCw, Search, Upload } from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'
import { formatStatus } from '../constants/jobStatus'

const PAGE_SIZE = 10
const STATUS_CLASS = { READY: 'bg-accent-green/15 text-accent-green', EDITING: 'bg-accent-cyan/15 text-accent-cyan', FAILED: 'bg-accent-red/15 text-accent-red' }
function formatDate(value) { return value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(new Date(value)) : '-' }

export default function ShortsLibrary() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('ALL')
  const [page, setPage] = useState(1)
  const load = async () => { setLoading(true); setError(''); try { const response = await apiClient.get('/shorts'); setProjects(Array.isArray(response.data) ? response.data : []) } catch (e) { if (e.response?.status === 500) setError('쇼츠 목록 API가 서버에서 실패했습니다. Spring/PostgreSQL 상태를 확인한 뒤 새로고침하세요. (HTTP 500)'); else if (!e.response) setError('백엔드 API에 연결할 수 없습니다. Docker Desktop과 Spring 서버가 실행 중인지 확인해 주세요.'); else setError(e.response?.data?.message || '쇼츠 작업 목록을 불러오지 못했습니다.') } finally { setLoading(false) } }
  useEffect(() => { load() }, [])
  const filtered = useMemo(() => projects.filter(project => { const needle = search.trim().toLowerCase(); return (!needle || `${project.title || ''} ${project.parentJobId || ''}`.toLowerCase().includes(needle)) && (status === 'ALL' || project.status === status) }), [projects, search, status])
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  useEffect(() => { if (page > totalPages) setPage(totalPages) }, [page, totalPages])
  const resetPage = (setter) => (value) => { setter(value); setPage(1) }

  return <Layout><div className="max-w-7xl mx-auto space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-accent-violet">쇼츠 제작실</p><h1 className="text-2xl font-bold text-white mt-1">쇼츠 프로젝트</h1><p className="text-sm text-gray-400 mt-2">원본 영상을 업로드해 쇼츠를 만들거나, 롱폼 상세 화면에서 핵심 구간을 선택해 전환합니다.</p></div><div className="flex gap-2"><button onClick={() => navigate('/longform')} className="border border-navy-600 text-white rounded-lg px-4 py-2.5 text-sm font-semibold">완성 롱폼에서 시작</button><button onClick={() => navigate('/shorts/new')} className="bg-accent-cyan text-navy-950 rounded-lg px-4 py-2.5 text-sm font-semibold flex items-center gap-2"><Plus size={16}/>새 쇼츠 만들기</button></div></div>
    <div className="grid md:grid-cols-2 gap-4"><button onClick={() => navigate('/shorts/new')} className="text-left rounded-xl border border-navy-700 bg-navy-800 hover:border-accent-cyan/60 p-5 transition"><Upload size={20} className="text-accent-cyan"/><h2 className="mt-4 font-semibold text-white">원본 영상으로 쇼츠 만들기</h2><p className="mt-2 text-sm text-gray-400">파일을 업로드하거나 원본을 지정해 구간 후보를 만들고 편집합니다.</p></button><button onClick={() => navigate('/longform')} className="text-left rounded-xl border border-navy-700 bg-navy-800 hover:border-accent-cyan/60 p-5 transition"><Film size={20} className="text-accent-violet"/><h2 className="mt-4 font-semibold text-white">완성된 롱폼에서 전환</h2><p className="mt-2 text-sm text-gray-400">롱폼 작업 상세의 ‘쇼츠 만들기’에서 문맥을 보며 핵심 장면을 선택합니다.</p></button></div>
    <section className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden"><div className="p-5 border-b border-navy-700 flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><Clapperboard size={18} className="text-accent-cyan"/><h2 className="font-semibold text-white">쇼츠 작업 목록</h2></div><p className="text-xs text-gray-500 mt-1">행을 열어 구간 편집, 재조립, 미리보기와 발행을 이어서 진행합니다.</p></div><div className="flex gap-2"><label className="relative"><Search size={15} className="absolute left-3 top-2.5 text-gray-500"/><input value={search} onChange={e => resetPage(setSearch)(e.target.value)} placeholder="제목 또는 원본 작업" className="bg-navy-900 border border-navy-600 rounded-lg pl-8 pr-3 py-2 text-xs text-white"/></label><select value={status} onChange={e => resetPage(setStatus)(e.target.value)} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white"><option value="ALL">상태 전체</option><option value="READY">완료</option><option value="EDITING">편집 중</option><option value="FAILED">오류</option></select><button onClick={load} disabled={loading} className="border border-navy-600 rounded-lg px-3 py-2 text-xs text-gray-300 disabled:opacity-50"><RefreshCw size={14} className={loading ? 'animate-spin' : ''}/></button></div></div>
      {error && <div className="m-5 border border-accent-red/40 bg-accent-red/10 text-accent-red rounded-lg px-4 py-3 text-sm">{error}</div>}
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="bg-navy-900/50 text-left text-xs text-gray-400"><tr><th className="px-5 py-3">쇼츠 프로젝트</th><th className="px-3 py-3">원본</th><th className="px-3 py-3">상태</th><th className="px-3 py-3">업데이트</th><th className="px-5 py-3 text-right">작업</th></tr></thead><tbody className="divide-y divide-navy-700">{loading && <tr><td colSpan="5" className="px-5 py-16 text-center text-gray-500">목록을 불러오는 중입니다.</td></tr>}{!loading && filtered.length === 0 && <tr><td colSpan="5" className="px-5 py-16 text-center text-gray-500">조건에 맞는 쇼츠 프로젝트가 없습니다.</td></tr>}{pageItems.map(project => <tr key={project.id} onClick={() => navigate(`/shorts/${project.id}`)} className="cursor-pointer hover:bg-navy-700/40 transition"><td className="px-5 py-4"><div className="font-semibold text-white">{project.title || '제목 없는 쇼츠'}</div><div className="text-xs text-gray-500 mt-1">{project.sourceType === 'LONGFORM' ? '롱폼에서 전환' : '업로드 원본'}</div></td><td className="px-3 py-4 text-gray-300">{project.parentJobId ? `롱폼 작업 #${project.parentJobId}` : '직접 업로드'}</td><td className="px-3 py-4"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_CLASS[project.status] || 'bg-navy-700 text-gray-300'}`}>{formatStatus(project.status || 'EDITING')}</span></td><td className="px-3 py-4 text-xs text-gray-500">{formatDate(project.updatedAt || project.createdAt)}</td><td className="px-5 py-4 text-right text-sm font-semibold text-accent-cyan">편집 계속하기 →</td></tr>)}</tbody></table></div>
      {filtered.length > PAGE_SIZE && <Pagination page={page} totalPages={totalPages} total={filtered.length} onChange={setPage}/>}
    </section>
  </div></Layout>
}

function Pagination({ page, totalPages, total, onChange }) {
  const numbers = pageNumbers(page, totalPages)
  return <div className="px-5 py-3 border-t border-navy-700 flex items-center justify-between text-xs"><span className="text-gray-500">{total}개 중 {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)}</span><div className="flex items-center gap-1"><button aria-label="이전 페이지" disabled={page === 1} onClick={() => onChange(page - 1)} className="border border-navy-600 p-1.5 rounded disabled:opacity-40"><ChevronLeft size={14}/></button>{numbers.map((number, index) => number === '…' ? <span key={`ellipsis-${index}`} className="px-1.5 text-gray-500">…</span> : <button key={number} onClick={() => onChange(number)} className={`min-w-7 h-7 rounded ${number === page ? 'bg-accent-cyan text-navy-950 font-bold' : 'text-gray-400 hover:bg-navy-700'}`}>{number}</button>)}<button aria-label="다음 페이지" disabled={page === totalPages} onClick={() => onChange(page + 1)} className="border border-navy-600 p-1.5 rounded disabled:opacity-40"><ChevronRight size={14}/></button></div></div>
}

function pageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1)
  const middle = [current - 1, current, current + 1].filter(number => number > 1 && number < total)
  return [1, ...(middle[0] > 2 ? ['…'] : []), ...middle, ...(middle.at(-1) < total - 1 ? ['…'] : []), total]
}
