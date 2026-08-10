import { useState, useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ChevronLeft, ChevronRight, Sparkles, Target, Sliders, DollarSign,
  Check, Zap, Users, Loader, Search, ExternalLink
} from 'lucide-react'
import Layout from '../components/Layout'
import Pagination from '../components/Pagination'
import { jobsApi } from '../api/jobs'
import apiClient from '../api/client'

/**
 * 새 영상 만들기 — 3단계 마법사 (Wizard).
 *
 * 이전 상태: 이 페이지는 "Sprint 1 Day 2에서 구현 예정" 이라는 placeholder만
 * 있어서, 사이드바의 "새 영상 만들기" 버튼이 사실상 죽어있었습니다.
 * (실제 폼은 Jobs.jsx 모달 안에만 있었음)
 *
 * 이 마법사는 영상 작업자·일반 직원용으로 설계되어 있어서 Jobs.jsx 모달의
 * "한 화면 압축형" 폼과는 별개로, 각 항목의 의미를 자세히 설명해 주는
 * 단계별 흐름을 제공합니다. 처음 쓰는 사람도 예산이나 자율성 모드가 뭘 뜻하는지
 * 이 화면 안에서 이해할 수 있습니다.
 */

const CATEGORY_OPTIONS = [
  { value: 'KOSPI', label: '코스피 (KOSPI)', desc: '한국 종합주가지수 및 대형주 중심' },
  { value: 'KOSDAQ', label: '코스닥 (KOSDAQ)', desc: '코스닥 종목·테마주·중소형주' },
  { value: 'US_STOCKS', label: '미국 주식', desc: 'S&P 500, 나스닥, 다우 지수' },
  { value: 'INDIVIDUAL_STOCK', label: '개별 종목', desc: '삼성전자, SK하이닉스, 테슬라 등' },
  { value: 'GLOBAL_MACRO', label: '글로벌 매크로', desc: 'FOMC, 환율, 국채, CPI' },
  { value: 'CRYPTO', label: '암호화폐', desc: '비트코인, 이더리움, 알트코인' },
  { value: 'CUSTOM', label: '직접 입력', desc: '위 카테고리에 안 맞는 주제' },
]

// 백엔드 macro_topic_detector.py의 MACRO_SIGNAL_TERMS와 동일 목록을 유지할 것.
// 이 목록이 바뀌면 두 곳 모두 업데이트해야 한다 (추후 공유 JSON화 권장).
const MACRO_SIGNAL_TERMS = [
  '연준', 'FOMC', 'fomc', '금리인하', '금리인상', '기준금리',
  '환율', '달러인덱스', 'DXY', '국채', '국채금리', '10년물',
  'CPI', 'PCE', '물가지수', '소비자물가', '고용지표', '실업률',
  '비농업고용', 'PMI', 'GDP', '양적긴축', '양적완화', '테이퍼링',
  '파월', '옐런', '잭슨홀',
]

const AUTONOMY_OPTIONS = [
  {
    value: 'AUTO', label: '자동 (AUTO)', icon: Zap,
    tag: '가장 빠름', tagColor: 'bg-accent-green/20 text-accent-green',
    desc: '키워드→스크립트→음성→이미지→영상 조립까지 모든 단계 자동. 브라우저 안 켜도 됨.',
    warning: '중간에 검토 없이 완주하므로, 마지막에 결과가 마음에 안 들면 다시 만들어야 합니다.',
  },
  {
    value: 'GUIDED', label: '반자동 (GUIDED)', icon: Users,
    tag: '추천', tagColor: 'bg-accent-cyan/20 text-accent-cyan',
    desc: '키워드·스크립트·목소리·이미지를 단계별로 검토하고 승인하면 다음 단계로 진행.',
    warning: null,
  },
]

const DURATION_OPTIONS = [
  { value: 1, label: '1분 테스트', hint: '정책 상한 ₩40,000. 배포 검증용' },
  { value: 5, label: '5분', hint: '정책 상한 ₩40,000. 인트로 45초 움짤' },
  { value: 10, label: '10분', hint: '정책 상한 ₩40,000. 표준 길이' },
  { value: 15, label: '15분', hint: '정책 상한 ₩40,000. 심층 분석' },
  { value: 20, label: '20분', hint: '정책 상한 ₩80,000. 풀 리포트' },
  { value: 30, label: '30분', hint: '정책 상한 ₩80,000. 장문 분석' },
]
const RESEARCH_PAGE_SIZE = 10

export default function JobNew() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [step, setStep] = useState(1)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [channels, setChannels] = useState([])
  const [researchKeyword, setResearchKeyword] = useState('')
  const [researchVideos, setResearchVideos] = useState([])
  const [researchPage, setResearchPage] = useState(1)
  const [researchLoading, setResearchLoading] = useState(false)
  const [researchError, setResearchError] = useState(null)

  useEffect(() => {
    apiClient.get('/channels')
      .then(r => setChannels(r.data))
      .catch(e => console.error('채널 조회 실패:', e))
  }, [])

  const [form, setForm] = useState({
    title: '',
    category: 'KOSPI',
    autonomy: 'GUIDED',
    longformTargetMinutes: 15,
    budgetCap: null,
    geminiImageBudgetCap: 15000,
    makeShorts: true,
    shortsCount: 3,
    dataVisualsEnabled: false,
  })

  // 매크로 주제 감지: 사용자가 카테고리를 명시적으로 GLOBAL_MACRO/CUSTOM/CRYPTO로
  // 바꾸지 않은 상태에서 제목에 매크로 신호 키워드가 있으면 배너를 띄운다.
  // KOSPI/KOSDAQ/INDIVIDUAL_STOCK/ASSOCIATED_STOCKS 카테고리는
  // market_data_collector.py의 collect_for_category()에서 미국 지표(us.*)를
  // 전혀 수집하지 않으므로, 이 상태로 매크로 주제를 진행하면 팩트체크 근거가
  // 부족해질 수 있다.
  const macroSkipCategories = ['GLOBAL_MACRO', 'CUSTOM', 'CRYPTO']
  const detectedMacroTerms = macroSkipCategories.includes(form.category)
    ? []
    : MACRO_SIGNAL_TERMS.filter(term => form.title.toLowerCase().includes(term.toLowerCase()))
  const showMacroCategoryBanner = detectedMacroTerms.length > 0

  useEffect(() => {
    const topic = searchParams.get('topic')
    const planId = searchParams.get('planId')
    const keywordList = searchParams.get('keywords')?.split('|').map(item => item.trim()).filter(Boolean).slice(0, 5) || location.state?.keywordPlan?.usedKeywords?.slice(0, 5) || []
    if (topic) {
      setForm(current => current.title ? current : {
        ...current,
        title: topic,
        keyword: keywordList.length ? keywordList.join(', ') : topic,
        keywordPlanId: planId || current.keywordPlanId,
        policyJson: JSON.stringify({ source: 'daily_keyword_research', planId, selectedKeywords: keywordList }),
      })
      setResearchKeyword(topic)
    }
  }, [searchParams, location.state])

  const canProceed = () => {
    if (step === 1) return form.title.trim().length > 0
    if (step === 2) return true
    if (step === 3) return true
    return false
  }

  const searchTopicResearch = async (query = researchKeyword.trim()) => {
    const keyword = query.trim()
    if (query === undefined || keyword.length === 0 && query !== '') return
    setResearchLoading(true)
    setResearchError(null)
    try {
      const result = await jobsApi.trendingYoutube(keyword)
      setResearchVideos(Array.isArray(result) ? result : (result?.videos || []))
      setResearchPage(1)
    } catch (err) {
      setResearchError(err?.response?.data?.message || '주제 검색에 실패했습니다.')
      setResearchVideos([])
      setResearchPage(1)
    } finally {
      setResearchLoading(false)
    }
  }

  const researchTotalPages = Math.max(1, Math.ceil(researchVideos.length / RESEARCH_PAGE_SIZE))
  const researchPageItems = researchVideos.slice((researchPage - 1) * RESEARCH_PAGE_SIZE, researchPage * RESEARCH_PAGE_SIZE)
  useEffect(() => { if (researchPage > researchTotalPages) setResearchPage(researchTotalPages) }, [researchPage, researchTotalPages])

  const handleSubmit = async () => {
    setCreating(true)
    setError(null)
    try {
      const job = await jobsApi.create(form)
      // 즉시 작업 상세 페이지(`/longform/${job.id}`)로 이동하여 사용자가 실시간 진행 상황을 확인하게 함
      jobsApi.searchKeyword(job.id, form.keyword || form.title, 5).catch(err => {
        console.warn('키워드 자동 탐색 백그라운드 호출:', err)
      })
      navigate(`/longform/${job.id}`)
    } catch (err) {
      setError(err?.response?.data?.message || err.message || '작업 생성 실패')
      setCreating(false)
    }
  }

  return (
    <Layout>
      <div className="max-w-3xl mx-auto">
        {/* 헤더 */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate('/longform')}
            className="text-gray-400 hover:text-white transition"
            title="목록으로 돌아가기"
          >
            <ChevronLeft size={22} />
          </button>
          <div>
            <h1 className="text-2xl font-bold">새 영상 만들기</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              세 단계로 나눠서 안내합니다. 각 항목 설명을 읽으면서 진행하세요.
            </p>
          </div>
        </div>

        {/* 진행 표시기 */}
        <div className="flex items-center gap-2 mb-8">
          {[
            { n: 1, label: '주제·카테고리' },
            { n: 2, label: '자율성·길이' },
            { n: 3, label: '예산·확인' },
          ].map((s, i) => (
            <div key={s.n} className="flex-1 flex items-center gap-2">
              <div className={`flex items-center gap-2 flex-1 ${step === s.n ? 'text-accent-cyan' : step > s.n ? 'text-accent-green' : 'text-gray-500'}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
                  step > s.n ? 'border-accent-green bg-accent-green/10' :
                  step === s.n ? 'border-accent-cyan bg-accent-cyan/10' :
                  'border-navy-600 bg-navy-800'
                }`}>
                  {step > s.n ? <Check size={14} /> : s.n}
                </div>
                <span className="text-xs font-medium">{s.label}</span>
              </div>
              {i < 2 && <div className={`flex-1 h-0.5 ${step > s.n ? 'bg-accent-green' : 'bg-navy-700'}`} />}
            </div>
          ))}
        </div>

        {/* 스텝별 본문 */}
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-6 mb-4">
          {step === 1 && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 mb-2">
                <Target size={18} className="text-accent-cyan" />
                <h2 className="font-semibold">1단계 — 영상 주제와 카테고리</h2>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1.5">영상 주제</label>
                <input
                  autoFocus
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="예: 코스피 주간 전망, 삼성전자 3분기 실적 분석"
                  className="w-full bg-navy-700 border border-navy-600 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                />
                <p className="text-xs text-gray-500 mt-1.5">
                  구체적일수록 좋습니다. "주식"보다는 "삼성전자 반도체 실적"처럼 대상을 좁혀 주세요.
                </p>
              </div>

              <div className="rounded-lg border border-navy-600 bg-navy-900/70 p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Search size={16} className="text-accent-cyan" />
                  <h3 className="text-sm font-semibold">주제 탐색 · 영상 성과 비교</h3>
                </div>
                <p className="text-xs text-gray-400 mb-3">현재 검색되는 관련 영상을 비교한 뒤 영상 제목을 주제로 가져올 수 있습니다.</p>
                <div className="flex gap-2">
                  <input
                    value={researchKeyword}
                    onChange={e => setResearchKeyword(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') searchTopicResearch() }}
                    placeholder="예: 반도체 수출, 금리 인하, 삼성전자"
                    className="flex-1 bg-navy-700 border border-navy-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                  />
                  <button type="button" onClick={() => searchTopicResearch()} disabled={!researchKeyword.trim() || researchLoading} className="flex items-center gap-1.5 rounded-lg bg-accent-cyan px-3 py-2 text-sm font-semibold text-navy-950 disabled:opacity-50">
                    {researchLoading ? <Loader size={14} className="animate-spin" /> : <Search size={14} />} 검색
                  </button>
                  <button type="button" onClick={() => searchTopicResearch('')} disabled={researchLoading} className="rounded-lg border border-navy-600 px-3 py-2 text-xs text-gray-300 hover:bg-navy-700 disabled:opacity-50">
                    현재 트렌드
                  </button>
                </div>
                {researchError && <p className="mt-2 text-xs text-accent-red">{researchError}</p>}
                {researchVideos.length > 0 && (
                  <div className="mt-3 space-y-2 max-h-80 overflow-y-auto">
                    {researchPageItems.map((video, index) => {
                      const views = Number(video.views || video.viewCount || 0)
                      const subscribers = Number(video.subscribers || video.subscriberCount || 0)
                      const ratio = subscribers > 0 ? (views / subscribers).toFixed(2) : '-'
                      const publishedAt = video.published_at || video.publishedAt || ''
                      const publishedMs = Date.parse(publishedAt)
                      const ageDays = Number.isFinite(publishedMs) ? Math.max(1, (Date.now() - publishedMs) / 86400000) : 1
                      const dailyViews = Math.round(views / ageDays)
                      const performance = Number(ratio) >= 5 ? 'Great' : Number(ratio) >= 2 ? 'Normal' : 'Low'
                      const likesAvailable = video.likes_available ?? video.likesAvailable ?? true
                      const likes = Number(video.likes || video.likeCount || 0)
                      const title = video.title || '제목 없음'
                      const videoId = video.video_id || video.videoId || ''
                      return (
                        <div key={videoId || index} className="rounded-lg border border-navy-700 bg-navy-800/70 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-white line-clamp-2">{title}</div>
                              <div className="text-xs text-gray-400 mt-1">{video.channel_title || video.channelTitle || '채널 미상'} · {publishedAt || '게시일 미상'}</div>
                            </div>
                            <button type="button" onClick={() => setForm({ ...form, title })} className="shrink-0 rounded border border-accent-cyan/60 px-2 py-1 text-xs text-accent-cyan hover:bg-accent-cyan/10">주제로 사용</button>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-400">
                            <span>조회 {views.toLocaleString()}</span><span>구독 {subscribers.toLocaleString()}</span><span>조회/구독 {ratio}×</span><span>일평균 조회 {dailyViews.toLocaleString()}</span><span>성과 {performance}</span><span>좋아요 {likesAvailable ? likes.toLocaleString() : '비공개'}</span>
                            {video.duration_seconds > 0 && <span>길이 {Math.round(video.duration_seconds)}초</span>}
                            {videoId && <a href={`https://www.youtube.com/watch?v=${videoId}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-cyan hover:underline">영상 보기 <ExternalLink size={11} /></a>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
                <Pagination total={researchVideos.length} currentPage={researchPage} onChange={setResearchPage} pageSize={RESEARCH_PAGE_SIZE}/>
                <p className="mt-2 text-[11px] text-gray-500">공개 API에서 제공되는 지표만 표시하며, 경쟁 채널의 평균 시청 시간·CTR은 제공되지 않습니다.</p>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1.5">대상 채널</label>
                <select
                  value={form.channelId || ''}
                  onChange={e => setForm({ ...form, channelId: e.target.value || null })}
                  className="w-full bg-navy-700 border border-navy-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
                >
                  <option value="">채널 선택 안 함 (기본)</option>
                  {channels.map(c => (
                    <option key={c.channelId} value={c.channelId}>
                      {c.channelName} ({c.channelId})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1.5">캐릭터 (선택사항)</label>
                <select value={form.characterOverride || ''} onChange={e => setForm({ ...form, characterOverride: e.target.value || null })} className="w-full bg-navy-700 border border-navy-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:ring-1 focus:ring-accent-cyan">
                  <option value="">채널 기본 캐릭터 상속</option>
                  {channels.map(c => <option key={c.channelId} value={c.channelId}>{c.channelName} 캐릭터</option>)}
                </select>
                <p className="text-[11px] text-gray-500 mt-1">기본은 채널 캐릭터이며, 특별한 작업만 여기서 덮어쓸 수 있습니다.</p>
              </div>

              <label className="flex items-start gap-3 bg-accent-cyan/5 border border-accent-cyan/20 rounded-lg p-3 cursor-pointer">
                <input type="checkbox" checked={form.dataVisualsEnabled} onChange={e => setForm({ ...form, dataVisualsEnabled: e.target.checked })} className="mt-1 accent-cyan-400" />
                <span><span className="block text-sm text-white font-semibold">레거시 수치 시각화 사용</span><span className="block text-[11px] text-gray-400 mt-1">기본 파이프라인은 기사형·일반형·정보형으로 대본 의미를 표현합니다. 이 옵션은 기존 숫자 카드·차트 오버레이 호환이 꼭 필요한 경우에만 사용합니다.</span></span>
              </label>

              <div>
                <label className="block text-sm text-gray-300 mb-2">카테고리</label>
                {showMacroCategoryBanner && (
                  <div className="mb-2 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
                    <span className="text-amber-400 text-sm mt-0.5">⚠</span>
                    <div className="flex-1">
                      <p className="text-xs text-amber-200">
                        입력한 주제에 매크로 지표 키워드({detectedMacroTerms.slice(0, 3).join(', ')})가 감지되었습니다.
                        현재 선택된 카테고리는 미국 시장 지표(연준 금리, CPI 등)를 수집하지 않아
                        팩트체크 근거가 부족해질 수 있습니다.
                      </p>
                      <button
                        type="button"
                        onClick={() => setForm({ ...form, category: 'GLOBAL_MACRO' })}
                        className="mt-2 text-xs font-semibold text-amber-300 underline hover:text-amber-200"
                      >
                        글로벌 매크로 카테고리로 전환
                      </button>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  {CATEGORY_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setForm({ ...form, category: opt.value })}
                      className={`text-left p-3 rounded-lg border transition ${
                        form.category === opt.value
                          ? 'border-accent-cyan bg-accent-cyan/10'
                          : 'border-navy-700 bg-navy-700/40 hover:border-navy-600'
                      }`}
                    >
                      <div className="text-sm font-semibold">{opt.label}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 mb-2">
                <Sliders size={18} className="text-accent-cyan" />
                <h2 className="font-semibold">2단계 — 자율성 모드와 목표 길이</h2>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-2">자율성 모드</label>
                <div className="space-y-2">
                  {AUTONOMY_OPTIONS.map(opt => {
                    const Icon = opt.icon
                    const selected = form.autonomy === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setForm({ ...form, autonomy: opt.value })}
                        className={`w-full text-left p-3.5 rounded-lg border transition ${
                          selected
                            ? 'border-accent-cyan bg-accent-cyan/10'
                            : 'border-navy-700 bg-navy-700/40 hover:border-navy-600'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <Icon size={18} className={selected ? 'text-accent-cyan mt-0.5' : 'text-gray-400 mt-0.5'} />
                            <div>
                              <div className="text-sm font-semibold flex items-center gap-2">
                                {opt.label}
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${opt.tagColor}`}>{opt.tag}</span>
                              </div>
                              <div className="text-xs text-gray-400 mt-1 leading-relaxed">{opt.desc}</div>
                              {opt.warning && (
                                <div className="text-xs text-accent-gold mt-1.5">⚠ {opt.warning}</div>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-2">목표 길이</label>
                <div className="grid grid-cols-5 gap-2">
                  {DURATION_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setForm({ ...form, longformTargetMinutes: opt.value })}
                      className={`p-2.5 rounded-lg border transition text-center ${
                        form.longformTargetMinutes === opt.value
                          ? 'border-accent-cyan bg-accent-cyan/10'
                          : 'border-navy-700 bg-navy-700/40 hover:border-navy-600'
                      }`}
                    >
                      <div className="text-sm font-bold">{opt.label}</div>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  {DURATION_OPTIONS.find(o => o.value === form.longformTargetMinutes)?.hint}
                </p>
              </div>

              <div className="border-t border-navy-700 pt-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.makeShorts}
                    onChange={e => setForm({ ...form, makeShorts: e.target.checked })}
                    className="mt-1 accent-accent-cyan"
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium">완성 후 쇼츠도 자동 생성</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      롱폼에서 시나리오 3개와 키워드 10개를 자동 추출해 쇼츠 후보로 만들어 줍니다.
                    </div>
                  </div>
                </label>
                {form.makeShorts && (
                  <div className="ml-6 mt-2 flex items-center gap-2">
                    <span className="text-xs text-gray-400">쇼츠 개수:</span>
                    <select
                      value={form.shortsCount}
                      onChange={e => setForm({ ...form, shortsCount: Number(e.target.value) })}
                      className="bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-white focus:outline-none"
                    >
                      <option value={1}>1개</option>
                      <option value={3}>3개</option>
                      <option value={5}>5개</option>
                    </select>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign size={18} className="text-accent-cyan" />
                <h2 className="font-semibold">3단계 — 예산 상한과 최종 확인</h2>
              </div>

              <div className="rounded-lg border border-accent-cyan/30 bg-accent-cyan/5 p-4">
                <div className="text-sm font-semibold text-gray-100">정책 예산 상한</div>
                <div className="mt-1 text-2xl font-bold text-accent-cyan">
                  ₩{(form.longformTargetMinutes >= 20 ? 70000 : 40000).toLocaleString()}
                </div>
                <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                  목표 길이에 따라 서버 정책이 자동 적용됩니다. 20분 미만은 ₩40,000, 20분 이상은 ₩70,000이며 임의 상향할 수 없습니다.
                </p>
              </div>

              <div className="bg-navy-700/50 rounded-lg p-4 border border-navy-600">
                <label className="block text-sm font-medium text-gray-100">Gemini 이미지 전용 상한</label>
                <p className="mt-1 text-xs text-gray-400">정지 이미지 생성에만 적용합니다. Fal 모션 비용은 이 값과 분리되며 전체 영상 상한은 그대로 유지됩니다.</p>
                <input
                  type="number"
                  min="1"
                  step="1000"
                  value={form.geminiImageBudgetCap}
                  onChange={e => setForm({ ...form, geminiImageBudgetCap: Number(e.target.value) })}
                  className="mt-3 w-full rounded border border-navy-600 bg-navy-800 px-3 py-2 text-sm text-white focus:border-accent-cyan focus:outline-none"
                />
                <div className="text-xs text-gray-400 mb-2">최종 확인</div>
                <div className="space-y-1.5 text-sm">
                  <Row label="주제" value={form.title || '(미입력)'} />
                  <Row label="카테고리" value={CATEGORY_OPTIONS.find(o => o.value === form.category)?.label} />
                  <Row label="자율성" value={AUTONOMY_OPTIONS.find(o => o.value === form.autonomy)?.label} />
                  <Row label="목표 길이" value={`${form.longformTargetMinutes}분`} />
                  <Row label="쇼츠 생성" value={form.makeShorts ? `${form.shortsCount}개` : '안 함'} />
                  <Row label="예산 상한" value={`₩${(form.longformTargetMinutes >= 20 ? 70000 : 40000).toLocaleString()}`} highlight />
                </div>
              </div>

              {error && (
                <div className="bg-accent-red/10 border border-accent-red/30 rounded-lg p-3 text-sm text-accent-red">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 하단 네비게이션 */}
        <div className="flex items-center justify-between">
          {step > 1 ? (
            <button
              onClick={() => setStep(step - 1)}
              disabled={creating}
              className="flex items-center gap-2 bg-navy-700 text-gray-300 hover:text-white rounded-lg px-4 py-2 text-sm transition disabled:opacity-50"
            >
              <ChevronLeft size={14} /> 이전
            </button>
          ) : <div />}

          {step < 3 ? (
            <button
              onClick={() => setStep(step + 1)}
              disabled={!canProceed()}
              className="flex items-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg px-5 py-2.5 text-sm hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              다음 <ChevronRight size={14} />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!canProceed() || creating}
              className="flex items-center gap-2 bg-accent-green text-navy-950 font-semibold rounded-lg px-5 py-2.5 text-sm hover:opacity-90 transition disabled:opacity-50"
            >
              {creating ? <Loader size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {creating ? '작업 생성 중...' : '작업 시작'}
            </button>
          )}
        </div>
      </div>
    </Layout>
  )
}

function Row({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-gray-400 text-xs">{label}</span>
      <span className={`font-medium ${highlight ? 'text-accent-cyan' : 'text-white'}`}>{value}</span>
    </div>
  )
}
