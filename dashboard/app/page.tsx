'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money, formatNumber } from '@/lib/utils';
import { Coins, Cpu, Key } from 'lucide-react';

interface Stats {
  total_cost: number;
  prompt_cost?: number;
  completion_cost?: number;
  thoughts_cost?: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  thoughts_tokens: number;
  total_keys: number;
}

export default function OverviewPage() {
  const [stats, setStats] = useState<Stats>({
    total_cost: 0,
    prompt_cost: 0,
    completion_cost: 0,
    thoughts_cost: 0,
    total_tokens: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    thoughts_tokens: 0,
    total_keys: 0,
  });

  const loadStats = async () => {
    try {
      const res = await adminFetch('/dashboard/api/stats');
      if (res.ok) {
        const data = await res.json();
        setStats({
          total_cost: data.total_cost || 0,
          prompt_cost: data.prompt_cost || 0,
          completion_cost: data.completion_cost || 0,
          thoughts_cost: data.thoughts_cost || 0,
          total_tokens: data.total_tokens || 0,
          prompt_tokens: data.prompt_tokens || 0,
          completion_tokens: data.completion_tokens || 0,
          thoughts_tokens: data.thoughts_tokens || 0,
          total_keys: data.total_keys || 0,
        });
      }
    } catch (err) {
      console.error("Failed to load dashboard stats:", err);
    }
  };

  useEffect(() => {
    loadStats();

    // Listen for authentication event to reload stats
    const handleAuth = () => {
      loadStats();
    };

    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  return (
    <section id="dashboard" className="tab-content active block pt-8">
      <div className="dashboard-banner"></div>

      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">Overview</h1>
          <p className="text-zinc-400 text-sm mt-1">Gateway usage and registry health</p>
        </div>
      </header>

      <div className="stats-grid grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total Cost Card */}
        <div className="stat-card glass-panel p-6 pl-10 flex items-center gap-6 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-blue-500/35 hover:shadow-[0_8px_30px_rgba(59,130,246,0.15)] transition-all duration-200">
          <div className="stat-icon text-blue-400 bg-blue-500/10 border border-blue-500/20 w-14 h-14 flex items-center justify-center rounded-xl">
            <Coins className="w-6 h-6 stroke-[1.8]" />
          </div>
          <div className="stat-details relative group">
            <h3 className="text-zinc-400 text-xs font-medium mb-1">Total Cost</h3>
            <div className="value val-cost font-heading text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
              {money(stats.total_cost, 4)}
            </div>

            {/* Elegant Hover Tooltip */}
            <div className="absolute top-[calc(100%+8px)] left-1/2 -translate-x-1/2 hidden group-hover:block z-50 bg-[#18181b]/95 border border-zinc-800 text-zinc-200 p-3 rounded-lg shadow-2xl pointer-events-none backdrop-blur-md">
              <div className="font-semibold text-[10px] text-zinc-400 mb-2.5 uppercase tracking-wider border-b border-zinc-800/80 pb-1.5 text-center">Cost Breakdown</div>
              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Input</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_cost > 0 ? Math.round(((stats.prompt_cost || 0) / stats.total_cost) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-[70px] text-right">{money(stats.prompt_cost || 0, 4)}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Thinking</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_cost > 0 ? Math.round(((stats.thoughts_cost || 0) / stats.total_cost) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-[70px] text-right">{money(stats.thoughts_cost || 0, 4)}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Output</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_cost > 0 ? Math.round(((stats.completion_cost || 0) / stats.total_cost) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-[70px] text-right">{money(stats.completion_cost || 0, 4)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tokens Processed Card */}
        <div className="stat-card glass-panel p-6 pl-10 flex items-center gap-6 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-sky-500/35 hover:shadow-[0_8px_30px_rgba(14,165,233,0.15)] transition-all duration-200">
          <div className="stat-icon text-sky-400 bg-sky-500/10 border border-sky-500/20 w-14 h-14 flex items-center justify-center rounded-xl">
            <Cpu className="w-6 h-6 stroke-[1.8]" />
          </div>
          <div className="stat-details relative group">
            <h3 className="text-zinc-400 text-xs font-medium mb-1">Tokens Processed</h3>
            <div className="value val-tokens font-heading text-3xl font-bold bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent">
              {formatNumber(stats.total_tokens)}
            </div>

            {/* Elegant Hover Tooltip */}
            <div className="absolute top-[calc(100%+8px)] left-1/2 -translate-x-1/2 hidden group-hover:block z-50 bg-[#18181b]/95 border border-zinc-800 text-zinc-200 p-3 rounded-lg shadow-2xl pointer-events-none backdrop-blur-md">
              <div className="font-semibold text-[10px] text-zinc-400 mb-2.5 uppercase tracking-wider border-b border-zinc-800/80 pb-1.5">Token Breakdown</div>
              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Input</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_tokens > 0 ? Math.round((stats.prompt_tokens / stats.total_tokens) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-16 text-right">{formatNumber(stats.prompt_tokens)}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Thinking</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_tokens > 0 ? Math.round((stats.thoughts_tokens / stats.total_tokens) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-16 text-right">{formatNumber(stats.thoughts_tokens)}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-6">
                  <span className="text-zinc-400 font-sans">Output</span>
                  <div className="flex items-center">
                    <span className="text-zinc-500 w-8 text-right">%{stats.total_tokens > 0 ? Math.round((stats.completion_tokens / stats.total_tokens) * 100) : 0}</span>
                    <span className="text-zinc-200 font-medium w-16 text-right">{formatNumber(stats.completion_tokens)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Virtual Keys Card */}
        <div className="stat-card glass-panel p-6 pl-10 flex items-center gap-6 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-indigo-500/35 hover:shadow-[0_8px_30px_rgba(99,102,241,0.15)] transition-all duration-200">
          <div className="stat-icon text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 w-14 h-14 flex items-center justify-center rounded-xl">
            <Key className="w-6 h-6 stroke-[1.8]" />
          </div>
          <div className="stat-details">
            <h3 className="text-zinc-400 text-xs font-medium mb-1">Virtual Keys</h3>
            <div className="value val-keys font-heading text-3xl font-bold bg-gradient-to-r from-indigo-400 to-blue-400 bg-clip-text text-transparent">
              {stats.total_keys || 0}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
