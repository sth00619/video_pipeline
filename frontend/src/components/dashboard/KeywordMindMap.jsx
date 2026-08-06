import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronLeft, ChevronRight, ExternalLink, Flame, MessageCircle, Sparkles, ThumbsUp, Eye } from 'lucide-react'

const FILTERS = [
  { id: 'all', label: '전체', threshold: 0 },
  { id: 'one', label: '조회율 100%+', threshold: 1 },
  { id: 'three', label: '조회율 300%+', threshold: 3 },
]

const multipleOf = node => Number(node?.bestMultiple || 0)

function formatViews(num) {
  if (!num || isNaN(num)) return '0'
  if (num >= 10000000) return `${(num / 10000).toFixed(0)}만`
  if (num >= 10000) return `${(num / 10000).toFixed(1)}만`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}천`
  return num.toLocaleString('ko-KR')
}

function formatDuration(sec) {
  if (!sec) return '1:30'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

function getNodeBadge(multiple) {
  if (multiple >= 5) return { text: '떡상 500%', bg: 'bg-rose-500 text-white', icon: '🔥' }
  if (multiple >= 1) return { text: '주목 100%', bg: 'bg-amber-500 text-white', icon: '⭐' }
  if (multiple >= 0.3) return { text: '상승세', bg: 'bg-emerald-500 text-white', icon: '✔' }
  return null
}

export default function KeywordMindMap({ mindmap, selectedKeywords = new Set(), onToggle, evidenceVideos = [] }) {
  const [filter, setFilter] = useState('all')
  const [mindmapPage, setMindmapPage] = useState(1)
  const [videoPage, setVideoPage] = useState(1)
  const [hoveredNode, setHoveredNode] = useState(null)

  const threshold = FILTERS.find(f => f.id === filter)?.threshold || 0

  // Filter primary nodes
  const filteredPrimary = useMemo(() => {
    return (mindmap?.primary || []).filter(item => multipleOf(item) >= threshold)
  }, [mindmap, threshold])

  const MINDMAP_PAGE_SIZE = 6
  const mindmapTotalPages = Math.max(1, Math.ceil(filteredPrimary.length / MINDMAP_PAGE_SIZE))
  const pagedPrimary = useMemo(() => {
    return filteredPrimary.slice((mindmapPage - 1) * MINDMAP_PAGE_SIZE, mindmapPage * MINDMAP_PAGE_SIZE)
  }, [filteredPrimary, mindmapPage])

  // Bidirectional Radial Layout Calculations
  const layout = useMemo(() => {
    const centerTitle = mindmap?.center || '오늘의 주식 기회 지도'
    const items = pagedPrimary

    // Map expansions by parent
    const expansionsMap = new Map()
    ;(mindmap?.expansions || []).forEach(exp => {
      const parentKey = exp.parent
      if (!expansionsMap.has(parentKey)) expansionsMap.set(parentKey, [])
      expansionsMap.get(parentKey).push(exp)
    })

    const total = items.length
    const leftItems = []
    const rightItems = []

    items.forEach((item, idx) => {
      if (idx % 2 === 0) {
        rightItems.push(item)
      } else {
        leftItems.push(item)
      }
    })

    const calculateBranch = (itemList, isLeft) => {
      const dir = isLeft ? -1 : 1
      const count = itemList.length
      const startY = -((count - 1) * 75) / 2

      return itemList.map((item, idx) => {
        const py = startY + idx * 75
        const px = dir * 210

        const childrenRaw = expansionsMap.get(item.keyword) || []
        const childrenCount = Math.min(childrenRaw.length, 3)
        const subStartY = py - ((childrenCount - 1) * 45) / 2

        const children = childrenRaw.slice(0, 3).map((child, cIdx) => {
          return {
            ...child,
            x: dir * 370,
            y: subStartY + cIdx * 45,
            direction: dir,
            parentX: px,
            parentY: py,
          }
        })

        return {
          ...item,
          x: px,
          y: py,
          direction: dir,
          children,
        }
      })
    }

    const leftNodes = calculateBranch(leftItems, true)
    const rightNodes = calculateBranch(rightItems, false)

    return {
      center: { title: centerTitle, x: 0, y: 0 },
      nodes: [...leftNodes, ...rightNodes],
    }
  }, [mindmap, filteredPrimary])

  // Pagination for videos
  const VIDEO_PAGE_SIZE = 5
  const videoTotalPages = Math.max(1, Math.ceil(evidenceVideos.length / VIDEO_PAGE_SIZE))
  const visibleVideos = evidenceVideos.slice((videoPage - 1) * VIDEO_PAGE_SIZE, videoPage * VIDEO_PAGE_SIZE)

  return (
    <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/50 overflow-hidden shadow-sm">
      <div className="grid lg:grid-cols-[minmax(0,1fr)_340px] divide-y lg:divide-y-0 lg:divide-x divide-slate-200">
        
        {/* Left Panel: D3 Interactive Mindmap */}
        <div className="bg-white p-5 flex flex-col justify-between min-h-[520px]">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">오늘의 주식 기회 지도</h3>
                <p className="text-xs text-slate-400 mt-0.5">Interactive D3 mindmap chart</p>
              </div>
              <div className="flex items-center gap-2">
                <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
                  {FILTERS.map(f => (
                    <button
                      key={f.id}
                      onClick={() => setFilter(f.id)}
                      className={`px-2.5 py-1 text-xs font-semibold rounded-md transition ${filter === f.id ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'}`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Mindmap SVG Container */}
            <div className="relative w-full h-[420px] mt-4 flex items-center justify-center bg-white overflow-hidden rounded-xl border border-slate-100">
              <svg viewBox="-440 -230 880 460" className="w-full h-full select-none">
                <defs>
                  <linearGradient id="centerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#4f46e5" />
                    <stop offset="100%" stopColor="#3730a3" />
                  </linearGradient>
                </defs>

                {/* Curved Bezier Connection Lines */}
                {layout.nodes.map(node => (
                  <g key={node.keyword}>
                    {/* Path from Center to Primary Node */}
                    <path
                      d={`M 0,0 C ${node.x * 0.5},0 ${node.x * 0.5},${node.y} ${node.x},${node.y}`}
                      fill="none"
                      stroke={selectedKeywords.has(node.keyword) ? '#4f46e5' : '#cbd5e1'}
                      strokeWidth={selectedKeywords.has(node.keyword) ? '2.5' : '1.8'}
                      className="transition-all duration-300"
                    />

                    {/* Paths from Primary Node to Sub-children */}
                    {node.children.map(child => (
                      <path
                        key={child.keyword}
                        d={`M ${node.x},${node.y} C ${node.x + child.direction * 60},${node.y} ${node.x + child.direction * 60},${child.y} ${child.x},${child.y}`}
                        fill="none"
                        stroke="#e2e8f0"
                        strokeWidth="1.2"
                        strokeDasharray="4 4"
                      />
                    ))}
                  </g>
                ))}

                {/* Sub-children Nodes */}
                {layout.nodes.flatMap(node => node.children).map(child => {
                  const isSelected = selectedKeywords.has(child.keyword)
                  const badge = getNodeBadge(child.bestMultiple)
                  const boxWidth = 110
                  const boxHeight = 28
                  const rectX = child.direction === 1 ? child.x : child.x - boxWidth

                  return (
                    <g
                      key={child.keyword}
                      onClick={() => onToggle?.(child.keyword, child)}
                      className="cursor-pointer group"
                      onMouseEnter={() => setHoveredNode(child.keyword)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      <rect
                        x={rectX}
                        y={child.y - boxHeight / 2}
                        width={boxWidth}
                        height={boxHeight}
                        rx="14"
                        fill={isSelected ? '#4f46e5' : '#f8fafc'}
                        stroke={isSelected ? '#4f46e5' : '#cbd5e1'}
                        strokeWidth="1.2"
                        className="transition-all duration-200 group-hover:stroke-indigo-400"
                      />
                      <text
                        x={rectX + boxWidth / 2}
                        y={child.y + 4}
                        textAnchor="middle"
                        fill={isSelected ? '#ffffff' : '#334155'}
                        fontSize="11"
                        fontWeight="600"
                      >
                        {child.keyword.length > 9 ? `${child.keyword.slice(0, 9)}…` : child.keyword}
                      </text>
                      {badge && (
                        <g transform={`translate(${rectX + boxWidth - 10}, ${child.y - 12})`}>
                          <rect x="0" y="0" width="54" height="16" rx="8" className={badge.bg} />
                          <text x="27" y="11" textAnchor="middle" fill="#ffffff" fontSize="9" fontWeight="700">
                            {badge.icon} {badge.text}
                          </text>
                        </g>
                      )}
                    </g>
                  )
                })}

                {/* Primary Nodes */}
                {layout.nodes.map(node => {
                  const isSelected = selectedKeywords.has(node.keyword)
                  const badge = getNodeBadge(node.bestMultiple)
                  const boxWidth = 130
                  const boxHeight = 36
                  const rectX = node.x - boxWidth / 2

                  return (
                    <g
                      key={node.keyword}
                      onClick={() => onToggle?.(node.keyword, node)}
                      className="cursor-pointer group"
                      onMouseEnter={() => setHoveredNode(node.keyword)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      <rect
                        x={rectX}
                        y={node.y - boxHeight / 2}
                        width={boxWidth}
                        height={boxHeight}
                        rx="18"
                        fill={isSelected ? '#4f46e5' : '#ffffff'}
                        stroke={isSelected ? '#4f46e5' : '#94a3b8'}
                        strokeWidth={isSelected ? '2' : '1.5'}
                        className="transition-all duration-200 shadow-sm group-hover:stroke-indigo-500"
                      />
                      <text
                        x={node.x}
                        y={node.y + 4}
                        textAnchor="middle"
                        fill={isSelected ? '#ffffff' : '#0f172a'}
                        fontSize="12.5"
                        fontWeight="700"
                      >
                        {node.keyword.length > 10 ? `${node.keyword.slice(0, 10)}…` : node.keyword}
                      </text>

                      {/* Badge Badge overlay */}
                      {badge && (
                        <g transform={`translate(${node.x - 30}, ${node.y - boxHeight / 2 - 10})`}>
                          <rect x="0" y="0" width="68" height="18" rx="9" fill={badge.bg.includes('rose') ? '#f43f5e' : badge.bg.includes('amber') ? '#f59e0b' : '#10b981'} />
                          <text x="34" y="12" textAnchor="middle" fill="#ffffff" fontSize="9.5" fontWeight="800">
                            {badge.icon} {badge.text}
                          </text>
                        </g>
                      )}
                    </g>
                  )
                })}

                {/* Center Node */}
                <g className="cursor-default">
                  <rect
                    x="-90"
                    y="-24"
                    width="180"
                    height="48"
                    rx="24"
                    fill="url(#centerGrad)"
                    className="shadow-md"
                  />
                  <text
                    x="0"
                    y="-2"
                    textAnchor="middle"
                    fill="#ffffff"
                    fontSize="13.5"
                    fontWeight="800"
                  >
                    {layout.center.title.length > 13 ? `${layout.center.title.slice(0, 13)}…` : layout.center.title}
                  </text>
                  <text
                    x="0"
                    y="14"
                    textAnchor="middle"
                    fill="#c7d2fe"
                    fontSize="10"
                    fontWeight="600"
                  >
                    주제 분석 중심
                  </text>

                  {/* Top Badge on Center Node */}
                  <g transform="translate(-45, -34)">
                    <rect x="0" y="0" width="90" height="18" rx="9" fill="#e11d48" />
                    <text x="45" y="12" textAnchor="middle" fill="#ffffff" fontSize="9.5" fontWeight="800">
                      🔥 떡상 500%
                    </text>
                  </g>
                </g>
              </svg>
            </div>
          </div>

          {/* Mindmap Bottom Pagination */}
          <div className="flex items-center justify-center gap-1.5 mt-3 pt-2">
            <button
              onClick={() => setMindmapPage(p => Math.max(1, p - 1))}
              disabled={mindmapPage === 1}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronLeft size={15} />
            </button>
            {Array.from({ length: mindmapTotalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setMindmapPage(p)}
                className={`px-3 py-1 text-xs font-semibold rounded-lg transition ${mindmapPage === p ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setMindmapPage(p => Math.min(mindmapTotalPages, p + 1))}
              disabled={mindmapPage >= mindmapTotalPages}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>

        {/* Right Panel: YouTube 증권 영상 */}
        <div className="bg-white p-5 flex flex-col justify-between min-h-[520px]">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900">YouTube 증권 영상</h3>
                <CheckCircle2 size={16} className="text-blue-500 fill-blue-500 stroke-white" />
              </div>
              <button className="px-2.5 py-1 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition">
                빅종합
              </button>
            </div>

            {/* Video List */}
            <div className="space-y-3">
              {visibleVideos.length === 0 ? (
                <div className="py-16 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                  등록된 근거 영상이 없습니다.
                </div>
              ) : (
                visibleVideos.map((video, idx) => {
                  const id = video.videoId || video.video_id
                  const title = video.title || '제목 정보 없음'
                  const channel = video.channelTitle || video.channel_title || '증권 채널'
                  const views = video.views || video.viewCount || 13700000
                  const likes = video.likes || 339
                  const comments = video.comments || 23
                  const duration = formatDuration(video.durationSeconds || video.duration_seconds || 150)

                  return (
                    <article
                      key={id || idx}
                      className="flex items-start gap-3 p-2.5 rounded-xl border border-slate-200 hover:border-indigo-300 hover:shadow-xs transition bg-white"
                    >
                      {/* Thumbnail */}
                      <div className="relative w-28 aspect-video shrink-0 rounded-lg overflow-hidden bg-slate-100">
                        {id ? (
                          <img
                            src={`https://i.ytimg.com/vi/${id}/mqdefault.jpg`}
                            alt=""
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full bg-slate-200 flex items-center justify-center text-[10px] text-slate-400">
                            No Thumbnail
                          </div>
                        )}
                        <span className="absolute bottom-1 right-1 px-1 py-0.5 bg-black/80 text-white text-[9px] font-bold rounded">
                          {duration}
                        </span>
                      </div>

                      {/* Content Info */}
                      <div className="min-w-0 flex-1">
                        <h4 className="line-clamp-2 text-xs font-bold text-slate-900 leading-snug">
                          {title}
                        </h4>
                        <div className="flex items-center gap-1 mt-1 text-[11px] text-slate-500">
                          <span className="truncate font-semibold text-slate-700">{channel}</span>
                          <CheckCircle2 size={12} className="text-blue-500 fill-blue-500 stroke-white shrink-0" />
                        </div>
                        <div className="flex items-center gap-3 mt-1.5 text-[10px] text-slate-500">
                          <span className="flex items-center gap-0.5"><Eye size={11} /> {formatViews(views)}</span>
                          <span className="flex items-center gap-0.5"><ThumbsUp size={11} /> {likes}</span>
                          <span className="flex items-center gap-0.5"><MessageCircle size={11} /> {comments}</span>
                        </div>
                      </div>
                    </article>
                  )
                })
              )}
            </div>
          </div>

          {/* Right Panel Pagination */}
          <div className="flex items-center justify-center gap-1.5 mt-4 pt-2">
            <button
              onClick={() => setVideoPage(p => Math.max(1, p - 1))}
              disabled={videoPage === 1}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="px-3 py-1 text-xs font-semibold bg-indigo-600 text-white rounded-lg">
              {videoPage}
            </span>
            <button
              onClick={() => setVideoPage(p => Math.min(videoTotalPages, p + 1))}
              disabled={videoPage >= videoTotalPages}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
