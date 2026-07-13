import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Shield, DollarSign, Video, Settings, Save } from 'lucide-react'
import Layout from '../components/Layout'
import JobFilterBar from '../components/JobFilterBar'
import Pagination from '../components/Pagination'
import StatusBadge from '../components/StatusBadge'
import apiClient from '../api/client'
import { isCompleted } from '../constants/jobStatus'

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

  const { data: jobs = [] } = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: () => apiClient.get('/jobs').then(r => r.data),
  })

  const { data: channels = [], refetch: refetchChannels } = useQuery({
    queryKey: ['admin-channels'],
    queryFn: () => apiClient.get('/channels').then(r => r.data),
  })

  const { data: voices = [] } = useQuery({
    queryKey: ['voices'],
    queryFn: () => apiClient.get('/channels/voices').then(r => r.data),
    staleTime: Infinity,
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
                        onClick={() => navigate(`/jobs/${job.id}`)}
                        className="hover:bg-navy-700/50 transition cursor-pointer"
                      >
                        <td className="px-6 py-3.5 text-gray-400">#{job.id}</td>
                        <td className="px-6 py-3.5 font-medium text-white truncate max-w-[280px]" title={job.title}>
                          {job.title}
                        </td>
                        <td className="px-6 py-3.5 text-gray-400">{job.category}</td>
                        <td className="px-6 py-3.5 text-gray-400">{job.autonomy}</td>
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
      ) : (
        <div className="space-y-4">
          {channels.length === 0 ? (
            <div className="bg-navy-800 border border-navy-700 rounded-xl p-8 text-center text-gray-500">
              등록된 채널 프로필이 없습니다.
            </div>
          ) : (
            channels.map(channel => {
              const currentVoiceId = editedVoices[channel.channelId] !== undefined
                ? editedVoices[channel.channelId]
                : (channel.voiceId || '');

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
                </div>
              );
            })
          )}
        </div>
      )}
    </Layout>
  )
}
