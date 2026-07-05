import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Video, CheckCircle, Clock, AlertCircle, Plus,
  TrendingUp, DollarSign, Zap
} from 'lucide-react'
import Layout from '../components/Layout'
import { jobsApi } from '../api/jobs'

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

export default function Dashboard() {
  const navigate = useNavigate()
  const [quickTitle, setQuickTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [filter, setFilter] = useState('ALL')
  const [category, setCategory] = useState('KOSPI')
  const [duration, setDuration] = useState(20)
  const [autonomy, setAutonomy] = useState('AUTO')

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

  const filteredJobs = jobs.filter(j => {
    if (filter === 'IN_PROGRESS') return !['READY', 'PUBLISHED', 'FAILED', 'BUDGET_BLOCKED', 'DRAFT'].includes(j.status)
    if (filter === 'COMPLETED') return ['READY', 'PUBLISHED'].includes(j.status)
    if (filter === 'FAILED') return ['FAILED', 'BUDGET_BLOCKED'].includes(j.status)
    return true
  })

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

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <p className="text-gray-400 text-sm mt-1">AI 주식 영상 자동화 플랫폼</p>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard
          icon={<Clock className="text-accent-cyan" />}
          label="진행 중"
          value={inProgress.length}
          active={filter === 'IN_PROGRESS'}
          onClick={() => setFilter(filter === 'IN_PROGRESS' ? 'ALL' : 'IN_PROGRESS')}
        />
        <StatCard
          icon={<CheckCircle className="text-accent-green" />}
          label="완료"
          value={completed.length}
          active={filter === 'COMPLETED'}
          onClick={() => setFilter(filter === 'COMPLETED' ? 'ALL' : 'COMPLETED')}
        />
        <StatCard
          icon={<AlertCircle className="text-accent-red" />}
          label="오류"
          value={failed.length}
          active={filter === 'FAILED'}
          onClick={() => setFilter(filter === 'FAILED' ? 'ALL' : 'FAILED')}
        />
      </div>

      {/* 빠른 영상 시작 */}
      <div className="bg-navy-800 rounded-xl p-6 mb-8 border border-navy-700">
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
              <option value="KOSPI">KOSPI</option>
              <option value="KOSDAQ">KOSDAQ</option>
              <option value="US_STOCKS">미국 주식</option>
              <option value="INDIVIDUAL_STOCK">개별 종목</option>
              <option value="GLOBAL_MACRO">글로벌 거시</option>
              <option value="CRYPTO">암호화폐</option>
              <option value="CUSTOM">직접 입력 (CUSTOM)</option>
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

      {/* 최근 작업 목록 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700">
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-700">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold">최근 작업</h2>
            {filter !== 'ALL' && (
              <span className="text-[10px] bg-accent-cyan/10 text-accent-cyan px-2 py-0.5 rounded-full font-semibold">
                필터: {filter === 'IN_PROGRESS' ? '진행 중' : filter === 'COMPLETED' ? '완료' : '오류'}
              </span>
            )}
          </div>
          <button
            onClick={() => navigate('/jobs')}
            className="text-sm text-accent-cyan hover:underline"
          >
            전체 보기
          </button>
        </div>
        {filteredJobs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>조건에 부합하는 작업이 없습니다.</p>
            {filter !== 'ALL' && (
              <button onClick={() => setFilter('ALL')} className="text-xs text-accent-cyan hover:underline mt-2">
                필터 해제하기
              </button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-navy-700">
            {filteredJobs.slice(0, 8).map(job => (
              <button
                key={job.id}
                onClick={() => navigate(`/jobs/${job.id}`)}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-navy-700/50 transition text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-navy-700 rounded-lg flex items-center justify-center">
                    <Video size={18} className="text-gray-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{job.title}</div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {job.category} · {job.longformTargetMinutes}분 · {job.autonomy}
                    </div>
                  </div>
                </div>
                <span className={`text-xs font-medium ${STATUS_COLOR[job.status] || 'text-gray-400'}`}>
                  {STATUS_LABEL[job.status] || job.status}
                </span>
              </button>
            ))}
          </div>
        )}
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
