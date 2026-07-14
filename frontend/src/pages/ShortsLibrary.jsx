import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clapperboard, Plus, RefreshCw, Film, Clock, Upload } from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'

function formatDate(value) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

const STATUS_STYLE = {
  READY: 'bg-accent-green/10 text-accent-green border-accent-green/20',
  EDITING: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/20',
  FAILED: 'bg-accent-red/10 text-accent-red border-accent-red/20',
}

export default function ShortsLibrary() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get('/shorts')
      setProjects(response.data || [])
    } catch (e) {
      setError(e.response?.data?.message || '쇼츠 작업 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-accent-cyan text-sm font-semibold"><Clapperboard size={18} /> 쇼츠 작업</div>
            <h1 className="text-2xl font-bold text-white mt-1">독립 쇼츠 프로젝트</h1>
            <p className="text-sm text-gray-400 mt-2">롱폼·업로드 원본과 분리되어 저장된 쇼츠 편집과 결과물입니다.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={load} disabled={loading} className="border border-navy-600 text-gray-300 hover:text-white px-3 py-2 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> 새로고침
            </button>
            <button onClick={() => navigate('/shorts/new')} className="bg-accent-cyan text-navy-950 font-bold px-4 py-2 rounded-lg text-sm flex items-center gap-2 hover:opacity-90">
              <Plus size={16} /> 새 쇼츠 만들기
            </button>
          </div>
        </div>

        {error && <div className="border border-accent-red/40 bg-accent-red/10 text-accent-red rounded-lg px-4 py-3 text-sm">{error}</div>}

        {loading ? (
          <div className="py-20 text-center text-gray-400"><RefreshCw size={22} className="animate-spin mx-auto mb-3" />목록을 불러오는 중입니다.</div>
        ) : projects.length === 0 ? (
          <div className="border border-dashed border-navy-600 rounded-xl py-20 text-center">
            <Film size={34} className="mx-auto text-navy-500 mb-3" />
            <div className="text-white font-semibold">아직 저장된 쇼츠 작업이 없습니다.</div>
            <div className="text-sm text-gray-400 mt-2">영상을 업로드하거나 롱폼에서 쇼츠를 만들면 여기에 표시됩니다.</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map(project => (
              <button key={project.id} onClick={() => navigate(`/shorts/${project.id}`)} className="text-left bg-navy-800 border border-navy-700 hover:border-accent-cyan/60 rounded-xl p-5 transition group">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-white font-semibold truncate group-hover:text-accent-cyan">{project.title}</div>
                    <div className="text-xs text-gray-500 mt-1">원본 Job #{project.parentJobId ?? '-'}</div>
                  </div>
                  <span className={`shrink-0 border rounded-full px-2 py-1 text-[11px] font-semibold ${STATUS_STYLE[project.status] || 'bg-navy-700 text-gray-400 border-navy-600'}`}>{project.status || 'EDITING'}</span>
                </div>
                <div className="mt-5 space-y-2 text-xs text-gray-400">
                  <div className="flex items-center gap-2"><Upload size={13} />{project.sourceType === 'LONGFORM' ? '롱폼 연동' : '업로드 원본'}</div>
                  <div className="flex items-center gap-2"><Clock size={13} />{formatDate(project.updatedAt || project.createdAt)}</div>
                </div>
                <div className="mt-5 text-xs text-accent-cyan font-semibold">편집기 열기 →</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
