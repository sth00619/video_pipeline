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

  const handleQuickStart = async (e) => {
    e.preventDefault()
    if (!quickTitle.trim()) return
    setCreating(true)
    try {
      const job = await jobsApi.create({
        title: quickTitle,
        category: 'KOSPI',
        autonomy: 'AUTO',
        longformTargetMinutes: 20,
        budgetCap: 100,
      })
      // AUTO 모드: 즉시 키워드 탐색 시작
      await jobsApi.searchKeyword(job.id, quickTitle, 5)
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
        <StatCard icon={<Clock className="text-accent-cyan" />} label="진행 중" value={inProgress.length} />
        <StatCard icon={<CheckCircle className="text-accent-green" />} label="완료" value={completed.length} />
        <StatCard icon={<AlertCircle className="text-accent-red" />} label="오류" value={failed.length} />
      </div>

      {/* AUTO 빠른 시작 */}
      <div className="bg-navy-800 rounded-xl p-6 mb-8 border border-navy-700">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="text-accent-gold" size={20} />
          <h2 className="font-semibold">AUTO 빠른 시작</h2>
          <span className="text-xs bg-accent-cyan/20 text-accent-cyan px-2 py-0.5 rounded-full">KOSPI · 20분 · 자동</span>
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
          키워드 탐색 → 스크립트 → 음성 → 이미지 → 영상 조립까지 자동으로 진행됩니다.
        </p>
      </div>

      {/* 최근 작업 목록 */}
      <div className="bg-navy-800 rounded-xl border border-navy-700">
        <div className="flex items-center justify-between px-6 py-4 border-b border-navy-700">
          <h2 className="font-semibold">최근 작업</h2>
          <button
            onClick={() => navigate('/jobs')}
            className="text-sm text-accent-cyan hover:underline"
          >
            전체 보기
          </button>
        </div>
        {jobs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Video size={40} className="mx-auto mb-3 opacity-30" />
            <p>작업이 없습니다.</p>
            <p className="text-sm mt-1">위에서 첫 번째 영상을 만들어보세요.</p>
          </div>
        ) : (
          <div className="divide-y divide-navy-700">
            {jobs.slice(0, 8).map(job => (
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

function StatCard({ icon, label, value }) {
  return (
    <div className="bg-navy-800 rounded-xl p-5 border border-navy-700">
      <div className="flex items-center justify-between mb-3">
        {icon}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm text-gray-400 mt-1">{label}</div>
    </div>
  )
}
