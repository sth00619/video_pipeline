import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Video, CheckCircle, Clock, AlertCircle, Plus, Zap } from 'lucide-react'
import Layout from '../components/Layout'
import JobFilterBar from '../components/JobFilterBar'
import Pagination from '../components/Pagination'
import StatusBadge from '../components/StatusBadge'
import { jobsApi } from '../api/jobs'
import StockMindMap from '../components/dashboard/StockMindMap'
import TrendingSidebar from '../components/dashboard/TrendingSidebar'
import {
  CATEGORIES, isInProgress, isCompleted, isError,
} from '../constants/jobStatus'

export default function Dashboard() {
  const navigate = useNavigate()
  const [quickTitle, setQuickTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('ALL')
  const [category, setCategory] = useState('KOSPI')
  const [duration, setDuration] = useState(20)
  const [autonomy, setAutonomy] = useState('AUTO')
  const [currentPage, setCurrentPage] = useState(1)

  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

  const [selectedTrendingKeyword, setSelectedTrendingKeyword] = useState('주식')
  const [selectedMindmapKeywords, setSelectedMindmapKeywords] = useState([])

  const handleSelectKeyword = (kw) => {
    let nextKeywords
    if (selectedMindmapKeywords.includes(kw)) {
      nextKeywords = selectedMindmapKeywords.filter(k => k !== kw)
    } else {
      nextKeywords = [...selectedMindmapKeywords, kw]
    }
    setSelectedMindmapKeywords(nextKeywords)
    setQuickTitle(nextKeywords.join(', '))
    setSelectedTrendingKeyword(nextKeywords.length > 0 ? nextKeywords[nextKeywords.length - 1] : '주식')
  }

  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: jobsApi.list,
    refetchInterval: 5000,
  })

  const inProgress = jobs.filter(j => isInProgress(j.status))
  const completed = jobs.filter(j => isCompleted(j.status))
  const failed = jobs.filter(j => isError(j.status))

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
        title: quickTitle, category, autonomy,
        longformTargetMinutes: duration, budgetCap: 100,
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

  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(j => {
    if (filter === 'IN_PROGRESS' && !isInProgress(j.status)) return false
    if (filter === 'COMPLETED' && !isCompleted(j.status)) return false
    if (filter === 'FAILED' && !isError(j.status)) return false
    if (searchQuery && !j.title?.toLowerCase().includes(searchQuery.toLowerCase())) return false
    if (selectedCategory !== 'ALL' && j.category !== selectedCategory) return false
    if (selectedMode !== 'ALL' && j.autonomy !== selectedMode) return false
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

  const pageItems = filteredJobs.slice((currentPage - 1) * 10, currentPage * 10)

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <p className="text-gray-400 text-sm mt-1">AI 주식 영상 자동화 플랫폼</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3 space-y-6">

          <div className="grid grid-cols-3 gap-4">
            <StatCard
              icon={<Clock className="text-accent-cyan" />}
              label="진행 중" value={inProgress.length}
              active={filter === 'IN_PROGRESS'}
              onClick={() => handleFilterChange(filter === 'IN_PROGRESS' ? 'ALL' : 'IN_PROGRESS')}
              glow="glow-cyan"
            />
            <StatCard
              icon={<CheckCircle className="text-accent-green" />}
              label="완료" value={completed.length}
              active={filter === 'COMPLETED'}
              onClick={() => handleFilterChange(filter === 'COMPLETED' ? 'ALL' : 'COMPLETED')}
              glow="glow-green"
            />
            <StatCard
              icon={<AlertCircle className="text-accent-red" />}
              label="오류" value={failed.length}
              active={filter === 'FAILED'}
              onClick={() => handleFilterChange(filter === 'FAILED' ? 'ALL' : 'FAILED')}
              glow="glow-gold"
            />
          </div>

          <StockMindMap
            selectedKeywords={selectedMindmapKeywords}
            onSelectKeyword={handleSelectKeyword}
          />

          <div className="bg-hero-gradient bg-candle-pattern rounded-xl p-6 border border-accent-gold/20 shadow-card-lg relative overflow-hidden">
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
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
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
                <button
                  onClick={() => { handleFilterChange('ALL'); handleResetFilters() }}
                  className="text-xs text-accent-cyan hover:underline mt-2"
                >
                  전체 초기화하기
                </button>
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
                      <div className="flex items-center gap-3 overflow-hidden mr-4">
                        <div className="w-9 h-9 bg-navy-700 rounded-lg flex items-center justify-center flex-shrink-0">
                          <Video size={18} className="text-gray-400" />
                        </div>
                        <div className="overflow-hidden">
                          <div className="text-sm font-semibold truncate text-white max-w-[320px]" title={job.title}>
                            {job.title}
                          </div>
                          <div className="text-xs text-gray-400 mt-0.5">
                            {job.category} · {job.longformTargetMinutes}분 · {job.autonomy}
                          </div>
                        </div>
                      </div>
                      <StatusBadge status={job.status} small />
                    </button>
                  ))}
                </div>
                <Pagination total={filteredJobs.length} currentPage={currentPage} onChange={setCurrentPage} />
              </>
            )}
          </div>
        </div>

        <div className="lg:col-span-1">
          <TrendingSidebar keyword={selectedTrendingKeyword} />
        </div>
      </div>
    </Layout>
  )
}

function StatCard({ icon, label, value, active, onClick, glow = 'glow-cyan' }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left bg-card-gradient rounded-xl p-5 border transition hover:border-navy-500 cursor-pointer ${
        active ? `border-accent-cyan shadow-${glow}` : 'border-navy-700 shadow-card'
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        {icon}
        {active && <span className="text-xs bg-accent-cyan/20 text-accent-cyan px-2 py-0.5 rounded font-bold">필터 적용</span>}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm text-navy-400 mt-1">{label}</div>
    </button>
  )
}
