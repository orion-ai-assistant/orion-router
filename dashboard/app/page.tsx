'use client';

import React, { useState, useEffect } from 'react';
import { adminFetch } from '@/lib/api';
import { money, formatNumber } from '@/lib/utils';

interface Stats {
  total_cost: number;
  total_tokens: number;
  total_keys: number;
}

export default function OverviewPage() {
  const [stats, setStats] = useState<Stats>({
    total_cost: 0,
    total_tokens: 0,
    total_keys: 0,
  });

  const loadStats = async () => {
    try {
      const res = await adminFetch('/dashboard/api/stats');
      if (res.ok) {
        const data = await res.json();
        setStats({
          total_cost: data.total_cost || 0,
          total_tokens: data.total_tokens || 0,
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
        <div className="stat-card glass-panel p-6 flex items-center gap-5 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-blue-500/35 hover:shadow-[0_8px_30px_rgba(59,130,246,0.12)] transition-all duration-200">
          <div className="stat-icon text-2xl font-semibold text-[#60a5fa] bg-[#3b82f6]/8 border border-[#3b82f6]/18 w-16 h-16 flex items-center justify-center rounded">
            $
          </div>
          <div className="stat-details">
            <h3 className="text-zinc-400 text-xs font-medium mb-1">Total Cost</h3>
            <div className="value val-cost font-heading text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
              {money(stats.total_cost, 4)}
            </div>
          </div>
        </div>

        {/* Tokens Processed Card */}
        <div className="stat-card glass-panel p-6 flex items-center gap-5 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-blue-500/35 hover:shadow-[0_8px_30px_rgba(59,130,246,0.12)] transition-all duration-200">
          <div className="stat-icon text-2xl font-semibold text-[#60a5fa] bg-[#3b82f6]/8 border border-[#3b82f6]/18 w-16 h-16 flex items-center justify-center rounded">
            T
          </div>
          <div className="stat-details">
            <h3 className="text-zinc-400 text-xs font-medium mb-1">Tokens Processed</h3>
            <div className="value val-tokens font-heading text-3xl font-bold bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent">
              {formatNumber(stats.total_tokens)}
            </div>
          </div>
        </div>

        {/* Virtual Keys Card */}
        <div className="stat-card glass-panel p-6 flex items-center gap-5 bg-[#131315] border border-white/5 rounded-md hover:translate-y-[-2px] hover:bg-[#18181b] hover:border-blue-500/35 hover:shadow-[0_8px_30px_rgba(59,130,246,0.12)] transition-all duration-200">
          <div className="stat-icon text-2xl font-semibold text-[#60a5fa] bg-[#3b82f6]/8 border border-[#3b82f6]/18 w-16 h-16 flex items-center justify-center rounded">
            K
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
