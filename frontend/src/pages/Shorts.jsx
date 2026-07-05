import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Upload, Scissors, Download, Loader, X, Plus, Trash2,
  Play, Pause, SkipBack, SkipForward, Clock
} from 'lucide-react'
import Layout from '../components/Layout'
import apiClient from '../api/client'
import { authStore } from '../store/auth'
import { useShortsStore } from '../store/shortsStore'

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

// JWT 포함 다운로드 — path 유효성 체크 + 에러 처리
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
  const fileRef = useRef(null), videoRef = useRef(null), tlRef = useRef(null)
  
  const [storeState, setStoreState] = useShortsStore()
  const {
    file, fileUrl, shortsCount, clipDur, mode, analyzing, cutting,
    autoSegments, autoClips, guidedSegments, guidedClips, manualSegments, manualClips,
    jobId, totalDur, curTime, playing, activeSeg, phase, downloadingIdx
  } = storeState

  const setFile = (val) => setStoreState(prev => ({ file: typeof val === 'function' ? val(prev.file) : val }))
  const setFileUrl = (val) => setStoreState(prev => ({ fileUrl: typeof val === 'function' ? val(prev.fileUrl) : val }))
  const setShortsCount = (val) => setStoreState(prev => ({ shortsCount: typeof val === 'function' ? val(prev.shortsCount) : val }))
  const setClipDur = (val) => setStoreState(prev => ({ clipDur: typeof val === 'function' ? val(prev.clipDur) : val }))
  const setMode = (val) => setStoreState(prev => ({ mode: typeof val === 'function' ? val(prev.mode) : val }))
  const setAnalyzing = (val) => setStoreState(prev => ({ analyzing: typeof val === 'function' ? val(prev.analyzing) : val }))
  const setCutting = (val) => setStoreState(prev => ({ cutting: typeof val === 'function' ? val(prev.cutting) : val }))
  const setJobId = (val) => setStoreState(prev => ({ jobId: typeof val === 'function' ? val(prev.jobId) : val }))
  const setTotalDur = (val) => setStoreState(prev => ({ totalDur: typeof val === 'function' ? val(prev.totalDur) : val }))
  const setCurTime = (val) => setStoreState(prev => ({ curTime: typeof val === 'function' ? val(prev.curTime) : val }))
  const setPlaying = (val) => setStoreState(prev => ({ playing: typeof val === 'function' ? val(prev.playing) : val }))
  const setActiveSeg = (val) => setStoreState(prev => ({ activeSeg: typeof val === 'function' ? val(prev.activeSeg) : val }))
  const setPhase = (val) => setStoreState(prev => ({ phase: typeof val === 'function' ? val(prev.phase) : val }))
  const setDownloadingIdx = (val) => setStoreState(prev => ({ downloadingIdx: typeof val === 'function' ? val(prev.downloadingIdx) : val }))

  const setAutoSegments = (val) => setStoreState(prev => ({ autoSegments: typeof val === 'function' ? val(prev.autoSegments) : val }))
  const setAutoClips = (val) => setStoreState(prev => ({ autoClips: typeof val === 'function' ? val(prev.autoClips) : val }))
  const setGuidedSegments = (val) => setStoreState(prev => ({ guidedSegments: typeof val === 'function' ? val(prev.guidedSegments) : val }))
  const setGuidedClips = (val) => setStoreState(prev => ({ guidedClips: typeof val === 'function' ? val(prev.guidedClips) : val }))
  const setManualSegments = (val) => setStoreState(prev => ({ manualSegments: typeof val === 'function' ? val(prev.manualSegments) : val }))
  const setManualClips = (val) => setStoreState(prev => ({ manualClips: typeof val === 'function' ? val(prev.manualClips) : val }))

  const segments = mode === 'AUTO' ? autoSegments : mode === 'GUIDED' ? guidedSegments : manualSegments
  const setSegments = (val) => {
    if (mode === 'AUTO') setAutoSegments(val)
    else if (mode === 'GUIDED') setGuidedSegments(val)
    else setManualSegments(val)
  }
  const clips = mode === 'AUTO' ? autoClips : mode === 'GUIDED' ? guidedClips : manualClips
  const setClips = (val) => {
    if (mode === 'AUTO') setAutoClips(val)
    else if (mode === 'GUIDED') setGuidedClips(val)
    else setManualClips(val)
  }

  const [drag, setDrag] = useState(false)
  const [dragging, setDragging] = useState(null)

  const handleFile = (f) => {
    if (!f || !f.type.startsWith('video/')) return
    if (fileUrl) URL.revokeObjectURL(fileUrl)
    setFile(f); setFileUrl(URL.createObjectURL(f))
    setAutoSegments([])
    setAutoClips([])
    setGuidedSegments([])
    setGuidedClips([])
    setManualSegments([])
    setManualClips([])
    setJobId(null)
    setActiveSeg(null); setPhase('upload')
  }

  const handleMeta = () => { if (videoRef.current) setTotalDur(videoRef.current.duration) }
  const handleTimeUpdate = () => { if (videoRef.current) setCurTime(videoRef.current.currentTime) }
  const seek = (t) => { if (videoRef.current) videoRef.current.currentTime = Math.max(0, Math.min(t, totalDur)) }
  const togglePlay = () => {
    if (!videoRef.current) return
    playing ? videoRef.current.pause() : videoRef.current.play()
    setPlaying(!playing)
  }

  const createJob = async () => {
    const res = await apiClient.post('/jobs', {
      title: `쇼츠: ${file?.name || '영상'}`,
      autonomy: mode, makeShorts: true,
      shortsCount, longformTargetMinutes: 20, budgetCap: 100,
    })
    const id = res.data.id; setJobId(id); return id
  }

  // ── AUTO/GUIDED: Whisper 분석 ──
  const handleAnalyze = async () => {
    if (!file) return
    setAnalyzing(true); setClips([])
    try {
      const jid = await createJob()
      const fd = new FormData(); fd.append('file', file)
      const res = await apiClient.post(
        `/jobs/${jid}/shorts/analyze?shortsCount=${shortsCount}`,
        fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 1800000 }
      )
      const d = res.data
      const dur = d.total_duration || totalDur || 300
      const adj = (d.suggested_segments || []).map((s, i) => ({
        ...s, index: i + 1,
        label: SEG_LABELS[i % SEG_LABELS.length],
        end: parseFloat(Math.min(s.start + clipDur, dur).toFixed(2)),
      }))
      setSegments(adj); setActiveSeg(0); setPhase('analyzed')
      if (mode === 'AUTO') await executeCut(jid, adj)
    } catch (e) {
      alert('분석 실패: ' + (e.response?.data?.detail || e.response?.data?.message || e.message))
    } finally { setAnalyzing(false) }
  }

  // ── MANUAL: 직접 구간 → 쇼츠 생성 ──
  const handleManualCut = async () => {
    if (!file) { alert('영상을 먼저 업로드하세요.'); return }
    if (segments.length === 0) { alert('구간을 먼저 추가하세요.'); return }
    setCutting(true)
    try {
      const jid = jobId || await createJob()
      const valid = segments.filter(s => s.end - s.start >= 5)
      if (!valid.length) { alert('유효한 구간 없음 (최소 5초 필요)'); return }

      const fd = new FormData()
      fd.append('file', file)
      fd.append('segments', JSON.stringify(valid.map((s, i) => ({
        index: i + 1, label: s.label || `구간 ${i + 1}`,
        start: s.start, end: s.end,
      }))))

      const res = await apiClient.post(`/jobs/${jid}/shorts/cut-direct`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 1800000
      })
      setClips(Array.isArray(res.data) ? res.data : [])
      setPhase('cut')
    } catch (e) {
      alert('쇼츠 생성 실패: ' + (e.response?.data?.message || e.message))
    } finally { setCutting(false) }
  }

  const executeCut = async (jid, segs) => {
    setCutting(true)
    try {
      const valid = segs.filter(s => s.end - s.start >= 5)
      if (!valid.length) { alert('유효한 구간 없음'); return }
      const res = await apiClient.post(`/jobs/${jid || jobId}/shorts/confirm`, {
        segments: valid.map((s, i) => ({
          index: i + 1, text: s.label || s.text || `구간 ${i + 1}`,
          start: s.start, end: s.end,
        }))
      })
      setClips(Array.isArray(res.data) ? res.data : [])
      setPhase('cut')
    } catch (e) {
      alert('쇼츠 생성 실패: ' + (e.response?.data?.message || e.message))
    } finally { setCutting(false) }
  }

  const handleGuidedCut = () => executeCut(jobId, segments)

  const updClip = (i, field, value) => {
    setClips(cls => cls.map((c, idx) => idx === i ? { ...c, [field]: value } : c))
  }

  const handleRegenerate = async () => {
    if (!jobId) { alert('작업 ID가 없습니다.'); return }
    setCutting(true)
    try {
      const res = await apiClient.post(`/jobs/${jobId}/shorts/confirm`, {
        segments: clips.map((c) => ({
          index: c.index,
          text: c.text || c.label || `쇼츠 ${c.index}`,
          start: c.start,
          end: c.end,
        }))
      })
      setClips(Array.isArray(res.data) ? res.data : [])
      alert('쇼츠 영상이 성공적으로 재생성되었습니다.')
    } catch (e) {
      alert('재생성 실패: ' + (e.response?.data?.message || e.message))
    } finally { setCutting(false) }
  }

  // ── 구간 관리 ──
  const addSeg = () => {
    const last = segments[segments.length - 1]
    const start = last ? Math.min(last.end + 2, Math.max(0, (totalDur || 300) - clipDur)) : 0
    const end = Math.min(start + clipDur, totalDur || start + clipDur)
    setSegments([...segments, {
      index: segments.length + 1, text: '',
      label: SEG_LABELS[segments.length % SEG_LABELS.length],
      start: parseFloat(start.toFixed(2)), end: parseFloat(end.toFixed(2)),
    }])
    setActiveSeg(segments.length)
  }

  const removeSeg = (i) => {
    setSegments(segments.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, index: idx + 1 })))
    if (activeSeg === i) setActiveSeg(null)
  }
  const updSeg = (i, f, v) => setSegments(segs => segs.map((s, idx) => idx === i ? { ...s, [f]: v } : s))
  const setStartHere = (i) => updSeg(i, 'start', parseFloat(curTime.toFixed(2)))
  const setEndHere = (i) => updSeg(i, 'end', parseFloat(curTime.toFixed(2)))

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

  return (
    <Layout>
      <div className="mb-4">
        <h1 className="text-2xl font-bold">쇼츠 생성</h1>
        <p className="text-gray-400 text-sm mt-1">주식 영상 핵심 구간 추출 · AUTO / GUIDED / MANUAL</p>
      </div>

      <div className="grid grid-cols-5 gap-4 mb-4">
        {/* 왼쪽: 플레이어 */}
        <div className="col-span-3">
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
                      <button onClick={() => setStartHere(activeSeg)}
                        className="text-xs bg-navy-700 text-accent-cyan px-2 py-1 rounded-lg hover:bg-navy-600">
                        ← 시작 지점
                      </button>
                      <button onClick={() => setEndHere(activeSeg)}
                        className="text-xs bg-navy-700 text-accent-cyan px-2 py-1 rounded-lg hover:bg-navy-600">
                        끝 지점 →
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
                className={`aspect-video flex flex-col items-center justify-center cursor-pointer transition ${drag ? 'bg-accent-cyan/5' : 'hover:bg-navy-700/30'}`}>
                <input ref={fileRef} type="file" accept="video/*" className="hidden"
                  onChange={e => handleFile(e.target.files[0])} />
                <Upload className="text-gray-500 mb-3" size={36} />
                <p className="text-gray-400 text-sm">주식 영상 드래그 또는 클릭</p>
                <p className="text-xs text-gray-600 mt-1">mp4 · mov · avi</p>
              </div>
            )}
          </div>
        </div>

        {/* 오른쪽: 설정 + 구간 */}
        <div className="col-span-2 flex flex-col gap-3">
          <div className="bg-navy-800 rounded-xl border border-navy-700 p-4">
            {file && (
              <div className="flex items-center justify-between mb-3 pb-3 border-b border-navy-700">
                <div>
                  <div className="text-xs font-medium truncate max-w-[150px]">{file.name}</div>
                  <div className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(1)}MB{totalDur ? ` · ${fmt(totalDur)}` : ''}</div>
                </div>
                <button onClick={() => { setFile(null); if (fileUrl) URL.revokeObjectURL(fileUrl); setFileUrl(null) }}
                  className="text-gray-500 hover:text-accent-red"><X size={14} /></button>
              </div>
            )}

            {/* 모드 선택 */}
            <div className="mb-3">
              <label className="block text-xs text-gray-400 mb-1.5">자동화 모드</label>
              <div className="flex gap-1">
                {[
                  { m: 'AUTO', label: '자동', desc: 'AI 분석 후 즉시 생성' },
                  { m: 'GUIDED', label: '반자동', desc: '분석 후 편집 가능' },
                  { m: 'MANUAL', label: '수동', desc: '직접 구간 지정' },
                ].map(({ m, label, desc }) => (
                  <button key={m} onClick={() => { setMode(m) }}
                    title={desc}
                    className={`flex-1 py-1.5 rounded text-xs font-semibold transition ${mode === m
                        ? m === 'AUTO' ? 'bg-accent-green text-navy-950'
                          : m === 'GUIDED' ? 'bg-accent-cyan text-navy-950'
                          : 'bg-accent-gold text-navy-950'
                        : 'bg-navy-700 text-gray-400 hover:bg-navy-600'}`}>{label}</button>
                ))}
              </div>
              <p className="text-xs text-gray-600 mt-1">
                {mode === 'AUTO' ? 'AI가 주식 핵심 구간을 자동으로 분석·생성합니다'
                  : mode === 'GUIDED' ? 'AI 분석 후 구간을 직접 편집할 수 있습니다'
                  : '영상을 보면서 원하는 구간을 직접 지정합니다'}
              </p>
            </div>

            {/* AUTO/GUIDED 설정 */}
            {mode !== 'MANUAL' && (
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">구간 수</label>
                  <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map(n => (
                      <button key={n} onClick={() => setShortsCount(n)}
                        className={`flex-1 py-1 rounded text-xs font-medium transition ${shortsCount === n ? 'bg-accent-cyan text-navy-950' : 'bg-navy-700 text-gray-400 hover:bg-navy-600'}`}>{n}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">기본 길이</label>
                  <select value={clipDur} onChange={e => setClipDur(Number(e.target.value))}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                    <option value={30}>30초</option>
                    <option value={45}>45초</option>
                    <option value={60}>60초</option>
                    <option value={90}>90초</option>
                  </select>
                </div>
              </div>
            )}

            {/* 액션 버튼 */}
            {mode !== 'MANUAL' ? (
              <button onClick={handleAnalyze} disabled={!file || analyzing}
                className="w-full flex items-center justify-center gap-2 bg-accent-cyan text-navy-950 font-semibold rounded-lg py-2 text-sm hover:opacity-90 disabled:opacity-50 transition">
                {analyzing ? <Loader size={14} className="animate-spin" /> : <Scissors size={14} />}
                {analyzing ? 'AI 분석 중...' : 'AI 구간 분석 시작'}
              </button>
            ) : (
              <div className="space-y-2">
                <button onClick={addSeg}
                  className="w-full flex items-center justify-center gap-2 bg-accent-gold text-navy-950 font-semibold rounded-lg py-2 text-sm hover:opacity-90 transition">
                  <Plus size={14} />구간 직접 추가
                </button>
                {segments.length > 0 && (
                  <button onClick={handleManualCut} disabled={cutting}
                    className="w-full flex items-center justify-center gap-2 bg-accent-green text-navy-950 font-semibold rounded-lg py-2 text-sm hover:opacity-90 disabled:opacity-50 transition">
                    {cutting ? <Loader size={14} className="animate-spin" /> : <Scissors size={14} />}
                    {cutting ? '쇼츠 생성 중...' : '쇼츠 생성'}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* 구간 목록 */}
          {segments.length > 0 && (
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-4 flex-1">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold">구간 목록 ({segments.length})</h3>
                <div className="flex gap-2">
                  <button onClick={addSeg}
                    className="flex items-center gap-1 text-xs bg-navy-700 text-gray-300 px-2 py-1 rounded hover:bg-navy-600">
                    <Plus size={11} />추가
                  </button>
                  {mode === 'GUIDED' && phase === 'analyzed' && (
                    <button onClick={handleGuidedCut} disabled={cutting}
                      className="flex items-center gap-1 text-xs bg-accent-green text-navy-950 font-semibold px-3 py-1 rounded hover:opacity-90 disabled:opacity-50">
                      {cutting ? <Loader size={11} className="animate-spin" /> : <Scissors size={11} />}
                      쇼츠 생성
                    </button>
                  )}
                </div>
              </div>
              <div className="space-y-1.5 overflow-y-auto max-h-52">
                {segments.map((seg, i) => (
                  <div key={i} onClick={() => { setActiveSeg(i); seek(seg.start) }}
                    className={`rounded-lg border cursor-pointer transition ${activeSeg === i ? 'border-accent-cyan bg-accent-cyan/5' : 'border-navy-700 hover:border-navy-600'}`}>
                    <div className="flex items-center justify-between px-3 py-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-xs font-bold flex-shrink-0 ${COLORS[i % COLORS.length]}`}>#{i + 1}</span>
                        <div className="min-w-0">
                          <input value={seg.label || ''}
                            onChange={e => { e.stopPropagation(); updSeg(i, 'label', e.target.value) }}
                            onClick={e => e.stopPropagation()}
                            className="bg-transparent text-xs font-medium w-24 focus:outline-none truncate"
                            placeholder={`구간 ${i + 1}`} />
                          <div className="text-xs text-gray-500 flex items-center gap-1">
                            <Clock size={9} />
                            <span contentEditable suppressContentEditableWarning
                              onBlur={e => updSeg(i, 'start', parseSec(e.target.innerText))}
                              className="focus:outline-none focus:text-accent-cyan cursor-text"
                            >{fmt(seg.start)}</span>
                            <span>→</span>
                            <span contentEditable suppressContentEditableWarning
                              onBlur={e => updSeg(i, 'end', parseSec(e.target.innerText))}
                              className="focus:outline-none focus:text-accent-cyan cursor-text"
                            >{fmt(seg.end)}</span>
                            <span className="text-gray-600">{(seg.end - seg.start).toFixed(0)}s</span>
                          </div>
                        </div>
                      </div>
                      <button onClick={e => { e.stopPropagation(); removeSeg(i) }}
                        className="text-gray-600 hover:text-accent-red flex-shrink-0 ml-1"><Trash2 size={13} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MANUAL 가이드 */}
          {mode === 'MANUAL' && segments.length === 0 && (
            <div className="bg-navy-800 rounded-xl border border-accent-gold/30 p-4">
              <p className="text-xs font-semibold text-accent-gold mb-2">수동 구간 설정 방법</p>
              <ol className="text-xs text-gray-400 space-y-1">
                <li>① [구간 직접 추가] 버튼 클릭</li>
                <li>② 영상 재생 → 원하는 지점에서 [← 시작 지점] 클릭</li>
                <li>③ 끝 지점에서 [끝 지점 →] 클릭</li>
                <li>④ 타임라인 핸들 드래그로 미세 조정</li>
                <li>⑤ [쇼츠 생성] 클릭</li>
              </ol>
            </div>
          )}
        </div>
      </div>

      {/* 타임라인 */}
      {totalDur > 0 && (
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-400">타임라인 — 구간 드래그 편집</h3>
            <span className="text-xs text-gray-500">{fmt(totalDur)}</span>
          </div>
          <div ref={tlRef}
            className="relative h-12 bg-navy-700 rounded-lg select-none cursor-pointer"
            onClick={e => { if (!dragging) seek(getT(e.clientX)) }}>
            {Array.from({ length: Math.floor(totalDur / 30) + 1 }).map((_, i) => {
              const t = i * 30
              return (
                <div key={i} className="absolute top-0 h-full pointer-events-none" style={{ left: pct(t) }}>
                  <div className="w-px h-2 bg-navy-600" />
                  <span style={{ fontSize: 9, marginLeft: 2 }} className="text-gray-600">{fmt(t)}</span>
                </div>
              )
            })}
            {segments.map((seg, i) => {
              const l = (seg.start / totalDur) * 100
              const w = Math.max(((seg.end - seg.start) / totalDur) * 100, 0.3)
              return (
                <div key={i}
                  className={`absolute top-2 h-8 rounded border-2 flex items-center justify-center transition ${BG_COLORS[i % BG_COLORS.length]} ${activeSeg === i ? 'opacity-100 ring-2 ring-white/20' : 'opacity-60'}`}
                  style={{ left: `${l}%`, width: `${w}%` }}
                  onClick={e => { e.stopPropagation(); setActiveSeg(i); seek(seg.start) }}>
                  <div className="absolute left-0 top-0 w-2 h-full cursor-w-resize hover:bg-white/20 rounded-l"
                    onMouseDown={e => onTlDown(e, i, 'start')} />
                  <span className="text-xs font-bold text-navy-950 pointer-events-none">#{i + 1}</span>
                  <div className="absolute right-0 top-0 w-2 h-full cursor-e-resize hover:bg-white/20 rounded-r"
                    onMouseDown={e => onTlDown(e, i, 'end')} />
                </div>
              )
            })}
            <div className="absolute top-0 h-full w-0.5 bg-accent-red pointer-events-none z-10" style={{ left: pct(curTime) }}>
              <div className="w-2 h-2 bg-accent-red rounded-full -ml-0.5 -mt-0.5" />
            </div>
          </div>
          <p className="text-xs text-gray-600 mt-1 text-center">
            블록 클릭: 구간 선택 · 핸들 드래그: 시작/끝 조정 · 타임라인 클릭: 재생 이동
          </p>
        </div>
      )}

      {/* 결과 */}
      {clips.length > 0 && (
        <div className="bg-navy-800 rounded-xl border border-accent-green p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-sm text-accent-green">
              ✓ 쇼츠 {clips.length}개 생성 완료 (9:16 세로 비율)
            </h3>
            <button onClick={handleRegenerate} disabled={cutting}
              className="flex items-center gap-1.5 bg-accent-gold text-navy-950 text-xs font-semibold py-1.5 px-3 rounded-lg hover:opacity-90 transition disabled:opacity-50">
              {cutting ? <Loader size={12} className="animate-spin" /> : <Scissors size={12} />}
              구간 적용 및 재생성
            </button>
          </div>
          <div className="space-y-2">
            {clips.map((clip, i) => (
              <div key={i} className="flex items-center justify-between bg-navy-700/50 rounded-lg px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-bold ${COLORS[i % COLORS.length]}`}>#{clip.index}</span>
                  <div>
                    <input value={clip.text || clip.label || ''}
                      onChange={e => updClip(i, 'text', e.target.value)}
                      className="bg-transparent text-sm font-semibold w-48 focus:outline-none focus:text-accent-cyan truncate"
                      placeholder={`쇼츠 ${clip.index}`} />
                    <div className="text-xs text-gray-500 flex items-center gap-1.5 mt-0.5">
                      <Clock size={9} />
                      <span contentEditable suppressContentEditableWarning
                        onBlur={e => updClip(i, 'start', parseSec(e.target.innerText))}
                        className="focus:outline-none focus:text-accent-cyan cursor-text font-medium"
                      >{fmt(clip.start)}</span>
                      <span>→</span>
                      <span contentEditable suppressContentEditableWarning
                        onBlur={e => updClip(i, 'end', parseSec(e.target.innerText))}
                        className="focus:outline-none focus:text-accent-cyan cursor-text font-medium"
                      >{fmt(clip.end)}</span>
                      <span className="text-gray-600 font-medium">{(clip.end - clip.start).toFixed(0)}s</span>
                      {clip.file_size_mb && <span className="ml-2 text-gray-600">{clip.file_size_mb}MB</span>}
                    </div>
                  </div>
                </div>
                <button
                  onClick={async () => {
                    setDownloadingIdx(i)
                    await downloadFile(clip.output_path, `short_${clip.index}.mp4`)
                    setDownloadingIdx(null)
                  }}
                  disabled={downloadingIdx === i}
                  className="flex items-center gap-1.5 bg-accent-green text-navy-950 text-xs font-semibold py-1.5 px-3 rounded-lg hover:opacity-90 transition disabled:opacity-50">
                  {downloadingIdx === i ? <Loader size={12} className="animate-spin" /> : <Download size={12} />}
                  MP4
                </button>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-3">9:16 세로 비율 (유튜브 쇼츠 포맷 · 재생성 시 변경 사항이 즉시 영상에 인코딩되어 반영됩니다)</p>
        </div>
      )}
    </Layout>
  )
}
