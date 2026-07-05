import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Shield, DollarSign, Video, Search, Filter } from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'

const CATEGORY_LIST = ['ALL', 'KOSPI', 'KOSDAQ', 'US_STOCKS', 'INDIVIDUAL_STOCK', 'GLOBAL_MACRO', 'CRYPTO', 'CUSTOM']
const MODE_LIST = ['ALL', 'AUTO', 'GUIDED', 'MANUAL']
const STATUS_LIST = [
  'ALL', 'DRAFT', 'KEYWORD_PENDING', 'SCRIPT_PENDING', 'TTS_PENDING', 'IMAGES_PENDING', 
  'ASSEMBLING', 'PREVIEW_PENDING', 'SHORTS_SEGMENTS_PENDING', 'SHORTS_GENERATING', 
  'SHORTS_PREVIEW_PENDING', 'READY', 'PUBLISHED', 'BUDGET_BLOCKED', 'FAILED'
]

const STATUS_LABEL = {
  DRAFT: '초안', KEYWORD_PENDING: '키워드 대기', SCRIPT_PENDING: '스크립트 생성',
  TTS_PENDING: 'TTS 생성', IMAGES_PENDING: '이미지 생성', ASSEMBLING: '조립중',
  PREVIEW_PENDING: '미리보기', READY: '완료', PUBLISHED: '업로드됨',
  BUDGET_BLOCKED: '예산초과', FAILED: '오류',
  SHORTS_SEGMENTS_PENDING: '쇼츠구간', SHORTS_GENERATING: '쇼츠생성',
  SHORTS_PREVIEW_PENDING: '쇼츠미리보기',
}

export default function Admin() {
  const navigate = useNavigate()
  const [adminFilter, setAdminFilter] = useState('ALL')
  const [currentPage, setCurrentPage] = useState(1)

  // 상세 필터 검색 상태
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

  const { data: jobs = [] } = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: () => apiClient.get('/jobs').then(r => r.data),
  })

  const totalCost = jobs.reduce((sum, j) => sum + (parseFloat(j.costAccumulated) || 0), 0)
  const completedJobs = jobs.filter(j => ['READY', 'PUBLISHED'].includes(j.status))

  const handleFilterChange = (filter) => {
    setAdminFilter(filter)
    setCurrentPage(1)
  }

  // 최신순 (ID 내림차순) 정렬 및 필터 적용
  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(job => {
    // 1. 상단 큰 카드 필터링 (전체 vs 완료된 영상)
    if (adminFilter === 'COMPLETED' && !['READY', 'PUBLISHED'].includes(job.status)) {
      return false
    }

    // 2. 검색 키워드 필터링 (제목 또는 작성자)
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      const titleMatch = job.title?.toLowerCase().includes(query)
      const creatorMatch = job.createdBy?.toLowerCase().includes(query)
      if (!titleMatch && !creatorMatch) return false
    }

    // 3. 카테고리 필터링
    if (selectedCategory !== 'ALL' && job.category !== selectedCategory) {
      return false
    }

    // 4. 자율성 모드 필터링
    if (selectedMode !== 'ALL' && job.autonomy !== selectedMode) {
      return false
    }

    // 5. 상태 필터링
    if (selectedStatus !== 'ALL' && job.status !== selectedStatus) {
      return false
    }

    return true
  })

  // 리셋 헬퍼
  const handleResetFilters = () => {
    setSearchQuery('')
    setSelectedCategory('ALL')
    setSelectedMode('ALL')
    setSelectedStatus('ALL')
    setCurrentPage(1)
  }

  return (
    <Layout>
      <div className="flex items-center gap-3 mb-6">
        <Shield className="text-accent-gold" size={24} />
        <div>
          <h1 className="text-2xl font-bold">관리자</h1>
          <p className="text-gray-400 text-sm mt-0.5">시스템 현황 및 통계</p>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <button
          onClick={() => handleFilterChange('ALL')}
          className={`text-left bg-navy-800 rounded-xl p-5 border transition hover:bg-navy-700/40 cursor-pointer ${
            adminFilter === 'ALL' ? 'border-accent-cyan shadow-sm shadow-accent-cyan/10' : 'border-navy-700'
          }`}
        >
          <Video className="text-accent-cyan mb-3" size={20} />
          <div className="text-2xl font-bold">{jobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">전체 작업</div>
        </button>
        <button
          onClick={() => handleFilterChange('COMPLETED')}
          className={`text-left bg-navy-800 rounded-xl p-5 border transition hover:bg-navy-700/40 cursor-pointer ${
            adminFilter === 'COMPLETED' ? 'border-accent-green shadow-sm shadow-accent-green/10' : 'border-navy-700'
          }`}
        >
          <Video className="text-accent-green mb-3" size={20} />
          <div className="text-2xl font-bold">{completedJobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">완료된 영상</div>
        </button>
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
          <DollarSign className="text-accent-gold mb-3" size={20} />
          <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
          <div className="text-sm text-gray-400 mt-1">총 누적 비용</div>
        </div>
      </div>

      {/* 필터 및 검색 바 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700 p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={16} className="text-accent-cyan" />
          <span className="text-sm font-semibold">정밀 검색 및 필터</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* 검색창 */}
          <div className="relative">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search size={14} className="text-gray-400" />
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              placeholder="제목, 작성자 검색..."
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

      {/* 전체 작업 테이블 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-navy-700 flex items-center justify-between">
          <h2 className="font-semibold text-sm">전체 작업 목록 ({filteredJobs.length}개)</h2>
          {adminFilter !== 'ALL' && (
            <span className="text-[10px] bg-accent-green/10 text-accent-green px-2 py-0.5 rounded-full font-bold">
              완료 필터 적용 중
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          {/* table-fixed 레이아웃 적용 및 컬럼 가로폭 비율 할당 */}
          <table className="w-full text-sm table-fixed min-w-[950px]">
            <thead>
              <tr className="border-b border-navy-700 bg-navy-900/10">
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[8%]">ID</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[32%]">제목</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[15%]">카테고리</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[10%]">모드</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[12%]">상태</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[10%]">비용</th>
                <th className="text-left px-6 py-3 text-gray-400 font-medium w-[13%]">작성자</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-700">
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan="7" className="text-center py-12 text-gray-500">
                    검색 조건에 부합하는 작업이 없습니다.
                  </td>
                </tr>
              ) : (
                filteredJobs.slice((currentPage - 1) * 10, currentPage * 10).map(job => (
                  <tr
                    key={job.id}
                    onClick={() => navigate(`/jobs/${job.id}`)}
                    className="hover:bg-navy-700/50 transition cursor-pointer"
                  >
                    <td className="px-6 py-3.5 text-gray-400">#{job.id}</td>
                    {/* 제목에 말줄임표 처리(truncate)를 주어 가로폭 찌그러짐을 영구 차단 */}
                    <td className="px-6 py-3.5 font-medium text-white truncate max-w-[280px]" title={job.title}>
                      {job.title}
                    </td>
                    <td className="px-6 py-3.5 text-gray-400">{job.category}</td>
                    <td className="px-6 py-3.5 text-gray-400">{job.autonomy}</td>
                    <td className="px-6 py-3.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        job.status === 'READY' ? 'bg-accent-green/20 text-accent-green' :
                        job.status === 'FAILED' ? 'bg-accent-red/20 text-accent-red' :
                        'bg-navy-700 text-gray-400'
                      }`}>
                        {STATUS_LABEL[job.status] || job.status}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-gray-400">${parseFloat(job.costAccumulated || 0).toFixed(2)}</td>
                    <td className="px-6 py-3.5 text-gray-400 truncate max-w-[120px]" title={job.createdBy}>
                      {job.createdBy}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
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
      </div>
    </Layout>
  )
}
