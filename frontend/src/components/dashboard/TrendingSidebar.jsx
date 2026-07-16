import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Youtube, Users, Eye, Clock, ExternalLink, ThumbsUp } from 'lucide-react';
import { jobsApi } from '../../api/jobs';

export default function TrendingSidebar({ keyword }) {
  const [activeKeyword, setActiveKeyword] = useState(keyword || '주식');

  useEffect(() => {
    if (keyword) setActiveKeyword(keyword);
  }, [keyword]);

  const { data: videos = [], isLoading, isError } = useQuery({
    queryKey: ['trending', activeKeyword],
    queryFn: () => jobsApi.trendingYoutube(activeKeyword),
    staleTime: 1000 * 60 * 60, // 1 hour frontend cache
    enabled: !!activeKeyword
  });

  const formatNumber = (num) => {
    if (!num) return '0';
    if (num >= 10000) return (num / 10000).toFixed(1) + '만';
    if (num >= 1000) return (num / 1000).toFixed(1) + '천';
    return num.toString();
  };

  return (
    <div className="bg-navy-800 rounded-xl border border-navy-700 h-full flex flex-col sticky top-6">
      <div className="p-5 border-b border-navy-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Youtube className="text-red-500" size={20} />
          <h2 className="font-bold text-sm">유튜브 인기 영상</h2>
        </div>
        {activeKeyword && (
          <span className="text-[10px] bg-red-500/10 text-red-500 px-2 py-1 rounded-full font-bold border border-red-500/20">
            {activeKeyword}
          </span>
        )}
      </div>

      <div className="p-4 flex-1 overflow-y-auto min-h-[600px] max-h-[800px] space-y-4">
        {isLoading && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-500 text-sm">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500 mb-3"></div>
            실시간 트렌드 수집 중...
          </div>
        )}
        
        {isError && (
          <div className="text-center py-10 text-red-400 text-xs">
            트렌드 데이터를 불러오지 못했습니다.
          </div>
        )}

        {!isLoading && !isError && videos.length === 0 && (
          <div className="text-center py-10 text-gray-500 text-xs">
            검색된 트렌드 영상이 없습니다.
          </div>
        )}

        {!isLoading && !isError && videos.map((video, idx) => (
          <div 
            key={idx} 
            className="group relative bg-navy-900/50 rounded-lg border border-navy-700 hover:border-red-500/50 transition p-3 cursor-pointer"
            onClick={() => window.open(`https://www.youtube.com/watch?v=${video.videoId}`, '_blank')}
          >
            <div className="flex gap-3">
              <div className="w-24 h-16 bg-navy-800 rounded flex-shrink-0 overflow-hidden relative">
                <img 
                  src={`https://i.ytimg.com/vi/${video.videoId}/mqdefault.jpg`} 
                  alt="thumbnail" 
                  className="w-full h-full object-cover group-hover:scale-110 transition duration-300"
                />
                <div className="absolute top-1 left-1 bg-black/70 text-white text-[9px] font-bold px-1.5 py-0.5 rounded">
                  #{idx + 1}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-white mb-1 line-clamp-2 leading-snug group-hover:text-red-400 transition">
                  {video.title}
                </div>
                <div className="text-[10px] text-gray-400 truncate mb-1">
                  {video.channelTitle}
                </div>
                <div className="flex items-center gap-3 text-[10px] text-gray-500 font-medium">
                  <span className="flex items-center gap-1"><Eye size={10}/> {formatNumber(video.views)}회</span>
                  <span className="flex items-center gap-1"><Users size={10}/> {formatNumber(video.subscribers)}명</span>
                  <span className="flex items-center gap-1"><ThumbsUp size={10}/> {(video.likes_available ?? video.likesAvailable) === false ? '비공개' : formatNumber(video.likes)}</span>
                  <span className="flex items-center gap-1"><Clock size={10}/> {video.hoursSincePublish < 24 ? `${Math.floor(video.hoursSincePublish)}시간 전` : `${Math.floor(video.hoursSincePublish/24)}일 전`}</span>
                </div>
                <div className="mt-1 text-[10px] text-gray-600">
                  조회/구독 {video.subscribers ? `${(video.views / video.subscribers).toFixed(2)}×` : '계산 불가'} · 영상 {video.durationSeconds ? `${Math.round(video.durationSeconds)}초` : '길이 없음'}
                </div>
              </div>
            </div>
            {/* Hover overlay external link icon */}
            <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition">
              <ExternalLink size={14} className="text-red-400" />
            </div>
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-navy-700 text-center">
        <p className="text-[10px] text-gray-500 flex items-center justify-center gap-1">
           Redis Cache &bull; YouTube Data API v3
        </p>
      </div>
    </div>
  );
}
