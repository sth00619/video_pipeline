import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronLeft, ChevronRight, MessageCircle, ThumbsUp, Eye } from 'lucide-react'

const MINDMAP_VIEW_BOX = Object.freeze({ x: -700, y: -180, width: 1400, height: 360 })
const MINDMAP_VIEW_BOX_VALUE = `${MINDMAP_VIEW_BOX.x} ${MINDMAP_VIEW_BOX.y} ${MINDMAP_VIEW_BOX.width} ${MINDMAP_VIEW_BOX.height}`
const CENTER_FILL = '#1e293b'
const CENTER_TEXT = '#ffffff'
const CENTER_RADIUS = 22
const PRIMARY_X = 300
const CHILD_X = 560
const PRIMARY_VERTICAL_GAP = 64
const CHILD_VERTICAL_GAP = 38

function formatViews(num) {
  if (num == null || Number.isNaN(Number(num))) return '—'
  const value = Number(num)
  if (value >= 10000000) return `${(value / 10000).toFixed(0)}만`
  if (value >= 10000) return `${(value / 10000).toFixed(1)}만`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}천`
  return value.toLocaleString('ko-KR')
}

function formatDuration(sec) {
  if (sec == null || Number.isNaN(Number(sec))) return '—'
  const value = Number(sec)
  const m = Math.floor(value / 60)
  const s = Math.floor(value % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

function formatCount(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('ko-KR')
}

function primaryAccentColor(index, direction) {
  if (direction === -1) return '#f43f5e'
  return index % 3 === 1 ? '#7c3aed' : '#3b82f6'
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
    const centerTitle = '오늘의 키워드'
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
      const startY = -((count - 1) * PRIMARY_VERTICAL_GAP) / 2

      return itemList.map((item, idx) => {
        const py = startY + idx * PRIMARY_VERTICAL_GAP
        const px = dir * PRIMARY_X

        const childrenRaw = expansionsMap.get(item.keyword) || []
        const childrenCount = Math.min(childrenRaw.length, 3)
        const subStartY = py - ((childrenCount - 1) * CHILD_VERTICAL_GAP) / 2

        const children = childrenRaw.slice(0, 3).map((child, cIdx) => {
          return {
            ...child,
            x: dir * CHILD_X,
            y: subStartY + cIdx * CHILD_VERTICAL_GAP,
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

  // 마우스 휠 확대·축소 없이 현재 레이아웃을 한 번만 화면에 맞춘다.
  useEffect(() => {
    if (!svgRef.current || !gRef.current) return
    const bounds = gRef.current.getBBox()
    if (!bounds.width || !bounds.height) return
    const viewBox = svgRef.current.viewBox?.baseVal
    const viewBoxX = viewBox?.x ?? MINDMAP_VIEW_BOX.x
    const viewBoxY = viewBox?.y ?? MINDMAP_VIEW_BOX.y
    const viewBoxWidth = viewBox?.width || MINDMAP_VIEW_BOX.width
    const viewBoxHeight = viewBox?.height || MINDMAP_VIEW_BOX.height
    const scale = Math.min(
      0.85 * viewBoxWidth / bounds.width,
      0.85 * viewBoxHeight / bounds.height,
      1.5
    )
    const viewBoxCenterX = viewBoxX + viewBoxWidth / 2
    const viewBoxCenterY = viewBoxY + viewBoxHeight / 2
    const tx = viewBoxCenterX - scale * (bounds.x + bounds.width / 2)
    const ty = viewBoxCenterY - scale * (bounds.y + bounds.height / 2)
    gRef.current.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`)
  }, [layout])

  // Pagination for videos
  const VIDEO_PAGE_SIZE = 5
  const videoTotalPages = Math.max(1, Math.ceil(evidenceVideos.length / VIDEO_PAGE_SIZE))
  const visibleVideos = evidenceVideos.slice((videoPage - 1) * VIDEO_PAGE_SIZE, videoPage * VIDEO_PAGE_SIZE)

  return (
    <div className="w-full">
      <div className="flex flex-col lg:flex-row gap-5 items-start">
        
        {/* Left Card: D3 Interactive Mindmap (70% width) */}
        <div className="w-full lg:w-[70%] min-h-[400px] overflow-hidden bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">오늘의 주식 기회 지도</h3>
                <p className="text-xs text-slate-400 mt-0.5">근거 영상 기반 키워드 관계도</p>
              </div>
            </div>

            {/* Mindmap SVG Container */}
            <div className="relative w-full h-[360px] mt-4 flex items-center justify-center bg-white overflow-hidden rounded-xl border border-slate-100">
              <svg ref={svgRef} viewBox={MINDMAP_VIEW_BOX_VALUE} className="w-full h-full select-none">
                <g ref={gRef}>
                  {/* Connection Lines */}
                  {layout.nodes.map(node => (
                    <g key={node.keyword}>
                      <path
                        d={`M 0,0 C ${node.x * 0.5},0 ${node.x * 0.5},${node.y} ${node.x},${node.y}`}
                        fill="none"
                        stroke={selectedKeywords.has(node.keyword) ? '#7c3aed' : '#64748b'}
                        strokeWidth="2"
                        opacity="1"
                        className="transition-all duration-300"
                      />

                      {node.children.map(child => (
                        <path
                          key={child.keyword}
                          d={`M ${node.x},${node.y} C ${node.x + child.direction * 60},${node.y} ${node.x + child.direction * 60},${child.y} ${child.x},${child.y}`}
                          fill="none"
                          stroke="#94a3b8"
                          strokeWidth="1.5"
                          strokeDasharray="4 3"
                          opacity="1"
                        />
                      ))}
                    </g>
                  ))}

                  {/* Sub-children Nodes */}
                  {layout.nodes.flatMap(node => node.children).map(child => {
                    const isSelected = selectedKeywords.has(child.keyword)
                    const boxWidth = 145
                    const boxHeight = 36
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
                          rx="18"
                          fill={isSelected ? '#f5f3ff' : '#f8fafc'}
                          stroke={isSelected ? '#7c3aed' : '#e2e8f0'}
                          strokeWidth={isSelected ? '1.5' : '1'}
                          strokeDasharray="4 3"
                          className="transition-all duration-200 shadow-xs group-hover:scale-105"
                        />
                        <text
                          x={rectX + boxWidth / 2}
                          y={child.y + 4}
                          textAnchor="middle"
                          fill={isSelected ? '#7c3aed' : '#64748b'}
                          fontSize="14"
                          fontWeight="600"
                        >
                          {child.keyword.length > 11 ? `${child.keyword.slice(0, 11)}…` : child.keyword}
                        </text>
                      </g>
                    )
                  })}

                  {/* Primary Nodes */}
                  {layout.nodes.map((node, idx) => {
                    const isSelected = selectedKeywords.has(node.keyword)
                    const accentColor = isSelected ? '#7c3aed' : primaryAccentColor(idx, node.direction)
                    const boxWidth = 160
                    const boxHeight = 46
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
                          rx="23"
                          fill={isSelected ? '#f5f3ff' : '#ffffff'}
                          stroke={isSelected ? '#7c3aed' : '#e2e8f0'}
                          strokeWidth={isSelected ? '2' : '1'}
                          className="transition-all duration-200 shadow-sm group-hover:scale-105"
                        />
                        <rect
                          x={rectX + 2}
                          y={node.y - boxHeight / 2 + 7}
                          width="5"
                          height={boxHeight - 14}
                          rx="2.5"
                          fill={accentColor}
                          pointerEvents="none"
                        />
                        <text
                          x={node.x}
                          y={node.y + 4}
                          textAnchor="middle"
                          fill="#1e293b"
                          fontSize="17"
                          fontWeight="700"
                        >
                          {node.keyword.length > 12 ? `${node.keyword.slice(0, 12)}…` : node.keyword}
                        </text>

                      </g>
                    )
                  })}

                  {/* Center Node */}
                  <g className="cursor-default">
                    <rect
                      x="-110"
                      y="-32"
                      width="220"
                      height="64"
                      rx={CENTER_RADIUS}
                      ry={CENTER_RADIUS}
                      fill={CENTER_FILL}
                      className="shadow-lg"
                    />
                    <text
                      x="0"
                      y="7"
                      textAnchor="middle"
                      fill={CENTER_TEXT}
                      fontSize="20"
                      fontWeight="800"
                    >
                      {layout.center.title.length > 13 ? `${layout.center.title.slice(0, 13)}…` : layout.center.title}
                    </text>
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
                  const views = video.views ?? video.viewCount ?? null
                  const likes = video.likes ?? video.likeCount ?? null
                  const comments = video.comments ?? video.commentCount ?? null
                  const duration = video.durationSeconds ?? video.duration_seconds ?? null

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
                            썸네일 없음
                          </div>
                        )}
                        <span className="absolute bottom-1 right-1 px-1 py-0.5 bg-black/80 text-white text-[9px] font-bold rounded">
                          {formatDuration(duration)}
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
                          <span className="flex items-center gap-0.5"><ThumbsUp size={11} /> {formatCount(likes)}</span>
                          <span className="flex items-center gap-0.5"><MessageCircle size={11} /> {formatCount(comments)}</span>
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
            <span className="px-3 py-1 text-xs font-bold bg-slate-900 text-white rounded-lg" style={{ color: '#ffffff' }}>
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
