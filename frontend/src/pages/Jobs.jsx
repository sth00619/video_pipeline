import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Video, ChevronRight } from 'lucide-react'
import Layout from '../components/Layout'
import JobFilterBar from '../components/JobFilterBar'
import Pagination from '../components/Pagination'
import StatusBadge from '../components/StatusBadge'
import { jobsApi } from '../api/jobs'
import { AUTONOMY_LABEL } from '../constants/jobStatus'
import apiClient from '../api/client'

/**
 * 이전에는 이 파일이 CATEGORY_LIST / STATUS_LIST / STATUS_LABEL / STATUS_COLOR /
 * 필터 마크업 / 페이지네이션 마크업을 전부 자체적으로 갖고 있었고, Dashboard.jsx /
 * Admin.jsx도 거의 동일한 코드를 각자 복붙해서 갖고 있었습니다. 그 결과
 * Dashboard에만 있던 ASSOCIATED_STOCKS 카테고리가 여기엔 없는 등 세 페이지가
 * 조금씩 어긋나 있었습니다. 이제 공통 컴포넌트(JobFilterBar/Pagination/StatusBadge)와
 * 공통 상수(constants/jobStatus.js)를 가져다 쓰는 것으로 통일했습니다.
 */
export default function Jobs() {
  const navigate = useNavigate()
  const [showModal, setShowModal] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)

  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

  const [form, setForm] = useState({
    title: '', category: 'KOSPI', autonomy: 'AUTO',
    longformTargetMinutes: 20, budgetCap: 100, channelId: ''
  })
  const [creating, setCreating] = useState(false)

  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.list,
    refetchInterval: 5000,
  })

  const { data: channels = [] } = useQuery({
    queryKey: ['channels'],
    queryFn: () => apiClient.get('/channels').then(r => r.data),
  })

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

  const handleResetFilters = () => {
    setSearchQuery('')
    setSelectedCategory('ALL')
    setSelectedMode('ALL')
    setSelectedStatus('ALL')
    setCurrentPage(1)
  }

  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(job => {
    if (selectedCategory !== 'ALL' && job.category !== selectedCategory) return false
    if (searchQuery && !job.title?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    if (selectedMode !== 'ALL' && job.autonomy !== selectedMode) return false
    if (selectedStatus !== 'ALL' && job.status !== selectedStatus) return false
    return true
  })

  const pageItems = filteredJobs.slice((currentPage - 1) * 10, currentPage * 10)

  return (
    <Layout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">롱폼 작업</h1>
          <p className="text-gray-400 text-sm mt-1">{filteredJobs.length}개 작업</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg px-5 py-2.5 text-sm hover:opacity-90 transition"
        >
          <Plus size={16} />
          새 작업
        </button>
      </div>

      <div className="mb-6">
        <JobFilterBar
          searchQuery={searchQuery}
          onSearchChange={v => { setSearchQuery(v); setCurrentPage(1) }}
          category={selectedCategory}
          onCategoryChange={v => { setSelectedCategory(v); setCurrentPage(1) }}
          mode={selectedMode}
          onModeChange={v => { setSelectedMode(v); setCurrentPage(1) }}
          status={selectedStatus}
          onStatusChange={v => { setSelectedStatus(v); setCurrentPage(1) }}
          onReset={handleResetFilters}
        />
      </div>

      <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
        {filteredJobs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>조건에 맞는 작업이 없습니다.</p>
          </div>
        ) : (
          <>
            <div className="divide-y divide-navy-700">
              {pageItems.map(job => (
                <button
                  key={job.id}
                  onClick={() => navigate(`/jobs/${job.id}`)}
                  className="w-full flex items-center justify-between px-6 py-4 hover:bg-navy-700/50 transition text-left"
                >
                  <div className="flex items-center gap-4 overflow-hidden mr-4">
                    <div className="w-10 h-10 bg-navy-700 rounded-lg flex items-center justify-center flex-shrink-0">
                      <Video size={18} className="text-gray-400" />
                    </div>
                    <div className="overflow-hidden">
                      <div className="font-semibold text-white truncate max-w-[340px]" title={job.title}>
                        {job.title}
                      </div>
                      <div className="text-xs text-gray-400 mt-1 flex items-center gap-2">
                        <span>{job.category}</span>
                        <span>·</span>
                        <span>{job.longformTargetMinutes}분</span>
                        <span>·</span>
                        <span>{AUTONOMY_LABEL[job.autonomy] || job.autonomy}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <StatusBadge status={job.status} small />
                    <ChevronRight size={16} className="text-gray-600" />
                  </div>
                </button>
              ))}
            </div>

            <Pagination
              total={filteredJobs.length}
              currentPage={currentPage}
              onChange={setCurrentPage}
            />
          </>
        )}
      </div>

      {/* 새 작업 모달 (빠른 생성용 — 상세 마법사는 /jobs/new) */}
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

              <div>
                <label className="block text-sm text-gray-400 mb-1">대상 채널</label>
                <select
                  value={form.channelId || ''}
                  onChange={e => setForm({ ...form, channelId: e.target.value || null })}
                  className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                >
                  <option value="">채널 선택 안 함 (기본)</option>
                  {channels.map(c => (
                    <option key={c.channelId} value={c.channelId}>
                      {c.channelName} ({c.channelId})
                    </option>
                  ))}
                </select>
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
                    <option value={1}>1분 테스트</option>
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
