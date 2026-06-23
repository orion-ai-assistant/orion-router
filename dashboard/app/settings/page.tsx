'use client';

import React, { useState } from 'react';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { ChevronDown, Check } from 'lucide-react';
import { SUPPORTED_LOCALES, LOCALE_NAMES, Locale } from '@/lib/i18n';

export default function SettingsPage() {
  const { showToast, updateAdminKey, t, locale, setLocale } = useApp();
  
  // Change Admin Secret states
  const [showChangeKeyModal, setShowChangeKeyModal] = useState<boolean>(false);
  const [currentSecret, setCurrentSecret] = useState<string>( '');
  const [newSecret, setNewSecret] = useState<string>('');
  const [confirmNewSecret, setConfirmNewSecret] = useState<string>('');
  const [updatingKey, setUpdatingKey] = useState<boolean>(false);
  
  // Clear logs states
  const [showClearLogsModal, setShowClearLogsModal] = useState<boolean>(false);
  const [confirmAdminKey, setConfirmAdminKey] = useState<string>('');
  const [clearing, setClearing] = useState<boolean>(false);

  // Locale dropdown states
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const [highlightedLocale, setHighlightedLocale] = useState<Locale | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const searchTimeoutRef = React.useRef<NodeJS.Timeout | null>(null);
  const dropdownRef = React.useRef<HTMLDivElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);

  const highlightedRef = React.useRef<Locale | null>(null);
  highlightedRef.current = highlightedLocale;

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setLangDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  React.useEffect(() => {
    if (langDropdownOpen) {
      setHighlightedLocale(locale as Locale);
      setSearchQuery('');
    }
  }, [langDropdownOpen, locale]);

  React.useEffect(() => {
    if (!langDropdownOpen) return;

    function normalizeString(str: string): string {
      return str
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.altKey || event.metaKey) return;

      const key = event.key;

      if (key === 'Escape') {
        event.preventDefault();
        setLangDropdownOpen(false);
        return;
      }

      if (key === 'Enter' || key === ' ') {
        event.preventDefault();
        const currentHighlight = highlightedRef.current;
        if (currentHighlight) {
          setLocale(currentHighlight);
        }
        setLangDropdownOpen(false);
        return;
      }

      if (key === 'ArrowDown') {
        event.preventDefault();
        const currentHighlight = highlightedRef.current;
        const currentIndex = currentHighlight ? SUPPORTED_LOCALES.indexOf(currentHighlight as any) : -1;
        const nextIndex = currentIndex < SUPPORTED_LOCALES.length - 1 ? currentIndex + 1 : 0;
        const nextLocale = SUPPORTED_LOCALES[nextIndex];
        setHighlightedLocale(nextLocale);
        
        const activeEl = listRef.current?.querySelector(`[data-locale="${nextLocale}"]`);
        if (activeEl) {
          activeEl.scrollIntoView({ block: 'nearest' });
        }
        return;
      }

      if (key === 'ArrowUp') {
        event.preventDefault();
        const currentHighlight = highlightedRef.current;
        const currentIndex = currentHighlight ? SUPPORTED_LOCALES.indexOf(currentHighlight as any) : -1;
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : SUPPORTED_LOCALES.length - 1;
        const prevLocale = SUPPORTED_LOCALES[prevIndex];
        setHighlightedLocale(prevLocale);

        const activeEl = listRef.current?.querySelector(`[data-locale="${prevLocale}"]`);
        if (activeEl) {
          activeEl.scrollIntoView({ block: 'nearest' });
        }
        return;
      }

      if (key.length === 1) {
        event.preventDefault();

        if (searchTimeoutRef.current) {
          clearTimeout(searchTimeoutRef.current);
        }

        const lowerKey = key.toLowerCase();
        setSearchQuery((prevQuery) => {
          let newQuery = prevQuery + lowerKey;
          const isRepeatedKey = prevQuery.length > 0 && prevQuery.split('').every(char => char === lowerKey);
          let match: Locale | null = null;
          const currentHighlight = highlightedRef.current;

          if (isRepeatedKey && lowerKey === prevQuery[0]) {
            const singleChar = lowerKey;
            const normalizedChar = normalizeString(singleChar);
            const matches = SUPPORTED_LOCALES.filter(l => {
              const name = normalizeString(LOCALE_NAMES[l] || l);
              const code = l.toLowerCase();
              return name.startsWith(normalizedChar) || code.startsWith(normalizedChar);
            });

            if (matches.length > 0) {
              const currentIndex = currentHighlight ? matches.indexOf(currentHighlight) : -1;
              const nextIndex = (currentIndex + 1) % matches.length;
              match = matches[nextIndex];
            }
            newQuery = singleChar;
          } else {
            const found = SUPPORTED_LOCALES.find(l => {
              const name = normalizeString(LOCALE_NAMES[l] || l);
              const code = l.toLowerCase();
              const normalizedQuery = normalizeString(newQuery);
              return name.startsWith(normalizedQuery) || code.startsWith(normalizedQuery);
            });
            if (found) {
              match = found;
            }
          }

          if (match) {
            setHighlightedLocale(match);
            const activeEl = listRef.current?.querySelector(`[data-locale="${match}"]`);
            if (activeEl) {
              activeEl.scrollIntoView({ block: 'nearest' });
            }
          }

          searchTimeoutRef.current = setTimeout(() => {
            setSearchQuery('');
          }, 1000);

          return newQuery;
        });
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [langDropdownOpen, setLocale]);

  const handleChangeAdminSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    const currentSec = currentSecret.trim();
    const newSec = newSecret.trim();
    const confirmNewSec = confirmNewSecret.trim();

    if (!currentSec) {
      showToast(t('settings.auth.error.currentRequired'), 'error');
      return;
    }
    if (!newSec) {
      showToast(t('settings.auth.error.newRequired'), 'error');
      return;
    }
    if (newSec !== confirmNewSec) {
      showToast(t('settings.auth.error.mismatch'), 'error');
      return;
    }

    setUpdatingKey(true);
    try {
      const res = await adminFetch('/dashboard/api/settings/admin-secret', {
        method: 'PUT',
        body: JSON.stringify({
          old_secret: currentSec,
          new_secret: newSec,
        }),
      });
      if (res.ok) {
        showToast(t('settings.passwordChanged'));
        updateAdminKey(newSec);
        setShowChangeKeyModal(false);
        setCurrentSecret('');
        setNewSecret('');
        setConfirmNewSecret('');
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || t('common.error'), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('settings.auth.error.networkUpdate'), 'error');
    } finally {
      setUpdatingKey(false);
    }
  };

  const handleClearLogs = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = confirmAdminKey.trim();
    if (!key) {
      showToast(t('settings.danger.error.keyRequired'), 'error');
      return;
    }

    setClearing(true);
    try {
      // Direct fetch bypasses global 401 interceptor that resets authentication
      const res = await fetch('/dashboard/api/logs', {
        method: 'DELETE',
        headers: {
          'X-Admin-Key': encodeURIComponent(key),
        },
      });

      if (res.ok) {
        showToast(t('settings.danger.success.cleared'));
        setShowClearLogsModal(false);
        setConfirmAdminKey('');
      } else {
        const data = await res.json().catch(() => ({}));
        if (res.status === 401) {
          showToast(t('settings.danger.error.incorrectKey'), 'error');
        } else {
          showToast(data.detail || t('settings.danger.error.failedClear'), 'error');
        }
      }
    } catch (err) {
      console.error(err);
      showToast(t('settings.danger.error.networkClear'), 'error');
    } finally {
      setClearing(false);
    }
  };

  return (
    <section id="settings" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('settings.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('settings.description')}</p>
        </div>
      </header>

      <div className="glass-panel p-8 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl max-w-2xl mb-8">
        <h2 className="font-heading text-lg font-semibold text-white mb-2">{t('settings.language.title')}</h2>
        <p className="text-zinc-400 text-sm mb-6">{t('settings.language.description')}</p>
        
        <div className="flex relative" ref={dropdownRef}>
          <button
            onClick={() => setLangDropdownOpen(!langDropdownOpen)}
            className="flex items-center justify-between bg-black/40 border border-zinc-800 text-white rounded px-4 py-2.5 min-w-[200px] outline-none hover:border-zinc-600 transition-colors"
          >
            <span>{LOCALE_NAMES[locale] || locale}</span>
            <ChevronDown className="w-4 h-4 ml-2 text-zinc-400 shrink-0" />
          </button>
          
          {langDropdownOpen && (
            <div
              ref={listRef}
              className="absolute top-[calc(100%+4px)] left-0 w-[240px] bg-zinc-900 border border-zinc-700 rounded-md shadow-2xl z-50 max-h-64 overflow-y-auto custom-scrollbar py-1"
            >
              {SUPPORTED_LOCALES.map((l) => (
                <button
                  key={l}
                  data-locale={l}
                  onMouseEnter={() => setHighlightedLocale(l)}
                  onClick={() => {
                    setLocale(l);
                    setLangDropdownOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 text-sm flex items-center justify-between transition-colors ${
                    highlightedLocale === l
                      ? 'bg-zinc-800 text-white font-medium'
                      : locale === l
                      ? 'bg-zinc-800/40 text-white/95 font-medium'
                      : 'text-zinc-300'
                  }`}
                >
                  <span dir="auto">{LOCALE_NAMES[l] || l}</span>
                  {locale === l && <Check className="w-4 h-4 text-emerald-500 shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel p-8 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl max-w-2xl">
        <h2 className="font-heading text-lg font-semibold text-white mb-2">{t('settings.auth.title')}</h2>
        <p className="text-zinc-400 text-sm mb-6">{t('settings.auth.description')}</p>
        
        <div className="flex">
          <Button
            type="button"
            onClick={() => setShowChangeKeyModal(true)}
            className="bg-white text-black hover:bg-zinc-200 font-semibold px-6 py-2.5 rounded transition-all duration-200 shadow-md"
          >
            {t('settings.auth.updateBtn')}
          </Button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="glass-panel p-8 bg-[#18181b] border border-red-950/20 rounded-md shadow-xl max-w-2xl mt-8">
        <h2 className="font-heading text-lg font-semibold text-red-500 mb-2">{t('settings.danger.title')}</h2>
        <p className="text-zinc-400 text-sm mb-6">
          {t('settings.danger.description')}
        </p>
        
        <div className="flex">
          <Button
            type="button"
            onClick={() => setShowClearLogsModal(true)}
            className="bg-red-950/20 hover:bg-red-900/30 text-red-400 border border-red-500/25 font-semibold px-6 py-2.5 rounded transition-all duration-200 shadow-md"
          >
            {t('settings.danger.resetBtn')}
          </Button>
        </div>
      </div>

      {/* Confirm Clear Logs Dialog */}
      <Dialog open={showClearLogsModal} onOpenChange={setShowClearLogsModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('settings.danger.resetStats')}</DialogTitle>
            <DialogDescription className="text-zinc-400 text-sm mt-2">
              {t('settings.danger.confirmReset')}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleClearLogs} className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('settings.auth.verifyAdminSecret')}</label>
              <Input
                type="password"
                value={confirmAdminKey}
                onChange={(e) => setConfirmAdminKey(e.target.value)}
                placeholder={t('settings.auth.enterAdminKeyToConfirm')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                type="button"
                variant="outline"
                disabled={clearing}
                onClick={() => {
                  setShowClearLogsModal(false);
                  setConfirmAdminKey('');
                }}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                disabled={clearing}
                className="bg-red-600 hover:bg-red-700 text-white rounded font-medium border border-red-700/30 flex items-center justify-center min-w-[120px]"
              >
                {clearing ? t('common.loading') : t('common.confirm')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Change Admin Secret Dialog */}
      <Dialog open={showChangeKeyModal} onOpenChange={setShowChangeKeyModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('settings.auth.updateBtn')}</DialogTitle>
            <DialogDescription className="text-zinc-400 text-sm mt-2">
              {t('settings.auth.description')}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleChangeAdminSecret} className="flex flex-col gap-4 my-4">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">{t('settings.auth.currentAdminSecret')}</label>
              <Input
                type="password"
                value={currentSecret}
                onChange={(e) => setCurrentSecret(e.target.value)}
                placeholder={t('settings.auth.enterCurrentSecret')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">{t('settings.auth.newAdminSecret')}</label>
              <Input
                type="password"
                value={newSecret}
                onChange={(e) => setNewSecret(e.target.value)}
                placeholder={t('settings.auth.enterNewSecret')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-450 text-sm font-medium">{t('settings.auth.confirmNewAdminSecret')}</label>
              <Input
                type="password"
                value={confirmNewSecret}
                onChange={(e) => setConfirmNewSecret(e.target.value)}
                placeholder={t('settings.auth.reEnterNewSecret')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
                required
              />
            </div>
            
            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                type="button"
                variant="outline"
                disabled={updatingKey}
                onClick={() => {
                  setShowChangeKeyModal(false);
                  setCurrentSecret('');
                  setNewSecret('');
                  setConfirmNewSecret('');
                }}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                disabled={updatingKey}
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium flex items-center justify-center min-w-[120px]"
              >
                {updatingKey ? t('common.loading') : t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
