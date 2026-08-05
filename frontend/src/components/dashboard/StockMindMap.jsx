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
    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm transition-all duration-300">
      <div 
        className="flex items-center justify-between cursor-pointer select-none mb-1"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600">
            <Zap className="animate-pulse" size={18} />
          </div>
          <div>
            <h2 className="font-bold text-base text-slate-900">실시간 주식 트렌드 마인드맵</h2>
            {!isCollapsed && (
              <p className="text-xs text-slate-500 mt-0.5">
                관심 있는 키워드를 클릭해 영상 제작에 바로 활용해보세요.
              </p>
            )}
          </div>
        </div>
        <button className="p-1.5 hover:bg-slate-100 rounded-lg transition text-slate-400 hover:text-slate-700">
          {isCollapsed ? <ChevronRight size={20} /> : <ChevronDown size={20} />}
        </button>
      </div>

      {!isCollapsed && (
        <div className="space-y-3 mt-4 animate-fadeIn">
          {MINDMAP_DATA.map((cat, idx) => {
            const isExpanded = expandedCategories[cat.category];
            const Icon = cat.icon;
            return (
              <div key={idx} className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50/50">
                <button
                  onClick={() => toggleCategory(cat.category)}
                  className={`w-full flex items-center justify-between p-3.5 transition hover:bg-slate-100/80 ${isExpanded ? 'bg-slate-100/60' : ''}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${cat.bg} ${cat.color}`}>
                      <Icon size={16} />
                    </div>
                    <span className="font-bold text-sm text-slate-800">{cat.category}</span>
                  </div>
                  {isExpanded ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}
                </button>

                {isExpanded && (
                  <div className="p-4 bg-white border-t border-slate-200/80">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {cat.items.map((item, itemIdx) => (
                        <div key={itemIdx} className="space-y-2">
                          <div className="text-xs font-bold text-slate-800 border-l-2 border-indigo-500 pl-2">
                            {item.name}
                          </div>
                          <div className="flex flex-wrap gap-2 pl-2">
                            {item.keywords.map((kw, kwIdx) => {
                              const isActive = selectedKeywords.includes(kw);
                              return (
                                <button
                                  key={kwIdx}
                                  onClick={() => onSelectKeyword(kw)}
                                  className={`text-xs px-3 py-1.5 rounded-lg transition border shadow-xs ${
                                    isActive
                                      ? 'bg-indigo-600 text-white border-indigo-600 font-semibold shadow-sm'
                                      : 'bg-white text-slate-700 border-slate-200 hover:text-indigo-700 hover:bg-indigo-50/60 hover:border-indigo-300'
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
