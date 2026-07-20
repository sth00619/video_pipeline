import { useEffect, useMemo, useRef, useState } from 'react'
import { hierarchy, linkHorizontal, tree } from 'd3'
import { Check, ChevronRight, Network, Sparkles } from 'lucide-react'

const FILTERS = [
  { id: 'all', label: '전체', threshold: 0 },
  { id: 'one', label: '1x 이상', threshold: 1 },
  { id: 'three', label: '3x 이상', threshold: 3 },
]

const ellipsis = (value, limit = 19) => value?.length > limit ? `${value.slice(0, limit)}…` : value
const multipleOf = node => Number(node?.bestMultiple || 0)
const evidenceMultiple = video => Number(video?.subscribers || video?.subscriberCount || 0) > 0
  ? Number(video?.views || video?.viewCount || 0) / Number(video?.subscribers || video?.subscriberCount || 0)
  : 0

function nodeStyle(node) {
  const value = multipleOf(node)
  if (node.kind === 'root') return { width: 182, fill: '#312e81', stroke: '#4f46e5', text: '#ffffff', subtext: '#c7d2fe', badge: '분석 중심' }
  if (node.kind === 'overflow') return { width: 126, fill: '#f8fafc', stroke: '#94a3b8', text: '#475569', subtext: '#64748b', badge: '더 보기' }
  if (value >= 5) return { width: 174, fill: '#fff1f2', stroke: '#ef4444', text: '#991b1b', subtext: '#dc2626', badge: '떡상' }
  if (value >= 1) return { width: 160, fill: '#ecfdf5', stroke: '#10b981', text: '#065f46', subtext: '#047857', badge: '주목' }
  if (value >= .3) return { width: 150, fill: '#fffbeb', stroke: '#f59e0b', text: '#92400e', subtext: '#b45309', badge: '관찰' }
  return { width: 148, fill: '#f8fafc', stroke: '#94a3b8', text: '#334155', subtext: '#64748b', badge: '낮음' }
}

function EvidenceCard({ video, active, elementRef }) {
  const title = video?.title || '제목 정보 없음'
  const multiple = evidenceMultiple(video)
  const grade = video?.performanceGrade || video?.performance_grade || 'A'
  const id = video?.videoId || video?.video_id
  return <a ref={elementRef} href={id ? `https://www.youtube.com/watch?v=${id}` : undefined} target="_blank" rel="noreferrer" className={`block w-full rounded-xl border p-3 text-left transition ${active ? 'border-violet-400 bg-violet-50 ring-2 ring-violet-100' : 'border-slate-200 bg-white hover:border-violet-300 hover:bg-slate-50'}`}>
    <div className="flex items-start gap-2">
      <span className={`inline-flex h-5 min-w-5 items-center justify-center rounded text-[10px] font-black ${grade === 'S' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{grade}</span>
      <div className="min-w-0"><p className="line-clamp-2 text-[12px] font-semibold leading-5 text-slate-800">{title}</p><p className="mt-1 text-[11px] text-slate-600">{video?.channelTitle || video?.channel_title || '채널 정보 없음'} · 구독자 대비 {multiple ? `${multiple.toFixed(2)}x` : '계산 불가'}</p></div>
    </div>
  </a>
}

function MindmapNode({ point, active, selected, onToggle, onFocusEvidence, onToggleBranch, onHover }) {
  const node = point.data
  const style = nodeStyle(node)
  const height = node.kind === 'root' ? 60 : 52
  const left = point.y - style.width / 2
  const top = point.x - height / 2
  const isParent = node.kind === 'primary' && node.hasChildren
  const handleSelect = () => {
    if (node.kind === 'root' || node.kind === 'overflow') return
    onToggle(node.keyword, node)
    if (node.sourceVideoId) onFocusEvidence?.(node.sourceVideoId, node.keyword)
  }
  return <g className={`transition-opacity duration-150 ${active ? 'opacity-100' : 'opacity-25'}`} onMouseEnter={() => onHover(node)} onMouseLeave={() => onHover(null)}>
    <rect x={left} y={top} width={style.width} height={height} rx="13" fill={selected ? style.stroke : style.fill} stroke={style.stroke} strokeWidth={node.kind === 'root' ? 2.5 : multipleOf(node) >= 5 ? 2 : 1.4} className={node.kind === 'root' || node.kind === 'overflow' ? '' : 'cursor-pointer'} onClick={handleSelect} />
    {node.kind === 'root' ? <><text x={point.y} y={point.x - 4} textAnchor="middle" fill={style.text} fontSize="16" fontWeight="800">{ellipsis(node.keyword, 17)}</text><text x={point.y} y={point.x + 14} textAnchor="middle" fill={style.subtext} fontSize="10">오늘의 분석 중심</text></> : <>
      <text x={point.y} y={point.x - 5} textAnchor="middle" fill={selected ? '#ffffff' : style.text} fontSize="13.5" fontWeight="700" className={node.kind === 'overflow' ? '' : 'cursor-pointer'} onClick={handleSelect}>{ellipsis(node.keyword, style.width >= 170 ? 18 : 16)}</text>
      <text x={point.y} y={point.x + 12} textAnchor="middle" fill={selected ? '#f1f5f9' : style.subtext} fontSize="10.5" fontWeight="700">{node.kind === 'overflow' ? '확장 주제 보기' : `${style.badge} · 최고 ${multipleOf(node).toFixed(2)}x`}</text>
    </>}
    {isParent && <g role="button" tabIndex="0" aria-label={`${node.keyword} 확장 ${node.collapsed ? '열기' : '접기'}`} className="cursor-pointer" onClick={event => { event.stopPropagation(); onToggleBranch(node.id) }} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onToggleBranch(node.id) } }}><circle cx={left + style.width - 1} cy={top + 1} r="10" fill="#ffffff" stroke={style.stroke} /><text x={left + style.width - 1} y={top + 4} textAnchor="middle" fill={style.text} fontSize="14" fontWeight="800">{node.collapsed ? '+' : '−'}</text></g>}
  </g>
}

export default function KeywordMindMap({ mindmap, selectedKeywords, onToggle, evidenceVideos = [], onFocusEvidence }) {
  // 0.25x 이상은 이미 서버에서 검증한다. 처음부터 1x 필터를 켜면
  // 유효한 신규 이슈까지 빈 지도처럼 보이므로 기본값은 전체다.
  const [filter, setFilter] = useState('all')
  const [collapsed, setCollapsed] = useState(() => new Set())
  const [hovered, setHovered] = useState(null)
  const evidenceRefs = useRef(new Map())
  const canvasRef = useRef(null)
  const [viewport, setViewport] = useState({ width: 900, height: 430 })
  const threshold = FILTERS.find(item => item.id === filter)?.threshold || 0

  useEffect(() => {
    const element = canvasRef.current
    if (!element || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0) setViewport(previous => Math.abs(previous.width - width) > 4 || Math.abs(previous.height - height) > 4 ? { width, height } : previous)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const layout = useMemo(() => {
    const expansionByParent = new Map()
    ;(mindmap?.expansions || []).forEach(item => expansionByParent.set(item.parent, [...(expansionByParent.get(item.parent) || []), item]))
    const primaryLimit = viewport.width < 680 ? 4 : viewport.width < 900 ? 5 : 6
    const primary = (mindmap?.primary || []).filter(item => multipleOf(item) >= threshold).sort((left, right) => multipleOf(right) - multipleOf(left)).slice(0, primaryLimit)
    const children = primary.map((item, index) => {
      const all = (expansionByParent.get(item.keyword) || []).filter(child => multipleOf(child) >= threshold).sort((left, right) => multipleOf(right) - multipleOf(left))
      const isCollapsed = collapsed.has(`primary-${index}-${item.keyword}`)
      const shown = isCollapsed ? [] : all.slice(0, 2).map((child, childIndex) => ({ ...child, kind: 'expansion', id: `child-${index}-${childIndex}-${child.keyword}` }))
      if (!isCollapsed && all.length > 2) shown.push({ kind: 'overflow', id: `more-${index}-${item.keyword}`, keyword: `+${all.length - 2}개 더 보기`, bestMultiple: item.bestMultiple })
      return { ...item, kind: 'primary', id: `primary-${index}-${item.keyword}`, hasChildren: all.length > 0, collapsed: isCollapsed, children: shown }
    })
    const data = { kind: 'root', id: 'root', keyword: mindmap?.center || '분석 중심', children }
    const root = hierarchy(data).sort((left, right) => multipleOf(right.data) - multipleOf(left.data))
    const verticalGap = Math.max(48, Math.min(62, (viewport.height - 58) / Math.max(children.length, 2)))
    const horizontalGap = viewport.width < 680 ? 170 : 205
    tree().nodeSize([verticalGap, horizontalGap])(root)
    const nodes = root.descendants()
    const minX = Math.min(...nodes.map(item => item.x - 36))
    const maxX = Math.max(...nodes.map(item => item.x + 36))
    const minY = Math.min(...nodes.map(item => item.y - nodeStyle(item.data).width / 2))
    const maxY = Math.max(...nodes.map(item => item.y + nodeStyle(item.data).width / 2))
    return { root, nodes, links: root.links(), viewBox: `${minY - 28} ${minX - 34} ${maxY - minY + 56} ${maxX - minX + 68}` }
  }, [mindmap, threshold, collapsed, viewport])

  if (!mindmap?.center) return null
  const activeIds = new Set()
  if (hovered?.id) {
    const item = layout.nodes.find(point => point.data.id === hovered.id)
    item?.ancestors().forEach(point => activeIds.add(point.data.id))
    item?.descendants().forEach(point => activeIds.add(point.data.id))
  }
  const hasHover = activeIds.size > 0
  const line = linkHorizontal().x(point => point.y).y(point => point.x)
  const focusEvidence = (videoId, keyword) => {
    onFocusEvidence?.(videoId, keyword)
    const video = evidenceVideos.find(item => item.videoId === videoId || item.video_id === videoId || String(item.title || '').includes(keyword))
    const key = video?.videoId || video?.video_id || video?.title
    evidenceRefs.current.get(key)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  return <section className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div className="border-b border-slate-200 bg-slate-50 px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><Network size={16} className="text-violet-600" /><div><h4 className="text-sm font-bold text-slate-900">핵심 주제 마인드맵</h4><p className="mt-0.5 text-[11px] text-slate-600">실선은 정제 키워드, 점선은 같은 근거 영상에서 뽑은 확장 주제입니다.</p></div></div><div className="flex items-center gap-2"><div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5" role="group" aria-label="성과 배율 필터">{FILTERS.map(item => <button key={item.id} onClick={() => setFilter(item.id)} className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${filter === item.id ? 'bg-violet-600 text-white' : 'text-slate-700 hover:bg-slate-100'}`}>{item.label}</button>)}</div><span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-1 text-[10px] font-bold text-violet-700"><Sparkles size={11} />화면 맞춤</span></div></div><div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-700"><span className="font-semibold text-slate-900">범례</span><span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-rose-500" />5x 이상 · 떡상</span><span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />1~5x · 주목</span><span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />0.3~1x · 관찰</span></div></div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_330px]">
      <div className="min-w-0 border-b border-slate-200 p-3 lg:border-b-0 lg:border-r"><div ref={canvasRef} className="h-[min(52vh,500px)] min-h-[340px] w-full"><svg viewBox={layout.viewBox} preserveAspectRatio="xMidYMid meet" className="block h-full w-full" aria-label="좌에서 우로 정렬된 자동 생성 주제 마인드맵">{layout.links.map(item => { const active = !hasHover || (activeIds.has(item.source.data.id) && activeIds.has(item.target.data.id)); return <path key={`${item.source.data.id}-${item.target.data.id}`} d={line(item)} fill="none" stroke={item.target.data.kind === 'expansion' || item.target.data.kind === 'overflow' ? '#94a3b8' : nodeStyle(item.target.data).stroke} strokeWidth={item.target.data.kind === 'primary' ? 2 : 1.5} strokeDasharray={item.target.data.kind === 'primary' ? undefined : '5 5'} className={`transition-opacity ${active ? 'opacity-90' : 'opacity-25'}`} /> })}{layout.nodes.map(point => <MindmapNode key={point.data.id} point={point} active={!hasHover || activeIds.has(point.data.id)} selected={selectedKeywords.has(point.data.keyword)} onToggle={onToggle} onFocusEvidence={focusEvidence} onToggleBranch={id => setCollapsed(previous => { const next = new Set(previous); next.has(id) ? next.delete(id) : next.add(id); return next })} onHover={setHovered} />)}</svg></div>{!layout.root.children?.length && <p className="py-8 text-center text-sm text-slate-600">이 필터 조건을 통과한 키워드가 없습니다. 전체를 선택해 확인하세요.</p>}<p className="mt-1 text-[11px] text-slate-700">화면 너비와 높이에 맞춰 핵심 4~6개를 자동 배치합니다. 키워드를 누르면 스크립트 기획 후보에 담깁니다.</p></div>
      <aside className="bg-slate-50 p-4"><div className="flex items-center justify-between"><div><h4 className="text-sm font-bold text-slate-900">검증 근거 영상</h4><p className="mt-1 text-[11px] text-slate-600">S/A 우선 정렬한 일반 공개 영상입니다.</p></div><span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-bold text-emerald-700">{evidenceVideos.length}개</span></div><div className="mt-3 space-y-2">{evidenceVideos.slice(0, 8).map(video => { const key = video.videoId || video.video_id || video.title; const matches = hovered && (video.videoId === hovered.sourceVideoId || video.video_id === hovered.sourceVideoId || String(video.title || '').includes(hovered.keyword)); return <EvidenceCard key={key} elementRef={element => { if (element) evidenceRefs.current.set(key, element); else evidenceRefs.current.delete(key) }} video={video} active={matches} /> })}</div>{evidenceVideos.length > 8 && <p className="mt-3 flex items-center text-[11px] text-slate-600">나머지 영상은 아래 목록에서 확인하세요 <ChevronRight size={13} /></p>}</aside>
    </div>
  </section>
}
