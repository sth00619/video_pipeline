import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Video, ChevronRight, Filter } from 'lucide-react'
import Layout from '../components/Layout'
import { jobsApi } from '../api/jobs'

const CATEGORIES = ['전체', 'KOSPI', 'KOSDAQ', 'US_STOCKS', 'INDIVIDUAL_STOCK', 'GLOBAL_MACRO', 'CRYPTO', 'CUSTOM']
const AUTONOMY_LABEL = { MANUAL: '수동', GUIDED: '반자동', AUTO: '자동' }
const STATUS_LABEL = {
  DRAFT: '초안', KEYWORD_PENDING: '키워드', SCRIPT_PENDING: '스크립트',
  TTS_PENDING: 'TTS', IMAGES_PENDING: '이미지', ASSEMBLING: '조립중',
  PREVIEW_PENDING: '미리보기', READY: '완료', PUBLISHED: '업로드됨',
  BUDGET_BLOCKED: '예산초과', FAILED: '오류',
  SHORTS_SEGMENTS_PENDING: '쇼츠구간', SHORTS_GENERATING: '쇼츠생성',
  SHORTS_PREVIEW_PENDING: '쇼츠미리보기',
}
const STATUS_COLOR = {
  READY: 'bg-accent-green/20 text-accent-green',
  PUBLISHED: 'bg-accent-green/20 text-accent-green',
  ASSEMBLING: 'bg-accent-cyan/20 text-accent-cyan',
  FAILED: 'bg-accent-red/20 text-accent-red',
  BUDGET_BLOCKED: 'bg-accent-red/20 text-accent-red',
  DRAFT: 'bg-gray-700/50 text-gray-400',
}

export default function Jobs() {
  const navigate = useNavigate()
  const [showModal, setShowModal] = useState(false)
  const [filter, setFilter] = useState('전체')
  const [form, setForm] = useState({
    title: '', category: 'KOSPI', autonomy: 'AUTO',
    longformTargetMinutes: 20, budgetCap: 100,
  })
  const [creating, setCreating] = useState(false)

  const { data: jobs = [], refetch } = useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.list,
    refetchInterval: 5000,
  })

  const filtered = filter === '전체' ? jobs : jobs.filter(j => j.category === filter)

  const handleCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    try {
      const job = await jobsApi.create(form)
      setShowModal(false)
      navigate(`/jobs/${job.id}`)
    } catch (err) {
      console.error(err)
    } finally {
      setCreating(false)
    }
  }

  return (
    <Layout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">롱폼 작업</h1>
          <p className="text-gray-400 text-sm mt-1">{jobs.length}개 작업</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg px-5 py-2.5 text-sm hover:opacity-90 transition"
        >
          <Plus size={16} />
          새 작업
        </button>
      </div>

      {/* 카테고리 필터 */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition ${
              filter === cat
                ? 'bg-accent-cyan text-navy-950 font-semibold'
                : 'bg-navy-800 text-gray-400 hover:bg-navy-700'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 작업 목록 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700">
        {filtered.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>작업이 없습니다.</p>
          </div>
        ) : (
          <div className="divide-y divide-navy-700">
            {filtered.map(job => (
              <button
                key={job.id}
                onClick={() => navigate(`/jobs/${job.id}`)}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-navy-700/50 transition text-left"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-navy-700 rounded-lg flex items-center justify-center">
                    <Video size={18} className="text-gray-400" />
                  </div>
                  <div>
                    <div className="font-medium">{job.title}</div>
                    <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                      <span>{job.category}</span>
                      <span>·</span>
                      <span>{job.longformTargetMinutes}분</span>
                      <span>·</span>
                      <span>{AUTONOMY_LABEL[job.autonomy] || job.autonomy}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                    STATUS_COLOR[job.status] || 'bg-navy-700 text-gray-400'
                  }`}>
                    {STATUS_LABEL[job.status] || job.status}
                  </span>
                  <ChevronRight size={16} className="text-gray-600" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 새 작업 모달 */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-navy-800 rounded-xl p-8 w-full max-w-md border border-navy-700 shadow-2xl">
            <h2 className="text-lg font-bold mb-6">새 롱폼 영상 만들기</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">영상 제목</label>
                <input
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="예: 코스피 주간 전망 분석"
                  className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  required
                  autoFocus
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">카테고리</label>
                  <select
                    value={form.category}
                    onChange={e => setForm({ ...form, category: e.target.value })}
                    className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  >
                    <option value="KOSPI">코스피</option>
                    <option value="KOSDAQ">코스닥</option>
                    <option value="US_STOCKS">미국 주식</option>
                    <option value="INDIVIDUAL_STOCK">개별 종목</option>
                    <option value="GLOBAL_MACRO">글로벌 매크로</option>
                    <option value="CRYPTO">암호화폐</option>
                    <option value="CUSTOM">기타</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">자율성 모드</label>
                  <select
                    value={form.autonomy}
                    onChange={e => setForm({ ...form, autonomy: e.target.value })}
                    className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  >
                    <option value="AUTO">자동 (AUTO)</option>
                    <option value="GUIDED">반자동 (GUIDED)</option>
                    <option value="MANUAL">수동 (MANUAL)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">목표 길이</label>
                  <select
                    value={form.longformTargetMinutes}
                    onChange={e => setForm({ ...form, longformTargetMinutes: Number(e.target.value) })}
                    className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  >
                    <option value={10}>10분</option>
                    <option value={15}>15분</option>
                    <option value={20}>20분</option>
                    <option value={30}>30분</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">예산 ($)</label>
                  <input
                    type="number"
                    value={form.budgetCap}
                    onChange={e => setForm({ ...form, budgetCap: Number(e.target.value) })}
                    min={1} max={1000}
                    className="w-full bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  />
                </div>
              </div>

              {form.autonomy !== 'AUTO' && (
                <div className="bg-navy-700/50 rounded-lg px-4 py-3 text-xs text-gray-400">
                  {form.autonomy === 'GUIDED'
                    ? '반자동: 키워드 선택과 최종 미리보기만 검토하고 나머지는 자동으로 진행됩니다.'
                    : '수동: 각 단계마다 검토 후 승인해야 다음 단계로 진행됩니다.'}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 bg-navy-700 text-gray-300 rounded-lg py-2.5 text-sm hover:bg-navy-600 transition"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 bg-accent-cyan text-navy-950 font-semibold rounded-lg py-2.5 text-sm hover:opacity-90 transition disabled:opacity-50"
                >
                  {creating ? '생성 중...' : '작업 시작'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Layout>
  )
}
