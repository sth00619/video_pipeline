import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Download, CheckCircle, Loader,
  ThumbsUp, ThumbsDown, Zap, Star, AlertCircle,
  FileText, Image as ImageIcon, Music, ChevronDown, ChevronUp
} from 'lucide-react'
import Layout from '../components/Layout'
import { jobsApi } from '../api/jobs'
import { authStore } from '../store/auth'

const PIPELINE_STEPS = [
  { key: 'keyword', label: '키워드 탐색', pendingStatus: 'KEYWORD_PENDING', gate: 'KEYWORD',
    runFn: (id) => jobsApi.searchKeyword(id, '', 5) },
  { key: 'script', label: '스크립트 생성', pendingStatus: 'SCRIPT_PENDING', gate: 'SCRIPT',
    runFn: (id) => jobsApi.generateScript(id) },
  { key: 'tts', label: '음성(TTS) 합성', pendingStatus: 'TTS_PENDING', gate: 'TTS',
    runFn: (id) => jobsApi.generateTts(id) },
  { key: 'images', label: '이미지 생성', pendingStatus: 'IMAGES_PENDING', gate: 'IMAGES',
    runFn: (id) => jobsApi.generateImages(id) },
  { key: 'longform', label: '영상 조립', pendingStatus: 'ASSEMBLING', gate: 'PREVIEW',
    runFn: (id) => jobsApi.generateLongform(id) },
]

const STATUS_ORDER = [
  'DRAFT','KEYWORD_PENDING','SCRIPT_PENDING','TTS_PENDING',
  'IMAGES_PENDING','ASSEMBLING','PREVIEW_PENDING','READY','PUBLISHED',
]

function getStepStatus(step, job, approvals) {
  if (approvals.find(a => a.gate === step.gate)) return 'done'
  if (['READY','PUBLISHED'].includes(job.status)) return 'done'
  if (job.status === step.pendingStatus) return 'active'
  if (job.status === 'ASSEMBLING' && step.key === 'longform') return 'active'
  const ji = STATUS_ORDER.indexOf(job.status)
  const si = STATUS_ORDER.indexOf(step.pendingStatus)
  return ji > si ? 'done' : 'idle'
}

const AUTONOMY_STYLE = {
  AUTO: 'bg-accent-green/20 text-accent-green border-accent-green/30',
  GUIDED: 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/30',
  MANUAL: 'bg-accent-gold/20 text-accent-gold border-accent-gold/30',
}
const AUTONOMY_DESC = {
  AUTO: '모든 단계 자동 진행', GUIDED: '키워드·미리보기 검토 후 자동', MANUAL: '각 단계마다 수동 승인 필요',
}

export default function JobDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [gateModal, setGateModal] = useState(null)
  const [runningStep, setRunningStep] = useState(null)
  const [expandedScript, setExpandedScript] = useState(false)

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', id], queryFn: () => jobsApi.get(id), refetchInterval: 3000,
  })
  const { data: approvals = [] } = useQuery({
    queryKey: ['approvals', id], queryFn: () => jobsApi.approvals(id), refetchInterval: 3000,
  })
  const { data: costs } = useQuery({
    queryKey: ['costs', id], queryFn: () => jobsApi.costs(id), refetchInterval: 10000,
  })

  // ── 각 단계 산출물 조회 (Asset 기반, 서버 상태 완전 복원) ──
  const { data: kwAssets = [] } = useQuery({
    queryKey: ['assets', id, 'KEYWORD'], queryFn: () => jobsApi.assets(id, 'KEYWORD'), enabled: !!job,
  })
  const { data: scriptAssets = [] } = useQuery({
    queryKey: ['assets', id, 'SCRIPT'], queryFn: () => jobsApi.assets(id, 'SCRIPT'), enabled: !!job,
  })
  const { data: imageAssets = [] } = useQuery({
    queryKey: ['assets', id, 'IMAGE'], queryFn: () => jobsApi.assets(id, 'IMAGE'), enabled: !!job,
  })
  const { data: ttsAssets = [] } = useQuery({
    queryKey: ['assets', id, 'TTS'], queryFn: () => jobsApi.assets(id, 'TTS'), enabled: !!job,
  })

  const kwCandidates = useMemo(() => {
    for (let i = kwAssets.length - 1; i >= 0; i--) {
      try { const m = JSON.parse(kwAssets[i].metaJson || '{}'); if (m.candidates) return m.candidates } catch {}
    }
    return []
  }, [kwAssets])

  const scriptData = useMemo(() => {
    if (!scriptAssets.length) return null
    try {
      const latest = scriptAssets[scriptAssets.length - 1]
      return JSON.parse(latest.metaJson || '{}')
    } catch { return null }
  }, [scriptAssets])

  const imageList = useMemo(() => {
    return imageAssets.map(a => {
      try { return JSON.parse(a.metaJson || '{}') } catch { return null }
    }).filter(Boolean)
  }, [imageAssets])

  const ttsInfo = useMemo(() => {
    if (!ttsAssets.length) return null
    try { return JSON.parse(ttsAssets[ttsAssets.length - 1].metaJson || '{}') } catch { return null }
  }, [ttsAssets])

  const approveMut = useMutation({
    mutationFn: ({ gate, comment }) => jobsApi.approve(id, gate, comment),
    onSuccess: () => { qc.invalidateQueries(['job',id]); qc.invalidateQueries(['approvals',id]); setGateModal(null) },
  })
  const rejectMut = useMutation({
    mutationFn: ({ gate, comment }) => jobsApi.reject(id, gate, comment),
    onSuccess: () => { qc.invalidateQueries(['job',id]); qc.invalidateQueries(['approvals',id]); setGateModal(null) },
  })

  const handleRun = async (step) => {
    setRunningStep(step.key)
    try {
      await step.runFn(id)
      qc.invalidateQueries(['job',id])
      qc.invalidateQueries(['approvals',id])
      qc.invalidateQueries(['assets',id])
    } catch(e){ console.error(e); alert('실행 실패: ' + (e.response?.data?.message || e.message)) }
    finally { setRunningStep(null) }
  }

  if (isLoading) return <Layout><div className="flex items-center justify-center h-64"><Loader className="animate-spin text-accent-cyan" size={32}/></div></Layout>
  if (!job) return <Layout><div className="text-gray-400 p-8">작업을 찾을 수 없습니다.</div></Layout>

  const isAuto = job.autonomy === 'AUTO'
  const isGuided = job.autonomy === 'GUIDED'
  const isManual = job.autonomy === 'MANUAL'
  const isDone = ['READY','PUBLISHED'].includes(job.status)
  const token = authStore.getToken()

  return (
    <Layout>
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/jobs')} className="text-gray-400 hover:text-white transition"><ChevronLeft size={24}/></button>
          <div>
            <h1 className="text-xl font-bold">{job.title}</h1>
            <div className="text-sm text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
              <span>{job.category}</span><span>·</span><span>{job.longformTargetMinutes}분</span><span>·</span>
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${AUTONOMY_STYLE[job.autonomy]}`}>{job.autonomy}</span>
              <span className="text-gray-500 text-xs">{AUTONOMY_DESC[job.autonomy]}</span>
            </div>
          </div>
        </div>
        <StatusBadge status={job.status}/>
      </div>

      {isManual && !isDone && (
        <div className="bg-accent-gold/10 border border-accent-gold/30 rounded-xl px-5 py-3 mb-5 flex items-center gap-3">
          <AlertCircle className="text-accent-gold flex-shrink-0" size={18}/>
          <p className="text-sm text-accent-gold"><span className="font-semibold">수동 모드</span> — 각 단계마다 "실행" 후 결과를 확인하고 승인해야 다음 단계로 넘어갑니다.</p>
        </div>
      )}
      {isGuided && !isDone && (
        <div className="bg-accent-cyan/10 border border-accent-cyan/30 rounded-xl px-5 py-3 mb-5 flex items-center gap-3">
          <AlertCircle className="text-accent-cyan flex-shrink-0" size={18}/>
          <p className="text-sm text-accent-cyan"><span className="font-semibold">반자동 모드</span> — 키워드 선택과 최종 미리보기만 검토하면 나머지는 자동 진행됩니다.</p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-3">
          {PIPELINE_STEPS.map((step, idx) => {
            const ss = getStepStatus(step, job, approvals)
            const approval = approvals.find(a => a.gate === step.gate)
            const showRun = ss === 'active' && isManual && runningStep === null
            const guidedGates = ['KEYWORD','PREVIEW']
            const showGuidedApprove = isGuided && ss === 'active' && guidedGates.includes(step.gate)
            const showManualApprove = isManual && ss === 'active' && runningStep !== step.key

            return (
              <div key={step.key} className={`bg-navy-800 rounded-xl border transition ${ss === 'active' ? 'border-accent-cyan' : 'border-navy-700'}`}>
                <div className="flex items-center justify-between px-5 py-4">
                  <div className="flex items-center gap-3">
                    <StepIcon status={ss} idx={idx+1}/>
                    <div>
                      <div className="font-medium text-sm">{step.label}</div>
                      {approval && <div className="text-xs text-gray-500 mt-0.5">{approval.result === 'AUTO_APPROVED' ? '⚡ 자동 승인' : `✓ ${approval.approvedBy}`}</div>}
                      {ss === 'active' && isAuto && <div className="text-xs text-accent-cyan mt-0.5 flex items-center gap-1"><Loader size={10} className="animate-spin"/>자동 진행 중</div>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {showRun && (
                      <button onClick={() => handleRun(step)} disabled={!!runningStep}
                        className="flex items-center gap-1.5 bg-accent-cyan text-navy-950 text-xs font-semibold px-3 py-1.5 rounded-lg hover:opacity-90 disabled:opacity-50 transition">
                        {runningStep === step.key ? <Loader size={12} className="animate-spin"/> : <Zap size={12}/>}실행
                      </button>
                    )}
                    {(showManualApprove || showGuidedApprove) && (
                      <button onClick={() => setGateModal({ gate: step.gate, step })}
                        className="text-xs bg-accent-gold/20 text-accent-gold border border-accent-gold/30 px-3 py-1.5 rounded-lg hover:bg-accent-gold/30 transition">검토 / 승인</button>
                    )}
                    {ss === 'active' && isAuto && <Loader size={14} className="animate-spin text-accent-cyan"/>}
                  </div>
                </div>

                {/* ── 키워드 후보 ── */}
                {step.key === 'keyword' && kwCandidates.length > 0 && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <p className="text-xs text-gray-500 mt-3 mb-2">후보 {kwCandidates.length}개</p>
                    <div className="space-y-1.5">
                      {kwCandidates.map((c, i) => (
                        <div key={i} className={`flex items-center justify-between px-3 py-2 rounded-lg ${c.is_outperformer ? 'bg-accent-gold/10 border border-accent-gold/20' : 'bg-navy-700/50'}`}>
                          <div className="flex items-center gap-2">
                            {c.is_outperformer && <Star size={11} className="text-accent-gold fill-accent-gold"/>}
                            <span className="text-xs">{c.keyword}</span>
                          </div>
                          <div className="text-xs text-gray-500 flex gap-3">
                            <span>×{c.outperformance_index?.toFixed(1)}</span>
                            <span>{c.velocity_vph?.toFixed(0)}vph</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    {job.keyword && <div className="mt-2 text-xs text-gray-400">✓ 확정: <span className="text-accent-cyan">{job.keyword}</span></div>}
                  </div>
                )}

                {/* ── 스크립트 미리보기 (신규) ── */}
                {step.key === 'script' && scriptData && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex items-center justify-between mt-3 mb-2">
                      <div className="flex items-center gap-2">
                        <FileText size={13} className="text-accent-cyan"/>
                        <span className="text-xs text-gray-400">
                          {scriptData.char_count?.toLocaleString()}자
                          {scriptData.used_real_llm === false && (
                            <span className="ml-2 text-accent-gold">⚠ Mock 스크립트 (ANTHROPIC_API_KEY 미설정)</span>
                          )}
                          {scriptData.used_real_llm === true && (
                            <span className="ml-2 text-accent-green">✓ Claude Sonnet 5 생성</span>
                          )}
                        </span>
                      </div>
                      <button onClick={() => setExpandedScript(!expandedScript)}
                        className="text-xs text-accent-cyan flex items-center gap-1 hover:underline">
                        {expandedScript ? '접기' : '전체 보기'}
                        {expandedScript ? <ChevronUp size={12}/> : <ChevronDown size={12}/>}
                      </button>
                    </div>
                    {scriptData.sections && (
                      <div className="space-y-2">
                        {scriptData.sections.map((sec, i) => (
                          <div key={i} className="bg-navy-700/40 rounded-lg p-3">
                            <div className="text-xs font-semibold text-accent-gold mb-1">{sec.title}</div>
                            <p className="text-xs text-gray-300 leading-relaxed">
                              {expandedScript ? sec.content : (sec.content?.slice(0, 80) + (sec.content?.length > 80 ? '...' : ''))}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* ── TTS 오디오 미리듣기 (신규) ── */}
                {step.key === 'tts' && ttsInfo && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex items-center gap-2 mt-3 mb-2">
                      <Music size={13} className="text-accent-cyan"/>
                      <span className="text-xs text-gray-400">
                        {ttsInfo.total_duration ? `${(ttsInfo.total_duration/60).toFixed(1)}분` : ''}
                        {ttsInfo.chunks && ` · ${ttsInfo.chunks.length}개 자막 청크`}
                        {ttsInfo.used_gtts === true && <span className="ml-2 text-accent-green">✓ gTTS 실제 음성</span>}
                      </span>
                    </div>
                    {ttsInfo.audio_path && (
                      <audio controls className="w-full h-8" style={{ filter: 'invert(0.9)' }}>
                        <source src={`/api/files/download?path=${encodeURIComponent(ttsInfo.audio_path)}`} type="audio/mpeg"/>
                      </audio>
                    )}
                  </div>
                )}

                {/* ── 이미지 갤러리 (신규) ── */}
                {step.key === 'images' && imageList.length > 0 && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex items-center gap-2 mt-3 mb-2">
                      <ImageIcon size={13} className="text-accent-cyan"/>
                      <span className="text-xs text-gray-400">{imageList.length}개 씬 이미지 (matplotlib 차트 기반)</span>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                      {imageList.slice(0, 8).map((img, i) => (
                        <div key={i} className="aspect-video bg-navy-700 rounded overflow-hidden border border-navy-600">
                          <img
                            src={`/api/files/download?path=${encodeURIComponent(img.image_path)}`}
                            alt={`씬 ${i+1}`}
                            className="w-full h-full object-cover"
                            onError={e => { e.target.style.display = 'none' }}
                          />
                        </div>
                      ))}
                    </div>
                    {imageList.length > 8 && (
                      <p className="text-xs text-gray-500 mt-1">외 {imageList.length - 8}개 씬</p>
                    )}
                  </div>
                )}
              </div>
            )
          })}

          {isDone && job.outputPath && (
            <div className="bg-navy-800 rounded-xl border border-accent-green p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CheckCircle className="text-accent-green" size={20}/>
                  <div>
                    <div className="font-semibold text-sm">영상 생성 완료</div>
                    <div className="text-xs text-gray-400 mt-0.5">{job.longformTargetMinutes}분 · 1920×1080</div>
                  </div>
                </div>
                <a href={`/api/files/download?path=${encodeURIComponent(job.outputPath)}`}
                  className="flex items-center gap-2 bg-accent-green text-navy-950 font-semibold text-sm px-4 py-2 rounded-lg hover:opacity-90 transition" download>
                  <Download size={14}/>MP4 다운로드
                </a>
              </div>
            </div>
          )}
        </div>

        {/* 오른쪽 패널 */}
        <div className="space-y-4">
          <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
            <h3 className="text-sm font-semibold mb-3">작업 정보</h3>
            <div className="space-y-2.5 text-sm">
              <InfoRow label="상태" value={<StatusBadge status={job.status} small/>}/>
              <InfoRow label="카테고리" value={job.category}/>
              <InfoRow label="목표 길이" value={`${job.longformTargetMinutes}분`}/>
              <InfoRow label="자율성" value={<span className={`text-xs px-2 py-0.5 rounded-full border ${AUTONOMY_STYLE[job.autonomy]}`}>{job.autonomy}</span>}/>
              {job.keyword && <InfoRow label="확정 키워드" value={<span className="text-accent-cyan text-xs">{job.keyword}</span>}/>}
            </div>
          </div>

          {/* 비용 상세 (보강) */}
          {costs && (
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
              <h3 className="text-sm font-semibold mb-3">비용 상세</h3>
              <div className="space-y-2 text-sm mb-3">
                <InfoRow label="누적" value={`$${parseFloat(costs.currentTotal||0).toFixed(2)}`}/>
                <InfoRow label="예산" value={costs.budgetCap ? `$${costs.budgetCap}` : '무제한'}/>
              </div>
              {costs.budgetCap && (
                <div className="mb-3">
                  <div className="h-1.5 bg-navy-700 rounded-full overflow-hidden">
                    <div className="h-full bg-accent-cyan rounded-full transition-all" style={{width:`${Math.min(100,(costs.currentTotal/costs.budgetCap)*100)}%`}}/>
                  </div>
                </div>
              )}
              {costs.items && costs.items.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-navy-700">
                  {costs.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">{item.provider}</span>
                      <span className="text-gray-300">${parseFloat(item.amount||0).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {approvals.length > 0 && (
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
              <h3 className="text-sm font-semibold mb-3">게이트 이력</h3>
              <div className="space-y-2">
                {approvals.map((a,i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">{a.gate}</span>
                    <span className={a.result==='REJECTED'?'text-accent-red':a.result==='AUTO_APPROVED'?'text-accent-cyan':'text-accent-green'}>
                      {a.result==='AUTO_APPROVED'?'⚡ 자동':a.result==='REJECTED'?'✗ 거부':'✓ 승인'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {gateModal && (
        <GateModal gate={gateModal.gate} step={gateModal.step}
          onApprove={c => approveMut.mutate({gate:gateModal.gate,comment:c})}
          onReject={c => rejectMut.mutate({gate:gateModal.gate,comment:c})}
          onClose={() => setGateModal(null)}
          loading={approveMut.isPending||rejectMut.isPending}/>
      )}
    </Layout>
  )
}

function StepIcon({status,idx}) {
  if (status==='done') return <CheckCircle className="text-accent-green flex-shrink-0" size={20}/>
  if (status==='active') return <Loader className="text-accent-cyan animate-spin flex-shrink-0" size={20}/>
  return <div className="w-5 h-5 rounded-full border border-navy-600 flex items-center justify-center text-xs text-gray-600 flex-shrink-0">{idx}</div>
}

function StatusBadge({status,small}) {
  const M={
    READY:{l:'완료',c:'bg-accent-green/20 text-accent-green'},
    PUBLISHED:{l:'업로드됨',c:'bg-accent-green/20 text-accent-green'},
    ASSEMBLING:{l:'조립중',c:'bg-accent-cyan/20 text-accent-cyan'},
    FAILED:{l:'오류',c:'bg-accent-red/20 text-accent-red'},
    BUDGET_BLOCKED:{l:'예산초과',c:'bg-accent-red/20 text-accent-red'},
    DRAFT:{l:'초안',c:'bg-navy-700 text-gray-400'},
    KEYWORD_PENDING:{l:'키워드',c:'bg-accent-cyan/10 text-accent-cyan'},
    SCRIPT_PENDING:{l:'스크립트',c:'bg-accent-cyan/10 text-accent-cyan'},
    TTS_PENDING:{l:'TTS',c:'bg-accent-cyan/10 text-accent-cyan'},
    IMAGES_PENDING:{l:'이미지',c:'bg-accent-cyan/10 text-accent-cyan'},
    PREVIEW_PENDING:{l:'미리보기 대기',c:'bg-accent-gold/20 text-accent-gold'},
  }
  const c=M[status]||{l:status,c:'bg-navy-700 text-gray-400'}
  return <span className={`${small?'text-xs px-2 py-0.5':'text-sm px-3 py-1.5'} rounded-full font-medium ${c.c}`}>{c.l}</span>
}

function InfoRow({label,value}) {
  return <div className="flex items-center justify-between gap-2"><span className="text-gray-500 flex-shrink-0">{label}</span><span className="font-medium text-right">{value}</span></div>
}

function GateModal({gate,step,onApprove,onReject,onClose,loading}) {
  const [comment,setComment]=useState('')
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-navy-800 rounded-xl p-6 w-full max-w-sm border border-navy-700 shadow-2xl">
        <h3 className="font-bold mb-2">{step.label} 검토</h3>
        <p className="text-sm text-gray-400 mb-4">결과를 확인하고 승인 또는 거부하세요.</p>
        <textarea value={comment} onChange={e=>setComment(e.target.value)} placeholder="코멘트 (선택사항)" rows={3}
          className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3 py-2 text-sm text-white mb-4 focus:outline-none focus:ring-1 focus:ring-accent-cyan resize-none"/>
        <div className="flex gap-3">
          <button onClick={()=>onReject(comment)} disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-lg py-2.5 text-sm hover:bg-accent-red/30 disabled:opacity-50 transition">
            <ThumbsDown size={14}/>거부
          </button>
          <button onClick={()=>onApprove(comment)} disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-accent-green/20 text-accent-green border border-accent-green/30 rounded-lg py-2.5 text-sm hover:bg-accent-green/30 disabled:opacity-50 transition">
            <ThumbsUp size={14}/>승인
          </button>
        </div>
        <button onClick={onClose} className="w-full mt-2 text-gray-500 text-xs hover:text-gray-300 transition">닫기</button>
      </div>
    </div>
  )
}
