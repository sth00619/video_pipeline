import { useQuery } from '@tanstack/react-query'
import { Users, TrendingUp, Tv } from 'lucide-react'
import apiClient from '../../api/client'

function formatSubscribers(count) {
  if (count == null || count === 0) return '정보 없음'
  if (count >= 10000) {
    const man = (count / 10000).toFixed(1)
    return `~${man.endsWith('.0') ? man.slice(0, -2) : man}만명`
  }
  return `~${count.toLocaleString('ko-KR')}명`
}

export default function ChannelBenchmark() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['youtube-channel-benchmark'],
    queryFn: () => apiClient.get('/youtube/channels/benchmark').then(res => res.data),
    staleTime: 1000 * 60 * 60 * 6, // 6시간 캐시
    retry: 1
  })

  const channels = data?.channels || [
    { channel_id: 'UC7usMJDHmtbs_oegmzQKKMA', title: '경제사냥꾼', subscriber_count: 640000 },
    { channel_id: 'UC86s17Zc-V7vP7zL6Z-Yd4g', title: '삼프로TV', subscriber_count: 2500000 },
    { channel_id: 'UCpAyogfL8-YzmKf3-wTfEBg', title: '주식하는형', subscriber_count: 150000 }
  ]

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Tv size={18} className="text-accent-cyan" />
          <h3 className="font-semibold text-slate-900">벤치마크 채널 현황</h3>
        </div>
        <span className="text-xs text-slate-400">Real-time YouTube Data</span>
      </div>

      {isLoading ? (
        <div className="text-center py-6 text-sm text-slate-400">채널 데이터를 불러오는 중...</div>
      ) : isError ? (
        <div className="text-center py-6 text-sm text-amber-500">채널 벤치마크 불러오기 실패</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {channels.map((ch) => (
            <div
              key={ch.channel_id || ch.title}
              className="flex items-center justify-between p-3.5 rounded-lg bg-slate-50 border border-slate-100"
            >
              <div>
                <div className="font-semibold text-sm text-slate-800">{ch.title}</div>
                <div className="text-xs text-slate-500 flex items-center gap-1 mt-1">
                  <Users size={12} className="text-slate-400" />
                  <span>구독자 {formatSubscribers(ch.subscriber_count)}</span>
                </div>
              </div>
              <TrendingUp size={16} className="text-accent-cyan opacity-80" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
