import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Check, ChevronDown, ChevronUp, ExternalLink, Flame, Loader, Network, Plus, RefreshCw, Search, ThumbsUp, MessageCircle, Youtube } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import apiClient from '../../api/client'
import { jobsApi } from '../../api/jobs'
import Pagination from '../Pagination'
import KeywordMindMap from './KeywordMindMap'

const PAGE_SIZE = 5
const MAX_SELECTED_KEYWORDS = 5
const MIN_EVIDENCE_SUBSCRIBERS = 3000
const MIN_EVIDENCE_VIEWS = 3000
const MIN_EVIDENCE_VIEWER_MULTIPLE = 0.25
const valueOf = (row, ...keys) => keys.map(key => row?.[key]).find(value => value !== undefined && value !== null)
const asNumber = value => Number.isFinite(Number(value)) ? Number(value) : null
const isEligibleEvidence = video => {
  const hours = asNumber(valueOf(video, 'hoursSincePublish', 'hours_since_publish'))
  const subscribers = asNumber(valueOf(video, 'subscribers', 'subscriberCount')) || 0
  const views = asNumber(valueOf(video, 'views', 'viewCount')) || 0
  return subscribers >= MIN_EVIDENCE_SUBSCRIBERS
    && views >= MIN_EVIDENCE_VIEWS
    && views / Math.max(subscribers, 1) >= MIN_EVIDENCE_VIEWER_MULTIPLE
    && hours != null && hours > 0 && hours <= 24 * 7
    && valueOf(video, 'isLive', 'is_live') !== true
    && valueOf(video, 'subscriberCountAvailable', 'subscriber_count_available') !== false
}
const displayNumber = value => asNumber(value) == null ? '—' : asNumber(value).toLocaleString('ko-KR', { maximumFractionDigits: 2 })

function gradeFor(video) {
  const supplied = valueOf(video, 'performanceGrade', 'performance_grade')
  if (supplied) return supplied
  const views = asNumber(video?.views) || 0
  const subscribers = asNumber(video?.subscribers) || 0
  const multiple = subscribers ? views / subscribers : 0
  return multiple >= 5 ? 'S' : multiple >= 1 ? 'A' : multiple >= .3 ? 'B' : 'C'
}

function metricsFor(video) {
  const views = asNumber(video?.views) || 0
  const subscribers = asNumber(video?.subscribers) || 0
  const likes = asNumber(video?.likes) || 0
  const comments = asNumber(video?.comments) || 0
  const hours = asNumber(valueOf(video, 'hoursSincePublish', 'hours_since_publish')) || 0
  return {
    multiple: subscribers ? views / subscribers : null,
    velocity: hours ? views / hours : null,
    likeRate: views ? likes / views : null,
    commentRate: views ? comments / views : null,
  }
}

function VideoTags({ tags = [], className = '' }) {
  const list = [...new Set((Array.isArray(tags) ? tags : []).map(tag => String(tag || '').replace(/^#/, '').trim()).filter(Boolean))].slice(0, 6)
  return list.length ? <div className={`flex flex-wrap gap-1 ${className}`}>{list.map(tag => <span key={tag} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700">#{tag}</span>)}</div> : null
}

function Metric({ label, children }) {
  return <div className="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2"><p className="text-[10px] font-medium text-slate-600">{label}</p><div className="mt-1 whitespace-nowrap text-sm font-bold text-slate-900">{children}</div></div>
}

function EvidenceVideoCard({ video, compact = false }) {
  const id = valueOf(video, 'videoId', 'video_id')
  const grade = gradeFor(video)
  const metrics = metricsFor(video)
  const title = video?.title || '제목 정보 없음'
  const isLongform = (asNumber(valueOf(video, 'durationSeconds', 'duration_seconds')) || 0) > 60
  const gradeClass = grade === 'S' ? 'border-rose-300 bg-rose-100 text-rose-700' : grade === 'A' ? 'border-emerald-300 bg-emerald-100 text-emerald-700' : 'border-slate-300 bg-slate-100 text-slate-700'
  return <article className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
    <span className={`absolute left-3 top-3 inline-flex h-7 min-w-7 items-center justify-center rounded-md border text-xs font-black ${gradeClass}`}>{grade}</span>
    <div className={`grid gap-3 ${compact ? 'lg:grid-cols-[minmax(0,1fr)_300px]' : 'xl:grid-cols-[minmax(0,1fr)_310px]'}`}>
      <div className="flex min-w-0 gap-3 pl-9">
        {id && <img src={`https://i.ytimg.com/vi/${id}/mqdefault.jpg`} alt="" className="h-16 w-[114px] shrink-0 rounded-lg bg-slate-100 object-cover" />}
        <div className="min-w-0"><div className="flex flex-wrap items-center gap-1.5"><p className="line-clamp-2 text-sm font-semibold leading-5 text-slate-900">{title}</p><span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700">{isLongform ? '롱폼' : '쇼츠'}</span></div><p className="mt-1 text-[11px] text-slate-600">{valueOf(video, 'channelTitle', 'channel_title') || '채널 정보 없음'} · 게시 {Math.max(0, Math.round(asNumber(valueOf(video, 'hoursSincePublish', 'hours_since_publish')) || 0))}시간 전</p><VideoTags tags={video?.tags} className="mt-2" />{id && <a href={`https://www.youtube.com/watch?v=${id}`} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-violet-700 hover:underline">영상 보기 <ExternalLink size={12} /></a>}</div>
      </div>
      <div className="grid min-w-[290px] grid-cols-2 gap-2"><Metric label="구독자 대비 조회">{metrics.multiple == null ? '계산 불가' : <span className={metrics.multiple >= 5 ? 'text-rose-700' : ''}>{metrics.multiple >= 5 && <Flame className="mr-1 inline" size={13} />}{displayNumber(metrics.multiple)}x</span>}</Metric><Metric label="게시 후 시간당 조회">{metrics.velocity == null ? '—' : `${displayNumber(metrics.velocity)}/시간`}</Metric><Metric label="좋아요율"><ThumbsUp className="mr-1 inline" size={13} />{metrics.likeRate == null ? '—' : `${(metrics.likeRate * 100).toFixed(2)}%`}</Metric><Metric label="댓글율"><MessageCircle className="mr-1 inline" size={13} />{metrics.commentRate == null ? '—' : `${(metrics.commentRate * 100).toFixed(2)}%`}</Metric></div>
    </div>
  </article>
}

function KeywordReason({ keyword, metric }) {
  const evidence = metric?.evidence || []
  return <article className="rounded-xl border border-violet-200 bg-violet-50/50 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><h5 className="font-semibold text-slate-900">{keyword}</h5><span className="rounded-full bg-violet-100 px-2 py-1 text-[11px] font-bold text-violet-700">최고 {displayNumber(metric?.bestMultiple)}x</span></div><p className="mt-1 text-[11px] text-slate-700">반복 태그: {(metric?.matchedTags || []).length ? (metric.matchedTags || []).map(tag => `#${tag}`).join(' · ') : '공개 제목·태그 공통어'}</p><div className="mt-2 space-y-2">{evidence.slice(0, 3).map(video => <div key={video.videoId} className="rounded-lg border border-slate-200 bg-white p-2"><p className="line-clamp-1 text-xs font-semibold text-slate-800">{video.title}</p><p className="mt-1 text-[10px] text-slate-600">{video.channelTitle} · 구독자 {displayNumber(video.subscribers)} · 조회 {displayNumber(video.views)} · 구독자 대비 {displayNumber(video.bestMultiple)}x</p><VideoTags tags={video.matchedTags} className="mt-1" /></div>)}</div></article>
}

function ManualContext({ context, onAdd, adding }) {
  if (!context) return null
  const confirmed = context.evidenceStatus === 'confirmed'
  return <div className="mx-5 mb-5 rounded-xl border border-amber-300 bg-amber-50 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-bold text-slate-900">직접 입력 키워드 최신성 확인 · {context.windowHours}시간</h4><p className={`mt-1 text-xs font-semibold ${confirmed ? 'text-emerald-700' : 'text-amber-700'}`}>{confirmed ? '최근 공개 뉴스 또는 영상 근거를 찾았습니다. 아래 근거를 확인한 뒤 후보에 추가하세요.' : '최근 1~2시간 안의 공개 근거를 찾지 못했습니다. 필요하면 근거 부족 상태로 추가할 수 있습니다.'}</p></div><button type="button" onClick={onAdd} disabled={adding} className="inline-flex items-center gap-1 rounded-lg bg-accent-gold px-3 py-2 text-xs font-bold text-navy-950 disabled:opacity-50"><Plus size={14} />후보에 추가</button></div><div className="mt-3 grid gap-3 lg:grid-cols-2"><div><p className="text-xs font-bold text-slate-800">최근 뉴스</p><div className="mt-2 space-y-2">{(context.recentNews || []).length ? context.recentNews.map(news => <a key={news.url || news.title} href={news.url} target="_blank" rel="noreferrer" className="block rounded-lg border border-amber-200 bg-white p-2 hover:border-amber-400"><p className="line-clamp-2 text-xs font-semibold text-slate-800">{news.title}</p><p className="mt-1 text-[10px] text-slate-600">{news.source || 'Google 뉴스'} · {news.hoursSincePublish}시간 전</p></a>) : <p className="rounded-lg border border-dashed border-amber-200 p-3 text-xs text-slate-600">최근 뉴스 없음</p>}</div></div><div><p className="text-xs font-bold text-slate-800">최근 공개 YouTube 영상</p><div className="mt-2 space-y-2">{(context.recentVideos || []).length ? context.recentVideos.slice(0, 4).map(video => <div key={video.video_id || video.videoId} className="rounded-lg border border-amber-200 bg-white p-2"><p className="line-clamp-2 text-xs font-semibold text-slate-800">{video.title}</p><VideoTags tags={video.tags} className="mt-1" /></div>) : <p className="rounded-lg border border-dashed border-amber-200 p-3 text-xs text-slate-600">최근 영상 없음</p>}</div></div></div><p className="mt-3 text-[10px] text-slate-600">{context.disclaimer}</p></div>
}

export default function DailyKeywordResearch({ onUseKeyword }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [researchKeyword, setResearchKeyword] = useState('주식')
  const [researchVideos, setResearchVideos] = useState([])
  const [mindmap, setMindmap] = useState(null)
  const [selected, setSelected] = useState({})
  const [manualKeyword, setManualKeyword] = useState('')
  const [note, setNote] = useState('')
  const [manualContext, setManualContext] = useState(null)
  const [dailyPage, setDailyPage] = useState(1)
  const [directPage, setDirectPage] = useState(1)
  const [expanded, setExpanded] = useState(null)
  const dailyRef = useRef(null)
  const directRef = useRef(null)
  const mindmapRequestRef = useRef(0)

  const { data, isLoading, isError } = useQuery({ queryKey: ['daily-keywords'], queryFn: () => apiClient.get('/keywords/daily').then(response => response.data), refetchInterval: 5 * 60 * 1000 })
  const refresh = useMutation({ mutationFn: () => apiClient.post('/keywords/refresh'), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-keywords'] }) })
  const searchVideos = useMutation({ mutationFn: keyword => jobsApi.trendingYoutube(keyword), onSuccess: result => { setResearchVideos(Array.isArray(result) ? result : result?.videos || []); setDirectPage(1); setMindmap(null); setSelected({}) } })
  const makeMindmap = useMutation({
    mutationFn: payload => apiClient.post('/keywords/mindmap', payload).then(response => response.data),
    onSuccess: (result, payload) => {
      // 느린 이전 요청이 최신 검색 결과의 지도를 덮어쓰지 않게 한다.
      if (payload.requestId === mindmapRequestRef.current) setMindmap(result)
    },
  })
  const previewManual = useMutation({ mutationFn: keyword => apiClient.post('/keywords/manual/preview', { keyword, recentHours: 2 }).then(response => response.data), onSuccess: setManualContext })
  const addManual = useMutation({ mutationFn: () => apiClient.post('/keywords/manual', { keyword: manualKeyword, category: 'CUSTOM', note }), onSuccess: () => { setManualKeyword(''); setNote(''); setManualContext(null); queryClient.invalidateQueries({ queryKey: ['daily-keywords'] }) } })

  const dailyItems = data?.items || []
  const dailyVideos = useMemo(() => dailyItems.map(item => ({ ...(valueOf(item, 'sourceVideos', 'source_videos')?.[0] || {}), title: item.keyword, performanceGrade: item.performanceGrade, performanceScore: item.performanceScore, views: item.views, subscribers: item.subscribers, likes: item.likes, comments: item.comments })), [dailyItems])
  const sourceVideos = useMemo(() => researchVideos.length ? researchVideos : dailyVideos, [researchVideos, dailyVideos])
  const trustedVideos = useMemo(() => sourceVideos.filter(isEligibleEvidence), [sourceVideos])
  const premiumVideos = useMemo(() => { const premium = trustedVideos.filter(video => ['S', 'A'].includes(gradeFor(video))); const rest = trustedVideos.filter(video => !['S', 'A'].includes(gradeFor(video))); return [...premium, ...rest].slice(0, 12) }, [trustedVideos])
  const sourceSignature = useMemo(() => premiumVideos.map(video => `${valueOf(video, 'videoId', 'video_id')}:${video.title}`).join('|'), [premiumVideos])
  const selectedKeywords = useMemo(() => new Set(Object.keys(selected)), [selected])
  const dailyTrustedVideos = useMemo(() => dailyVideos.filter(isEligibleEvidence), [dailyVideos])
  const directTrustedVideos = useMemo(() => researchVideos.filter(isEligibleEvidence), [researchVideos])
  const dailyVisible = dailyTrustedVideos.slice((dailyPage - 1) * PAGE_SIZE, dailyPage * PAGE_SIZE)
  const directVisible = directTrustedVideos.slice((directPage - 1) * PAGE_SIZE, directPage * PAGE_SIZE)

  useEffect(() => {
    if (!sourceSignature) {
      setMindmap(null)
      setSelected({})
      return
    }
    mindmapRequestRef.current += 1
    setSelected({})
    makeMindmap.mutate({ requestId: mindmapRequestRef.current, keyword: researchVideos.length ? researchKeyword.trim() : '오늘의 S/A 주식 기회', videos: premiumVideos })
  }, [sourceSignature])

  const toggleKeyword = (keyword, node = {}) => {
    setSelected(current => {
      if (current[keyword]) return Object.fromEntries(Object.entries(current).filter(([key]) => key !== keyword))
      if (Object.keys(current).length >= MAX_SELECTED_KEYWORDS) return current
      const metrics = metricsFor(node)
      return { ...current, [keyword]: { metric: { keyword, bestMultiple: node.bestMultiple ?? metrics.multiple, viewsPerHour: metrics.velocity, views: asNumber(node.views), likes: asNumber(node.likes), comments: asNumber(node.comments), matchedTags: node.raw || node.matchedTags || [], evidence: node.evidence || [] } } }
    })
  }
  const requestManualPreview = () => { if (manualKeyword.trim()) previewManual.mutate(manualKeyword.trim()) }
  const movePage = (setter, page, ref) => { setter(page); ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const openSelectedKeywordSetup = () => {
    const keywords = Object.keys(selected)
    if (!keywords.length) return
    const topic = `${keywords.slice(0, 3).join(' · ')} 분석`
    const params = new URLSearchParams({
      topic,
      keywords: keywords.join('|'),
      planId: 'mindmap-selection',
    })
    navigate(`/longform/new?${params.toString()}`, {
      state: {
        keywordPlan: {
          planId: 'mindmap-selection',
          title: topic,
          usedKeywords: keywords,
          source: 'daily_keyword_research',
        },
      },
    })
  }

  return <section className={`overflow-hidden rounded-2xl border border-navy-700 bg-navy-800 shadow-sm ${selectedKeywords.size > 0 ? 'pb-28' : ''}`}>
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-navy-700 px-5 py-5"><div><p className="text-xs font-semibold text-accent-cyan">YouTube 기반 롱폼 리서치</p><h2 className="mt-1 text-lg font-bold text-white">오늘 무엇으로 롱폼을 만들까요?</h2><p className="mt-1 text-xs text-gray-400">최근 7일 · 일반 영상만 · 구독자/조회수 각 3천 이상 · 구독자 대비 조회 0.25배 이상 영상을 수집합니다. S/A는 우선 정렬하며 수치는 공개 API 원본만 표시합니다.</p></div><button onClick={() => refresh.mutate()} disabled={refresh.isPending} className="inline-flex items-center gap-1.5 rounded-lg border border-accent-cyan/50 px-3 py-2 text-xs font-semibold text-accent-cyan disabled:opacity-50"><RefreshCw size={14} className={refresh.isPending ? 'animate-spin' : ''} />오늘의 분석 새로고침</button></header>
    <div className="border-b border-navy-700 bg-navy-950/25 p-5"><div className="flex items-center gap-2"><Network size={17} className="text-violet-300" /><h3 className="text-sm font-bold text-white">{researchVideos.length ? `“${researchKeyword}” 실시간 주제 지도` : '오늘의 주식 기회 지도'}</h3></div><p className="mt-1 text-xs text-gray-400">최근 7일의 일반 영상 중 3천/3천·0.25배 기준을 사용합니다. S/A 영상은 우선 배치하고, 부족분은 같은 기준을 통과한 영상으로 보완합니다.</p>{makeMindmap.isPending && <p className="mt-4 rounded-xl bg-navy-900 p-5 text-center text-xs text-gray-400">공통 태그와 근거 영상을 분석하는 중입니다.</p>}{mindmap && <><KeywordMindMap mindmap={mindmap} selectedKeywords={selectedKeywords} onToggle={toggleKeyword} evidenceVideos={premiumVideos} /><div className="mt-3 rounded-xl border border-violet-200 bg-white p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><h4 className="text-sm font-bold text-slate-900">스크립트용 정제 키워드 후보</h4><p className="mt-0.5 text-[11px] text-slate-600">반복 태그와 최근 7일 3천/3천·0.25배 기준 근거 영상이 있는 키워드만 최대 5개까지 선택합니다.</p></div><span className="rounded-full bg-violet-100 px-2 py-1 text-[11px] font-bold text-violet-700">{selectedKeywords.size}/{MAX_SELECTED_KEYWORDS}</span></div><div className="mt-3 flex flex-wrap gap-2">{(mindmap.primary || []).slice(0, 8).map(node => <button key={node.keyword} type="button" onClick={() => toggleKeyword(node.keyword, node)} className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${selectedKeywords.has(node.keyword) ? 'border-violet-500 bg-violet-600 text-white' : 'border-slate-300 bg-slate-50 text-slate-800 hover:border-violet-400'}`}>{selectedKeywords.has(node.keyword) && <Check size={12} className="mr-1 inline" />}{node.keyword} · 최고 {displayNumber(node.bestMultiple)}x</button>)}</div>{selectedKeywords.size >= MAX_SELECTED_KEYWORDS && <p className="mt-2 text-xs text-amber-700">최대 5개가 선택되었습니다. 다른 후보를 선택하려면 하나를 해제하세요.</p>}<div className="mt-3 grid gap-2 lg:grid-cols-2">{Object.entries(selected).map(([keyword, item]) => <KeywordReason key={keyword} keyword={keyword} metric={item.metric} />)}</div></div></>}</div>
    <div ref={dailyRef} className="border-b border-navy-700 p-5"><h3 className="text-sm font-bold text-white">마인드맵 근거 영상</h3><p className="mt-1 text-[11px] text-gray-400">최근 7일 일반 영상 중 구독자·조회수 각 3천 이상, 구독자 대비 조회 0.25배 이상인 공개 YouTube 태그와 지표만 표시합니다.</p>{isLoading && <p className="py-8 text-center text-xs text-gray-400">오늘의 고성과 영상을 불러오는 중입니다.</p>}{isError && <p className="py-8 text-center text-xs text-accent-red">자동 후보를 불러오지 못했습니다.</p>}<div className="mt-3 space-y-3">{dailyVisible.map((video, index) => { const item = dailyItems.find(candidate => candidate.keyword === video.title) || {}; const key = `${video.title}-${index}`; const sources = valueOf(item, 'sourceVideos', 'source_videos') || []; return <div key={key}><EvidenceVideoCard video={video} compact /><div className="mt-1 flex justify-end gap-3 text-xs"><button onClick={() => setExpanded(expanded === key ? null : key)} className="inline-flex items-center gap-1 text-gray-400 hover:text-white">근거 세부 보기 ({sources.length}) {expanded === key ? <ChevronUp size={12} /> : <ChevronDown size={12} />}</button><button onClick={() => onUseKeyword?.(video.title)} className="inline-flex items-center gap-1 text-accent-cyan hover:underline">이 주제로 작업 설정 <ArrowUpRight size={12} /></button></div>{expanded === key && <div className="mt-2 space-y-2 rounded-xl border border-navy-700 bg-navy-950/35 p-3">{sources.map(source => <EvidenceVideoCard key={valueOf(source, 'videoId', 'video_id')} video={source} compact />)}</div>}</div>})}</div><Pagination total={dailyTrustedVideos.length} currentPage={dailyPage} onChange={page => movePage(setDailyPage, page, dailyRef)} pageSize={PAGE_SIZE} /></div>
    <div className="border-b border-navy-700 bg-navy-900/20 p-5"><div className="flex items-center gap-2"><Youtube size={17} className="text-red-400" /><h3 className="text-sm font-bold text-white">직접 키워드로 다시 분석</h3></div><p className="mt-1 text-xs text-gray-400">긴급 뉴스나 새 종목을 입력하면 최근 7일의 일반 영상 중 3천/3천·0.25배 기준을 통과한 공개 태그로 지도를 다시 만듭니다.</p><div className="mt-3 flex flex-wrap gap-2"><input value={researchKeyword} onChange={event => setResearchKeyword(event.target.value)} onKeyDown={event => event.key === 'Enter' && researchKeyword.trim() && searchVideos.mutate(researchKeyword.trim())} placeholder="예: 삼성전자 실적, 코스피 전망, FOMC 금리" className="min-w-[260px] flex-1 rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-xs text-white" /><button onClick={() => researchKeyword.trim() && searchVideos.mutate(researchKeyword.trim())} disabled={searchVideos.isPending || !researchKeyword.trim()} className="inline-flex items-center gap-1.5 rounded-lg bg-accent-cyan px-3 py-2 text-xs font-bold text-navy-950 disabled:opacity-50">{searchVideos.isPending ? <Loader size={14} className="animate-spin" /> : <Search size={14} />}영상 검색</button><button onClick={() => onUseKeyword?.(researchKeyword.trim())} className="rounded-lg border border-accent-cyan/60 px-3 py-2 text-xs font-semibold text-accent-cyan">이 검색어로 작업 설정</button></div>{researchVideos.length > 0 && <div ref={directRef} className="mt-4 space-y-3">{directVisible.map(video => <EvidenceVideoCard key={valueOf(video, 'videoId', 'video_id')} video={video} />)}<Pagination total={directTrustedVideos.length} currentPage={directPage} onChange={page => movePage(setDirectPage, page, directRef)} pageSize={PAGE_SIZE} /></div>}</div>
    <div className="border-b border-navy-700 px-5 py-4"><div className="flex flex-wrap gap-2"><input value={manualKeyword} onChange={event => { setManualKeyword(event.target.value); setManualContext(null) }} placeholder="긴급 뉴스 키워드를 직접 추가하기 전 최신 근거 확인" className="min-w-[240px] flex-1 rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-xs text-white" /><input value={note} onChange={event => setNote(event.target.value)} placeholder="추가 사유 메모 (선택)" className="w-44 rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-xs text-white" /><button onClick={requestManualPreview} disabled={!manualKeyword.trim() || previewManual.isPending} className="inline-flex items-center gap-1 rounded-lg border border-accent-gold px-3 py-2 text-xs font-semibold text-accent-gold disabled:opacity-50">{previewManual.isPending ? <Loader size={14} className="animate-spin" /> : <Search size={14} />}최근 2시간 근거 확인</button></div></div><ManualContext context={manualContext} onAdd={() => addManual.mutate()} adding={addManual.isPending} />
    {selectedKeywords.size > 0 && <aside className="fixed inset-x-4 bottom-4 z-30 rounded-xl border border-accent-cyan/40 bg-navy-900/95 p-3 shadow-2xl backdrop-blur lg:left-72 lg:right-8"><div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"><div className="min-w-0"><p className="text-xs font-semibold text-white">선택한 정제 키워드 {selectedKeywords.size}개</p><div className="mt-1 flex flex-wrap gap-1">{[...selectedKeywords].map(item => <button key={item} onClick={() => toggleKeyword(item)} className="max-w-full truncate rounded-full bg-accent-cyan/15 px-2 py-1 text-[11px] text-accent-cyan">{item} ×</button>)}</div></div><button onClick={openSelectedKeywordSetup} className="w-full rounded-lg bg-accent-cyan px-3 py-2 text-xs font-bold text-navy-950 lg:w-auto">선택 키워드로 작업 설정 열기</button></div></aside>}
    <footer className="flex items-center gap-1 border-t border-navy-700 px-5 py-3 text-[10px] text-gray-400">타 채널의 평균 시청 시간·CTR·노출수는 공개 API로 확인할 수 없어 표시하지 않습니다.</footer>
  </section>
}
