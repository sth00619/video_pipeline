import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Download, CheckCircle, Loader,
  ThumbsUp, ThumbsDown, Zap, Star, AlertCircle,
  FileText, Image as ImageIcon, Music, ChevronDown, ChevronUp,
  Clock, Edit, Save, Printer, Scissors, Copy, ExternalLink, Youtube
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

const STEP_PROGRESS_INFO = {
  keyword: {
    est: '약 20초 ~ 30초 소요',
    desc: '실시간 국내/해외 주요 지수 및 환율 정보를 조회하고 당일 뉴스 RSS 피드를 수집하여 팩트를 분석하고 트렌디한 영상 키워드 후보를 도출합니다.',
  },
  script: {
    est: '약 1분 ~ 1분 30초 소요',
    desc: '수집한 주식 및 경제 수치들에 대해 3단계 교차 검증(3-Round Fact Checker)을 거쳐 정확한 사실만 확정합니다. 확정된 수치만을 사용하여 영상 길이에 맞춘 스토리보드 대본을 생성합니다. (분량에 비례하여 글자 수가 타겟팅됩니다.)',
  },
  tts: {
    est: '약 20초 ~ 30초 소요',
    desc: '작성된 영상 대본의 톤앤매너에 맞게 고음질 인공지능 성우의 음성 오디오 데이터로 합성하는 과정을 진행합니다.',
  },
  images: {
    est: '약 40초 ~ 50초 소요',
    desc: '각 시나리오 씬별 주식/경제 분석 흐름에 맞춰, 일관성 있는 금색 코인 마스코트 캐릭터와 직관적인 설명적 배경이 어우러진 고품질 AI 일러스트 이미지를 Google Gemini API를 통해 생성합니다.',
  },
  longform: {
    est: '약 1분 ~ 2분 소요',
    desc: '최종 생성된 스크립트 대본, TTS 오디오 타임라인, 생성된 AI 일러스트와 씬 전환 영상을 시간 동기화하여 자막과 함께 고화질 MP4 동영상 파일로 합치고 인코딩합니다.',
  },
}

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

/**
 * [UI 개선]
 * - 기존 text-gray-*(Tailwind 기본 회색) → text-navy-400(라벨류) / text-gray-200(본문류)로 통일.
 *   navy 배경 위에서 gray는 색감이 미묘하게 어긋나 탁해 보이는 원인이었습니다.
 * - text-[9px]/text-[10px]/text-[11px]처럼 너무 작은 임의 크기들을 text-xs(12px)
 *   이상으로 올렸고, 대사/설명 본문(text-xs)은 text-sm(14px)으로 상향했습니다.
 * - 카드들에 shadow-card를 추가해 배경과의 구분감을 살렸습니다.
 * - 기능 로직(뮤테이션, 쿼리, 씬 편집/분할/재생성 등)은 전혀 건드리지 않았습니다.
 */
export default function JobDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [gateModal, setGateModal] = useState(null)
  const [runningStep, setRunningStep] = useState(null)
  const [expandedScript, setExpandedScript] = useState(false)

  const [isEditingScript, setIsEditingScript] = useState(false)
  const [editedScriptText, setEditedScriptText] = useState('')
  const [scriptViewMode, setScriptViewMode] = useState('paragraphs')
  const [editingSceneIndex, setEditingSceneIndex] = useState(null)
  const [editingSceneText, setEditingSceneText] = useState('')
  const [imageSalt, setImageSalt] = useState(0)
  const [isGuidedConfirmOpen, setIsGuidedConfirmOpen] = useState(false)

  const { data: job, isLoading } = useQuery({
    queryKey: ['job', id], queryFn: () => jobsApi.get(id), refetchInterval: 3000,
  })
  const { data: approvals = [] } = useQuery({
    queryKey: ['approvals', id], queryFn: () => jobsApi.approvals(id), refetchInterval: 3000,
  })
  const { data: costs } = useQuery({
    queryKey: ['costs', id], queryFn: () => jobsApi.costs(id), refetchInterval: 10000,
  })

  useEffect(() => {
    if (!job || job.autonomy !== 'AUTO' || runningStep || isLoading) return;
    const activeStep = PIPELINE_STEPS.find(step => {
      const ss = getStepStatus(step, job, approvals);
      return ss === 'active';
    });
    if (activeStep) {
      console.log('AUTO 모드: 자동 실행 트리거 ->', activeStep.key);
      handleRun(activeStep);
    }
  }, [job, approvals, runningStep, isLoading]);

  const { data: kwAssets = [] } = useQuery({
    queryKey: ['assets', id, 'KEYWORD'], queryFn: () => jobsApi.assets(id, 'KEYWORD'), enabled: !!job,
  })
  const { data: scriptAssets = [] } = useQuery({
    queryKey: ['assets', id, 'SCRIPT'], queryFn: () => jobsApi.assets(id, 'SCRIPT'), enabled: !!job,
  })
  const { data: imageAssets = [] } = useQuery({
    queryKey: ['assets', id, 'SCENE_IMAGE'], queryFn: () => jobsApi.assets(id, 'SCENE_IMAGE'), enabled: !!job,
  })
  const { data: ttsAssets = [] } = useQuery({
    queryKey: ['assets', id, 'TTS_AUDIO'], queryFn: () => jobsApi.assets(id, 'TTS_AUDIO'), enabled: !!job,
  })
  const { data: youtubeMetadataAssets = [] } = useQuery({
    queryKey: ['assets', id, 'YOUTUBE_METADATA'], queryFn: () => jobsApi.assets(id, 'YOUTUBE_METADATA'), enabled: !!job,
  })

  const youtubePackage = useMemo(() => {
    if (!youtubeMetadataAssets.length) return null
    try {
      return JSON.parse(youtubeMetadataAssets[youtubeMetadataAssets.length - 1].metaJson || '{}')
    } catch { return null }
  }, [youtubeMetadataAssets])

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

  const fmt = (s) => {
    if (s == null || isNaN(s)) return '0:00'
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec < 10 ? '0' : ''}${sec}`
  }

  const imageList = useMemo(() => {
    return imageAssets.map(a => {
      try { return JSON.parse(a.metaJson || '{}') } catch { return null }
    }).filter(Boolean)
  }, [imageAssets])

  const sortedImageList = useMemo(() => {
    return [...imageList].sort((a, b) => (a.index || 0) - (b.index || 0))
  }, [imageList])

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

  const saveScriptMut = useMutation({
    mutationFn: (text) => jobsApi.confirmScript(id, text),
    onSuccess: () => {
      qc.invalidateQueries(['job', id])
      qc.invalidateQueries(['assets', id, 'SCRIPT'])
      setIsEditingScript(false)
    },
    onError: (err) => {
      alert('스크립트 저장 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const regenImageMut = useMutation({
    mutationFn: ({ index, text, section, mode }) => jobsApi.updateSceneImage(id, index, text, section, mode),
    onSuccess: (data, variables) => {
      qc.invalidateQueries(['assets', id, 'SCENE_IMAGE'])
      setEditingSceneIndex(null)
      setImageSalt(prev => prev + 1)
      const modeStr = variables.mode === 'image' ? '이미지만' : variables.mode === 'text' ? '텍스트만' : '텍스트와 이미지 모두';
      alert(`${modeStr} 수정이 성공적으로 반영되었습니다. 자막/음성을 비디오 파일에 완전히 적용하려면 우측 상단의 '동영상 재조립' 버튼을 꼭 클릭해 주세요.`);
    },
    onError: (err) => {
      alert('수정 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const splitSceneMut = useMutation({
    mutationFn: ({ index, part1, part2 }) => jobsApi.splitScene(id, index, part1, part2),
    onSuccess: () => {
      qc.invalidateQueries(['assets', id, 'SCENE_IMAGE'])
      setEditingSceneIndex(null)
      alert("씬 분할이 성공적으로 반영되었습니다. 수정 사항을 최종 동영상 파일에 완전히 적용하려면 우측 상단의 '동영상 재조립' 버튼을 꼭 클릭해 주세요.");
    },
    onError: (err) => {
      alert('씬 분할 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const rebuildLongformMut = useMutation({
    mutationFn: () => jobsApi.rebuildLongform(id),
    onSuccess: () => {
      qc.invalidateQueries(['job', id])
      qc.invalidateQueries(['assets', id])
      setImageSalt(prev => prev + 1)
      alert('동영상이 성공적으로 재조립되었습니다.')
    },
    onError: (err) => {
      alert('동영상 재조립 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const stopMutation = useMutation({
    mutationFn: () => jobsApi.stop(id),
    onSuccess: () => {
      qc.invalidateQueries(['job', id])
      alert('작업이 중지되었습니다.')
    },
    onError: (err) => {
      alert('작업 중지 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const deleteMutation = useMutation({
    mutationFn: () => jobsApi.delete(id),
    onSuccess: () => {
      alert('작업이 성공적으로 삭제되었습니다.')
      navigate('/jobs')
    },
    onError: (err) => {
      alert('작업 삭제 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const handleStop = () => {
    if (window.confirm('정말로 진행 중인 영상 제작 작업을 즉시 중지하시겠습니까?')) {
      stopMutation.mutate()
    }
  }

  const handleDelete = () => {
    if (window.confirm('정말로 이 작업을 삭제하시겠습니까? 관련 데이터베이스 기록 및 미디어 파일이 완전히 제거됩니다.')) {
      deleteMutation.mutate()
    }
  }

  const publishMut = useMutation({
    mutationFn: () => jobsApi.publish(id),
    onSuccess: () => {
      qc.invalidateQueries(['job', id])
      qc.invalidateQueries(['assets', id])
      alert("유튜브 업로드가 완료되었습니다!");
    },
    onError: (err) => {
      alert('유튜브 업로드 실패: ' + (err.response?.data?.message || err.message))
    }
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
  if (!job) return <Layout><div className="text-navy-400 p-8">작업을 찾을 수 없습니다.</div></Layout>

  const isAuto = job.autonomy === 'AUTO'
  const isGuided = job.autonomy === 'GUIDED'
  const isManual = job.autonomy === 'MANUAL'
  const isDone = ['READY','PUBLISHED'].includes(job.status)
  const isRunning = !['DRAFT', 'READY', 'PUBLISHED', 'FAILED'].includes(job.status)
  const isDeletable = ['DRAFT', 'READY', 'FAILED'].includes(job.status)
  const token = authStore.getToken()

  return (
    <Layout>
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/jobs')} className="text-navy-400 hover:text-white transition"><ChevronLeft size={24}/></button>
          <div>
            <h1 className="text-2xl font-bold">{job.title}</h1>
            <div className="text-sm text-navy-400 mt-1 flex items-center gap-2 flex-wrap">
              <span>{job.category}</span><span>·</span><span>{job.longformTargetMinutes}분</span><span>·</span>
              <span className={`text-sm px-2.5 py-1 rounded-full border font-medium ${AUTONOMY_STYLE[job.autonomy]}`}>{job.autonomy}</span>
              <span className="text-navy-400 text-sm">{AUTONOMY_DESC[job.autonomy]}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={job.status}/>
          {isRunning && (
            <button
              onClick={handleStop}
              disabled={stopMutation.isPending}
              className="text-sm bg-red-950/40 text-red-400 border border-red-900/60 hover:bg-red-900/50 disabled:opacity-50 px-4 py-2 rounded-lg transition font-semibold"
            >
              작업 중지
            </button>
          )}
          {isDeletable && (
            <button
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="text-sm bg-navy-700/60 text-navy-400 border border-navy-600 hover:bg-navy-600/50 disabled:opacity-50 px-4 py-2 rounded-lg transition"
            >
              작업 삭제
            </button>
          )}
        </div>
      </div>

      {isManual && !isDone && (
        <div className="bg-accent-gold/10 border border-accent-gold/30 rounded-xl px-5 py-4 mb-5 flex items-center gap-3">
          <AlertCircle className="text-accent-gold flex-shrink-0" size={20}/>
          <p className="text-sm text-accent-gold"><span className="font-semibold">수동 모드</span> — 각 단계마다 "실행" 후 결과를 확인하고 승인해야 다음 단계로 넘어갑니다.</p>
        </div>
      )}
      {isGuided && !isDone && (
        <div className="bg-accent-cyan/10 border border-accent-cyan/30 rounded-xl px-5 py-4 mb-5 flex items-center gap-3">
          <AlertCircle className="text-accent-cyan flex-shrink-0" size={20}/>
          <p className="text-sm text-accent-cyan"><span className="font-semibold">반자동 모드</span> — 키워드 선택과 최종 미리보기만 검토하면 나머지는 자동 진행됩니다.</p>
        </div>
      )}
      {isAuto && !isDone && (
        <div className="bg-accent-green/10 border border-accent-green/30 rounded-xl px-5 py-4 mb-5 flex items-center gap-3">
          <Zap className="text-accent-green flex-shrink-0" size={20}/>
          <div>
            <p className="text-sm text-accent-green"><span className="font-semibold">완전 자동 모드</span> — 백엔드 서버가 모든 단계를 자율적으로 실행합니다.</p>
            <p className="text-sm text-accent-green/70 mt-1">브라우저를 닫으셔도 진행됩니다. 이 페이지에서 실시간 진행 현황을 모니터링할 수 있습니다.</p>
          </div>
        </div>
      )}

      {job.outputPath && (
        <div className="bg-navy-800 rounded-xl border border-accent-green p-5 space-y-4 mb-6 shadow-card">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle className="text-accent-green" size={22}/>
              <div>
                <div className="font-semibold text-base">
                  {isDone ? '영상 생성 완료' : '영상 조립 완료 (미리보기)'}
                </div>
                <div className="text-sm text-navy-400 mt-0.5">{job.longformTargetMinutes}분 · 1920×1080</div>
              </div>
            </div>
            <div className="flex gap-2">
              {['PREVIEW_PENDING', 'READY'].includes(job.status) && (
                <button
                  onClick={() => rebuildLongformMut.mutate()}
                  disabled={rebuildLongformMut.isPending}
                  className="flex items-center gap-1.5 bg-accent-gold text-navy-950 font-semibold text-sm px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition"
                >
                  {rebuildLongformMut.isPending ? <Loader size={14} className="animate-spin"/> : <Zap size={14}/>}
                  동영상 재조립
                </button>
              )}
              {['PREVIEW_PENDING', 'READY'].includes(job.status) && (
                <a href={`/jobs/${id}/shorts`}
                  className="flex items-center gap-1.5 bg-accent-cyan text-navy-950 font-semibold text-sm px-4 py-2 rounded-lg hover:opacity-90 transition"
                >
                  쇼츠 제작하기
                </a>
              )}
              <a href={`/api/files/download?path=${encodeURIComponent(job.outputPath)}&token=${token}`}
                className="flex items-center gap-2 bg-accent-green text-navy-950 font-semibold text-sm px-4 py-2 rounded-lg hover:opacity-90 transition" download>
                <Download size={14}/>MP4 다운로드
              </a>
            </div>
          </div>

          <div className="aspect-video bg-navy-950 rounded-lg overflow-hidden border border-navy-700">
            <video
              key={imageSalt}
              controls
              className="w-full h-full"
              src={`/api/files/download?path=${encodeURIComponent(job.outputPath)}&token=${token}`}
            />
          </div>
        </div>
      )}

      {['READY', 'PUBLISHED'].includes(job.status) && (
        <div className="bg-navy-800 rounded-xl border border-accent-cyan p-5 space-y-4 mb-6 shadow-card">
          <div className="flex items-center justify-between border-b border-navy-700 pb-3">
            <h3 className="text-base font-bold text-accent-cyan flex items-center gap-1.5">
              <Youtube size={18}/> YouTube 업로드 및 수동 발행 지원 킷
            </h3>
            {job.status === 'PUBLISHED' ? (
              <span className="text-sm bg-accent-green/10 text-accent-green font-bold px-2.5 py-1 rounded border border-accent-green/20">
                업로드 완료
              </span>
            ) : (
              <span className="text-sm bg-accent-gold/10 text-accent-gold font-bold px-2.5 py-1 rounded border border-accent-gold/20">
                업로드 대기 중 ({job.autonomy} 모드)
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-navy-900/60 p-3 rounded-lg border border-navy-700 flex flex-col justify-between">
              <div>
                <h4 className="text-sm font-semibold text-gray-200 mb-2">AI 자동 생성 썸네일</h4>
                <div className="aspect-video bg-navy-950 rounded border border-navy-700 overflow-hidden relative">
                  <img
                    src={`/api/jobs/${id}/thumbnail/longform?t=${imageSalt}`}
                    alt="YouTube Thumbnail"
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=400&q=80";
                    }}
                  />
                </div>
              </div>
              <a
                href={`/api/jobs/${id}/thumbnail/longform`}
                target="_blank"
                rel="noreferrer"
                download
                className="mt-3 w-full bg-navy-700 border border-navy-600 text-center text-sm text-accent-cyan py-2 rounded hover:bg-navy-600 transition flex items-center justify-center gap-1"
              >
                <Download size={14}/> 썸네일 다운로드
              </a>
            </div>

            <div className="md:col-span-2 space-y-3">
              {youtubePackage?.longform ? (
                <>
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-navy-400">추천 제목 (3안)</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(youtubePackage.longform.titles?.join('\n') || '');
                          alert('추천 제목 3안이 복사되었습니다.');
                        }}
                        className="text-sm text-accent-cyan hover:underline flex items-center gap-0.5"
                      >
                        <Copy size={12}/> 전체 복사
                      </button>
                    </div>
                    <div className="bg-navy-950 p-3 rounded border border-navy-700 space-y-2 mt-1.5">
                      {youtubePackage.longform.titles?.map((t, idx) => (
                        <div key={idx} className="flex items-start gap-1.5 text-sm text-gray-200">
                          <span className="text-accent-cyan font-bold">안{idx+1}.</span>
                          <span className="flex-1 select-all">{t}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-navy-400">더보기 상세 설명글 (Description)</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(youtubePackage.longform.description || '');
                          alert('더보기 글이 복사되었습니다.');
                        }}
                        className="text-sm text-accent-cyan hover:underline flex items-center gap-0.5"
                      >
                        <Copy size={12}/> 복사
                      </button>
                    </div>
                    <textarea
                      readOnly
                      value={youtubePackage.longform.description || ''}
                      className="w-full bg-navy-950 border border-navy-700 rounded p-3 text-sm text-gray-200 mt-1.5 h-20 focus:outline-none resize-none font-mono"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-navy-400 font-mono">태그 / 해시태그</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(youtubePackage.longform.tags?.join(', ') || '');
                          alert('해시태그가 복사되었습니다.');
                        }}
                        className="text-sm text-accent-cyan hover:underline flex items-center gap-0.5"
                      >
                        <Copy size={12}/> 복사
                      </button>
                    </div>
                    <div className="bg-navy-950 p-3 rounded border border-navy-700 mt-1.5 text-sm text-accent-cyan flex flex-wrap gap-1.5">
                      {youtubePackage.longform.tags?.map((tag, idx) => (
                        <span key={idx} className="bg-navy-800 px-2 py-1 rounded border border-navy-700">#{tag}</span>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-sm text-navy-400 h-full flex items-center justify-center">
                  <Loader size={14} className="animate-spin mr-1.5"/> 유튜브 메타데이터 생성 중...
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-navy-700 pt-3 flex items-center justify-between">
            <div>
              {job.youtubeUrl && (
                <a
                  href={job.youtubeUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-accent-cyan hover:underline flex items-center gap-1"
                >
                  <ExternalLink size={14}/> YouTube 업로드 동영상 링크 열기
                </a>
              )}
            </div>

            <div className="flex gap-2">
              {job.status === 'READY' && (
                <button
                  onClick={() => {
                    if (job.autonomy === 'GUIDED') {
                      setIsGuidedConfirmOpen(true);
                    } else {
                      if (confirm("유튜브 채널로 즉시 업로드(시뮬레이션)하시겠습니까?")) {
                        publishMut.mutate();
                      }
                    }
                  }}
                  disabled={publishMut.isPending}
                  className="flex items-center gap-1.5 bg-red-600 text-white font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-red-500 disabled:opacity-50 transition"
                >
                  {publishMut.isPending ? <Loader size={14} className="animate-spin"/> : <Youtube size={14}/>}
                  {job.autonomy === 'GUIDED' ? '업로드 검토 및 발행' : '즉시 YouTube 업로드'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {isGuidedConfirmOpen && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-navy-900 border border-navy-700 rounded-xl p-6 max-w-xl w-full space-y-4">
            <h3 className="text-base font-bold text-accent-cyan flex items-center gap-1.5 border-b border-navy-800 pb-3">
              <Youtube size={18}/> YouTube 업로드 검토 (GUIDED 게이트)
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-sm text-navy-400">제목 선택</label>
                <div className="space-y-1.5 mt-1.5">
                  {youtubePackage?.longform?.titles?.map((t, idx) => (
                    <label key={idx} className="flex items-start gap-2 bg-navy-950 p-2.5 rounded border border-navy-800 hover:border-navy-700 cursor-pointer text-sm text-gray-200">
                      <input
                        type="radio"
                        name="selected_title"
                        defaultChecked={idx === 0}
                        className="mt-0.5 accent-accent-cyan"
                      />
                      <span>{t}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm text-navy-400">더보기 상세 설명글</label>
                <textarea
                  readOnly
                  value={youtubePackage?.longform?.description || ''}
                  className="w-full bg-navy-950 border border-navy-800 rounded p-2.5 text-sm text-gray-200 mt-1.5 h-24 focus:outline-none resize-none font-mono"
                />
              </div>

              <div>
                <label className="text-sm text-navy-400">추천 해시태그</label>
                <div className="bg-navy-950 p-2.5 rounded border border-navy-800 mt-1.5 text-sm text-accent-cyan flex flex-wrap gap-1.5">
                  {youtubePackage?.longform?.tags?.map((tag, idx) => (
                    <span key={idx} className="bg-navy-900 px-2 py-1 rounded border border-navy-800">#{tag}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-navy-800 pt-3">
              <button
                onClick={() => setIsGuidedConfirmOpen(false)}
                className="bg-navy-700 hover:bg-navy-600 text-sm px-4 py-2 rounded text-navy-400 transition"
              >
                닫기
              </button>
              <button
                onClick={() => {
                  setIsGuidedConfirmOpen(false);
                  publishMut.mutate();
                }}
                className="bg-red-600 hover:bg-red-500 text-sm px-5 py-2 rounded text-white font-semibold transition"
              >
                검토 승인 및 업로드
              </button>
            </div>
          </div>
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
              <div key={step.key} className={`bg-navy-800 rounded-xl border transition shadow-card ${ss === 'active' ? 'border-accent-cyan' : 'border-navy-700'}`}>
                <div className="flex items-center justify-between px-5 py-4">
                  <div className="flex items-center gap-3">
                    <StepIcon status={ss} idx={idx+1}/>
                    <div>
                      <div className="font-semibold text-base">{step.label}</div>
                      {approval && <div className="text-sm text-navy-400 mt-0.5">{approval.result === 'AUTO_APPROVED' ? '⚡ 자동 승인' : `✓ ${approval.approvedBy}`}</div>}
                      {ss === 'active' && isAuto && <div className="text-sm text-accent-cyan mt-0.5 flex items-center gap-1"><Loader size={12} className="animate-spin"/>자동 진행 중</div>}
                      {ss === 'active' && !isAuto && <div className="text-sm text-accent-gold mt-0.5">승인 대기 중</div>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {showRun && (
                      <button onClick={() => handleRun(step)} disabled={!!runningStep}
                        className="flex items-center gap-1.5 bg-accent-cyan text-navy-950 text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition">
                        {runningStep === step.key ? <Loader size={14} className="animate-spin"/> : <Zap size={14}/>}실행
                      </button>
                    )}
                    {(showManualApprove || showGuidedApprove) && (
                      <button onClick={() => setGateModal({ gate: step.gate, step })}
                        className="text-sm bg-accent-gold/20 text-accent-gold border border-accent-gold/30 px-4 py-2 rounded-lg hover:bg-accent-gold/30 transition">검토 / 승인</button>
                    )}
                    {ss === 'active' && isAuto && <Loader size={16} className="animate-spin text-accent-cyan"/>}
                  </div>
                </div>

                {ss === 'active' && (
                  <div className="mx-5 mb-4 p-4 bg-navy-900/50 rounded-lg border border-navy-700/60 text-sm space-y-2.5">
                    <div className="flex items-center justify-between text-gray-200 font-semibold">
                      <div className="flex items-center gap-1.5">
                        <Clock size={14} className="text-accent-cyan"/>
                        <span>예상 대기 시간:</span>
                        <span className="text-accent-cyan">{STEP_PROGRESS_INFO[step.key]?.est}</span>
                      </div>
                      {step.key === 'script' && (
                        <div className="text-navy-400">
                          목표 분량: <span className="text-accent-cyan">{job.longformTargetMinutes || 20}분</span>
                          (약 <span className="text-accent-cyan">{(job.longformTargetMinutes || 20) * 300}자</span> 생성)
                        </div>
                      )}
                    </div>
                    <div className="text-navy-400 leading-relaxed text-sm">
                      {STEP_PROGRESS_INFO[step.key]?.desc}
                    </div>
                    {isAuto && (
                      <div className="pt-2.5 border-t border-navy-700/40 flex items-center gap-2 text-accent-cyan text-sm">
                        <Loader size={12} className="animate-spin"/>
                        <span>자동 모드가 실행 중입니다. 브라우저 창을 켜둔 채 잠시만 기다려 주세요.</span>
                      </div>
                    )}
                  </div>
                )}

                {step.key === 'keyword' && kwCandidates.length > 0 && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <p className="text-sm text-navy-400 mt-3 mb-2">후보 {kwCandidates.length}개</p>
                    <div className="space-y-1.5">
                      {kwCandidates.map((c, i) => (
                        <div key={i} className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg ${c.is_outperformer ? 'bg-accent-gold/10 border border-accent-gold/20' : 'bg-navy-700/50'}`}>
                          <div className="flex items-center gap-2">
                            {c.is_outperformer && <Star size={13} className="text-accent-gold fill-accent-gold"/>}
                            <span className="text-sm">{c.keyword}</span>
                          </div>
                          <div className="text-sm text-navy-400 flex gap-3">
                            <span>×{c.outperformance_index?.toFixed(1)}</span>
                            <span>{c.velocity_vph?.toFixed(0)}vph</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    {job.keyword && <div className="mt-2 text-sm text-navy-400">✓ 확정: <span className="text-accent-cyan">{job.keyword}</span></div>}
                  </div>
                )}

                {step.key === 'script' && scriptData && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex flex-wrap items-center justify-between gap-3 mt-3 mb-3 border-b border-navy-700/50 pb-3">
                      <div className="flex items-center gap-2">
                        <FileText size={15} className="text-accent-cyan"/>
                        <span className="text-sm text-navy-400">
                          {scriptData.char_count?.toLocaleString()}자
                          {scriptData.used_real_llm === false && (
                            <span className="ml-2 text-accent-gold">⚠ Mock 스크립트</span>
                          )}
                          {scriptData.used_real_llm === true && (
                            <span className="ml-2 text-accent-green">✓ LLM 생성</span>
                          )}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        <div className="flex bg-navy-700 rounded p-1 text-xs">
                          <button onClick={() => setScriptViewMode('paragraphs')}
                            className={`px-2.5 py-1 rounded transition ${scriptViewMode === 'paragraphs' ? 'bg-accent-cyan text-navy-950 font-bold' : 'text-navy-400 hover:text-white'}`}>단락 가독성</button>
                          {sortedImageList.length > 0 && (
                            <button onClick={() => setScriptViewMode('mixed')}
                              className={`px-2.5 py-1 rounded transition ${scriptViewMode === 'mixed' ? 'bg-accent-cyan text-navy-950 font-bold' : 'text-navy-400 hover:text-white'}`}>대본 + 이미지</button>
                          )}
                          <button onClick={() => setScriptViewMode('raw')}
                            className={`px-2.5 py-1 rounded transition ${scriptViewMode === 'raw' ? 'bg-accent-cyan text-navy-950 font-bold' : 'text-navy-400 hover:text-white'}`}>기본 텍스트</button>
                        </div>

                        <div className="flex gap-1">
                          <button onClick={() => {
                            const txt = scriptData.script || '';
                            const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `script_${id}.txt`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }} className="bg-navy-700 text-gray-200 hover:text-white text-xs px-2.5 py-1.5 rounded border border-navy-600 transition">TXT</button>

                          <button onClick={() => {
                            const txt = scriptData.script || '';
                            const cleanParas = txt.split(/\r?\n+/).map(p => p.trim()).filter(Boolean);

                            const bodyContent = sortedImageList.length > 0 ? `
                              <h2>주식 자동화 영상 스토리보드 대본 (Job #${id})</h2>
                              <div class="meta">
                                <p style="margin-bottom: 4pt;"><strong>영상 주제:</strong> ${job.title}</p>
                                <p style="margin-bottom: 0pt;"><strong>선택 키워드:</strong> ${job.keyword || ''}</p>
                              </div>
                              <hr style="margin-bottom: 20pt; border: none; border-top: 1px solid #dddddd;"/>
                              ${sortedImageList.map(img => `
                                <div style="margin-bottom: 20pt; page-break-inside: avoid;">
                                  <p style="font-family: Arial, sans-serif; font-size: 11pt; font-weight: bold; color: #0088cc; margin-bottom: 6pt;">[씬 #${img.index}] (${fmt(img.start)} ~ ${fmt(img.start + img.duration)})</p>
                                  <table cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse;">
                                    <tr>
                                      <td style="width: 240px; padding-right: 15px; vertical-align: top;">
                                        <img src="${window.location.origin}/api/files/download?path=${encodeURIComponent(img.image_path)}&token=${token}" width="240" height="135" style="border: 1px solid #dddddd; display: block;" />
                                      </td>
                                      <td style="vertical-align: top; font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.6; text-align: justify; color: #333333;">
                                        ${img.text || img.prompt || ''}
                                      </td>
                                    </tr>
                                  </table>
                                </div>
                              `).join('')}
                            ` : `
                              <h2>주식 자동화 영상 스크립트 (Job #${id})</h2>
                              <div class="meta">
                                <p style="margin-bottom: 4pt;"><strong>영상 주제:</strong> ${job.title}</p>
                                <p style="margin-bottom: 0pt;"><strong>선택 키워드:</strong> ${job.keyword || ''}</p>
                              </div>
                              <hr style="margin-bottom: 20pt; border: none; border-top: 1px solid #dddddd;"/>
                              ${cleanParas.map(p => `<p>${p}</p>`).join('')}
                            `;

                            const html = `
                              <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
                              <head>
                                <meta charset="utf-8">
                                <title>Script</title>
                                <style>
                                  body { padding: 40px; }
                                  h2 { font-family: 'Malgun Gothic', Arial, sans-serif; color: #0d1b2a; margin-bottom: 16pt; border-bottom: 2px solid #0d1b2a; padding-bottom: 6pt; }
                                  .meta { font-family: 'Malgun Gothic', Arial, sans-serif; font-size: 10pt; color: #555555; margin-bottom: 20pt; background: #f4f6f9; padding: 10pt; }
                                  p { font-family: 'Malgun Gothic', Arial, sans-serif; line-height: 1.6; font-size: 11pt; margin-top: 0pt; margin-bottom: 12pt; text-align: justify; }
                                </style>
                              </head>
                              <body>
                                ${bodyContent}
                              </body>
                              </html>
                            `;
                            const blob = new Blob([html], { type: 'application/msword;charset=utf-8' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `script_${id}.doc`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }} className="bg-navy-700 text-gray-200 hover:text-white text-xs px-2.5 py-1.5 rounded border border-navy-600 transition">Word</button>

                          <button onClick={() => {
                            const txt = scriptData.script || '';
                            const cleanParas = txt.split(/\r?\n+/).map(p => p.trim()).filter(Boolean);
                            const printWindow = window.open('', '_blank');

                            const bodyContent = sortedImageList.length > 0 ? `
                              <h2>주식 자동화 영상 스토리보드 대본</h2>
                              <div class="meta">
                                <div><strong>작업 ID:</strong> Job #${id}</div>
                                <div><strong>영상 주제:</strong> ${job.title}</div>
                                <div><strong>선택 키워드:</strong> ${job.keyword || ''}</div>
                              </div>
                              ${sortedImageList.map(img => `
                                <div class="scene-block" style="margin-bottom: 25px; page-break-inside: avoid; border-bottom: 1px solid #eeeeee; padding-bottom: 15px; display: flex; gap: 20px;">
                                  <div style="width: 240px; flex-shrink: 0;">
                                    <img src="${window.location.origin}/api/files/download?path=${encodeURIComponent(img.image_path)}&token=${token}" style="width: 240px; height: 135px; object-fit: cover; border: 1px solid #cccccc; border-radius: 4px;" />
                                  </div>
                                  <div style="flex: 1;">
                                    <div style="font-weight: bold; color: #0d1b2a; font-size: 13px; margin-bottom: 6px;">씬 #${img.index} (${fmt(img.start)} ~ ${fmt(img.start + img.duration)})</div>
                                    <p style="margin-top: 0; margin-bottom: 0; text-align: justify; font-size: 13px; line-height: 1.8;">
                                      ${img.text || img.prompt || ''}
                                    </p>
                                  </div>
                                </div>
                              `).join('')}
                            ` : `
                              <h2>주식 자동화 영상 스크립트</h2>
                              <div class="meta">
                                <div><strong>작업 ID:</strong> Job #${id}</div>
                                <div><strong>영상 주제:</strong> ${job.title}</div>
                                <div><strong>선택 키워드:</strong> ${job.keyword || ''}</div>
                              </div>
                              ${cleanParas.map(p => `<p>${p}</p>`).join('')}
                            `;

                            const htmlContent = `
                              <html>
                              <head>
                                <title>스크립트 인쇄 - Job #${id}</title>
                                <style>
                                  body { font-family: 'Malgun Gothic', 'Nanum Gothic', Arial, sans-serif; padding: 40px; line-height: 1.8; color: #333; }
                                  h2 { border-bottom: 2px solid #0d1b2a; padding-bottom: 10px; margin-bottom: 20px; color: #0d1b2a; }
                                  .meta { margin-bottom: 30px; font-size: 13px; color: #555; background: #f8f9fa; padding: 15px; border-left: 4px solid #00d4ff; }
                                  .meta div { margin-bottom: 6px; }
                                  p { margin-top: 0; margin-bottom: 16px; text-align: justify; font-size: 14px; text-justify: inter-word; }
                                </style>
                              </head>
                              <body>
                                ${bodyContent}
                                <script>window.onload = function() { window.print(); window.close(); }</script>
                              </body>
                              </html>
                            `;
                            printWindow.document.write(htmlContent);
                            printWindow.document.close();
                          }} className="bg-navy-700 text-gray-200 hover:text-white text-xs px-2.5 py-1.5 rounded border border-navy-600 transition flex items-center gap-1">
                            <Printer size={12}/>PDF 인쇄
                          </button>
                        </div>

                        {job.status === 'SCRIPT_PENDING' && (
                          <button onClick={() => {
                            if (isEditingScript) {
                              setIsEditingScript(false);
                            } else {
                              setEditedScriptText(scriptData.script || '');
                              setIsEditingScript(true);
                            }
                          }} className="flex items-center gap-1 text-xs bg-accent-gold/20 text-accent-gold border border-accent-gold/30 px-2.5 py-1.5 rounded hover:bg-accent-gold/30 transition">
                            <Edit size={12}/>{isEditingScript ? '편집 취소' : '스크립트 수정'}
                          </button>
                        )}

                        <button onClick={() => setExpandedScript(!expandedScript)}
                          className="text-sm text-accent-cyan flex items-center gap-1 hover:underline">
                          {expandedScript ? '접기' : '전체 보기'}
                          {expandedScript ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
                        </button>
                      </div>
                    </div>

                    {isEditingScript ? (
                      <div className="space-y-3">
                        <textarea
                          value={editedScriptText}
                          onChange={e => setEditedScriptText(e.target.value)}
                          className="w-full bg-navy-700 border border-navy-600 rounded-lg p-3.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan font-mono resize-y"
                          rows={12}
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setIsEditingScript(false)}
                            className="bg-navy-700 text-navy-400 hover:text-white text-sm px-4 py-2 rounded transition"
                          >
                            취소
                          </button>
                          <button
                            onClick={() => saveScriptMut.mutate(editedScriptText)}
                            disabled={saveScriptMut.isPending}
                            className="flex items-center gap-1.5 bg-accent-green text-navy-950 text-sm font-semibold px-4 py-2 rounded hover:opacity-90 disabled:opacity-50 transition"
                          >
                            <Save size={14}/>
                            {saveScriptMut.isPending ? '저장 중...' : '수정 저장 및 확정'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        {scriptViewMode === 'paragraphs' ? (
                          <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 bg-navy-900/30 rounded-lg p-4 border border-navy-700/50">
                            {(expandedScript ? (scriptData.script || '') : ((scriptData.script || '').slice(0, 400) + ((scriptData.script || '').length > 400 ? '...' : '')))
                              .split(/\n+/)
                              .filter(Boolean)
                              .map((para, idx) => (
                                <p key={idx} className="text-sm text-gray-200 leading-relaxed text-justify">
                                  {para}
                                </p>
                              ))}
                          </div>
                        ) : scriptViewMode === 'mixed' && sortedImageList.length > 0 ? (
                          <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 bg-navy-900/30 rounded-lg p-4 border border-navy-700/50">
                            {sortedImageList.map((img, idx) => (
                              <div key={img.index || idx} className="flex gap-4 border-b border-navy-800 pb-3 last:border-0 last:pb-0">
                                <div className="w-28 aspect-video bg-navy-700 rounded overflow-hidden border border-navy-600 flex-shrink-0">
                                  <img
                                    src={`/api/files/download?path=${encodeURIComponent(img.image_path)}&token=${token}&salt=${imageSalt}`}
                                    alt={`씬 ${img.index}`}
                                    className="w-full h-full object-cover"
                                    onError={e => { e.target.style.display = 'none' }}
                                  />
                                </div>
                                <div className="flex-1">
                                  <div className="text-xs font-bold text-accent-cyan mb-1 flex items-center gap-1.5">
                                    <span>씬 #{img.index}</span>
                                    <span className="text-navy-400 font-normal">
                                      {fmt(img.start)} ~ {fmt(img.start + img.duration)}
                                    </span>
                                  </div>
                                  <p className="text-sm text-gray-200 leading-relaxed text-justify">
                                    {img.text || img.prompt || '(내용 없음)'}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div>
                            {scriptData.sections && scriptData.sections.length > 0 ? (
                              <div className="space-y-2">
                                {scriptData.sections.map((sec, i) => (
                                  <div key={i} className="bg-navy-700/40 rounded-lg p-3.5">
                                    <div className="text-sm font-semibold text-accent-gold mb-1">{sec.title}</div>
                                    <p className="text-sm text-gray-200 leading-relaxed">
                                      {expandedScript ? sec.content : (sec.content?.slice(0, 80) + (sec.content?.length > 80 ? '...' : ''))}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            ) : scriptData.script ? (
                              <div className="bg-navy-700/40 rounded-lg p-3.5">
                                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">
                                  {expandedScript ? scriptData.script : (scriptData.script.slice(0, 300) + (scriptData.script.length > 300 ? '...' : ''))}
                                </p>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {step.key === 'tts' && ttsInfo && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex items-center gap-2 mt-3 mb-2.5">
                      <Music size={15} className="text-accent-cyan"/>
                      <span className="text-sm text-navy-400">
                        {ttsInfo.total_duration ? `${(ttsInfo.total_duration/60).toFixed(1)}분` : ''}
                        {ttsInfo.chunks && ` · ${ttsInfo.chunks.length}개 자막 청크`}
                        {ttsInfo.used_gtts === true && <span className="ml-2 text-accent-green">✓ gTTS 실제 음성</span>}
                      </span>
                    </div>
                    {ttsInfo.audio_path && (
                      <audio controls className="w-full h-9" style={{ filter: 'invert(0.9)' }}>
                        <source src={`/api/files/download?path=${encodeURIComponent(ttsInfo.audio_path)}&token=${token}`} type="audio/mpeg"/>
                      </audio>
                    )}
                  </div>
                )}

                {((step.key === 'images' || step.key === 'longform') && sortedImageList.length > 0) && (
                  <div className="px-5 pb-4 border-t border-navy-700">
                    <div className="flex items-center justify-between mt-3 mb-3">
                      <div className="flex items-center gap-2">
                        <ImageIcon size={15} className="text-accent-cyan"/>
                        <span className="text-sm text-navy-400">
                          {sortedImageList.length}개 씬 이미지 (AI 일러스트 기반)
                        </span>
                      </div>
                      {['IMAGES_PENDING', 'PREVIEW_PENDING', 'READY'].includes(job.status) && (
                        <span className="text-xs bg-accent-cyan/10 text-accent-cyan px-2.5 py-1 rounded-full font-semibold">
                          수정/재생성 활성화됨
                        </span>
                      )}
                    </div>

                    <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 bg-navy-900/30 rounded-lg p-3 border border-navy-700/50">
                      {sortedImageList.map((img, i) => {
                        const isEditingThis = editingSceneIndex === img.index;
                        const isRegeneratingThis = regenImageMut.isPending && editingSceneIndex === img.index;

                        return (
                          <div key={img.index || i} className="flex gap-4 bg-navy-800/40 border border-navy-700/60 rounded-lg p-3.5 hover:border-navy-600 transition">
                            <div className="w-40 aspect-video bg-navy-700 rounded overflow-hidden border border-navy-600 flex-shrink-0 relative">
                              <img
                                src={`/api/files/download?path=${encodeURIComponent(img.image_path)}&token=${token}&salt=${imageSalt}`}
                                alt={`씬 ${img.index}`}
                                className="w-full h-full object-cover"
                                onError={e => { e.target.style.display = 'none' }}
                              />
                            </div>

                            <div className="flex-1 flex flex-col justify-between">
                              <div>
                                <div className="flex items-center justify-between">
                                  <div className="text-xs font-semibold text-accent-cyan flex items-center gap-1.5">
                                    <span className="bg-accent-cyan/10 px-2 py-0.5 rounded font-bold">씬 #{img.index}</span>
                                    <span className="text-navy-400 font-normal flex items-center gap-0.5">
                                      <Clock size={12}/>
                                      {fmt(img.start)} ~ {fmt(img.start + img.duration)} ({img.duration?.toFixed(1)}초)
                                    </span>
                                  </div>
                                  <span className="text-xs bg-navy-700 text-navy-400 px-2 py-0.5 rounded border border-navy-600">
                                    구분: {img.section}
                                  </span>
                                </div>

                                <div className="mt-2.5">
                                  {isEditingThis ? (
                                    <textarea
                                      id={`scene-edit-${img.index}`}
                                      value={editingSceneText}
                                      onChange={e => setEditingSceneText(e.target.value)}
                                      className="w-full bg-navy-700 border border-navy-600 rounded p-2.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan resize-none"
                                      rows={2}
                                    />
                                  ) : (
                                    <p className="text-sm text-gray-200 leading-relaxed text-justify line-clamp-3">
                                      {img.text || img.prompt || '(내용 없음)'}
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div className="flex justify-end gap-2 mt-2.5">
                                {isEditingThis ? (
                                  <>
                                    <button
                                      onClick={() => {
                                        const ta = document.getElementById(`scene-edit-${img.index}`);
                                        if (!ta) return;
                                        const pos = ta.selectionStart;
                                        const val = ta.value;
                                        if (pos <= 0 || pos >= val.length) {
                                          alert("텍스트 입력창에서 분할할 커서 위치를 클릭한 뒤 눌러주세요.");
                                          return;
                                        }
                                        const p1 = val.substring(0, pos).trim();
                                        const p2 = val.substring(pos).trim();
                                        if (!p1 || !p2) {
                                          alert("커서 앞뒤로 텍스트가 존재해야 분할이 가능합니다.");
                                          return;
                                        }
                                        if (confirm("이 위치에서 씬을 두 개로 분할하시겠습니까?")) {
                                          splitSceneMut.mutate({ index: img.index, part1: p1, part2: p2 });
                                        }
                                      }}
                                      disabled={isRegeneratingThis || splitSceneMut.isPending}
                                      className="flex items-center gap-1 bg-red-500 text-white text-xs font-semibold px-2.5 py-1.5 rounded hover:opacity-90 disabled:opacity-50 transition"
                                      title="커서가 있는 위치를 기준으로 씬을 2개로 분할합니다."
                                    >
                                      {splitSceneMut.isPending ? <Loader size={12} className="animate-spin"/> : <Scissors size={12}/>}
                                      씬 분할
                                    </button>
                                    <button
                                      onClick={() => setEditingSceneIndex(null)}
                                      disabled={isRegeneratingThis || splitSceneMut.isPending}
                                      className="bg-navy-700 text-navy-400 hover:text-white text-xs px-3 py-1.5 rounded transition"
                                    >
                                      취소
                                    </button>
                                    <button
                                      onClick={() => regenImageMut.mutate({
                                        index: img.index,
                                        text: img.text || img.prompt || '',
                                        section: img.section,
                                        mode: 'image'
                                      })}
                                      disabled={isRegeneratingThis || splitSceneMut.isPending}
                                      className="flex items-center gap-1 bg-accent-cyan text-navy-950 text-xs font-semibold px-2.5 py-1.5 rounded hover:opacity-90 disabled:opacity-50 transition"
                                      title="대사를 유지한 채 캐릭터 이미지만 다시 생성합니다."
                                    >
                                      {isRegeneratingThis ? <Loader size={12} className="animate-spin"/> : <Save size={12}/>}
                                      이미지만 수정
                                    </button>
                                    <button
                                      onClick={() => regenImageMut.mutate({
                                        index: img.index,
                                        text: editingSceneText,
                                        section: img.section,
                                        mode: 'text'
                                      })}
                                      disabled={isRegeneratingThis}
                                      className="flex items-center gap-1 bg-accent-gold text-navy-950 text-xs font-semibold px-2.5 py-1.5 rounded hover:opacity-90 disabled:opacity-50 transition"
                                      title="이미지는 유지하고 자막/대사 텍스트만 업데이트합니다. (동영상 재조립 시 음성도 자동 반영됩니다.)"
                                    >
                                      {isRegeneratingThis ? <Loader size={12} className="animate-spin"/> : <Save size={12}/>}
                                      텍스트만 수정
                                    </button>
                                    <button
                                      onClick={() => regenImageMut.mutate({
                                        index: img.index,
                                        text: editingSceneText,
                                        section: img.section,
                                        mode: 'both'
                                      })}
                                      disabled={isRegeneratingThis}
                                      className="flex items-center gap-1 bg-accent-green text-navy-950 text-xs font-semibold px-2.5 py-1.5 rounded hover:opacity-90 disabled:opacity-50 transition"
                                      title="대사 텍스트를 수정하고 이미지도 새로 생성합니다."
                                    >
                                      {isRegeneratingThis ? <Loader size={12} className="animate-spin"/> : <Save size={12}/>}
                                      텍스트+이미지 수정
                                    </button>
                                  </>
                                ) : (
                                  ['IMAGES_PENDING', 'PREVIEW_PENDING', 'READY'].includes(job.status) && (
                                    <button
                                      onClick={() => {
                                        setEditingSceneIndex(img.index);
                                        setEditingSceneText(img.text || img.prompt || '');
                                      }}
                                      className="flex items-center gap-1 text-xs bg-navy-700 text-gray-200 hover:text-white border border-navy-600 px-2.5 py-1.5 rounded transition"
                                    >
                                      <Edit size={12}/>
                                      텍스트 수정 / 재생성
                                    </button>
                                  )
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

        </div>

        <div className="space-y-4">
          <div className="bg-navy-800 rounded-xl border border-navy-700 p-5 shadow-card">
            <h3 className="text-base font-semibold mb-3">작업 정보</h3>
            <div className="space-y-3 text-sm">
              <InfoRow label="상태" value={<StatusBadge status={job.status} small/>}/>
              <InfoRow label="카테고리" value={job.category}/>
              <InfoRow label="목표 길이" value={`${job.longformTargetMinutes}분`}/>
              <InfoRow label="자율성" value={<span className={`text-sm px-2.5 py-1 rounded-full border ${AUTONOMY_STYLE[job.autonomy]}`}>{job.autonomy}</span>}/>
              {job.keyword && <InfoRow label="확정 키워드" value={<span className="text-accent-cyan text-sm">{job.keyword}</span>}/>}
            </div>
          </div>

          {costs && (
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-5 shadow-card">
              <h3 className="text-base font-semibold mb-3">비용 상세</h3>
              <div className="space-y-2.5 text-sm mb-3">
                <InfoRow label="누적" value={`$${parseFloat(costs.currentTotal||0).toFixed(2)}`}/>
                <InfoRow label="예산" value={costs.budgetCap ? `$${costs.budgetCap}` : '무제한'}/>
              </div>
              {costs.budgetCap && (
                <div className="mb-3">
                  <div className="h-2 bg-navy-700 rounded-full overflow-hidden">
                    <div className="h-full bg-accent-cyan rounded-full transition-all" style={{width:`${Math.min(100,(costs.currentTotal/costs.budgetCap)*100)}%`}}/>
                  </div>
                </div>
              )}
              {costs.items && costs.items.length > 0 && (
                <div className="space-y-2 pt-2.5 border-t border-navy-700">
                  {costs.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-navy-400">{item.provider}</span>
                      <span className="text-gray-200">${parseFloat(item.amount||0).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {approvals.length > 0 && (
            <div className="bg-navy-800 rounded-xl border border-navy-700 p-5 shadow-card">
              <h3 className="text-base font-semibold mb-3">게이트 이력</h3>
              <div className="space-y-2.5">
                {approvals.map((a,i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-navy-400">{a.gate}</span>
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
  if (status==='done') return <CheckCircle className="text-accent-green flex-shrink-0" size={22}/>
  if (status==='active') return <Loader className="text-accent-cyan animate-spin flex-shrink-0" size={22}/>
  return <div className="w-6 h-6 rounded-full border border-navy-600 flex items-center justify-center text-sm text-navy-400 flex-shrink-0">{idx}</div>
}

function StatusBadge({status,small}) {
  const M={
    READY:{l:'완료',c:'bg-accent-green/20 text-accent-green'},
    PUBLISHED:{l:'업로드됨',c:'bg-accent-green/20 text-accent-green'},
    ASSEMBLING:{l:'조립중',c:'bg-accent-cyan/20 text-accent-cyan'},
    FAILED:{l:'오류',c:'bg-accent-red/20 text-accent-red'},
    BUDGET_BLOCKED:{l:'예산초과',c:'bg-accent-red/20 text-accent-red'},
    DRAFT:{l:'초안',c:'bg-navy-700 text-navy-400'},
    KEYWORD_PENDING:{l:'키워드',c:'bg-accent-cyan/10 text-accent-cyan'},
    SCRIPT_PENDING:{l:'스크립트',c:'bg-accent-cyan/10 text-accent-cyan'},
    TTS_PENDING:{l:'TTS',c:'bg-accent-cyan/10 text-accent-cyan'},
    IMAGES_PENDING:{l:'이미지',c:'bg-accent-cyan/10 text-accent-cyan'},
    PREVIEW_PENDING:{l:'미리보기 대기',c:'bg-accent-gold/20 text-accent-gold'},
  }
  const c=M[status]||{l:status,c:'bg-navy-700 text-navy-400'}
  return <span className={`${small?'text-sm px-3 py-1':'text-base px-4 py-1.5'} rounded-full font-medium ${c.c}`}>{c.l}</span>
}

function InfoRow({label,value}) {
  return <div className="flex items-center justify-between gap-2"><span className="text-navy-400 flex-shrink-0">{label}</span><span className="font-medium text-right">{value}</span></div>
}

function GateModal({gate,step,onApprove,onReject,onClose,loading}) {
  const [comment,setComment]=useState('')
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-navy-800 rounded-xl p-6 w-full max-w-sm border border-navy-700 shadow-2xl">
        <h3 className="font-bold text-base mb-2">{step.label} 검토</h3>
        <p className="text-sm text-navy-400 mb-4">결과를 확인하고 승인 또는 거부하세요.</p>
        <textarea value={comment} onChange={e=>setComment(e.target.value)} placeholder="코멘트 (선택사항)" rows={3}
          className="w-full bg-navy-700 border border-navy-700 rounded-lg px-3.5 py-2.5 text-sm text-white mb-4 focus:outline-none focus:ring-1 focus:ring-accent-cyan resize-none"/>
        <div className="flex gap-3">
          <button onClick={()=>onReject(comment)} disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-accent-red/20 text-accent-red border border-accent-red/30 rounded-lg py-2.5 text-sm hover:bg-accent-red/30 disabled:opacity-50 transition">
            <ThumbsDown size={15}/>거부
          </button>
          <button onClick={()=>onApprove(comment)} disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-accent-green/20 text-accent-green border border-accent-green/30 rounded-lg py-2.5 text-sm hover:bg-accent-green/30 disabled:opacity-50 transition">
            <ThumbsUp size={15}/>승인
          </button>
        </div>
        <button onClick={onClose} className="w-full mt-2 text-navy-400 text-sm hover:text-gray-200 transition">닫기</button>
      </div>
    </div>
  )
}
