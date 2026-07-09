import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Video, CheckCircle, Clock, AlertCircle, Plus,
  Search, Filter, Zap
} from 'lucide-react'
import Layout from '../components/Layout'
import { jobsApi } from '../api/jobs'
import StockMindMap from '../components/dashboard/StockMindMap'
import TrendingSidebar from '../components/dashboard/TrendingSidebar'

const STATUS_COLOR = {
  READY: 'text-accent-green',
  ASSEMBLING: 'text-accent-cyan',
  FAILED: 'text-accent-red',
  BUDGET_BLOCKED: 'text-accent-red',
  DRAFT: 'text-gray-400',
}

const STATUS_LABEL = {
  DRAFT: '초안',
  KEYWORD_PENDING: '키워드 검토중',
  SCRIPT_PENDING: '스크립트 생성중',
  TTS_PENDING: 'TTS 생성중',
  IMAGES_PENDING: '이미지 생성중',
  ASSEMBLING: '영상 조립중',
  PREVIEW_PENDING: '미리보기 대기',
  SHORTS_SEGMENTS_PENDING: '쇼츠 구간 검토',
  SHORTS_GENERATING: '쇼츠 생성중',
  SHORTS_PREVIEW_PENDING: '쇼츠 미리보기',
  READY: '완료',
  PUBLISHED: '업로드 완료',
  BUDGET_BLOCKED: '예산 초과',
  FAILED: '오류',
}

const CATEGORY_LIST = ['ALL', 'KOSPI', 'KOSDAQ', 'US_STOCKS', 'INDIVIDUAL_STOCK', 'ASSOCIATED_STOCKS', 'GLOBAL_MACRO', 'CRYPTO', 'CUSTOM']
const CATEGORY_LABEL = {
  ALL: '전체',
  KOSPI: 'KOSPI',
  KOSDAQ: 'KOSDAQ',
  US_STOCKS: '미국 주식',
  INDIVIDUAL_STOCK: '개별 종목',
  ASSOCIATED_STOCKS: '연관 종목군',
  GLOBAL_MACRO: '글로벌 거시',
  CRYPTO: '암호화폐',
  CUSTOM: '직접 입력 (CUSTOM)'
}
const MODE_LIST = ['ALL', 'AUTO', 'GUIDED', 'MANUAL']
const STATUS_LIST = [
  'ALL', 'DRAFT', 'KEYWORD_PENDING', 'SCRIPT_PENDING', 'TTS_PENDING', 'IMAGES_PENDING', 
  'ASSEMBLING', 'PREVIEW_PENDING', 'SHORTS_SEGMENTS_PENDING', 'SHORTS_GENERATING', 
  'SHORTS_PREVIEW_PENDING', 'READY', 'PUBLISHED', 'BUDGET_BLOCKED', 'FAILED'
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [quickTitle, setQuickTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('ALL')
  const [category, setCategory] = useState('KOSPI')
  const [duration, setDuration] = useState(20)
  const [autonomy, setAutonomy] = useState('AUTO')
  const [currentPage, setCurrentPage] = useState(1)

  // 정밀 필터 검색 상태
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

  const [selectedTrendingKeyword, setSelectedTrendingKeyword] = useState('주식')
  const [selectedMindmapKeywords, setSelectedMindmapKeywords] = useState([])

  const handleSelectKeyword = (kw) => {
    let nextKeywords;
    if (selectedMindmapKeywords.includes(kw)) {
      nextKeywords = selectedMindmapKeywords.filter(k => k !== kw);
    } else {
      nextKeywords = [...selectedMindmapKeywords, kw];
    }
    setSelectedMindmapKeywords(nextKeywords);
    setQuickTitle(nextKeywords.join(', '));
    if (nextKeywords.length > 0) {
      setSelectedTrendingKeyword(nextKeywords[nextKeywords.length - 1]);
    } else {
      setSelectedTrendingKeyword('주식');
    }
  }

  const { data: jobs = [], refetch } = useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.list,
    refetchInterval: 5000,
  })

  const inProgress = jobs.filter(j =>
    !['READY', 'PUBLISHED', 'FAILED', 'BUDGET_BLOCKED', 'DRAFT'].includes(j.status)
  )
  const completed = jobs.filter(j => ['READY', 'PUBLISHED'].includes(j.status))
  const failed = jobs.filter(j => ['FAILED', 'BUDGET_BLOCKED'].includes(j.status))

  const handleFilterChange = (newFilter) => {
    setFilter(newFilter)
    setCurrentPage(1)
  }

  const handleQuickStart = async (e) => {
    e.preventDefault()
    if (!quickTitle.trim()) return
    setCreating(true)
    try {
      const job = await jobsApi.create({
        title: quickTitle,
        category: category,
        autonomy: autonomy,
        longformTargetMinutes: duration,
        budgetCap: 100,
      })
      if (autonomy !== 'MANUAL') {
        await jobsApi.searchKeyword(job.id, quickTitle, 5)
      }
      navigate(`/jobs/${job.id}`)
    } catch (err) {
      console.error(err)
    } finally {
      setCreating(false)
    }
  }

  // 최신순 정렬 (ID 내림차순) 및 다중 필터 적용
  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(j => {
    // 1. 상단 통계 카드 필터링
    if (filter === 'IN_PROGRESS' && ['READY', 'PUBLISHED', 'FAILED', 'BUDGET_BLOCKED', 'DRAFT'].includes(j.status)) return false
    if (filter === 'COMPLETED' && !['READY', 'PUBLISHED'].includes(j.status)) return false
    if (filter === 'FAILED' && !['FAILED', 'BUDGET_BLOCKED'].includes(j.status)) return false

    // 2. 키워드 검색 필터링
    if (searchQuery && !j.title?.toLowerCase().includes(searchQuery.toLowerCase())) return false

    // 3. 카테고리 필터링
    if (selectedCategory !== 'ALL' && j.category !== selectedCategory) return false

    // 4. 모드 필터링
    if (selectedMode !== 'ALL' && j.autonomy !== selectedMode) return false

    // 5. 상태 상세 필터링
    if (selectedStatus !== 'ALL' && j.status !== selectedStatus) return false

    return true
  })

  const handleResetFilters = () => {
    setSearchQuery('')
    setSelectedCategory('ALL')
    setSelectedMode('ALL')
    setSelectedStatus('ALL')
    setCurrentPage(1)
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <p className="text-gray-400 text-sm mt-1">AI 주식 영상 자동화 플랫폼</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* 좌측 메인 영역 (ColSpan: 3) */}
        <div className="lg:col-span-3 space-y-6">
          
          {/* 통계 카드 */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard
          icon={<Clock className="text-accent-cyan" />}
          label="진행 중"
          value={inProgress.length}
          active={filter === 'IN_PROGRESS'}
          onClick={() => handleFilterChange(filter === 'IN_PROGRESS' ? 'ALL' : 'IN_PROGRESS')}
        />
        <StatCard
          icon={<CheckCircle className="text-accent-green" />}
          label="완료"
          value={completed.length}
          active={filter === 'COMPLETED'}
          onClick={() => handleFilterChange(filter === 'COMPLETED' ? 'ALL' : 'COMPLETED')}
        />
          <StatCard
            icon={<AlertCircle className="text-accent-red" />}
            label="오류"
            value={failed.length}
            active={filter === 'FAILED'}
            onClick={() => handleFilterChange(filter === 'FAILED' ? 'ALL' : 'FAILED')}
          />
        </div>

        {/* 마인드맵 (NEW) */}
        <StockMindMap 
          selectedKeywords={selectedMindmapKeywords}
          onSelectKeyword={handleSelectKeyword} 
        />

        {/* 빠른 영상 시작 */}
        <div className="bg-navy-800 rounded-xl p-6 border border-navy-700">
        <div className="flex flex-wrap gap-4 items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="text-accent-gold" size={20} />
            <h2 className="font-semibold">빠른 영상 시작</h2>
          </div>
          <div className="flex gap-2">
            <select
              value={category}
              onChange={e => setCategory(e.target.value)}
              className="bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-1 text-xs text-accent-cyan font-semibold focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              {CATEGORY_LIST.filter(c => c !== 'ALL').map(cat => (
                <option key={cat} value={cat}>{CATEGORY_LABEL[cat]}</option>
              ))}
            </select>

            <select
              value={duration}
              onChange={e => setDuration(Number(e.target.value))}
              className="bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-1 text-xs text-accent-cyan font-semibold focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              <option value="5">5분</option>
              <option value="10">10분</option>
              <option value="15">15분</option>
              <option value="20">20분</option>
              <option value="30">30분</option>
            </select>

            <select
              value={autonomy}
              onChange={e => setAutonomy(e.target.value)}
              className="bg-navy-700 border border-navy-600 rounded-lg px-2.5 py-1 text-xs text-accent-cyan font-semibold focus:outline-none focus:ring-1 focus:ring-accent-cyan cursor-pointer"
            >
              <option value="AUTO">자동 (AUTO)</option>
              <option value="GUIDED">반자동 (GUIDED)</option>
              <option value="MANUAL">수동 (MANUAL)</option>
            </select>
          </div>
        </div>
        <form onSubmit={handleQuickStart} className="flex gap-3">
          <input
            value={quickTitle}
            onChange={e => setQuickTitle(e.target.value)}
            placeholder="영상 주제 입력 (예: 코스피 전망)"
            className="flex-1 bg-navy-700 border border-navy-700 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
            required
          />
          <button
            type="submit"
            disabled={creating}
            className="flex items-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg px-5 py-2.5 text-sm hover:opacity-90 transition disabled:opacity-50 whitespace-nowrap"
          >
            <Plus size={16} />
            {creating ? '시작 중...' : '영상 만들기'}
          </button>
        </form>
        <p className="text-xs text-gray-500 mt-2">
          {autonomy === 'AUTO' && '키워드 탐색 → 스크립트 → 음성 → 이미지 → 영상 조립까지 완전 자동으로 가동됩니다.'}
          {autonomy === 'GUIDED' && '단계마다 생성 결과를 검토하고 수동 승인/수정하며 진행하는 모드입니다.'}
          {autonomy === 'MANUAL' && '직접 키워드를 작성하거나 영상 조립 구간을 정의하는 모드입니다.'}
          </p>
        </div>

        {/* 정밀 검색 필터 */}
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-4">
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
                <option key={cat} value={cat}>{CATEGORY_LABEL[cat]}</option>
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

      {/* 최근 작업 목록 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-700">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold text-sm">작업 목록 ({filteredJobs.length}개)</h2>
            {filter !== 'ALL' && (
              <span className="text-[10px] bg-accent-cyan/10 text-accent-cyan px-2 py-0.5 rounded-full font-semibold">
                필터: {filter === 'IN_PROGRESS' ? '진행 중' : filter === 'COMPLETED' ? '완료' : '오류'}
              </span>
            )}
          </div>
          <button
            onClick={() => navigate('/jobs')}
            className="text-xs text-accent-cyan hover:underline font-medium"
          >
            롱폼 작업 리스트 보기
          </button>
        </div>
        {filteredJobs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>조건에 부합하는 작업이 없습니다.</p>
            {(filter !== 'ALL' || searchQuery || selectedCategory !== 'ALL' || selectedMode !== 'ALL' || selectedStatus !== 'ALL') && (
              <button
                onClick={() => { handleFilterChange('ALL'); handleResetFilters(); }}
                className="text-xs text-accent-cyan hover:underline mt-2"
              >
                전체 초기화하기
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
                  <div className="flex items-center gap-3 overflow-hidden mr-4">
                    <div className="w-9 h-9 bg-navy-700 rounded-lg flex items-center justify-center flex-shrink-0">
                      <Video size={18} className="text-gray-400" />
                    </div>
                    <div className="overflow-hidden">
                      {/* 말줄임표 처리로 가로 크기 찌그러짐 차단 */}
                      <div className="text-sm font-semibold truncate text-white max-w-[320px]" title={job.title}>
                        {job.title}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {CATEGORY_LABEL[job.category] || job.category} · {job.longformTargetMinutes}분 · {job.autonomy}
                      </div>
                    </div>
                  </div>
                  <span className={`text-xs font-semibold flex-shrink-0 ${STATUS_COLOR[job.status] || 'text-gray-400'}`}>
                    {STATUS_LABEL[job.status] || job.status}
                  </span>
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
      </div>

      {/* 우측 사이드바 영역 (ColSpan: 1) */}
      <div className="lg:col-span-1">
        <TrendingSidebar keyword={selectedTrendingKeyword} />
      </div>
    </div>
  </Layout>
  )
}

function StatCard({ icon, label, value, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left bg-navy-800 rounded-xl p-5 border transition hover:bg-navy-700/40 cursor-pointer ${
        active ? 'border-accent-cyan shadow-lg shadow-accent-cyan/10' : 'border-navy-700'
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        {icon}
        {active && <span className="text-[10px] bg-accent-cyan/20 text-accent-cyan px-1.5 py-0.5 rounded font-bold">필터 적용</span>}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm text-gray-400 mt-1">{label}</div>
    </button>
  )
}
