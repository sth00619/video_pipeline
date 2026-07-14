import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Upload, Scissors, Download, Loader, X, Plus, Trash2,
  Play, Pause, SkipBack, SkipForward, Clock, FileText, Sparkles, Tag, ArrowRight, Video,
  Youtube, Copy, ExternalLink, CheckCircle
} from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'
import { authStore } from '../store/auth'

const SEG_LABELS = ['핵심 분석','시나리오 분석','실행 가이드','결론 요약','데이터 정리']
const COLORS = ['text-accent-cyan','text-accent-gold','text-accent-green','text-purple-400','text-pink-400']
const BG_COLORS = ['bg-accent-cyan','bg-accent-gold','bg-accent-green','bg-purple-400','bg-pink-400']

function fmt(s) {
  if (s == null || isNaN(s)) return '0:00'
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function parseSec(str = '') {
  const p = String(str).split(':')
  return p.length === 2 ? parseFloat(p[0]) * 60 + parseFloat(p[1] || 0) : parseFloat(str) || 0
}

function isSpokenKorean(text) {
  const value = String(text || '').trim()
  return /[가-힣]{2}/.test(value) && !/(2d digital|comic illustration|no readable text|scene:|action:|camera:)/i.test(value)
}

function makeTimelineSegments(allScenes, selectedIndices) {
  const ordered = allScenes.filter(s => isSpokenKorean(s.text)).sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
  const anchors = new Set((selectedIndices || []).map(Number))
  let best = null
  for (let left = 0; left < ordered.length; left++) {
    for (let right = left; right < ordered.length; right++) {
      const start = Number(ordered[left].start || 0)
      const end = Number(ordered[right].start || 0) + Number(ordered[right].duration || 0)
      const duration = Math.max(0, end - start)
      if (duration > 60.05) break
      const hits = ordered.slice(left, right + 1).filter(s => anchors.has(Number(s.index))).length
      if (!hits) continue
      const score = hits * 100 - Math.abs(42 - duration)
      if (!best || score > best.score) best = { left, right, score }
    }
  }
  if (!best) return []
  return ordered.slice(best.left, best.right + 1).map((s, idx) => ({
    index: idx + 1, label: s.title || `Scene ${s.index}`, text: s.text,
    start: Number(s.start || 0), end: Number(s.start || 0) + Number(s.duration || 0)
  }))
}

// JWT 포함 다운로드
async function downloadFile(path, filename) {
  if (!path || path === 'undefined' || path === 'null') {
    alert('파일 경로가 없습니다. 쇼츠 생성이 완료되지 않았을 수 있습니다.')
    return
  }
  try {
    const token = authStore.getToken()
    if (!token) { alert('로그인이 필요합니다.'); return }
    const res = await fetch(`/api/files/download?path=${encodeURIComponent(path)}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (res.status === 403) { alert('권한 오류: 다시 로그인해주세요.'); return }
    if (res.status === 404) { alert('파일 없음: 쇼츠 생성을 다시 시도해주세요.'); return }
    if (!res.ok) { alert('다운로드 실패: ' + res.status); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || 'short.mp4'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('다운로드 오류: ' + e.message)
  }
}

export default function Shorts() {
  const { id } = useParams() // Longform Job ID (있으면 연동 모드)
  const navigate = useNavigate()
  const token = authStore.getToken()

  const fileRef = useRef(null)
  const videoRef = useRef(null)
  const tlRef = useRef(null)

  // 로컬 비디오 업로드 모드 상태
  const [file, setFile] = useState(null)
  const [fileUrl, setFileUrl] = useState(null)
  
  // 롱폼 연동 모드 전용 상태
  const [job, setJob] = useState(null)
  const [scenes, setScenes] = useState([])
  const [transcript, setTranscript] = useState('')
  const [loadingJob, setLoadingJob] = useState(false)
  const [aiScenarios, setAiScenarios] = useState(null)
  const [extractingAi, setExtractingAi] = useState(false)
  const [selectedKeywords, setSelectedKeywords] = useState([])
  const [aiActiveTab, setAiActiveTab] = useState('scenario') // 'scenario' | 'keyword'

  // 공통 상태
  const [shortsCount, setShortsCount] = useState(3)
  const [clipDur, setClipDur] = useState(60)
  const [mode, setMode] = useState(id ? 'GUIDED' : 'MANUAL') // 기본 모드
  const [analyzing, setAnalyzing] = useState(false)
  const [cutting, setCutting] = useState(false)
  const [segments, setSegments] = useState([])
  const [clips, setClips] = useState([])
  
  const [totalDur, setTotalDur] = useState(0)
  const [curTime, setCurTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [activeSeg, setActiveSeg] = useState(null)
  const [downloadingIdx, setDownloadingIdx] = useState(null)
  const [dragging, setDragging] = useState(null)
  const [drag, setDrag] = useState(false)
  const [youtubePackage, setYoutubePackage] = useState(null)
  const [isGuidedConfirmOpen, setIsGuidedConfirmOpen] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [imageSalt, setImageSalt] = useState(0)

  // 1. 롱폼 연동 모드 데이터 로드
  useEffect(() => {
    if (!id) return
    
    const loadLongformData = async () => {
      setLoadingJob(true)
      try {
        // Job 상세 정보 가져오기
        const jobRes = await apiClient.get(`/jobs/${id}`)
        setJob(jobRes.data)
        
        // 롱폼 비디오가 존재하는 경우 프리뷰 URL 매핑
        if (jobRes.data.outputPath) {
          setFileUrl(`/api/files/download?path=${encodeURIComponent(jobRes.data.outputPath)}&token=${token}`)
        }

        // 씬 목록 가져오기
        const assetRes = await apiClient.get(`/jobs/${id}/assets?type=SCENE_IMAGE`)
        const sortedScenes = (assetRes.data || []).map(asset => {
          try {
            return JSON.parse(asset.metaJson)
          } catch(e) {
            return null
          }
        }).filter(scene => scene && isSpokenKorean(scene.text)).sort((a, b) => a.index - b.index)
        
        let activeScenes = sortedScenes
        if (activeScenes.length === 0) {
          try {
            const transcriptRes = await apiClient.get(`/jobs/${id}/assets?type=TRANSCRIPT`)
            const latest = transcriptRes.data?.[transcriptRes.data.length - 1]
            if (latest?.metaJson) {
              const transcriptMeta = JSON.parse(latest.metaJson)
              setTranscript(transcriptMeta.transcript || '')
              activeScenes = (transcriptMeta.segments || []).map((s, i) => ({
                index: s.index || i + 1,
                title: `대본 ${s.index || i + 1}`,
                text: s.text || '',
                start: Number(s.start || 0),
                duration: Number(s.duration ?? Math.max(0, Number(s.end || 0) - Number(s.start || 0)))
              }))
            }
          } catch (err) {}
        }
        setScenes(activeScenes)
        
        // 총 씬 지속 시간의 합을 동적 분량으로 설정
        const sumDur = activeScenes.reduce((acc, s) => acc + (s.duration || 0), 0)
        setTotalDur(sumDur || 300)

        // 자동 생성된 쇼츠 시나리오가 있는지 확인 및 자동 로드
        try {
          const scenarioRes = await apiClient.get(`/jobs/${id}/assets?type=SHORTS_SCENARIO`)
          if (scenarioRes.data && scenarioRes.data.length > 0) {
            const latestScenario = scenarioRes.data[scenarioRes.data.length - 1]
            if (latestScenario.metaJson) {
              setAiScenarios(JSON.parse(latestScenario.metaJson))
            }
          }
        } catch (err) {}

        // 유튜브 메타데이터 가져오기
        try {
          const youtubeMetaRes = await apiClient.get(`/jobs/${id}/assets?type=YOUTUBE_METADATA`)
          if (youtubeMetaRes.data && youtubeMetaRes.data.length > 0) {
            const latest = youtubeMetaRes.data[youtubeMetaRes.data.length - 1]
            if (latest.metaJson) {
              setYoutubePackage(JSON.parse(latest.metaJson))
            }
          }
        } catch (err) {}
      } catch (e) {
        alert('롱폼 프로젝트 로드 실패: ' + e.message)
      } finally {
        setLoadingJob(false)
      }
    }

    loadLongformData()
  }, [id, token])

  // 업로드 파일 핸들러 (로컬 모드)
  const handleFile = (f) => {
    if (!f || !f.type.startsWith('video/')) return
    if (fileUrl) URL.revokeObjectURL(fileUrl)
    setFile(f)
    setFileUrl(URL.createObjectURL(f))
    setSegments([])
    setClips([])
    setAiScenarios(null)
    setTranscript('')
    setActiveSeg(null)
  }

  const handleMeta = () => { if (videoRef.current) setTotalDur(videoRef.current.duration) }
  const handleTimeUpdate = () => { if (videoRef.current) setCurTime(videoRef.current.currentTime) }
  const seek = (t) => { if (videoRef.current) videoRef.current.currentTime = Math.max(0, Math.min(t, totalDur)) }
  const togglePlay = () => {
    if (!videoRef.current) return
    playing ? videoRef.current.pause() : videoRef.current.play()
    setPlaying(!playing)
  }

  // ── AI 기승전결 시나리오 및 추천 키워드 추출 (Claude 4.6 호출) ──
  const handleExtractAiScenarios = async () => {
    const targetId = id || (job && job.id);
    if (!targetId) {
      alert('로컬 비디오의 경우 먼저 비디오 바로 아래에 있는 [업로드 영상 자동 분석 시작] 버튼을 눌러 스크립트를 추출해주세요.');
      return;
    }
    setExtractingAi(true)
    setSelectedKeywords([])
    try {
      // 롱폼 씬 데이터가 없다면, 직접 업로드한 씬(segments)을 전송
      if (scenes.length > 0) {
        const res = await apiClient.post(`/jobs/${targetId}/shorts/extract-scenarios`, {})
        setAiScenarios(res.data)
        if (Array.isArray(res.data.timeline_scenes) && res.data.timeline_scenes.length > 0) {
          setScenes(res.data.timeline_scenes.map((scene, i) => ({
            ...scene,
            index: Number(scene.index ?? i + 1),
            title: scene.title || `Scene ${scene.index ?? i + 1}`,
            start: Number(scene.start || 0),
            duration: Number(scene.duration || 0),
          })))
          const repairedDuration = res.data.timeline_scenes.reduce((max, scene) => Math.max(max, Number(scene.end || 0), Number(scene.start || 0) + Number(scene.duration || 0)), 0)
          if (repairedDuration > 0) setTotalDur(repairedDuration)
        }
      } else {
        alert('먼저 업로드 영상을 분석해 시간 정보가 있는 대본을 추출해 주세요.')
      }
    } catch (e) {
      alert('AI 추천 추출 실패: ' + (e.response?.data?.message || e.message))
    } finally {
      setExtractingAi(false)
    }
  }

  // ── 특정 키워드 클릭 시 다중 선택 및 매칭 씬 결합 ──
  const toggleKeyword = (kw) => {
    let newSelected;
    if (selectedKeywords.find(k => k.word === kw.word)) {
      newSelected = selectedKeywords.filter(k => k.word !== kw.word);
    } else {
      newSelected = [...selectedKeywords, kw];
    }
    setSelectedKeywords(newSelected);

    if (newSelected.length === 0) {
      setSegments([]);
      return;
    }

    const indices = newSelected.flatMap(k => k.matching_scene_indices || [])
    const newSegs = makeTimelineSegments(scenes, indices)
    if (!newSegs.length) {
      setSegments([]);
      return;
    }
    setSegments(newSegs)
    setActiveSeg(0)
    seek(newSegs[0].start)
  }

  // ── AI 시나리오 클릭 시 해당 씬 리스트 적용 ──
  const handleApplyScenario = (scenario) => {
    const indices = scenario.selected_scene_indices || scenario.scene_indices || [];
    const newSegs = makeTimelineSegments(scenes, indices)
    if (!newSegs.length) {
      alert('해당 시나리오의 씬 정보를 찾을 수 없습니다. (매칭된 인덱스 없음)')
      return
    }

    setSegments(newSegs)
    setActiveSeg(0)
    seek(newSegs[0].start)
    setSelectedKeywords([])
    
    // 시나리오 적용과 동시에 자동으로 단일 쇼츠 생성(Merge) 요청
    handleCutShorts(true, newSegs)
  }

  // ── 드래그 앤 드롭 대본 추가 ──
  const handleDragStart = (e, scene) => {
    e.dataTransfer.setData("application/json", JSON.stringify(scene))
  }

  const handleDropOnTimeline = (e) => {
    e.preventDefault()
    try {
      const dataStr = e.dataTransfer.getData("application/json")
      if (!dataStr) return
      const scene = JSON.parse(dataStr)
      
      // 이미 타임라인에 있는지 확인
      if (segments.some(s => s.text === scene.text)) {
        return
      }

      const newSeg = {
        index: segments.length + 1,
        label: scene.title || `Scene ${scene.index}`,
        text: scene.text || '',
        start: scene.start,
        end: scene.start + scene.duration
      }
      setSegments([...segments, newSeg])
      setActiveSeg(segments.length)
      seek(scene.start)
    } catch (err) {
      console.error(err)
    }
  }

  // ── 쇼츠 비디오 컷팅/병합 요청 ──
  const handleCutShorts = async (isMerge = false, overrideSegments = null) => {
    const targetSegments = overrideSegments || segments;
    if (targetSegments.length === 0) {
      alert('구간을 선택하거나 드래그하여 타임라인을 채워주세요.')
      return
    }

    // 시간 정보 유효성 검증
    const invalidSegments = targetSegments.filter(s => s.start === null || s.start === undefined || isNaN(s.start));
    if (false && invalidSegments.length > 0) {
      alert('⚠️ 씬의 시간 정보(타임스탬프)가 존재하지 않는 예전 버전의 프로젝트입니다.\n\n해결 방법: 상단의 [에디터] 탭으로 이동하신 후 우측 상단의 [수정 반영 및 재조립] 버튼을 한 번 눌러주세요. 영상이 재조립되면서 시간 정보가 정상적으로 매핑됩니다.');
      return;
    }

    setCutting(true)
    try {
      const targetId = id || job?.id
      if (!targetId) {
        alert('쇼츠 원본 job을 찾을 수 없습니다. 먼저 영상을 분석해 주세요.')
        return
      }
      const endpoint = isMerge ? `/jobs/${targetId}/shorts/confirm-merge` : `/jobs/${targetId}/shorts/confirm`
      const res = await apiClient.post(endpoint, {
        segments: targetSegments.map(s => ({
          index: s.index,
          text: s.label || s.text || `쇼츠 ${s.index}`,
          start: s.start,
          end: s.end
        }))
      })
      setClips(Array.isArray(res.data) ? res.data : [res.data])
      alert(isMerge ? '선택한 구간들이 하나의 쇼츠로 병합 완료되었습니다.' : '개별 쇼츠 영상이 생성되었습니다.')
    } catch (e) {
      alert('생성 실패: ' + (e.response?.data?.message || e.message))
    } finally {
      setCutting(false)
    }
  }

  const handlePublish = async () => {
    setPublishing(true)
    try {
      await apiClient.post(`/jobs/${id}/publish`)
      const jobRes = await apiClient.get(`/jobs/${id}`)
      setJob(jobRes.data)
      alert('유튜브 업로드가 완료되었습니다!')
    } catch (e) {
      alert('유튜브 업로드 실패: ' + e.message)
    } finally {
      setPublishing(false)
    }
  }

  // ── 로컬 비디오 업로드 모드: 분석 및 컷팅 ──
  const handleLocalAnalyze = async () => {
    if (!file) return
    setAnalyzing(true)
    setClips([])
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiClient.post('/jobs', {
        title: `쇼츠: ${file.name}`,
        autonomy: 'GUIDED',
        makeShorts: true,
        shortsCount,
        longformTargetMinutes: 20
      })
      const jid = res.data.id
      
      const resAnalyze = await apiClient.post(
        `/jobs/${jid}/shorts/analyze?shortsCount=${shortsCount}`,
        fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 1800000 }
      )
      const d = resAnalyze.data
      setTranscript(d.transcript || '')
      const adj = (d.suggested_segments || []).map((s, i) => ({
        ...s, index: i + 1,
        label: SEG_LABELS[i % SEG_LABELS.length],
        color: COLORS[i % COLORS.length],
        end: s.end || parseFloat(Math.min(s.start + clipDur, totalDur || 300).toFixed(2))
      }))
      
      const transcriptScenes = (d.transcript_segments || []).map((s, i) => ({
        index: s.index || i + 1,
        title: `대본 ${s.index || i + 1}`,
        text: s.text || '',
        start: Number(s.start || 0),
        duration: Number(s.duration ?? Math.max(0, Number(s.end || 0) - Number(s.start || 0)))
      })).filter(s => s.duration > 0 || s.text)
      const generatedScenes = transcriptScenes.length ? transcriptScenes : adj.map(s => ({
        index: s.index,
        title: s.label,
        text: s.text,
        start: s.start,
        duration: s.end - s.start
      }))
      
      setSegments(adj)
      setScenes(generatedScenes)
      setJob({ id: jid, outputPath: null })
      setActiveSeg(0)
    } catch (e) {
      alert('분석 실패: ' + (e.response?.data?.message || e.message))
    } finally {
      setAnalyzing(false)
    }
  }

  const handleLocalCut = async () => {
    if (segments.length === 0) return
    setCutting(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('segments', JSON.stringify(segments))
      // Mock Job ID 로 임시 생성
      const resJob = await apiClient.post('/jobs', {
        title: `수동 쇼츠: ${file.name}`,
        autonomy: 'MANUAL',
        makeShorts: true
      })
      const res = await apiClient.post(`/jobs/${resJob.data.id}/shorts/cut-direct`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 1800000
      })
      setClips(res.data)
    } catch (e) {
      alert('컷팅 실패: ' + e.message)
    } finally {
      setCutting(false)
    }
  }

  // ── 구간 수정/삭제 ──
  const removeSeg = (i) => {
    setSegments(segments.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, index: idx + 1 })))
    if (activeSeg === i) setActiveSeg(null)
  }
  const updSeg = (i, f, v) => setSegments(segs => segs.map((s, idx) => idx === i ? { ...s, [f]: v } : s))
  const addSeg = () => {
    const last = segments[segments.length - 1]
    const start = last ? Math.min(last.end + 2, Math.max(0, totalDur - clipDur)) : 0
    const end = Math.min(start + clipDur, totalDur)
    setSegments([...segments, {
      index: segments.length + 1, text: '',
      label: `구간 ${segments.length + 1}`,
      start: parseFloat(start.toFixed(2)), end: parseFloat(end.toFixed(2))
    }])
    setActiveSeg(segments.length)
  }

  // ── 타임라인 드래그 ──
  const getT = useCallback((cx) => {
    if (!tlRef.current || !totalDur) return 0
    const r = tlRef.current.getBoundingClientRect()
    return Math.max(0, Math.min(1, (cx - r.left) / r.width)) * totalDur
  }, [totalDur])

  const onTlDown = (e, si, handle) => {
    e.preventDefault(); e.stopPropagation()
    const seg = segments[si]
    setDragging({ si, handle, startX: e.clientX, origStart: seg.start, origEnd: seg.end })
    setActiveSeg(si)
  }

  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      const dT = ((e.clientX - dragging.startX) / (tlRef.current?.getBoundingClientRect().width || 1)) * totalDur
      setSegments(segs => segs.map((s, i) => {
        if (i !== dragging.si) return s
        if (dragging.handle === 'start')
          return { ...s, start: parseFloat(Math.max(0, Math.min(dragging.origStart + dT, s.end - 5)).toFixed(2)) }
        if (dragging.handle === 'end')
          return { ...s, end: parseFloat(Math.min(totalDur, Math.max(dragging.origEnd + dT, s.start + 5)).toFixed(2)) }
        const dur = dragging.origEnd - dragging.origStart
        const ns = Math.max(0, Math.min(dragging.origStart + dT, totalDur - dur))
        return { ...s, start: parseFloat(ns.toFixed(2)), end: parseFloat((ns + dur).toFixed(2)) }
      }))
    }
    const onUp = () => setDragging(null)
    window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [dragging, totalDur])

  const pct = (t) => totalDur ? `${(t / totalDur) * 100}%` : '0%'

  const targetJobId = id || (job && job.id);

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Video className="text-accent-cyan" size={24} />
            {targetJobId ? (id ? `롱폼 연동 쇼츠 에디터 (Job #${id})` : `업로드 분석 쇼츠 에디터 (Job #${targetJobId})`) : '쇼츠 수동 제작기'}
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {targetJobId ? '추출된 대사를 확인하며 마음에 드는 부분을 합쳐 쇼츠를 생성하세요.' : '비디오 파일을 직접 업로드해 잘라냅니다.'}
          </p>
        </div>
        {id && (
          <button onClick={() => navigate(`/jobs/${id}`)} className="text-xs border border-navy-600 bg-navy-800 text-gray-400 hover:text-white px-3 py-1.5 rounded-lg transition">
            ← 롱폼 상세로 돌아가기
          </button>
        )}
      </div>

      {loadingJob ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader size={36} className="animate-spin text-accent-cyan" />
          <span className="text-xs text-gray-500">롱폼 프로젝트 및 씬 구조 로드 중...</span>
        </div>
      ) : (
        <div className="grid grid-cols-5 gap-6">
          
          {/* ==================== 좌측 패널 (대본 씬 리스트) ==================== */}
          <div className="col-span-2 bg-navy-800 rounded-xl border border-navy-700 p-4 flex flex-col max-h-[680px]">
              <div className="flex items-center gap-2 mb-3 pb-3 border-b border-navy-700">
                <FileText size={16} className="text-accent-cyan" />
                <h3 className="font-semibold text-sm text-white">{id ? '롱폼 전체 대본' : '추출된 영상 대본'} (드래그 가능)</h3>
              </div>
              <p className="text-[10px] text-gray-500 mb-2 leading-relaxed">
                * 씬 대사 블록을 마우스로 잡고 우측 타임라인으로 끌어다 놓으면 해당 구간이 추가됩니다.<br />
                * 카드를 클릭하면 해당 구간으로 비디오 재생이 이동합니다.
              </p>
              {!id && transcript && (
                <details className="mb-3 rounded border border-navy-700 bg-navy-950/60 p-2">
                  <summary className="cursor-pointer text-xs font-medium text-accent-cyan">추출된 전체 대본 보기</summary>
                  <p className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-gray-300">{transcript}</p>
                </details>
              )}
              
              <div className="space-y-2.5 overflow-y-auto flex-1 pr-1.5">
                {scenes.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 opacity-50 text-center">
                    <span className="text-xs text-gray-400">비디오를 업로드하고 분석을 진행하면<br/>여기에 스크립트가 추출됩니다.</span>
                  </div>
                ) : scenes.map((scene) => {
                  const isHighlighted = selectedKeywords.some(k => k.matching_scene_indices?.includes(scene.index));
                  return (
                    <div
                      key={scene.index}
                      draggable
                      onDragStart={(e) => handleDragStart(e, scene)}
                      onClick={() => seek(scene.start)}
                      className={`p-3 rounded-lg border text-left cursor-pointer transition select-none ${
                        isHighlighted 
                          ? 'border-accent-cyan bg-accent-cyan/10 shadow-lg shadow-accent-cyan/5' 
                          : 'border-navy-700 bg-navy-900/50 hover:border-navy-600'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-bold text-accent-gold">Scene #{scene.index}</span>
                        <span className="text-[10px] text-gray-500 tabular-nums">
                          {fmt(scene.start)} ~ {fmt(scene.start + scene.duration)} ({scene.duration?.toFixed(1)}초)
                        </span>
                      </div>
                      <p className="text-xs text-gray-200 leading-relaxed font-medium">
                        {scene.text || '(대사 없음)'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

          {/* ==================== 우측 패널 (플레이어 & 타임라인 & AI 기능) ==================== */}
          <div className="col-span-3 space-y-4">
            
            {/* 비디오 플레이어 */}
            <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
              {fileUrl ? (
                <>
                  <video ref={videoRef} src={fileUrl} className="w-full aspect-video bg-black"
                    onLoadedMetadata={handleMeta} onTimeUpdate={handleTimeUpdate}
                    onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />
                  <div className="flex items-center gap-3 px-4 py-3 border-t border-navy-700">
                    <button onClick={() => seek(curTime - 10)} className="text-gray-400 hover:text-white"><SkipBack size={16} /></button>
                    <button onClick={togglePlay} className="w-8 h-8 flex items-center justify-center bg-accent-cyan text-navy-950 rounded-full hover:opacity-90">
                      {playing ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                    <button onClick={() => seek(curTime + 10)} className="text-gray-400 hover:text-white"><SkipForward size={16} /></button>
                    <span className="text-xs text-gray-400 tabular-nums">{fmt(curTime)} / {fmt(totalDur)}</span>
                    
                    {activeSeg !== null && segments[activeSeg] && (
                      <div className="ml-auto flex gap-2">
                        <button onClick={() => updSeg(activeSeg, 'start', parseFloat(curTime.toFixed(2)))}
                          className="text-[10px] bg-navy-700 text-accent-cyan px-2 py-1 rounded hover:bg-navy-600">
                          ← 시작 설정
                        </button>
                        <button onClick={() => updSeg(activeSeg, 'end', parseFloat(curTime.toFixed(2)))}
                          className="text-[10px] bg-navy-700 text-accent-cyan px-2 py-1 rounded hover:bg-navy-600">
                          끝 설정 →
                        </button>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div onDragOver={e => { e.preventDefault(); setDrag(true) }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={e => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]) }}
                  onClick={() => fileRef.current?.click()}
                  className="aspect-video flex flex-col items-center justify-center cursor-pointer hover:bg-navy-700/30 transition">
                  <input ref={fileRef} type="file" accept="video/*" className="hidden"
                    onChange={e => handleFile(e.target.files[0])} />
                  <Upload className="text-gray-500 mb-3" size={36} />
                  <p className="text-gray-400 text-sm">로컬 영상 업로드하기</p>
                </div>
              )}
            </div>

            {/* 업로드 모드 분석 컨트롤 (비디오 하단에 바로 배치하여 가시성 확보) */}
            {!id && fileUrl && !job && (
              <div className="bg-navy-800 rounded-xl border border-navy-700 p-4 shadow-lg shadow-accent-cyan/10 ring-1 ring-accent-cyan/20">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-bold text-accent-cyan flex items-center gap-1.5">
                      <Sparkles size={16} /> 스크립트 자동 추출 및 분석
                    </h3>
                    <p className="text-xs text-gray-400 mt-1">
                      비디오를 분석하여 대사(스크립트)를 추출하고 좌측 패널에 생성합니다.
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-400">쇼츠 갯수:</label>
                      <input type="number" value={shortsCount} onChange={e => setShortsCount(Number(e.target.value))}
                        className="w-16 bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-white text-center" />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-400">쇼츠 분량(초):</label>
                      <input type="number" value={clipDur} onChange={e => setClipDur(Number(e.target.value))}
                        className="w-16 bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-white text-center" />
                    </div>
                  </div>
                </div>
                <button onClick={handleLocalAnalyze} disabled={analyzing || !file}
                  className="w-full flex items-center justify-center gap-2 bg-accent-cyan text-navy-950 font-bold py-2.5 rounded-lg hover:opacity-90 transition shadow-md shadow-accent-cyan/20">
                  {analyzing ? <Loader size={16} className="animate-spin" /> : <Scissors size={16} />}
                  {analyzing ? '비디오를 클라우드에 업로드하고 분석하는 중입니다 (1~2분 소요)...' : '업로드 영상 자동 분석 시작'}
                </button>
              </div>
            )}

            {/* AI 기승전결 추천 & 키워드 보드 */}
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-white flex items-center gap-1.5">
                    <Sparkles size={14} className="text-accent-gold" />
                    AI 스토리 분석 및 추천 (Claude 4.6)
                  </h4>
                  <button
                    onClick={handleExtractAiScenarios}
                    disabled={extractingAi}
                    className="flex items-center gap-1 bg-accent-gold text-navy-950 text-xs font-semibold px-3 py-1.5 rounded-lg hover:opacity-90 disabled:opacity-50 transition"
                  >
                    {extractingAi ? <Loader size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    {aiScenarios ? '시나리오 재추천' : '스토리 분석하기'}
                  </button>
                </div>

                {extractingAi && (
                  <div className="flex items-center justify-center py-6 gap-2 text-xs text-gray-500">
                    <Loader size={14} className="animate-spin text-accent-gold" />
                    <span>Claude 4.6 모델이 대본 구조를 정밀 분석하여 10~20초 분량 씬 단위로 최적의 기승전결 시나리오를 구성하고 있습니다...</span>
                  </div>
                )}

                {aiScenarios && !extractingAi && (
                  <div className="space-y-4">
                    <div className="flex gap-6 border-b border-navy-700">
                      <button onClick={() => setAiActiveTab('scenario')} className={`text-sm font-bold pb-2 border-b-2 transition ${aiActiveTab === 'scenario' ? 'text-accent-gold border-accent-gold' : 'text-gray-400 border-transparent hover:text-white'}`}>
                        🎬 기승전결 시나리오 추천
                      </button>
                      <button onClick={() => setAiActiveTab('keyword')} className={`text-sm font-bold pb-2 border-b-2 transition ${aiActiveTab === 'keyword' ? 'text-accent-gold border-accent-gold' : 'text-gray-400 border-transparent hover:text-white'}`}>
                        🏷️ 연관 키워드 추천
                      </button>
                    </div>

                    {aiActiveTab === 'keyword' && (
                      <div className="animate-fade-in">
                        <span className="text-xs text-gray-400 block mb-2 flex items-center gap-1">
                          <Tag size={11} />추천 키워드 (여러 개 선택 시 <strong>하나라도 포함(OR)</strong>된 구간이 합쳐집니다):
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {aiScenarios.keywords?.map((kw, i) => (
                            <button
                              key={i}
                              onClick={() => toggleKeyword(kw)}
                              className={`text-xs px-3 py-1.5 rounded-full border transition ${
                                selectedKeywords.some(k => k.word === kw.word)
                                  ? 'bg-accent-cyan text-navy-950 border-accent-cyan font-bold shadow-md'
                                  : 'bg-navy-900 border-navy-700 text-gray-300 hover:border-accent-cyan hover:text-accent-cyan'
                              }`}
                              title={kw.description}
                            >
                              #{kw.word}
                            </button>
                          ))}
                        </div>
                        {selectedKeywords.length > 0 && (
                          <div className="mt-4 flex flex-col items-start justify-between bg-accent-cyan/10 border border-accent-cyan/20 p-3 rounded-lg">
                            <span className="text-xs text-accent-cyan font-medium mb-3">
                              ✓ 다중 선택된 <strong>{selectedKeywords.map(k => '#' + k.word).join(', ')}</strong>에 매칭되는 <strong>{segments.length}</strong>개 구간이 타임라인에 구성되었습니다.
                            </span>
                            <button
                              onClick={() => handleCutShorts(true)}
                              disabled={cutting}
                              className="bg-accent-cyan text-navy-950 text-xs font-bold px-4 py-2 rounded shadow hover:opacity-90 transition w-full text-center"
                            >
                              이 구간 모두 합쳐서 단일 쇼츠 즉시 생성
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {aiActiveTab === 'scenario' && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 animate-fade-in">
                        {Object.entries(aiScenarios.scenarios || {}).map(([key, sc]) => {
                          if (key === 'keywords') return null;
                          return (
                            <div key={key} className="bg-navy-900 border border-navy-600 rounded-lg p-4 flex flex-col justify-between hover:border-accent-gold transition shadow-sm hover:shadow-md">
                              <div>
                                <h5 className="font-bold text-white text-sm mb-2">{sc.title}</h5>
                                <p className="text-[11px] text-gray-400 leading-relaxed mb-4">{sc.description}</p>
                              </div>
                              <button
                                onClick={() => handleApplyScenario(sc)}
                                className="w-full bg-navy-800 border border-navy-700 text-gray-300 text-xs py-2.5 rounded font-medium hover:text-white hover:bg-navy-700 hover:border-accent-gold transition flex items-center justify-center gap-1.5"
                              >
                                이 시나리오 즉시 제작하기 <ArrowRight size={12} />
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>

            {/* 타임라인 드롭존 및 편집 */}
            {totalDur > 0 && (
              <div className="bg-navy-800 rounded-xl border border-navy-700 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-gray-400">쇼츠 타임라인 구간 편집</h3>
                  <div className="flex gap-2">
                    <button onClick={addSeg} className="flex items-center gap-1 text-[10px] bg-navy-700 text-gray-300 px-2 py-1 rounded hover:bg-navy-600">
                      <Plus size={11} />수동 추가
                    </button>
                    {segments.length > 0 && (
                      <button onClick={() => setSegments([])} className="text-[10px] bg-navy-700 text-accent-red px-2 py-1 rounded hover:bg-navy-600">
                        초기화
                      </button>
                    )}
                  </div>
                </div>

                {/* 타임라인 블록 영역 */}
                <div
                  ref={tlRef}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDropOnTimeline}
                  className="relative h-14 bg-navy-900 border-2 border-dashed border-navy-700 rounded-lg select-none cursor-pointer flex items-center justify-center mb-4"
                  onClick={e => { if (!dragging) seek(getT(e.clientX)) }}
                >
                  {segments.length === 0 && (
                    <span className="text-xs text-gray-600 pointer-events-none">
                      {id ? '좌측 대본 카드를 여기에 끌어다 놓아 씬을 배치하세요.' : '재생 바를 이동시켜 구간을 추가하세요.'}
                    </span>
                  )}
                  {Array.from({ length: Math.floor(totalDur / 30) + 1 }).map((_, i) => {
                    const t = i * 30
                    return (
                      <div key={i} className="absolute top-0 h-full pointer-events-none" style={{ left: pct(t) }}>
                        <div className="w-px h-2 bg-navy-800" />
                        <span style={{ fontSize: 8, marginLeft: 2 }} className="text-gray-700">{fmt(t)}</span>
                      </div>
                    )
                  })}
                  {segments.map((seg, i) => {
                    const l = (seg.start / totalDur) * 100
                    const w = Math.max(((seg.end - seg.start) / totalDur) * 100, 0.5)
                    return (
                      <div key={i}
                        className={`absolute top-2.5 h-9 rounded border flex items-center justify-center transition ${BG_COLORS[i % BG_COLORS.length]} ${activeSeg === i ? 'opacity-100 ring-2 ring-white/20' : 'opacity-70'}`}
                        style={{ left: `${l}%`, width: `${w}%` }}
                        onClick={e => { e.stopPropagation(); setActiveSeg(i); seek(seg.start) }}>
                        <div className="absolute left-0 top-0 w-1.5 h-full cursor-w-resize hover:bg-white/20 rounded-l"
                          onMouseDown={e => onTlDown(e, i, 'start')} />
                        <span className="text-[10px] font-bold text-navy-950 pointer-events-none truncate max-w-[80%]">#{seg.index}</span>
                        <div className="absolute right-0 top-0 w-1.5 h-full cursor-e-resize hover:bg-white/20 rounded-r"
                          onMouseDown={e => onTlDown(e, i, 'end')} />
                      </div>
                    )
                  })}
                  <div className="absolute top-0 h-full w-px bg-accent-red pointer-events-none z-10" style={{ left: pct(curTime) }}>
                    <div className="w-2 h-2 bg-accent-red rounded-full -ml-1 -mt-0.5" />
                  </div>
                </div>

                {/* 구간 리스트 카드들 */}
                {segments.length > 0 && (
                  <div className="space-y-2 overflow-y-auto max-h-52 mb-4">
                    {segments.map((seg, i) => (
                      <div
                        key={i}
                        onClick={() => { setActiveSeg(i); seek(seg.start) }}
                        className={`p-2.5 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                          activeSeg === i ? 'border-accent-cyan bg-accent-cyan/5' : 'border-navy-700 bg-navy-900/30'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span className={`text-xs font-bold ${COLORS[i % COLORS.length]}`}>#{i + 1}</span>
                          <div>
                            <input
                              value={seg.label || ''}
                              onChange={e => { e.stopPropagation(); updSeg(i, 'label', e.target.value) }}
                              onClick={e => e.stopPropagation()}
                              className="bg-transparent text-xs font-semibold text-white focus:outline-none"
                              placeholder={`구간 ${i+1}`}
                            />
                            <div className="text-[10px] text-gray-500 flex items-center gap-1.5 mt-0.5">
                              <Clock size={9} />
                              <span>{fmt(seg.start)} ~ {fmt(seg.end)}</span>
                              <span className="text-gray-600">({(seg.end - seg.start).toFixed(0)}초)</span>
                            </div>
                          </div>
                        </div>
                        <button onClick={e => { e.stopPropagation(); removeSeg(i) }} className="text-gray-600 hover:text-accent-red">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* 최종 컷팅 및 병합 액션 버튼 */}
                {segments.length > 0 && (
                  <div className="flex gap-3 pt-2">
                    {id ? (
                      <>
                        <button
                          onClick={() => handleCutShorts(true)}
                          disabled={cutting}
                          className="flex-1 flex items-center justify-center gap-2 bg-accent-green text-navy-950 font-bold rounded-lg py-2.5 text-xs hover:opacity-90 disabled:opacity-50 transition"
                        >
                          {cutting ? <Loader size={14} className="animate-spin" /> : <Scissors size={14} />}
                          선택된 구간 전부 합쳐서 단일 쇼츠 비디오 생성
                        </button>
                        <button
                          onClick={() => handleCutShorts(false)}
                          disabled={cutting}
                          className="flex-1 flex items-center justify-center gap-2 bg-navy-700 text-white border border-navy-600 font-bold rounded-lg py-2.5 text-xs hover:bg-navy-600 disabled:opacity-50 transition"
                        >
                          각 구간별 개별 쇼츠 클립으로 생성
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={handleLocalCut}
                        disabled={cutting}
                        className="w-full flex items-center justify-center gap-2 bg-accent-green text-navy-950 font-bold rounded-lg py-2.5 text-xs hover:opacity-90 disabled:opacity-50 transition"
                      >
                        {cutting ? <Loader size={14} className="animate-spin" /> : <Scissors size={14} />}
                        로컬 컷팅 시작
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 쇼츠 산출물 표시 및 다운로드 */}
            {clips.length > 0 && (
              <div className="bg-navy-800 rounded-xl border border-accent-green p-5">
                <h3 className="font-semibold text-sm text-accent-green mb-3 flex items-center gap-2">
                  <CheckCircle size={16} /> 쇼츠 비디오 렌더링 완료 (9:16 포맷)
                </h3>
                <div className="space-y-2">
                  {clips.map((clip, i) => (
                    <div key={i} className="flex items-center justify-between bg-navy-700/50 rounded-lg px-4 py-3 border border-navy-600">
                      <div>
                        <div className="text-sm font-semibold text-white truncate max-w-xs">
                          #{clip.index} {clip.text || '합성 쇼츠'}
                        </div>
                        <div className="text-xs text-gray-500 flex items-center gap-1.5 mt-0.5">
                          <Clock size={9} />
                          <span>{clip.duration?.toFixed(1)}초 분량</span>
                          {clip.file_size_mb && <span className="ml-2 text-gray-600">{clip.file_size_mb}MB</span>}
                        </div>
                      </div>
                      <button
                        onClick={async () => {
                          setDownloadingIdx(i)
                          await downloadFile(clip.output_path, `short_${clip.index}.mp4`)
                          setDownloadingIdx(null)
                        }}
                        disabled={downloadingIdx === i}
                        className="flex items-center gap-1.5 bg-accent-green text-navy-950 text-xs font-semibold py-1.5 px-3 rounded-lg hover:opacity-90 transition disabled:opacity-50"
                      >
                        {downloadingIdx === i ? <Loader size={12} className="animate-spin" /> : <Download size={12} />}
                        다운로드
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* YouTube 메타데이터 및 업로드 게이트 패키지 (쇼츠용) */}
            {clips.length > 0 && job && (
              <div className="bg-navy-800 rounded-xl border border-accent-cyan p-5 space-y-4 mt-6">
                <div className="flex items-center justify-between border-b border-navy-700 pb-3">
                  <h3 className="text-sm font-bold text-accent-cyan flex items-center gap-1.5">
                    <Youtube size={16}/> YouTube Shorts 업로드 및 수동 발행 지원 킷
                  </h3>
                  {job.status === 'PUBLISHED' ? (
                    <span className="text-[11px] bg-accent-green/10 text-accent-green font-bold px-2 py-0.5 rounded border border-accent-green/20">
                      업로드 완료
                    </span>
                  ) : (
                    <span className="text-[11px] bg-accent-gold/10 text-accent-gold font-bold px-2 py-0.5 rounded border border-accent-gold/20">
                      업로드 대기 중 ({job.autonomy} 모드)
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* 썸네일 다운로드 */}
                  <div className="bg-navy-900/60 p-3 rounded-lg border border-navy-700 flex flex-col justify-between">
                    <div>
                      <h4 className="text-xs font-semibold text-gray-300 mb-2">AI 자동 생성 썸네일 (9:16)</h4>
                      <div className="aspect-[9/16] w-24 mx-auto bg-navy-950 rounded border border-navy-700 overflow-hidden relative">
                        <img
                          src={`/api/jobs/${id}/thumbnail/shorts?t=${imageSalt}`}
                          alt="YouTube Shorts Thumbnail"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.target.onerror = null;
                            e.target.src = "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=400&q=80";
                          }}
                        />
                      </div>
                    </div>
                    <a
                      href={`/api/jobs/${id}/thumbnail/shorts`}
                      target="_blank"
                      rel="noreferrer"
                      download
                      className="mt-3 w-full bg-navy-700 border border-navy-600 text-center text-xs text-accent-cyan py-1.5 rounded hover:bg-navy-600 transition flex items-center justify-center gap-1"
                    >
                      <Download size={12}/> 썸네일 다운로드
                    </a>
                  </div>

                  {/* 유튜브 메타데이터 복사 패널 */}
                  <div className="md:col-span-2 space-y-3">
                    {youtubePackage?.shorts ? (
                      <>
                        <div>
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-semibold text-gray-400">추천 제목 (3안)</span>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(youtubePackage.shorts.titles?.join('\n') || '');
                                alert('추천 제목 3안이 복사되었습니다.');
                              }}
                              className="text-[10px] text-accent-cyan hover:underline flex items-center gap-0.5"
                            >
                              <Copy size={10}/> 전체 복사
                            </button>
                          </div>
                          <div className="bg-navy-950 p-2 rounded border border-navy-700 space-y-1.5 mt-1">
                            {youtubePackage.shorts.titles?.map((t, idx) => (
                              <div key={idx} className="flex items-start gap-1.5 text-xs text-gray-300">
                                <span className="text-accent-cyan font-bold">안{idx+1}.</span>
                                <span className="flex-1 select-all">{t}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div>
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-semibold text-gray-400">더보기 상세 설명글 (Description)</span>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(youtubePackage.shorts.description || '');
                                alert('더보기 글이 복사되었습니다.');
                              }}
                              className="text-[10px] text-accent-cyan hover:underline flex items-center gap-0.5"
                            >
                              <Copy size={10}/> 복사
                            </button>
                          </div>
                          <textarea
                            readOnly
                            value={youtubePackage.shorts.description || ''}
                            className="w-full bg-navy-950 border border-navy-700 rounded p-2 text-xs text-gray-300 mt-1 h-20 focus:outline-none resize-none font-mono"
                          />
                        </div>

                        <div>
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-semibold text-gray-400 font-mono">태그 / 해시태그</span>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(youtubePackage.shorts.tags?.join(', ') || '');
                                alert('해시태그가 복사되었습니다.');
                              }}
                              className="text-[10px] text-accent-cyan hover:underline flex items-center gap-0.5"
                            >
                              <Copy size={10}/> 복사
                            </button>
                          </div>
                          <div className="bg-navy-950 p-2 rounded border border-navy-700 mt-1 text-xs text-accent-cyan flex flex-wrap gap-1">
                            {youtubePackage.shorts.tags?.map((tag, idx) => (
                              <span key={idx} className="bg-navy-800 px-1.5 py-0.5 rounded border border-navy-700">#{tag}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="text-xs text-gray-400 h-full flex items-center justify-center">
                        <Loader size={12} className="animate-spin mr-1"/> 유튜브 메타데이터 생성 중...
                      </div>
                    )}
                  </div>
                </div>

                {/* 게이트 및 업로드 버튼 */}
                <div className="border-t border-navy-700 pt-3 flex items-center justify-between">
                  <div>
                    {job.youtubeUrl && (
                      <a
                        href={job.youtubeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-accent-cyan hover:underline flex items-center gap-1"
                      >
                        <ExternalLink size={12}/> YouTube 업로드 동영상 링크 열기
                      </a>
                    )}
                  </div>
                  
                  <div className="flex gap-2">
                    {job.status !== 'PUBLISHED' && (
                      <button
                        onClick={() => {
                          if (job.autonomy === 'GUIDED') {
                            setIsGuidedConfirmOpen(true);
                          } else {
                            if (confirm("유튜브 채널로 쇼츠를 업로드(시뮬레이션)하시겠습니까?")) {
                              handlePublish();
                            }
                          }
                        }}
                        disabled={publishing}
                        className="flex items-center gap-1.5 bg-red-600 text-white font-semibold text-xs px-4 py-2 rounded-lg hover:bg-red-500 disabled:opacity-50 transition"
                      >
                        {publishing ? <Loader size={12} className="animate-spin"/> : <Youtube size={12}/>}
                        {job.autonomy === 'GUIDED' ? '쇼츠 업로드 검토 및 발행' : '즉시 Shorts 업로드'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* GUIDED 모드 유튜브 Shorts 업로드 검토 팝업 */}
            {isGuidedConfirmOpen && (
              <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
                <div className="bg-navy-900 border border-navy-700 rounded-xl p-5 max-w-xl w-full space-y-4">
                  <h3 className="text-sm font-bold text-accent-cyan flex items-center gap-1.5 border-b border-navy-800 pb-2">
                    <Youtube size={16}/> YouTube Shorts 업로드 검토 (GUIDED 게이트)
                  </h3>
                  
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-gray-400">쇼츠 제목 선택</label>
                      <div className="space-y-1.5 mt-1">
                        {youtubePackage?.shorts?.titles?.map((t, idx) => (
                          <label key={idx} className="flex items-start gap-2 bg-navy-950 p-2 rounded border border-navy-800 hover:border-navy-700 cursor-pointer text-xs text-gray-300">
                            <input
                              type="radio"
                              name="selected_shorts_title"
                              defaultChecked={idx === 0}
                              className="mt-0.5 accent-accent-cyan"
                            />
                            <span>{t}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="text-xs text-gray-400">설명글</label>
                      <textarea
                        readOnly
                        value={youtubePackage?.shorts?.description || ''}
                        className="w-full bg-navy-950 border border-navy-800 rounded p-2 text-xs text-gray-300 mt-1 h-24 focus:outline-none resize-none font-mono"
                      />
                    </div>

                    <div>
                      <label className="text-xs text-gray-400">추천 해시태그</label>
                      <div className="bg-navy-950 p-2 rounded border border-navy-800 mt-1 text-xs text-accent-cyan flex flex-wrap gap-1">
                        {youtubePackage?.shorts?.tags?.map((tag, idx) => (
                          <span key={idx} className="bg-navy-900 px-1.5 py-0.5 rounded border border-navy-800">#{tag}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 border-t border-navy-800 pt-3">
                    <button
                      onClick={() => setIsGuidedConfirmOpen(false)}
                      className="bg-navy-700 hover:bg-navy-600 text-xs px-3 py-1.5 rounded text-gray-400 transition"
                    >
                      닫기
                    </button>
                    <button
                      onClick={() => {
                        setIsGuidedConfirmOpen(false);
                        handlePublish();
                      }}
                      className="bg-red-600 hover:bg-red-500 text-xs px-4 py-1.5 rounded text-white font-semibold transition"
                    >
                      검토 승인 및 업로드
                    </button>
                  </div>
                </div>
              </div>
            )}
            
          </div>
        </div>
      )}
    </Layout>
  )
}
