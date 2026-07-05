import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Video, ChevronRight, Filter, Search } from 'lucide-react'
import Layout from '../components/Layout'
import { jobsApi } from '../api/jobs'

const CATEGORY_LIST = ['ALL', 'KOSPI', 'KOSDAQ', 'US_STOCKS', 'INDIVIDUAL_STOCK', 'GLOBAL_MACRO', 'CRYPTO', 'CUSTOM']
const MODE_LIST = ['ALL', 'AUTO', 'GUIDED', 'MANUAL']
const STATUS_LIST = [
  'ALL', 'DRAFT', 'KEYWORD_PENDING', 'SCRIPT_PENDING', 'TTS_PENDING', 'IMAGES_PENDING', 
  'ASSEMBLING', 'PREVIEW_PENDING', 'SHORTS_SEGMENTS_PENDING', 'SHORTS_GENERATING', 
  'SHORTS_PREVIEW_PENDING', 'READY', 'PUBLISHED', 'BUDGET_BLOCKED', 'FAILED'
]

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
  const [currentPage, setCurrentPage] = useState(1)

  // 정밀 필터 검색 상태
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

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

  // 최신순 정렬 (ID 내림차순) 및 필터 융합 적용
  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(job => {
    // 1. 카테고리 필터링
    if (selectedCategory !== 'ALL' && job.category !== selectedCategory) return false

    // 2. 키워드 검색 필터링
    if (searchQuery && !job.title?.toLowerCase().includes(searchQuery.toLowerCase())) return false

    // 3. 자율성 모드 필터링
    if (selectedMode !== 'ALL' && job.autonomy !== selectedMode) return false

    // 4. 상태 필터링
    if (selectedStatus !== 'ALL' && job.status !== selectedStatus) return false

    return true
  })

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

      {/* 정밀 검색 및 필터링 제어판 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700 p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={16} className="text-accent-cyan" />
          <span className="text-sm font-semibold">정밀 검색 및 필터</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* 검색 키워드 */}
          <div className="relative">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search size={14} className="text-gray-400" />
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              placeholder="작업 제목 검색..."
              className="w-full bg-navy-700 border border-navy-600 rounded-lg pl-9 pr-3 py-2 text-xs text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-accent-cyan"
            />
          </div>

          {/* 카테고리 */}
          <div>
            <select
              value={selectedCategory}
              onChange={e => { setSelectedCategory(e.target.value); setCurrentPage(1); }}
              className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              <option value="ALL">카테고리: 전체</option>
              {CATEGORY_LIST.filter(c => c !== 'ALL').map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          {/* 모드 */}
          <div>
            <select
              value={selectedMode}
              onChange={e => { setSelectedMode(e.target.value); setCurrentPage(1); }}
              className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              <option value="ALL">모드: 전체</option>
              {MODE_LIST.filter(m => m !== 'ALL').map(mode => (
                <option key={mode} value={mode}>{mode}</option>
              ))}
            </select>
          </div>

          {/* 상태 */}
          <div>
            <select
              value={selectedStatus}
              onChange={e => { setSelectedStatus(e.target.value); setCurrentPage(1); }}
              className="w-full bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              <option value="ALL">상태: 전체</option>
              {STATUS_LIST.filter(s => s !== 'ALL').map(status => (
                <option key={status} value={status}>{STATUS_LABEL[status] || status}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 필터 초기화 버튼 */}
        {(searchQuery || selectedCategory !== 'ALL' || selectedMode !== 'ALL' || selectedStatus !== 'ALL') && (
          <div className="flex justify-end mt-3">
            <button
              onClick={handleResetFilters}
              className="text-[11px] text-accent-cyan hover:underline"
            >
              필터 전체 초기화
            </button>
          </div>
        )}
      </div>

      {/* 작업 목록 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
        {filteredJobs.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>작업이 없습니다.</p>
            {(searchQuery || selectedCategory !== 'ALL' || selectedMode !== 'ALL' || selectedStatus !== 'ALL') && (
              <button
                onClick={handleResetFilters}
                className="text-xs text-accent-cyan hover:underline mt-2"
              >
                필터 초기화하기
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="divide-y divide-navy-700">
              {filteredJobs.slice((currentPage - 1) * 10, currentPage * 10).map(job => (
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
                      {/* 말줄임표 처리로 가로폭 찌그러짐 원천 봉쇄 */}
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
                    <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                      STATUS_COLOR[job.status] || 'bg-navy-700 text-gray-400'
                    }`}>
                      {STATUS_LABEL[job.status] || job.status}
                    </span>
                    <ChevronRight size={16} className="text-gray-600" />
                  </div>
                </button>
              ))}
            </div>

            {/* 페이지네이션 제어기 */}
            {filteredJobs.length > 10 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-navy-700 bg-navy-900/20">
                <div className="text-xs text-gray-400">
                  총 {filteredJobs.length}개 중 {Math.min((currentPage - 1) * 10 + 1, filteredJobs.length)} - {Math.min(currentPage * 10, filteredJobs.length)} 표시
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-2.5 py-1.5 rounded-lg bg-navy-700 border border-navy-600 text-xs font-semibold hover:bg-navy-600 transition disabled:opacity-30 disabled:hover:bg-navy-700"
                  >
                    이전
                  </button>
                  {Array.from({ length: Math.ceil(filteredJobs.length / 10) }).map((_, i) => {
                    const pageNum = i + 1;
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition border ${
                          currentPage === pageNum
                            ? 'bg-accent-cyan text-navy-950 border-accent-cyan shadow-sm shadow-accent-cyan/20'
                            : 'bg-navy-800 text-gray-300 border-navy-700 hover:bg-navy-700'
                        }`}
                      >
                        {pageNum}
                      </button>
                    )
                  })}
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(filteredJobs.length / 10)))}
                    disabled={currentPage === Math.ceil(filteredJobs.length / 10)}
                    className="px-2.5 py-1.5 rounded-lg bg-navy-700 border border-navy-600 text-xs font-semibold hover:bg-navy-600 transition disabled:opacity-30 disabled:hover:bg-navy-700"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}
          </>
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
