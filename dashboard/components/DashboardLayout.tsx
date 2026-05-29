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
  LogOut
} from 'lucide-react';

interface SidebarTab {
  id: string;
  label: string;
  icon: React.ComponentType<any>;
  url: string;
}

const TABS: SidebarTab[] = [
  { id: 'dashboard', label: 'Overview', icon: LayoutDashboard, url: '/' },
  { id: 'keys', label: 'Virtual Keys', icon: Key, url: '/keys' },
  { id: 'logs', label: 'Logs', icon: FileText, url: '/logs' },
  { id: 'key-pool', label: 'Provider Keys', icon: Lock, url: '/key-pool' },
  { id: 'models', label: 'Models', icon: Bot, url: '/models' },
  { id: 'groups', label: 'Groups', icon: Network, url: '/groups' },
  { id: 'playground', label: 'Playground', icon: Terminal, url: '/playground' },
  { id: 'model-info', label: 'Model Info', icon: Info, url: '/model-info' },
  { id: 'settings', label: 'Settings', icon: Settings, url: '/settings' }
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { isAuthenticated, logout } = useApp();

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
      <div className="min-h-screen bg-[#121212] flex items-center justify-center">
        {/* Authentication dialog will be opened by AppProvider */}
      </div>
    );
  }

  return (
    <div className="app-container flex h-[calc(100vh/1.1)] overflow-hidden p-6 gap-6 max-w-[1600px] mx-auto">
      {/* Sidebar Navigation */}
      <aside className="sidebar w-[280px] pt-6 px-6 pb-3 glass-panel flex flex-col shrink-0 h-full">
        <div className="logo flex items-center gap-3.5 px-2 mb-6">
          <div className="logo-icon"></div>
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
                  <span>{tab.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Logout button at bottom of sidebar */}
        <div className="mt-auto pt-4 border-t border-zinc-800">
          <button
            onClick={logout}
            className="flex w-full items-center gap-3.5 px-5 py-3 rounded-md cursor-pointer transition-all duration-200 font-medium text-[14px] text-red-400/80 hover:bg-red-950/20 hover:text-red-400"
          >
            <LogOut className="w-[18px] h-[18px]" />
            <span>Sign Out</span>
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
