import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Shield, DollarSign, Video, Settings, Save, ImagePlus, RefreshCw } from 'lucide-react'
import Layout from '../components/Layout'
import JobFilterBar from '../components/JobFilterBar'
import Pagination from '../components/Pagination'
import StatusBadge from '../components/StatusBadge'
import apiClient from '../api/client'
import { formatAutonomy, formatCategory, isCompleted } from '../constants/jobStatus'

export default function Admin() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState('jobs')
  const [adminFilter, setAdminFilter] = useState('ALL')
  const [currentPage, setCurrentPage] = useState(1)

  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('ALL')
  const [selectedMode, setSelectedMode] = useState('ALL')
  const [selectedStatus, setSelectedStatus] = useState('ALL')

  const [editedVoices, setEditedVoices] = useState({})
  const [channelPreviewText, setChannelPreviewText] = useState({})
  const [channelPreviewUrls, setChannelPreviewUrls] = useState({})
  const [channelPreviewLoading, setChannelPreviewLoading] = useState({})
  const [characterDescriptions, setCharacterDescriptions] = useState({})
  const [characterKeys, setCharacterKeys] = useState({})
  const [newChannel, setNewChannel] = useState({ channelId: '', channelName: '', characterKey: '', characterStylePrompt: '', referenceStyleProfile: 'black_han_sans_v1', voiceId: '' })

  const { data: jobs = [] } = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: () => apiClient.get('/jobs').then(r => r.data),
  })

  const { data: channels = [], error: channelsError, refetch: refetchChannels } = useQuery({
    queryKey: ['admin-channels'],
    queryFn: () => apiClient.get('/channels').then(r => r.data),
  })

  const { data: voices = [], error: voicesError } = useQuery({
    queryKey: ['voices'],
    queryFn: () => apiClient.get('/channels/voices').then(r => r.data),
    staleTime: Infinity,
  })

  const { data: integrations = {} } = useQuery({
    queryKey: ['integration-status'],
    queryFn: () => apiClient.get('/integrations/status').then(r => r.data),
    retry: false,
  })

  const { data: characterLibraries = {} } = useQuery({
    queryKey: ['character-libraries', channels.map(c => c.channelId)],
    queryFn: async () => {
      const entries = await Promise.all(channels.map(async channel => {
        try {
          const response = await apiClient.get(`/channels/${channel.channelId}/character-library`)
          return [channel.channelId, response.data]
        } catch (_) {
          return [channel.channelId, { exists: false, poses: [], poseCount: 0 }]
        }
      }))
      return Object.fromEntries(entries)
    },
    enabled: channels.length > 0,
  })

  const saveChannelMutation = useMutation({
    mutationFn: (profile) => apiClient.post('/channels', profile).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['admin-channels'])
      alert('채널 프로필 설정이 성공적으로 저장되었습니다!')
    },
    onError: (err) => {
      alert('채널 설정 저장 실패: ' + (err.response?.data?.message || err.message))
    }
  })

  const createChannelMutation = useMutation({
    mutationFn: () => apiClient.post('/channels', newChannel).then(r => r.data),
    onSuccess: () => {
      setNewChannel({ channelId: '', channelName: '', characterKey: '', characterStylePrompt: '', referenceStyleProfile: 'black_han_sans_v1', voiceId: '' })
      qc.invalidateQueries({ queryKey: ['admin-channels'] })
    },
    onError: (err) => alert('채널 생성 실패: ' + (err.response?.data?.message || err.message)),
  })

  const characterLibraryMutation = useMutation({
    mutationFn: ({ channelId, characterDescription, regenerate }) =>
      apiClient.post(`/channels/${channelId}/character-library`, {
        characterDescription,
        regenerate,
      }).then(r => r.data),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['character-libraries'] })
      qc.invalidateQueries({ queryKey: ['admin-channels'] })
      refetchChannels()
      alert(variables.regenerate ? '캐릭터 포즈를 전체 재생성했습니다.' : '없는 캐릭터 포즈를 생성하고 채널에 연결했습니다.')
    },
    onError: (err) => {
      alert('캐릭터 포즈 생성 실패: ' + (err.response?.data?.message || err.message))
    },
  })

  const previewChannelVoice = async (channelId, voiceId) => {
    const text = (channelPreviewText[channelId] || '오늘 시장의 핵심 숫자와 외국인 수급의 방향을 차분하게 확인해보겠습니다.').trim()
    if (!voiceId || !text || text.length > 100) return
    setChannelPreviewLoading(prev => ({ ...prev, [channelId]: true }))
    try {
      const response = await apiClient.post('/channels/voices/preview', { voiceId, text }, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      setChannelPreviewUrls(prev => {
        if (prev[channelId]) URL.revokeObjectURL(prev[channelId])
        return { ...prev, [channelId]: url }
      })
    } catch (error) {
      alert('음성 미리듣기 생성에 실패했습니다. ElevenLabs 연결 상태를 확인하세요.')
    } finally {
      setChannelPreviewLoading(prev => ({ ...prev, [channelId]: false }))
    }
  }

  const totalCost = jobs.reduce((sum, j) => sum + (parseFloat(j.costAccumulated) || 0), 0)
  const completedJobs = jobs.filter(j => isCompleted(j.status))

  const handleFilterChange = (filter) => {
    setAdminFilter(filter)
    setCurrentPage(1)
  }

  const sortedJobs = [...jobs].sort((a, b) => b.id - a.id)

  const filteredJobs = sortedJobs.filter(job => {
    if (adminFilter === 'COMPLETED' && !isCompleted(job.status)) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      const titleMatch = job.title?.toLowerCase().includes(q)
      const creatorMatch = job.createdBy?.toLowerCase().includes(q)
      if (!titleMatch && !creatorMatch) return false
    }
    if (selectedCategory !== 'ALL' && job.category !== selectedCategory) return false
    if (selectedMode !== 'ALL' && job.autonomy !== selectedMode) return false
    if (selectedStatus !== 'ALL' && job.status !== selectedStatus) return false
    return true
  })

  const handleResetFilters = () => {
    setSearchQuery('')
    setSelectedCategory('ALL')
    setSelectedMode('ALL')
    setSelectedStatus('ALL')
    setCurrentPage(1)
  }

  const pageItems = filteredJobs.slice((currentPage - 1) * 10, currentPage * 10)
  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / 10))
  useEffect(() => { if (currentPage > totalPages) setCurrentPage(totalPages) }, [currentPage, totalPages])

  return (
    <Layout>
      <div className="flex items-center gap-3 mb-6">
        <Shield className="text-accent-gold" size={24} />
        <div>
          <h1 className="text-2xl font-bold">관리자</h1>
          <p className="text-gray-400 text-sm mt-0.5">시스템 현황 및 통계</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <button
          onClick={() => handleFilterChange('ALL')}
          className={`text-left bg-navy-800 rounded-xl p-5 border transition hover:bg-navy-700/40 cursor-pointer ${
            adminFilter === 'ALL' ? 'border-accent-cyan shadow-sm shadow-accent-cyan/10' : 'border-navy-700'
          }`}
        >
          <Video className="text-accent-cyan mb-3" size={20} />
          <div className="text-2xl font-bold">{jobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">전체 작업</div>
        </button>
        <button
          onClick={() => handleFilterChange('COMPLETED')}
          className={`text-left bg-navy-800 rounded-xl p-5 border transition hover:bg-navy-700/40 cursor-pointer ${
            adminFilter === 'COMPLETED' ? 'border-accent-green shadow-sm shadow-accent-green/10' : 'border-navy-700'
          }`}
        >
          <Video className="text-accent-green mb-3" size={20} />
          <div className="text-2xl font-bold">{completedJobs.length}</div>
          <div className="text-sm text-gray-400 mt-1">완료된 영상</div>
        </button>
        <div className="bg-navy-800 rounded-xl border border-navy-700 p-5">
          <DollarSign className="text-accent-gold mb-3" size={20} />
          <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
          <div className="text-sm text-gray-400 mt-1">총 누적 비용</div>
        </div>
      </div>

      <div className="mb-6 bg-navy-800 border border-navy-700 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3"><div><h2 className="font-semibold text-white">외부 API 연결 상태</h2><p className="text-[11px] text-gray-500 mt-1">키가 없으면 키워드 후보는 제한되며, 화면의 ‘unavailable’ 값은 추정하지 않고 그대로 표시합니다.</p></div><span className="text-[11px] text-gray-500">현재 서버 환경 기준</span></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <ProviderBadge label="YouTube Data API v3" configured={integrations.youtube?.configured} />
          <ProviderBadge label="ElevenLabs" configured={integrations.elevenlabs?.configured} />
          <ProviderBadge label="Anthropic Claude" configured={integrations.anthropic?.configured} />
        </div>
        {integrations.youtube && !integrations.youtube.configured && <div className="mt-4 bg-navy-900/70 rounded-lg p-3 text-[11px] text-gray-400 leading-relaxed">YouTube 키 설정: Google Cloud Console → 프로젝트 생성 → <b>YouTube Data API v3</b> 활성화 → 사용자 인증 정보에서 API 키 생성 → 프로젝트 루트 `.env`의 `YOUTUBE_API_KEY=발급키`에 입력 후 `docker compose up -d --build fastapi-workers spring-app` 실행. 키는 브라우저에 노출하지 않고 FastAPI 서버에서만 사용합니다.</div>}
      </div>

      <div className="flex gap-4 mb-6 border-b border-navy-700 pb-px">
        <button
          onClick={() => setActiveTab('jobs')}
          className={`pb-3 font-semibold text-sm transition relative ${
            activeTab === 'jobs' ? 'text-accent-cyan border-b-2 border-accent-cyan' : 'text-gray-400 hover:text-white'
          }`}
        >
          작업 목록
        </button>
        <button
          onClick={() => setActiveTab('channels')}
          className={`pb-3 font-semibold text-sm transition relative ${
            activeTab === 'channels' ? 'text-accent-cyan border-b-2 border-accent-cyan' : 'text-gray-400 hover:text-white'
          }`}
        >
          채널 프로필 관리
        </button>
        <button
          onClick={() => setActiveTab('people')}
          className={`pb-3 font-semibold text-sm transition relative ${
            activeTab === 'people' ? 'text-accent-cyan border-b-2 border-accent-cyan' : 'text-gray-400 hover:text-white'
          }`}
        >
          실사 인물 에셋
        </button>
      </div>

      {activeTab === 'jobs' ? (
        <>
          <div className="mb-6">
            <JobFilterBar
              searchQuery={searchQuery}
              onSearchChange={v => { setSearchQuery(v); setCurrentPage(1) }}
              category={selectedCategory}
              onCategoryChange={v => { setSelectedCategory(v); setCurrentPage(1) }}
              mode={selectedMode}
              onModeChange={v => { setSelectedMode(v); setCurrentPage(1) }}
              status={selectedStatus}
              onStatusChange={v => { setSelectedStatus(v); setCurrentPage(1) }}
              showAuthorSearch
              onReset={handleResetFilters}
            />
          </div>

          <div className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-navy-700 flex items-center justify-between">
              <h2 className="font-semibold text-sm">전체 작업 목록 ({filteredJobs.length}개)</h2>
              {adminFilter !== 'ALL' && (
                <span className="text-[10px] bg-accent-green/10 text-accent-green px-2 py-0.5 rounded-full font-bold">
                  완료 필터 적용 중
                </span>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm table-fixed min-w-[950px]">
                <thead>
                  <tr className="border-b border-navy-700 bg-navy-900/10">
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[8%]">ID</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[32%]">제목</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[15%]">카테고리</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[10%]">모드</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[12%]">상태</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[10%]">비용</th>
                    <th className="text-left px-6 py-3 text-gray-400 font-medium w-[13%]">작성자</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-700">
                  {filteredJobs.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="text-center py-12 text-gray-500">
                        검색 조건에 부합하는 작업이 없습니다.
                      </td>
                    </tr>
                  ) : (
                    pageItems.map(job => (
                      <tr
                        key={job.id}
                        onClick={() => navigate(`/longform/${job.id}`)}
                        className="hover:bg-navy-700/50 transition cursor-pointer"
                      >
                        <td className="px-6 py-3.5 text-gray-400">#{job.id}</td>
                        <td className="px-6 py-3.5 font-medium text-white truncate max-w-[280px]" title={job.title}>
                          {job.title}
                        </td>
                        <td className="px-6 py-3.5 text-gray-400">{formatCategory(job.category)}</td>
                        <td className="px-6 py-3.5 text-gray-400">{formatAutonomy(job.autonomy)}</td>
                        <td className="px-6 py-3.5">
                          <StatusBadge status={job.status} small />
                        </td>
                        <td className="px-6 py-3.5 text-gray-400">${parseFloat(job.costAccumulated || 0).toFixed(2)}</td>
                        <td className="px-6 py-3.5 text-gray-400 truncate max-w-[120px]" title={job.createdBy}>
                          {job.createdBy}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <Pagination total={filteredJobs.length} currentPage={currentPage} onChange={setCurrentPage} />
          </div>
        </>
      ) : activeTab === 'channels' ? (
        <div className="space-y-4">
          <div className="bg-navy-800 border border-accent-cyan/30 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div><h2 className="font-semibold text-white">채널 프로필 추가</h2><p className="text-[11px] text-gray-500 mt-1">채널별 고정 캐릭터와 기본 음성을 지정하면 이후 작업이 자동으로 상속합니다.</p></div>
              <button onClick={() => createChannelMutation.mutate()} disabled={!newChannel.channelId.trim() || !newChannel.channelName.trim() || createChannelMutation.isPending} className="bg-accent-cyan text-navy-950 rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">{createChannelMutation.isPending ? '저장 중…' : '채널 추가'}</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
              <input value={newChannel.channelId} onChange={e => setNewChannel({ ...newChannel, channelId: e.target.value })} placeholder="채널 ID (channel_a)" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
              <input value={newChannel.channelName} onChange={e => setNewChannel({ ...newChannel, channelName: e.target.value })} placeholder="채널명" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
              <input value={newChannel.characterKey} onChange={e => setNewChannel({ ...newChannel, characterKey: e.target.value })} placeholder="캐릭터 키 (coin_character)" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
              <input value={newChannel.characterStylePrompt} onChange={e => setNewChannel({ ...newChannel, characterStylePrompt: e.target.value })} placeholder="캐릭터 스타일 프롬프트" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
              <select value={newChannel.referenceStyleProfile} onChange={e => setNewChannel({ ...newChannel, referenceStyleProfile: e.target.value })} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white">
                <option value="black_han_sans_v1">Black Han Sans v1</option>
              </select>
              <select value={newChannel.voiceId} onChange={e => setNewChannel({ ...newChannel, voiceId: e.target.value })} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white"><option value="">기본 음성 사용</option>{voices.map(v => <option key={v.voiceId} value={v.voiceId}>{v.name}</option>)}</select>
            </div>
          </div>
          {(channelsError || voicesError) && <div className="bg-accent-red/10 border border-accent-red/30 rounded-xl p-4 text-xs text-accent-red">백엔드 API가 연결되지 않았습니다. Spring/FastAPI 컨테이너를 먼저 실행한 뒤 새로고침하세요. {channelsError?.message || voicesError?.message}</div>}
          {channels.length === 0 ? (
            <div className="bg-navy-800 border border-navy-700 rounded-xl p-8 text-center text-gray-500">
              등록된 채널 프로필이 없습니다. 위에서 채널 A/B를 추가하세요.
            </div>
          ) : (
            channels.map(channel => {
              const currentVoiceId = editedVoices[channel.channelId] !== undefined
                ? editedVoices[channel.channelId]
                : (channel.voiceId || '');
              const library = characterLibraries[channel.channelId] || { exists: false, poses: [], poseCount: 0 }
              const characterDescription = characterDescriptions[channel.channelId] !== undefined
                ? characterDescriptions[channel.channelId]
                : (channel.characterStylePrompt || '')
              const characterKey = characterKeys[channel.channelId] !== undefined
                ? characterKeys[channel.channelId] : (channel.characterKey || channel.channelId)
              const isGeneratingLibrary = characterLibraryMutation.isPending
                && characterLibraryMutation.variables?.channelId === channel.channelId

              return (
                <div key={channel.channelId} className="bg-navy-800 border border-navy-700 rounded-xl p-6 shadow-card space-y-4">
                  <div className="flex items-start justify-between border-b border-navy-700 pb-3">
                    <div>
                      <h3 className="text-lg font-bold text-white">{channel.channelName}</h3>
                      <span className="text-xs text-navy-400">ID: {channel.channelId}</span>
                    </div>
                    <span className="text-[10px] bg-accent-cyan/10 text-accent-cyan px-2 py-0.5 rounded-full font-bold">
                      채널 프로필
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1 font-semibold">채널 기본 캐릭터</label>
                      <div className="flex gap-2">
                        <input value={characterKey} onChange={e => setCharacterKeys({ ...characterKeys, [channel.channelId]: e.target.value })} placeholder="coin_character" className="flex-1 bg-navy-700 border border-navy-600 rounded-lg px-3 py-2 text-sm text-white" />
                        <button onClick={() => saveChannelMutation.mutate({ ...channel, characterKey })} className="bg-accent-gold text-navy-950 text-xs font-semibold px-3 rounded-lg">기본 저장</button>
                      </div>
                      <p className="text-[11px] text-gray-500 mt-1">관리자/채널은 이 캐릭터를 기본으로 상속하고, 작업 생성 화면에서만 예외 override가 가능합니다.</p>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1 font-semibold">ElevenLabs 나레이션 목소리</label>
                      <div className="flex items-center gap-2 mt-1">
                        <select
                          value={currentVoiceId}
                          onChange={e => setEditedVoices({ ...editedVoices, [channel.channelId]: e.target.value })}
                          className="flex-1 bg-navy-700 border border-navy-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-accent-cyan"
                        >
                          <option value="">목소리 선택 안 함 (gTTS 기본값)</option>
                          {voices.map(v => (
                            <option key={v.voiceId} value={v.voiceId}>
                              {v.name} ({v.category})
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => saveChannelMutation.mutate({
                            ...channel,
                            voiceId: currentVoiceId
                          })}
                          disabled={saveChannelMutation.isPending}
                          className="flex items-center gap-1.5 bg-accent-cyan text-navy-950 text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition"
                        >
                          <Save size={14} />
                          저장
                        </button>
                      </div>
                      {currentVoiceId && voices.find(v => v.voiceId === currentVoiceId) && (
                        <div className="mt-2 space-y-2 bg-navy-900/40 p-2 rounded-lg border border-navy-700/60">
                          {voices.find(v => v.voiceId === currentVoiceId).previewUrl && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-navy-400 font-semibold w-14">성우 톤:</span>
                              <audio
                                src={voices.find(v => v.voiceId === currentVoiceId).previewUrl}
                                controls
                                className="h-6 flex-1"
                                style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}
                              />
                            </div>
                          )}
                          {voices.find(v => v.voiceId === currentVoiceId).auditionUrl && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-accent-cyan font-semibold w-14">예시 낭독:</span>
                              <audio
                                src={voices.find(v => v.voiceId === currentVoiceId).auditionUrl}
                                controls
                                className="h-6 flex-1"
                                style={{ filter: 'invert(0.9) hue-rotate(180deg)' }}
                              />
                            </div>
                          )}
                        </div>
                      )}
                      {currentVoiceId && (
                        <div className="mt-2 rounded-lg border border-accent-cyan/20 bg-accent-cyan/5 p-2.5 space-y-2">
                          <div className="text-[11px] font-semibold text-accent-cyan">기본 예시 문장 미리듣기</div>
                          <div className="flex items-center gap-2">
                            <input
                              value={channelPreviewText[channel.channelId] || '오늘 시장의 핵심 숫자와 외국인 수급의 방향을 차분하게 확인해보겠습니다.'}
                              maxLength={100}
                              onChange={e => setChannelPreviewText({ ...channelPreviewText, [channel.channelId]: e.target.value })}
                              className="flex-1 bg-navy-900 border border-navy-600 rounded px-2 py-1.5 text-xs text-white"
                            />
                            <button
                              type="button"
                              onClick={() => previewChannelVoice(channel.channelId, currentVoiceId)}
                              disabled={channelPreviewLoading[channel.channelId]}
                              className="px-2.5 py-1.5 rounded bg-accent-cyan/20 text-accent-cyan text-xs font-semibold disabled:opacity-50"
                            >{channelPreviewLoading[channel.channelId] ? '생성 중…' : '미리듣기'}</button>
                          </div>
                          {channelPreviewUrls[channel.channelId] && <audio src={channelPreviewUrls[channel.channelId]} controls autoPlay className="h-7 w-full" />}
                        </div>
                      )}
                      <p className="text-[11px] text-gray-500 mt-1.5">
                        지정한 목소리는 이 채널로 생성되는 모든 작업(자동/수동)의 기본 음성으로 자동 적용됩니다.
                      </p>
                    </div>

                    <div>
                      <label className="block text-xs text-gray-400 mb-1 font-semibold">캐릭터 이미지 경로 및 세부 스타일</label>
                      <div className="text-sm text-gray-300 bg-navy-900/40 p-2.5 rounded-lg border border-navy-700 font-mono text-xs truncate mt-1" title={channel.characterStylePrompt}>
                        {channel.characterStylePrompt || '설정된 프롬프트가 없습니다.'}
                      </div>
                      <p className="text-[11px] text-gray-500 mt-1.5">
                        AI 이미지 생성 시 일체형 모드/LoRA 가중치 제어용 프롬프트 정보입니다.
                      </p>
                    </div>
                  </div>

                  <div className="border-t border-navy-700 pt-4 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-white flex items-center gap-2">
                          <ImagePlus size={16} className="text-accent-cyan" />
                          고정 캐릭터 포즈 라이브러리
                        </div>
                        <p className="text-[11px] text-gray-500 mt-1">
                          장면의 역할에 맞춰 표정·의상·포즈를 골라 배경 위에 합성합니다. 생성 후 이 채널의 모든 새 작업에 적용됩니다.
                        </p>
                      </div>
                      <span className={`text-[11px] px-2 py-1 rounded-full font-semibold ${library.exists ? 'bg-accent-green/10 text-accent-green' : 'bg-navy-700 text-gray-400'}`}>
                        {library.exists ? `${library.pose_count || library.poses?.length || 0}개 포즈 준비됨` : '아직 생성되지 않음'}
                      </span>
                    </div>

                    <textarea
                      value={characterDescription}
                      onChange={e => setCharacterDescriptions({ ...characterDescriptions, [channel.channelId]: e.target.value })}
                      placeholder="예: 초록색 지폐 마스코트, 3D 에디토리얼 카툰, 굵은 검은 외곽선, 큰 눈, 친근하고 신뢰감 있는 표정"
                      rows={3}
                      className="w-full bg-navy-900/40 border border-navy-600 rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-accent-cyan"
                    />

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => characterLibraryMutation.mutate({
                          channelId: channel.channelId,
                          characterDescription,
                          regenerate: false,
                        })}
                        disabled={!characterDescription.trim() || isGeneratingLibrary}
                        className="flex items-center gap-1.5 bg-accent-cyan text-navy-950 text-sm font-semibold px-3 py-2 rounded-lg hover:opacity-90 disabled:opacity-50"
                      >
                        <ImagePlus size={14} />
                        {isGeneratingLibrary ? '생성 중…' : library.exists ? '누락 포즈 보완' : '포즈 라이브러리 생성'}
                      </button>
                      {library.exists && (
                        <button
                          onClick={() => characterLibraryMutation.mutate({
                            channelId: channel.channelId,
                            characterDescription,
                            regenerate: true,
                          })}
                          disabled={!characterDescription.trim() || isGeneratingLibrary}
                          className="flex items-center gap-1.5 border border-navy-600 text-gray-300 text-sm px-3 py-2 rounded-lg hover:border-accent-gold hover:text-white disabled:opacity-50"
                        >
                          <RefreshCw size={14} /> 전체 재생성
                        </button>
                      )}
                      <span className="text-[11px] text-gray-500">외부 이미지 생성 API를 호출합니다.</span>
                    </div>

                    {library.exists && library.poses?.length > 0 && (
                      <div className="grid grid-cols-4 sm:grid-cols-7 gap-2 pt-1">
                        {library.poses.map(item => (
                          <div key={item.pose} className="rounded-lg bg-navy-900/50 border border-navy-700 overflow-hidden">
                            <img
                              src={`/api/channels/${channel.channelId}/character-library/pose/${item.pose}`}
                              alt={item.label || item.pose}
                              className="w-full aspect-[3/4] object-contain bg-white/5"
                              loading="lazy"
                            />
                            <div className="px-1.5 py-1 text-[10px] text-center text-gray-400 truncate" title={item.label || item.pose}>
                              {item.label || item.pose}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        <PersonAssetsPanel />
      )}
    </Layout>
  )
}

const PERSON_LICENSES = [
  ['OWNED', '직접 촬영·소유'],
  ['PRESS_KIT', '공식 보도자료'],
  ['KOGL_TYPE1', '공공누리 1유형'],
  ['CC_BY', 'CC BY'],
  ['CC_BY_SA', 'CC BY-SA'],
  ['STOCK_LICENSED', '스톡 라이선스'],
  ['AGENCY_LICENSED', '에이전시 계약'],
]

function PersonAssetsPanel() {
  const qc = useQueryClient()
  const [selectedPersonId, setSelectedPersonId] = useState('')
  const [personForm, setPersonForm] = useState({
    personId: '', nameKo: '', nameEn: '', aliasesJson: '[]',
  })
  const [photoForm, setPhotoForm] = useState({
    file: null,
    licenseType: 'OWNED',
    licenseRef: '',
    creditText: '',
    authorName: '',
    emotionTag: 'neutral',
    pose: 'portrait',
  })
  const { data: people = [] } = useQuery({
    queryKey: ['person-assets'],
    queryFn: () => apiClient.get('/assets/person').then(r => r.data),
  })
  useEffect(() => {
    if (!selectedPersonId && people.length) setSelectedPersonId(people[0].personId)
  }, [people, selectedPersonId])
  const { data: photos = [] } = useQuery({
    queryKey: ['person-photos', selectedPersonId],
    queryFn: () => apiClient.get(`/assets/person/${selectedPersonId}/photos`).then(r => r.data),
    enabled: Boolean(selectedPersonId),
  })
  const createPerson = useMutation({
    mutationFn: () => apiClient.post('/assets/person', personForm).then(r => r.data),
    onSuccess: (person) => {
      setSelectedPersonId(person.personId)
      setPersonForm({ personId: '', nameKo: '', nameEn: '', aliasesJson: '[]' })
      qc.invalidateQueries({ queryKey: ['person-assets'] })
    },
    onError: (error) => alert(error.response?.data?.message || '인물 등록에 실패했습니다.'),
  })
  const uploadPhoto = useMutation({
    mutationFn: async () => {
      const payload = new FormData()
      payload.append('file', photoForm.file)
      for (const key of ['licenseType', 'licenseRef', 'creditText', 'authorName', 'emotionTag', 'pose']) {
        if (photoForm[key]) payload.append(key, photoForm[key])
      }
      return apiClient.post(`/assets/person/${selectedPersonId}/photos`, payload).then(r => r.data)
    },
    onSuccess: () => {
      setPhotoForm(current => ({ ...current, file: null }))
      qc.invalidateQueries({ queryKey: ['person-photos', selectedPersonId] })
      alert('사진을 등록했습니다. 검토 후 승인해야 썸네일에 사용됩니다.')
    },
    onError: (error) => alert(error.response?.data?.message || '사진 등록에 실패했습니다.'),
  })
  const reviewPhoto = useMutation({
    mutationFn: ({ photoId, action }) =>
      apiClient.post(`/assets/person/${selectedPersonId}/photos/${photoId}/${action}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['person-photos', selectedPersonId] }),
    onError: (error) => alert(error.response?.data?.message || '검토 상태 변경에 실패했습니다.'),
  })
  const licenseNeedsRef = photoForm.licenseType !== 'OWNED'
  const licenseNeedsCredit = ['CC_BY', 'CC_BY_SA', 'KOGL_TYPE1'].includes(photoForm.licenseType)

  return (
    <div className="space-y-5">
      <div className="bg-navy-800 border border-accent-gold/30 rounded-xl p-5">
        <h2 className="font-semibold text-white">실사형 썸네일 권리 원칙</h2>
        <p className="text-xs text-gray-400 leading-relaxed mt-2">
          블러·누끼·색보정은 시각 효과일 뿐 저작권이나 초상권을 없애지 않습니다.
          직접 소유하거나 이용 허락이 확인된 사진만 등록하고, 승인된 사진만 자동 썸네일 추천에 사용됩니다.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <section className="bg-navy-800 border border-navy-700 rounded-xl p-5 space-y-3">
          <h3 className="font-semibold text-white">1. 인물 등록</h3>
          <div className="grid grid-cols-2 gap-2">
            <input value={personForm.personId} onChange={e => setPersonForm({ ...personForm, personId: e.target.value })} placeholder="ID: sundar_pichai" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <input value={personForm.nameKo} onChange={e => setPersonForm({ ...personForm, nameKo: e.target.value })} placeholder="한글 이름" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <input value={personForm.nameEn} onChange={e => setPersonForm({ ...personForm, nameEn: e.target.value })} placeholder="영문 이름" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <input value={personForm.aliasesJson} onChange={e => setPersonForm({ ...personForm, aliasesJson: e.target.value })} placeholder='["구글 CEO"]' className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
          </div>
          <button onClick={() => createPerson.mutate()} disabled={!personForm.personId || !personForm.nameKo || createPerson.isPending} className="bg-accent-cyan text-navy-950 rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
            {createPerson.isPending ? '등록 중…' : '인물 등록'}
          </button>
          <div className="pt-2">
            <label className="block text-xs text-gray-400 mb-1">사진을 등록할 인물</label>
            <select value={selectedPersonId} onChange={e => setSelectedPersonId(e.target.value)} className="w-full bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-sm text-white">
              <option value="">인물을 선택하세요</option>
              {people.map(person => <option key={person.personId} value={person.personId}>{person.nameKo} · {person.personId}</option>)}
            </select>
          </div>
        </section>

        <section className="bg-navy-800 border border-navy-700 rounded-xl p-5 space-y-3">
          <h3 className="font-semibold text-white">2. 권리확인 사진 등록</h3>
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => setPhotoForm({ ...photoForm, file: e.target.files?.[0] || null })} className="block w-full text-xs text-gray-300 file:mr-3 file:rounded-lg file:border-0 file:bg-accent-cyan file:px-3 file:py-2 file:font-semibold file:text-navy-950" />
          <div className="grid grid-cols-2 gap-2">
            <select value={photoForm.licenseType} onChange={e => setPhotoForm({ ...photoForm, licenseType: e.target.value })} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white">
              {PERSON_LICENSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <input value={photoForm.licenseRef} onChange={e => setPhotoForm({ ...photoForm, licenseRef: e.target.value })} placeholder={licenseNeedsRef ? '출처 URL·계약 번호 (필수)' : '출처 메모 (선택)'} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <input value={photoForm.creditText} onChange={e => setPhotoForm({ ...photoForm, creditText: e.target.value })} placeholder={licenseNeedsCredit ? '표시할 크레딧 (필수)' : '크레딧 문구'} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <input value={photoForm.authorName} onChange={e => setPhotoForm({ ...photoForm, authorName: e.target.value })} placeholder="촬영자·권리자" className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white" />
            <select value={photoForm.emotionTag} onChange={e => setPhotoForm({ ...photoForm, emotionTag: e.target.value })} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white">
              <option value="neutral">중립</option><option value="serious">진지함</option><option value="surprised">놀람</option><option value="worried">걱정</option><option value="happy">긍정</option>
            </select>
            <select value={photoForm.pose} onChange={e => setPhotoForm({ ...photoForm, pose: e.target.value })} className="bg-navy-900 border border-navy-600 rounded-lg px-3 py-2 text-xs text-white">
              <option value="portrait">정면 인물</option><option value="pointing">가리키는 포즈</option><option value="hand_up">손을 든 포즈</option><option value="profile">측면</option>
            </select>
          </div>
          <button onClick={() => uploadPhoto.mutate()} disabled={!selectedPersonId || !photoForm.file || (licenseNeedsRef && !photoForm.licenseRef) || (licenseNeedsCredit && !photoForm.creditText) || uploadPhoto.isPending} className="bg-accent-gold text-navy-950 rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
            {uploadPhoto.isPending ? '업로드 중…' : '검토 대기 사진 등록'}
          </button>
        </section>
      </div>

      <section className="bg-navy-800 border border-navy-700 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div><h3 className="font-semibold text-white">3. 사진 검토 및 승인</h3><p className="text-[11px] text-gray-500 mt-1">승인된 선명한 사진만 대본의 인물명과 매칭되어 실사형 추천에 들어갑니다.</p></div>
          <span className="text-xs text-gray-400">{photos.length}장</span>
        </div>
        {photos.length === 0 ? (
          <div className="py-10 text-center text-sm text-gray-500">선택한 인물의 등록 사진이 없습니다.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {photos.map(photo => (
              <article key={photo.photoId} className="bg-navy-900/60 border border-navy-700 rounded-xl overflow-hidden">
                <img src={`/api/assets/person/${selectedPersonId}/photos/${photo.photoId}/content`} alt="" className="w-full aspect-video object-cover bg-black" />
                <div className="p-3 space-y-2">
                  <div className="flex items-center justify-between"><span className="text-xs font-semibold text-white">{photo.licenseType}</span><span className={`text-[10px] px-2 py-0.5 rounded-full ${photo.approved ? 'bg-accent-green/10 text-accent-green' : photo.rightsReviewStatus === 'REJECTED' ? 'bg-accent-red/10 text-accent-red' : 'bg-accent-gold/10 text-accent-gold'}`}>{photo.approved ? '승인됨' : photo.rightsReviewStatus === 'REJECTED' ? '반려됨' : '검토 대기'}</span></div>
                  <div className="text-[11px] text-gray-500 break-all">{photo.licenseRef || '직접 소유 사진'}</div>
                  <div className="flex gap-2">
                    <button onClick={() => reviewPhoto.mutate({ photoId: photo.photoId, action: 'approve' })} className="flex-1 bg-accent-green/15 text-accent-green rounded py-1.5 text-xs font-semibold">승인</button>
                    <button onClick={() => reviewPhoto.mutate({ photoId: photo.photoId, action: 'reject' })} className="flex-1 bg-accent-red/15 text-accent-red rounded py-1.5 text-xs font-semibold">반려</button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ProviderBadge({ label, configured }) {
  const unavailable = configured === undefined
  return <div className="bg-navy-900/60 border border-navy-700 rounded-lg px-3 py-2 flex items-center justify-between"><span className="text-gray-300">{label}</span><span className={unavailable ? 'text-accent-red' : configured ? 'text-accent-green' : 'text-accent-gold'}>{unavailable ? '확인 실패' : configured ? '연결됨' : '키 없음'}</span></div>
}
