'use client';

import { useState, useEffect } from 'react';
import { useApp } from '@/components/AppContext';

interface ModelRule {
  info: string;
  models: string[];
}

interface ModelFamily {
  name: string;
  rules: ModelRule[];
}

export default function ModelInfoPage() {
  const { showToast, t } = useApp();
  const [modelFamilies, setModelFamilies] = useState<ModelFamily[]>([]);
  const [selectedFamily, setSelectedFamily] = useState<ModelFamily | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadModelInfo = async () => {
    try {
      const res = await fetch('/v1/model-info');
      if (res.ok) {
        const data = await res.json();
        const families = data.families || [];
        setModelFamilies(families);
        if (families.length > 0) {
          setSelectedFamily(families[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch model info:', err);
      showToast(t('modelInfo.toast.fetchFailed'), 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModelInfo();
  }, []);

  return (
    <section id="model-info" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('modelInfo.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('modelInfo.description')}</p>
        </div>
      </header>

      <div className="model-info-layout glass-panel bg-[#18181b] border border-zinc-800 rounded-md overflow-hidden shadow-xl flex h-[calc(100vh-300px)]">
        {/* Sidebar */}
        <div className="model-info-sidebar w-[260px] border-r border-border pt-6 pb-4 flex flex-col gap-0.5 overflow-y-auto bg-[#18181b]/50 shrink-0 custom-scrollbar">
          {loading ? (
            <div className="text-zinc-500 text-xs px-6 py-4 italic">{t('modelInfo.loading')}</div>
          ) : modelFamilies.length === 0 ? (
            <div className="text-zinc-500 text-xs px-6 py-4 italic">{t('modelInfo.noFamilies')}</div>
          ) : (
            modelFamilies.map((family) => (
              <button
                key={family.name}
                onClick={() => setSelectedFamily(family)}
                className={`family-btn w-full text-left px-6 py-3.5 border-l-3 text-[14px] font-medium transition-all ${
                  selectedFamily && selectedFamily.name === family.name
                    ? 'bg-zinc-800 text-white border-l-white'
                    : 'bg-transparent text-zinc-450 border-l-transparent hover:bg-zinc-800/40 hover:text-white'
                }`}
              >
                {family.name}
              </button>
            ))
          )}
        </div>

        {/* Content Area */}
        <div className="model-info-content flex-1 p-8 overflow-y-auto custom-scrollbar bg-zinc-900/20">
          {!selectedFamily ? (
            <div className="empty-state flex flex-col items-center justify-center h-full text-zinc-500 italic gap-4">
              <p>{t('modelInfo.selectFamily')}</p>
            </div>
          ) : (
            <div className="flex flex-col gap-6 animate-in fade-in duration-300">
              {(!selectedFamily.rules || selectedFamily.rules.length === 0) ? (
                <div className="empty-state flex flex-col items-center justify-center py-12 text-zinc-500 italic">
                  {t('modelInfo.noRules')}
                </div>
              ) : (
                selectedFamily.rules.map((rule, idx) => (
                  <div
                    key={idx}
                    className="rule-card bg-zinc-800/30 border border-zinc-700/60 rounded-lg p-6 hover:bg-zinc-800/45 hover:border-zinc-600/70 hover:-translate-y-0.5 transition-all duration-200 shadow-md"
                  >
                    <div className="rule-info text-zinc-100 text-sm font-medium leading-relaxed mb-4 flex gap-3 items-start">
                      <span className="text-amber-500 shrink-0 text-base">⚠️</span>
                      <span>{t(rule.info)}</span>
                    </div>
                    <div className="rule-models flex flex-wrap gap-2 pt-4 border-t border-dashed border-zinc-700/50">
                      {rule.models.map((m) => (
                        <span
                          key={m}
                          className="model-badge bg-zinc-800/50 border border-zinc-600/50 text-zinc-300 font-mono text-[11px] px-3 py-1.5 rounded-full"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
