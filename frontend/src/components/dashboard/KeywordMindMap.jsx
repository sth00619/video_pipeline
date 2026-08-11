import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronLeft, ChevronRight, MessageCircle, ThumbsUp, Eye } from 'lucide-react'
import * as d3 from 'd3'

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

const PALETTES = [
  { bg: '#fff1f2', stroke: '#f43f5e', text: '#9f1239', badgeBg: '#f43f5e', badgeText: '🔥 떡상 500%' },
  { bg: '#fef3c7', stroke: '#f59e0b', text: '#78350f', badgeBg: '#f59e0b', badgeText: '⭐ 주목 100%' },
  { bg: '#d1fae5', stroke: '#10b981', text: '#064e3b', badgeBg: '#10b981', badgeText: '✔ 상승세' },
  { bg: '#e0e7ff', stroke: '#6366f1', text: '#312e81', badgeBg: '#6366f1', badgeText: '★ 급상승' },
  { bg: '#f1f5f9', stroke: '#64748b', text: '#0f172a', badgeBg: null, badgeText: null },
]

function getNodeStyle(node, idx) {
  const mult = multipleOf(node)
  if (mult >= 5 || idx % 4 === 0) return PALETTES[0]
  if (mult >= 1 || idx % 4 === 1) return PALETTES[1]
  if (mult >= 0.3 || idx % 4 === 2) return PALETTES[2]
  return PALETTES[3]
}

export default function KeywordMindMap({ mindmap, selectedKeywords = new Set(), onToggle, evidenceVideos = [] }) {
  const [videoPage, setVideoPage] = useState(1)
  const [hoveredNode, setHoveredNode] = useState(null)

  const svgRef = useRef(null)
  const gRef = useRef(null)

  // Primary nodes without page-slicing
  const filteredPrimary = useMemo(() => {
    return mindmap?.primary || []
  }, [mindmap])

  // Bidirectional Radial Layout Calculations
  const layout = useMemo(() => {
    const centerTitle = mindmap?.center || '오늘의 주식 기회 지도'
    const items = filteredPrimary

    const expansionsMap = new Map()
    ;(mindmap?.expansions || []).forEach(exp => {
      const parentKey = exp.parent
      if (!expansionsMap.has(parentKey)) expansionsMap.set(parentKey, [])
      expansionsMap.get(parentKey).push(exp)
    })

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
      const startY = -((count - 1) * 80) / 2

      return itemList.map((item, idx) => {
        const py = startY + idx * 80
        const px = dir * 220

        const childrenRaw = expansionsMap.get(item.keyword) || []
        const childrenCount = Math.min(childrenRaw.length, 3)
        const subStartY = py - ((childrenCount - 1) * 46) / 2

        const children = childrenRaw.slice(0, 3).map((child, cIdx) => {
          return {
            ...child,
            x: dir * 380,
            y: subStartY + cIdx * 46,
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

  // D3 Zoom behavior and auto-fit to view
  useEffect(() => {
    if (!svgRef.current || !gRef.current) return
    const svg = d3.select(svgRef.current)
    const g = d3.select(gRef.current)

    const zoom = d3.zoom()
      .scaleExtent([0.4, 2.5])
      .on("zoom", (event) => {
        g.attr("transform", event.transform)
      })

    svg.call(zoom)

    const fitToView = () => {
      const bounds = g.node()?.getBBox()
      if (!bounds || !bounds.width || !bounds.height) return
      const fullWidth = svgRef.current.clientWidth || 900
      const fullHeight = svgRef.current.clientHeight || 460
      const scale = Math.min(
        0.9 * fullWidth / bounds.width,
        0.9 * fullHeight / bounds.height,
        1.5
      )
      const tx = fullWidth / 2 - scale * (bounds.x + bounds.width / 2)
      const ty = fullHeight / 2 - scale * (bounds.y + bounds.height / 2)
      svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale))
    }
    fitToView()
  }, [layout])

  // Pagination for videos
  const VIDEO_PAGE_SIZE = 5
  const videoTotalPages = Math.max(1, Math.ceil(evidenceVideos.length / VIDEO_PAGE_SIZE))
  const visibleVideos = evidenceVideos.slice((videoPage - 1) * VIDEO_PAGE_SIZE, videoPage * VIDEO_PAGE_SIZE)

  return (
    <div className="w-full">
      <div className="flex flex-col lg:flex-row gap-5 items-start">
        
        {/* Left Card: D3 Interactive Mindmap (70% width) */}
        <div className="w-full lg:w-[70%] min-h-[520px] overflow-hidden bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">오늘의 주식 기회 지도</h3>
                <p className="text-xs text-slate-400 mt-0.5">Interactive D3 mindmap chart</p>
              </div>
            </div>

            {/* Mindmap SVG Container */}
            <div className="relative w-full h-[450px] mt-4 flex items-center justify-center bg-white overflow-hidden rounded-xl border border-slate-100">
              <svg ref={svgRef} viewBox="-450 -230 900 460" className="w-full h-full select-none">
                <defs>
                  <linearGradient id="centerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#4338ca" />
                    <stop offset="100%" stopColor="#312e81" />
                  </linearGradient>
                </defs>

                <g ref={gRef}>
                  {/* Connection Lines */}
                  {layout.nodes.map(node => (
                    <g key={node.keyword}>
                      <path
                        d={`M 0,0 C ${node.x * 0.5},0 ${node.x * 0.5},${node.y} ${node.x},${node.y}`}
                        fill="none"
                        stroke={selectedKeywords.has(node.keyword) ? '#4f46e5' : '#cbd5e1'}
                        strokeWidth={selectedKeywords.has(node.keyword) ? '2.5' : '1.8'}
                        className="transition-all duration-300"
                      />

                      {node.children.map(child => (
                        <path
                          key={child.keyword}
                          d={`M ${node.x},${node.y} C ${node.x + child.direction * 60},${node.y} ${node.x + child.direction * 60},${child.y} ${child.x},${child.y}`}
                          fill="none"
                          stroke="#cbd5e1"
                          strokeWidth="1.2"
                          strokeDasharray="4 4"
                        />
                      ))}
                    </g>
                  ))}

                  {/* Sub-children Nodes */}
                  {layout.nodes.flatMap(node => node.children).map((child, idx) => {
                    const isSelected = selectedKeywords.has(child.keyword)
                    const style = getNodeStyle(child, idx + 2)
                    const boxWidth = 115
                    const boxHeight = 30
                    const rectX = child.direction === 1 ? child.x : child.x - boxWidth

                    return (
                      <g
                        key={child.keyword}
                        onClick={() => onToggle?.(child.keyword, child)}
                        className="cursor-pointer group"
                      >
                        <rect
                          x={rectX}
                          y={child.y - boxHeight / 2}
                          width={boxWidth}
                          height={boxHeight}
                          rx="15"
                          fill={isSelected ? '#4f46e5' : '#ffffff'}
                          stroke={isSelected ? '#4f46e5' : style.stroke}
                          strokeWidth="1.5"
                          className="transition-all duration-200 shadow-xs group-hover:scale-105"
                        />
                        <text
                          x={rectX + boxWidth / 2}
                          y={child.y + 4}
                          textAnchor="middle"
                          fill={isSelected ? '#ffffff' : style.text}
                          fontSize="11"
                          fontWeight="700"
                        >
                          {child.keyword.length > 9 ? `${child.keyword.slice(0, 9)}…` : child.keyword}
                        </text>
                      </g>
                    )
                  })}

                  {/* Primary Nodes */}
                  {layout.nodes.map((node, idx) => {
                    const isSelected = selectedKeywords.has(node.keyword)
                    const style = getNodeStyle(node, idx)
                    const boxWidth = 135
                    const boxHeight = 38
                    const rectX = node.x - boxWidth / 2

                    return (
                      <g
                        key={node.keyword}
                        onClick={() => onToggle?.(node.keyword, node)}
                        className="cursor-pointer group"
                      >
                        <rect
                          x={rectX}
                          y={node.y - boxHeight / 2}
                          width={boxWidth}
                          height={boxHeight}
                          rx="19"
                          fill={isSelected ? '#4f46e5' : style.bg}
                          stroke={isSelected ? '#4f46e5' : style.stroke}
                          strokeWidth={isSelected ? '2.5' : '1.8'}
                          className="transition-all duration-200 shadow-sm group-hover:scale-105"
                        />
                        <text
                          x={node.x}
                          y={node.y + 4}
                          textAnchor="middle"
                          fill={isSelected ? '#ffffff' : style.text}
                          fontSize="12.5"
                          fontWeight="800"
                        >
                          {node.keyword.length > 10 ? `${node.keyword.slice(0, 10)}…` : node.keyword}
                        </text>

                        {/* Badge overlay */}
                        {style.badgeText && (
                          <g transform={`translate(${node.x - 34}, ${node.y - boxHeight / 2 - 10})`}>
                            <rect x="0" y="0" width="68" height="18" rx="9" fill={style.badgeBg} />
                            <text x="34" y="12" textAnchor="middle" fill="#ffffff" fontSize="9.5" fontWeight="800">
                              {style.badgeText}
                            </text>
                          </g>
                        )}
                      </g>
                    )
                  })}

                  {/* Center Node */}
                  <g className="cursor-default">
                    <rect
                      x="-95"
                      y="-25"
                      width="190"
                      height="50"
                      rx="25"
                      fill="url(#centerGrad)"
                      className="shadow-lg"
                    />
                    <text
                      x="0"
                      y="-2"
                      textAnchor="middle"
                      fill="#ffffff"
                      fontSize="14"
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

                    {/* Top Badge sitting on center node */}
                    <g transform="translate(-45, -36)">
                      <rect x="0" y="0" width="90" height="18" rx="9" fill="#ef4444" />
                      <text x="45" y="12" textAnchor="middle" fill="#ffffff" fontSize="9.5" fontWeight="800">
                        🔥 떡상 500%
                      </text>
                    </g>
                  </g>
                </g>
              </svg>
            </div>
          </div>
        </div>

        {/* Right Card: YouTube 증권 영상 (30% width) */}
        <div className="w-full lg:w-[30%] min-h-[520px] overflow-y-auto bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between shrink-0">
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
                <div className="py-20 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
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

          {/* Right Video Pagination */}
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
