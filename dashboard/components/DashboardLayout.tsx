'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useApp } from './AppContext';
import {
  LayoutDashboard,
  Key,
  FileText,
  Lock,
  Bot,
  Network,
  Terminal,
  Info,
  Settings,
  LogOut,
  ArrowUpRight
} from 'lucide-react';

interface SidebarTab {
  id: string;
  i18nKey: string;
  icon: React.ComponentType<any>;
  url: string;
}

const TABS: SidebarTab[] = [
  { id: 'dashboard', i18nKey: 'nav.overview', icon: LayoutDashboard, url: '/' },
  { id: 'keys', i18nKey: 'nav.keys', icon: Key, url: '/keys' },
  { id: 'logs', i18nKey: 'nav.logs', icon: FileText, url: '/logs' },
  { id: 'key-pool', i18nKey: 'nav.providerKeys', icon: Lock, url: '/key-pool' },
  { id: 'models', i18nKey: 'nav.models', icon: Bot, url: '/models' },
  { id: 'groups', i18nKey: 'nav.groups', icon: Network, url: '/groups' },
  { id: 'playground', i18nKey: 'nav.playground', icon: Terminal, url: '/playground' },
  { id: 'settings', i18nKey: 'nav.settings', icon: Settings, url: '/settings' }
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { isAuthenticated, logout, t, versionInfo, startSystemUpdate } = useApp();

  // Normalize path because pathname might have trailing slash or not
  const isActive = (tabUrl: string) => {
    // If it's the root tab '/'
    if (tabUrl === '/') {
      return pathname === '/' || pathname === '';
    }
    // For other tabs, check if pathname starts with tabUrl or equal
    return pathname.replace(/\/$/, '') === tabUrl;
  };

  if (!isAuthenticated) {
    return (
      <div className="fixed inset-0 z-0 overflow-hidden bg-[#121212]" aria-hidden="true" />
    );
  }

  return (
    <div className="app-container flex h-[calc(100vh/1.1)] overflow-hidden p-6 gap-6 max-w-[1600px] mx-auto">
      {/* Sidebar Navigation */}
      <aside className="sidebar w-[280px] pt-6 px-6 pb-3 glass-panel flex flex-col shrink-0 h-full">
        <div className="logo flex items-center gap-3.5 px-2 mb-6">
          <img src="/dashboard/favicon.svg" alt="Orion Logo" className="w-9 h-9 shrink-0 object-contain" />
          <h2 className="font-heading text-xl font-semibold tracking-wide">
            Orion<span className="font-light text-zinc-400">Gateway</span>
          </h2>
        </div>

        <ul className="nav-links flex flex-col gap-2 list-none overflow-y-auto custom-scrollbar pr-2 flex-1 mb-4">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = isActive(tab.url);
            return (
              <li key={tab.id}>
                <Link
                  href={tab.url}
                  className={`flex items-center gap-3.5 px-5 py-3.5 rounded-md cursor-pointer transition-all duration-200 font-medium text-[15px] ${active
                    ? 'bg-zinc-800 text-white border-l-3 border-l-zinc-300'
                    : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-white'
                    }`}
                >
                  <Icon className="w-[18px] h-[18px] shrink-0" />
                  <span>{t(tab.i18nKey)}</span>
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Version & Update area */}
        <div className="mt-auto pt-3 pb-2.5 border-t border-zinc-800/80 flex flex-col gap-1.5 px-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-500 font-mono text-[12px] tracking-tight">
              v{versionInfo?.current_version || '0.1.0'}
            </span>
            {versionInfo?.update_available && (
              <button
                type="button"
                onClick={startSystemUpdate}
                className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-950/50 hover:bg-emerald-900/60 border border-emerald-500/30 px-2 py-0.5 rounded-full transition-all duration-200 group cursor-pointer"
                title={`${t('settings.system.updateAvailable')}: v${versionInfo.latest_version}`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>v{versionInfo.latest_version} Güncelle</span>
                <ArrowUpRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </button>
            )}
          </div>
        </div>

        {/* Logout button at bottom of sidebar */}
        <div className="pt-1">
          <button
            onClick={logout}
            className="flex w-full items-center gap-3.5 px-5 py-3 rounded-md cursor-pointer transition-all duration-200 font-medium text-[14px] text-red-400/80 hover:bg-red-950/20 hover:text-red-400"
          >
            <LogOut className="w-[18px] h-[18px]" />
            <span>{t('nav.signOut')}</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="content-area flex-1 overflow-y-auto overflow-x-hidden h-full custom-scrollbar pr-4">
        <div className="animate-in fade-in slide-in-from-bottom-3 duration-300 pb-10">
          {children}
        </div>
      </main>
    </div>
  );
}
