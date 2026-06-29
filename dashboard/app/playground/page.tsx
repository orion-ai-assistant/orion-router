'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import ChatTab from './components/ChatTab';
import TtsTab from './components/TtsTab';
import EmbedTab from './components/EmbedTab';

export default function PlaygroundPage() {
  const { t } = useApp();
  
  const getSavedState = (key: string, defaultVal: string) => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || defaultVal;
    }
    return defaultVal;
  };

  const [activeTab, setActiveTab] = useState<'chat' | 'tts' | 'embed'>(
    getSavedState('pg_activeTab', 'chat') as 'chat' | 'tts' | 'embed'
  );
  
  const [models, setModels] = useState<any[]>([]);
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadModels = async () => {
    try {
      const res = await adminFetch('/dashboard/api/models');
      if (res.ok) {
        const data = await res.json();
        setModels(data.models || []);
      }
    } catch (e) {
      console.error('Failed to load models:', e);
    }
  };

  const loadGroups = async () => {
    try {
      const res = await adminFetch('/dashboard/api/model-groups');
      if (res.ok) {
        const data = await res.json();
        setGroups(data.groups || []);
      }
    } catch (e) {
      console.error('Failed to load groups:', e);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await Promise.all([
        loadModels(),
        loadGroups()
      ]);
      setLoading(false);
    };
    initData();
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('pg_activeTab', activeTab);
    }
  }, [activeTab]);

  return (
    <section id="playground" className="tab-content active block pt-4">
      <header className="flex justify-between items-end mb-4 pb-4 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">{t('playground.title')}</h1>
          <p className="text-zinc-400 text-xs mt-0.5">{t('playground.description')}</p>
        </div>
      </header>

      <div className="pg-segmented-control flex gap-1 bg-[#18181b] border border-zinc-800 p-0.5 rounded-md mb-4 max-w-max">
        {(['chat', 'tts', 'embed'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-[8px] font-medium text-xs transition-all cursor-pointer ${activeTab === tab
              ? 'bg-zinc-800 text-white shadow'
              : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-white'
              }`}
          >
            {tab === 'chat' ? t('playground.chat') : tab === 'tts' ? t('playground.tts') : t('playground.embed')}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="glass-panel p-8 text-center text-zinc-400">{t('playground.loading')}</div>
      ) : (
        <>
          {activeTab === 'chat' && <ChatTab models={models} groups={groups} />}
          {activeTab === 'tts' && <TtsTab models={models} groups={groups} />}
          {activeTab === 'embed' && <EmbedTab models={models} groups={groups} />}
        </>
      )}
    </section>
  );
}
