import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Youtube, Users, Eye, Clock, ExternalLink, ThumbsUp, TrendingUp } from 'lucide-react';
import { jobsApi } from '../../api/jobs';

const TABS = [
  { id: 'outperformer', label: '조회율 급상승', ranking: 'outperformer', minSubscribers: 0, description: '구독자 3천명 이상 채널 중 구독자 대비 조회율이 높은 영상' },
  { id: '50k', label: '5만+', ranking: 'large_channel', minSubscribers: 50_000, description: '구독자 5만명 이상 채널의 최근 업로드' },
  { id: '100k', label: '10만+', ranking: 'large_channel', minSubscribers: 100_000, description: '구독자 10만명 이상 채널의 최근 업로드' },
  { id: '200k', label: '20만+', ranking: 'large_channel', minSubscribers: 200_000, description: '구독자 20만명 이상 채널의 최근 업로드' },
  { id: '300k', label: '30만+', ranking: 'large_channel', minSubscribers: 300_000, description: '구독자 30만명 이상 채널의 최근 업로드' },
  { id: '500k', label: '50만+', ranking: 'large_channel', minSubscribers: 500_000, description: '구독자 50만명 이상 채널의 최근 업로드' },
  { id: '1m', label: '100만+', ranking: 'large_channel', minSubscribers: 1_000_000, description: '구독자 100만명 이상 채널의 최근 업로드' },
];

const formatNumber = (num) => {
  if (!num) return '0';
  if (num >= 10000) return `${(num / 10000).toFixed(1)}만`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}천`;
  return num.toString();
};

const valueOf = (video, camelCase, snakeCase) => video?.[camelCase] ?? video?.[snakeCase];
const formatSubscriberResponse = (views, subscribers) => {
  if (!subscribers) return '계산 불가';
  return `${((views / subscribers) * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`;
};

export default function TrendingSidebar({ keyword }) {
  const [activeKeyword, setActiveKeyword] = useState(keyword || '주식');
  const [activeTabId, setActiveTabId] = useState(TABS[0].id);
  const activeTab = TABS.find(tab => tab.id === activeTabId) || TABS[0];

  useEffect(() => {
    if (keyword) setActiveKeyword(keyword);
  }, [keyword]);

  const { data: videos = [], isLoading, isError } = useQuery({
    queryKey: ['trending', activeKeyword, activeTab.ranking, activeTab.minSubscribers],
    queryFn: () => jobsApi.trendingYoutube(activeKeyword, activeTab),
    staleTime: 1000 * 60 * 60,
    enabled: !!activeKeyword,
  });

  return (
    <section className="bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
      <div className="p-5 border-b border-navy-700">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Youtube className="text-red-500" size={20} />
            <div>
              <h2 className="font-bold text-sm text-white">YouTube 채널 벤치마크</h2>
              <p className="text-xs text-gray-500 mt-1">대형 채널의 최근 영상 형식과 반응을 비교하세요.</p>
            </div>
          </div>
          <span className="text-[10px] bg-red-500/10 text-red-400 px-2 py-1 rounded-full font-bold border border-red-500/20">{activeKeyword}</span>
        </div>
        <div className="flex gap-2 overflow-x-auto pt-4 pb-1">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTabId(tab.id)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${activeTabId === tab.id ? 'border-red-500 bg-red-500 text-white' : 'border-navy-600 bg-navy-900 text-gray-400 hover:border-red-500/60 hover:text-white'}`}
            >
              {tab.id === 'outperformer' && <TrendingUp size={12} className="inline mr-1 -mt-0.5" />}{tab.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-gray-400">{activeTab.description} · 라이브와 7일 이전 업로드는 제외</p>
      </div>

      {isLoading && <div className="flex flex-col items-center justify-center h-44 text-gray-500 text-sm"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-red-500 mb-3" />수집 중...</div>}
      {isError && <div className="text-center py-12 text-red-400 text-sm">트렌드 데이터를 불러오지 못했습니다.</div>}
      {!isLoading && !isError && videos.length === 0 && <div className="text-center py-12 text-gray-500 text-sm">이 조건에 맞는 최근 영상이 없습니다.</div>}

      {!isLoading && !isError && videos.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 p-4">
          {videos.map((video, idx) => {
            const videoId = valueOf(video, 'videoId', 'video_id');
            const channelTitle = valueOf(video, 'channelTitle', 'channel_title');
            const hoursSincePublish = Number(valueOf(video, 'hoursSincePublish', 'hours_since_publish'));
            const durationSeconds = Number(valueOf(video, 'durationSeconds', 'duration_seconds'));
            const likesAvailable = valueOf(video, 'likesAvailable', 'likes_available');
            return (
              <button key={videoId || idx} onClick={() => videoId && window.open(`https://www.youtube.com/watch?v=${videoId}`, '_blank')} className="group relative text-left bg-navy-900/50 rounded-lg border border-navy-700 hover:border-red-500/60 transition overflow-hidden">
                <div className="aspect-video bg-navy-900 overflow-hidden relative">
                  {videoId ? <img src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`} alt="" className="w-full h-full object-cover group-hover:scale-105 transition duration-300" /> : <div className="flex h-full items-center justify-center text-xs text-gray-500">썸네일 정보 없음</div>}
                  <span className="absolute top-2 left-2 bg-black/70 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">#{idx + 1}</span>
                  <ExternalLink size={14} className="absolute right-2 top-2 text-white opacity-0 group-hover:opacity-100 transition" />
                </div>
                <div className="p-3">
                  <p className="text-xs font-bold text-white line-clamp-2 min-h-8 leading-snug group-hover:text-red-400 transition">{video.title}</p>
                  <p className="text-[11px] text-gray-400 truncate mt-2">{channelTitle || '채널 정보 없음'}</p>
                  <div className="grid grid-cols-2 gap-x-2 gap-y-1 mt-2 text-[10px] text-gray-500">
                    <span className="flex items-center gap-1"><Users size={10} />{formatNumber(video.subscribers)}명</span>
                    <span className="flex items-center gap-1"><Eye size={10} />{formatNumber(video.views)}회</span>
                    <span className="flex items-center gap-1"><ThumbsUp size={10} />{likesAvailable === false ? '비공개' : formatNumber(video.likes)}</span>
                    <span className="flex items-center gap-1"><Clock size={10} />{Number.isFinite(hoursSincePublish) ? (hoursSincePublish < 24 ? `${Math.floor(hoursSincePublish)}시간 전` : `${Math.floor(hoursSincePublish / 24)}일 전`) : '게시일 미상'}</span>
                  </div>
                  <p className="mt-2 text-[10px] text-gray-600">구독자 대비 조회율 {formatSubscriberResponse(video.views, video.subscribers)} · {Number.isFinite(durationSeconds) && durationSeconds > 0 ? `${Math.round(durationSeconds)}초` : '길이 정보 없음'}</p>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
