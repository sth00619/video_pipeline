import { useState } from 'react';
import { TrendingUp, Globe, Link2, ChevronDown, ChevronRight, Zap } from 'lucide-react';

const MINDMAP_DATA = [
  {
    category: "개별 종목",
    icon: TrendingUp,
    color: "text-accent-cyan",
    bg: "bg-accent-cyan/10",
    items: [
      { name: "삼성전자", keywords: ["삼성전자 반도체", "삼성전자 HBM", "삼성전자 파운드리"] },
      { name: "SK하이닉스", keywords: ["SK하이닉스 HBM", "SK하이닉스 실적"] },
      { name: "테슬라", keywords: ["테슬라 FSD", "테슬라 로보택시", "테슬라 인도량"] },
      { name: "엔비디아", keywords: ["엔비디아 실적", "엔비디아 AI칩"] }
    ]
  },
  {
    category: "시장 이슈",
    icon: Globe,
    color: "text-accent-gold",
    bg: "bg-accent-gold/10",
    items: [
      { name: "FOMC 금리결정", keywords: ["FOMC 금리 인하", "연준 점도표", "파월 발언"] },
      { name: "환율 급등", keywords: ["원달러 환율", "강달러 수혜주"] },
      { name: "미국 CPI", keywords: ["미국 CPI 발표", "인플레이션 둔화"] }
    ]
  },
  {
    category: "연결 테마주",
    icon: Link2,
    color: "text-accent-green",
    bg: "bg-accent-green/10",
    items: [
      { name: "AI 반도체", keywords: ["한미반도체", "이수페타시스", "AI 반도체 수혜주"] },
      { name: "이차전지", keywords: ["에코프로비엠", "엘앤에프", "이차전지 전망"] },
      { name: "원자력", keywords: ["두산에너빌리티", "우진", "체코 원전"] }
    ]
  }
];

export default function StockMindMap({ onSelectKeyword, selectedKeywords = [] }) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState({
    "개별 종목": true,
    "시장 이슈": true,
    "연결 테마주": true
  });

  const toggleCategory = (category) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }));
  };

  return (
    <div className="bg-navy-800 rounded-xl border border-navy-700 p-5 transition-all duration-300">
      <div 
        className="flex items-center justify-between cursor-pointer select-none mb-2"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div className="flex items-center gap-2">
          <Zap className="text-accent-cyan animate-pulse" size={18} />
          <h2 className="font-bold text-sm">실시간 주식 트렌드 마인드맵</h2>
          {!isCollapsed && (
            <span className="text-[10px] text-gray-400 ml-2 hidden sm:inline">
              키워드를 클릭해 영상을 바로 생성하세요.
            </span>
          )}
        </div>
        <button className="p-1 hover:bg-navy-700 rounded transition text-gray-400 hover:text-white">
          {isCollapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
        </button>
      </div>

      {!isCollapsed && (
        <div className="space-y-4 mt-4 animate-fadeIn">
          {MINDMAP_DATA.map((cat, idx) => {
            const isExpanded = expandedCategories[cat.category];
            const Icon = cat.icon;
            return (
              <div key={idx} className="border border-navy-700 rounded-lg overflow-hidden bg-navy-900/10">
                <button
                  onClick={() => toggleCategory(cat.category)}
                  className={`w-full flex items-center justify-between p-3 transition hover:bg-navy-700/50 ${isExpanded ? 'bg-navy-700/30' : ''}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`p-1.5 rounded-md ${cat.bg} ${cat.color}`}>
                      <Icon size={14} />
                    </div>
                    <span className="font-semibold text-sm">{cat.category}</span>
                  </div>
                  {isExpanded ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
                </button>

                {isExpanded && (
                  <div className="p-3 bg-navy-900/30 border-t border-navy-700">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {cat.items.map((item, itemIdx) => (
                        <div key={itemIdx} className="space-y-2">
                          <div className="text-xs font-bold text-gray-300 border-l-2 border-navy-600 pl-2">
                            {item.name}
                          </div>
                          <div className="flex flex-wrap gap-2 pl-2">
                            {item.keywords.map((kw, kwIdx) => {
                              const isActive = selectedKeywords.includes(kw);
                              return (
                                <button
                                  key={kwIdx}
                                  onClick={() => onSelectKeyword(kw)}
                                  className={`text-[11px] px-2.5 py-1 rounded-full transition border ${
                                    isActive
                                      ? 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/80 font-semibold shadow-sm shadow-accent-cyan/10'
                                      : 'bg-navy-700 text-gray-300 border-navy-600 hover:text-white hover:bg-accent-cyan/20 hover:border-accent-cyan/50'
                                  }`}
                                >
                                  {kw}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
