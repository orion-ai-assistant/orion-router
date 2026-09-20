'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { getAdminKey, setAdminKey, UNAUTHORIZED_EVENT, adminFetch } from '@/lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AlertCircle, CheckCircle, AlertTriangle, X, Sparkles, CheckCircle2 } from 'lucide-react';
import { 
  detectLocale, 
  loadLocale, 
  createTranslator, 
  FALLBACK_LOCALE,
  LOCALE_STORAGE_KEY,
  TranslatorFunction,
  isValidLocale,
  RTL_LOCALES
} from '@/lib/i18n';

export type ToastType = 'success' | 'error';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ConfirmDialogState {
  show: boolean;
  message: string;
  callback: (() => void) | null;
}

export interface BannerPreset {
  id: string;
  style: React.CSSProperties;
}

export const BANNER_PRESETS: BannerPreset[] = [
  {
    id: 'default',
    style: {
      backgroundImage: "url('/dashboard/static/images/dashboard_banner.png')",
      backgroundSize: 'cover',
      backgroundPosition: 'center 30%',
      backgroundRepeat: 'no-repeat',
    }
  },
  {
    id: 'preset-neon',
    style: {
      backgroundColor: '#09090b',
      backgroundImage: `
        linear-gradient(to right, rgba(236, 72, 153, 0.12) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(236, 72, 153, 0.12) 1px, transparent 1px),
        linear-gradient(135deg, #09090b 0%, #1e1b4b 30%, #4c1d95 70%, #09090b 100%)
      `,
      backgroundSize: '40px 40px, 40px 40px, 100% 100%',
      backgroundPosition: 'center center',
      backgroundRepeat: 'repeat, repeat, no-repeat',
    }
  },
  {
    id: 'preset-network',
    style: {
      backgroundColor: '#18181b',
      backgroundImage: `
        radial-gradient(circle at 20% 30%, rgba(99, 102, 241, 0.15) 0%, transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(14, 165, 233, 0.15) 0%, transparent 40%),
        radial-gradient(1.5px 1.5px at 40px 60px, rgba(255, 255, 255, 0.25) 100%, transparent),
        radial-gradient(1.5px 1.5px at 120px 150px, rgba(255, 255, 255, 0.2) 100%, transparent),
        radial-gradient(1.5px 1.5px at 220px 80px, rgba(255, 255, 255, 0.25) 100%, transparent),
        radial-gradient(1.5px 1.5px at 320px 120px, rgba(255, 255, 255, 0.2) 100%, transparent),
        radial-gradient(1.5px 1.5px at 420px 40px, rgba(255, 255, 255, 0.25) 100%, transparent),
        radial-gradient(1.5px 1.5px at 520px 140px, rgba(255, 255, 255, 0.2) 100%, transparent),
        linear-gradient(135deg, #121214 0%, #18181b 100%)
      `,
      backgroundSize: '100% 100%, 100% 100%, 120px 180px, 200px 200px, 150px 150px, 250px 250px, 180px 180px, 300px 300px, 100% 100%',
      backgroundPosition: 'center, center, 0 0, 40px 60px, 130px 10px, 70px 220px, 20px 80px, 110px 190px, center',
      backgroundRepeat: 'no-repeat, no-repeat, repeat, repeat, repeat, repeat, repeat, repeat, no-repeat',
    }
  },
  {
    id: 'preset-forest',
    style: {
      backgroundImage: "url('/dashboard/static/images/forest_banner.png')",
      backgroundSize: 'cover',
      backgroundPosition: 'center 30%',
      backgroundRepeat: 'no-repeat',
    }
  }
];

export interface VersionInfo {
  current_version: string;
  latest_version: string;
  update_available: boolean;
  behind_commits?: number;
  release_notes?: string;
  release_url?: string;
  is_git_repo?: boolean;
  last_checked?: string;
}

interface AppContextType {
  adminKey: string;
  isAuthenticated: boolean;
  isDefaultPassword: boolean;
  showToast: (message: string, type?: ToastType) => void;
  confirmAction: (message: string, callback: () => void) => void;
  logout: () => void;
  updateAdminKey: (key: string) => void;
  locale: string;
  setLocale: (lang: string) => void;
  t: TranslatorFunction;
  bannerStyle: React.CSSProperties;
  activeBannerId: string;
  updateActiveBannerId: (id: string) => void;
  versionInfo: VersionInfo | null;
  refreshVersionInfo: (force?: boolean) => Promise<VersionInfo | null>;
  isUpdateModalOpen: boolean;
  setIsUpdateModalOpen: (open: boolean) => void;
  updateRunning: boolean;
  updateStep: string;
  updateProgress: number;
  updateLogs: string[];
  updateError: string | null;
  updateSuccess: boolean;
  startSystemUpdate: () => Promise<void>;
  closeUpdateModal: () => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [adminKey, setAdminKeyState] = useState<string>('');
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isDefaultPassword, setIsDefaultPassword] = useState<boolean>(false);
  const [defaultPasswordValue, setDefaultPasswordValue] = useState<string>('');
  const [showLogin, setShowLogin] = useState<boolean>(false);
  const [adminKeyInput, setAdminKeyInput] = useState<string>('');
  const [loginError, setLoginError] = useState<string>('');

  // Banner State
  const [activeBannerId, setActiveBannerId] = useState<string>('default');
  const [bannerStyle, setBannerStyle] = useState<React.CSSProperties>(BANNER_PRESETS[0].style);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedBannerId = localStorage.getItem('orion-active-banner-id') || 'default';
      setActiveBannerId(savedBannerId);
      const preset = BANNER_PRESETS.find(p => p.id === savedBannerId) || BANNER_PRESETS[0];
      setBannerStyle(preset.style);
    }
  }, []);

  const updateActiveBannerId = (id: string) => {
    setActiveBannerId(id);
    const preset = BANNER_PRESETS.find(p => p.id === id) || BANNER_PRESETS[0];
    setBannerStyle(preset.style);
    if (typeof window !== 'undefined') {
      localStorage.setItem('orion-active-banner-id', id);
    }
  };

  // Toasts State
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Confirm State
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState>({
    show: false,
    message: '',
    callback: null,
  });

  // i18n State
  const [locale, setLocaleState] = useState<string>(FALLBACK_LOCALE);
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [fallbackTranslations, setFallbackTranslations] = useState<Record<string, string>>({});
  const [i18nReady, setI18nReady] = useState<boolean>(false);

  const t = createTranslator(translations, fallbackTranslations);

  // System Version & Updates State
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState<boolean>(false);
  const [updateRunning, setUpdateRunning] = useState<boolean>(false);
  const [updateStep, setUpdateStep] = useState<string>('idle');
  const [updateProgress, setUpdateProgress] = useState<number>(0);
  const [updateLogs, setUpdateLogs] = useState<string[]>([]);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState<boolean>(false);
  const updateLogsEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (updateLogsEndRef.current) {
      updateLogsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [updateLogs]);

  const closeUpdateModal = () => {
    if (!updateRunning) {
      setIsUpdateModalOpen(false);
    }
  };

  const startSystemUpdate = async () => {
    setIsUpdateModalOpen(true);
    setUpdateRunning(true);
    setUpdateStep('started');
    setUpdateProgress(10);
    setUpdateLogs([]);
    setUpdateError(null);
    setUpdateSuccess(false);

    try {
      const res = await adminFetch('/dashboard/api/system/update', {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Güncelleme başlatılamadı');
      }

      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await adminFetch('/dashboard/api/system/update-status');
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            setUpdateStep(statusData.step || 'started');
            setUpdateProgress(statusData.progress || 10);
            if (statusData.logs) {
              setUpdateLogs(statusData.logs);
            }
            if (statusData.error) {
              setUpdateError(statusData.error);
              setUpdateRunning(false);
              clearInterval(pollInterval);
            } else if (statusData.success || statusData.step === 'completed') {
              setUpdateSuccess(true);
              setUpdateRunning(false);
              clearInterval(pollInterval);

              setTimeout(() => {
                const reloadInterval = setInterval(async () => {
                  try {
                    const health = await fetch('/health');
                    if (health.ok) {
                      clearInterval(reloadInterval);
                      window.location.reload();
                    }
                  } catch {}
                }, 1000);
              }, 2000);
            }
          }
        } catch (pollErr) {
          console.log('Update poll ping:', pollErr);
        }
      }, 1000);
    } catch (err: any) {
      setUpdateError(err.message || 'Güncelleme hatası');
      setUpdateRunning(false);
    }
  };

  const refreshVersionInfo = async (force: boolean = false): Promise<VersionInfo | null> => {
    try {
      const url = force ? '/dashboard/api/system/version?check_now=true' : '/dashboard/api/system/version';
      const res = await fetch(url);
      if (res.ok) {
        const data: VersionInfo = await res.json();
        setVersionInfo(data);
        return data;
      }
    } catch (e) {
      console.warn('Failed to fetch system version info', e);
    }
    return null;
  };

  useEffect(() => {
    if (isAuthenticated) {
      refreshVersionInfo(false);
    }
  }, [isAuthenticated]);

  // Check default password status on load
  const checkPasswordStatus = async () => {
    try {
      const res = await fetch('/dashboard/api/settings/is-default-password');
      if (res.ok) {
        const data = await res.json();
        setIsDefaultPassword(data.is_default);
        if (data.default_password) {
          setDefaultPasswordValue(data.default_password);
        }
      }
    } catch (err) {
      console.error("Error checking password status:", err);
    }
  };

  useEffect(() => {
    checkPasswordStatus();
    
    // Check if key exists in storage
    const key = getAdminKey();
    if (!key) {
      setShowLogin(true);
    } else {
      setAdminKeyState(key);
      setIsAuthenticated(true);
    }

    // Listen to unauthorized event
    const handleUnauthorized = () => {
      setIsAuthenticated(false);
      setAdminKeyState('');
      setAdminKey(null as any);
      setShowLogin(true);
    };

    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    
    // Load i18n
    const initI18n = async () => {
      const detected = detectLocale();
      setLocaleState(detected);

      const [fallback, current] = await Promise.all([
        loadLocale(FALLBACK_LOCALE),
        detected === FALLBACK_LOCALE ? Promise.resolve({}) : loadLocale(detected)
      ]);

      setFallbackTranslations(fallback);
      if (detected === FALLBACK_LOCALE) {
        setTranslations(fallback);
      } else {
        setTranslations(current);
      }
      setI18nReady(true);
    };
    initI18n();

    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    };
  }, []);

  // Update HTML lang and dir when locale changes
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = 'ltr'; // Keep layout LTR so it doesn't mirror
    
    if (RTL_LOCALES.includes(locale)) {
      document.body.classList.add('rtl-language');
    } else {
      document.body.classList.remove('rtl-language');
    }
  }, [locale]);

  const setLocale = async (lang: string) => {
    if (!isValidLocale(lang)) return;
    
    localStorage.setItem(LOCALE_STORAGE_KEY, lang);
    setLocaleState(lang);
    
    if (lang === FALLBACK_LOCALE) {
      setTranslations(fallbackTranslations);
    } else {
      const newTranslations = await loadLocale(lang);
      setTranslations(newTranslations);
    }
  };

  const login = async () => {
    const key = adminKeyInput.trim();
    if (!key) return;
    setLoginError('');

    try {
      // Temporarily set it in session to test if it's correct
      setAdminKey(key);
      const res = await fetch('/dashboard/api/stats', {
        headers: { 'X-Admin-Key': encodeURIComponent(key) }
      });
      if (res.ok) {
        setAdminKeyState(key);
        setIsAuthenticated(true);
        setShowLogin(false);
        setAdminKeyInput('');
        // Reload page data
        window.dispatchEvent(new Event('orion-authenticated'));
      } else {
        setLoginError(t('auth.invalidKey'));
        setAdminKey('');
      }
    } catch (err) {
      setLoginError(t('auth.failed'));
      setAdminKey('');
    }
  };

  const logout = () => {
    setAdminKey('');
    setAdminKeyState('');
    setIsAuthenticated(false);
    setShowLogin(true);
  };

  const updateAdminKey = (key: string) => {
    setAdminKey(key);
    setAdminKeyState(key);
    setIsAuthenticated(!!key);
    checkPasswordStatus();
  };

  // Toast helper
  const showToast = (message: string, type: ToastType = 'success') => {
    const id = Date.now() + Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Confirm helper
  const confirmAction = (message: string, callback: () => void) => {
    setConfirmDialog({
      show: true,
      message,
      callback,
    });
  };

  const executeConfirm = () => {
    if (confirmDialog.callback) {
      confirmDialog.callback();
    }
    setConfirmDialog((prev) => ({ ...prev, show: false }));
  };

  if (!i18nReady) {
    return (
      <div className="fixed inset-0 bg-[#09090b] flex items-center justify-center text-white font-sans">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-zinc-800 border-t-white rounded-full animate-spin"></div>
          <span className="text-xs text-zinc-400 tracking-wider">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <AppContext.Provider value={{
      adminKey,
      isAuthenticated,
      isDefaultPassword,
      showToast,
      confirmAction,
      logout,
      updateAdminKey,
      locale,
      setLocale,
      t,
      bannerStyle,
      activeBannerId,
      updateActiveBannerId,
      versionInfo,
      refreshVersionInfo,
      isUpdateModalOpen,
      setIsUpdateModalOpen,
      updateRunning,
      updateStep,
      updateProgress,
      updateLogs,
      updateError,
      updateSuccess,
      startSystemUpdate,
      closeUpdateModal
    }}>
      {children}

      {/* Admin Login Dialog */}
      <Dialog open={showLogin} onOpenChange={() => {}} modal>
        <DialogContent
          showCloseButton={false}
          className="max-w-[500px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl"
        >
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('auth.title')}</DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-1.5 leading-relaxed">
              {t('auth.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="my-4">
            <Input
              type="password"
              value={adminKeyInput}
              onChange={(e) => setAdminKeyInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && login()}
              placeholder={t('auth.passwordPlaceholder')}
              className="bg-black/40 border border-zinc-800 text-white rounded px-4 py-3 w-full"
            />
            {loginError && (
              <div className="mt-3 text-red-500 bg-red-950/20 border border-red-500/30 rounded p-3 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{loginError}</span>
              </div>
            )}
            {isDefaultPassword && (
              <div className="mt-3 w-full [container-type:inline-size]">
                <div 
                  className="text-zinc-500 text-center leading-relaxed whitespace-nowrap overflow-hidden text-ellipsis flex items-center justify-center gap-1.5"
                  style={{ fontSize: 'clamp(8px, 2.6cqw, 11px)' }}
                >
                  <span>{t('auth.defaultPasswordInfo')}</span>
                  <code 
                    className="px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-white font-mono cursor-pointer hover:bg-zinc-800 hover:border-zinc-700 transition-colors active:scale-95 duration-100 inline-block align-middle" 
                    style={{ fontSize: 'clamp(8px, 2.6cqw, 11px)' }}
                    title={t('common.copy')} 
                    onClick={() => { 
                      navigator.clipboard.writeText(defaultPasswordValue); 
                      showToast(t('common.copied'), 'success'); 
                    }}
                  >
                    {defaultPasswordValue}
                  </code>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="mt-4">
            <Button
              onClick={login}
              className="w-full bg-white text-black hover:bg-zinc-200 font-medium py-3 rounded-md transition-all shadow-lg hover:shadow-xl"
            >
              {t('auth.unlock')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Global Confirm Dialog */}
      <Dialog
        open={confirmDialog.show}
        onOpenChange={(show) => setConfirmDialog((prev) => ({ ...prev, show }))}
        onOpenChangeComplete={(open) => {
          if (!open) {
            setConfirmDialog({ show: false, message: '', callback: null });
          }
        }}
      >
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-6 rounded-2xl text-center glass-panel text-white shadow-2xl">
          <div className="flex flex-col items-center justify-center">
            <div className="text-red-500 mb-4 bg-red-950/30 border border-red-500/20 w-16 h-16 rounded-full flex items-center justify-center">
              <AlertTriangle className="w-8 h-8" />
            </div>
            <DialogHeader>
              <DialogTitle className="text-lg font-heading font-semibold text-white">{t('common.confirm')}</DialogTitle>
              <DialogDescription className="text-zinc-400 text-sm mt-2">
                {confirmDialog.message}
              </DialogDescription>
            </DialogHeader>
          </div>
          <DialogFooter className="mt-6 flex justify-center gap-3 w-full">
            <Button
              variant="outline"
              onClick={() => setConfirmDialog((prev) => ({ ...prev, show: false }))}
              className="border-zinc-800 text-white hover:bg-zinc-900 rounded-md font-medium"
            >
              {t('common.cancel')}
            </Button>
            <Button
              onClick={executeConfirm}
              className="bg-red-600 hover:bg-red-700 text-white rounded-md font-medium border border-red-700/30"
            >
              {t('common.yes')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Global System Update Modal */}
      <Dialog open={isUpdateModalOpen} onOpenChange={(open) => {
        if (!updateRunning) setIsUpdateModalOpen(open);
      }}>
        <DialogContent className="max-w-[550px] border border-border bg-zinc-950 p-6 rounded-2xl glass-panel text-white shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-emerald-400" />
              <span>{t('settings.system.modalTitle')}</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-1">
              {updateSuccess ? t('settings.system.completed') : t('settings.system.modalDesc')}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 my-4">
            {/* Progress Bar */}
            <div className="w-full bg-zinc-900 h-2 rounded-full overflow-hidden border border-zinc-800">
              <div
                className={`h-full transition-all duration-500 ${
                  updateSuccess 
                    ? 'bg-emerald-500' 
                    : updateError 
                    ? 'bg-red-500' 
                    : 'bg-blue-500 animate-pulse'
                }`}
                style={{ width: `${updateProgress}%` }}
              />
            </div>

            {/* Steps pills */}
            <div className="grid grid-cols-4 gap-2 text-center text-[11px] font-medium">
              <div className={`p-1.5 rounded border ${updateProgress >= 15 ? 'bg-blue-950/40 border-blue-500/40 text-blue-300' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
                1. {t('settings.system.stepGit')}
              </div>
              <div className={`p-1.5 rounded border ${updateProgress >= 40 ? 'bg-blue-950/40 border-blue-500/40 text-blue-300' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
                2. {t('settings.system.stepDeps')}
              </div>
              <div className={`p-1.5 rounded border ${updateProgress >= 70 ? 'bg-blue-950/40 border-blue-500/40 text-blue-300' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
                3. {t('settings.system.stepBuild')}
              </div>
              <div className={`p-1.5 rounded border ${updateProgress >= 95 ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
                4. {t('settings.system.stepRestart')}
              </div>
            </div>

            {/* Live Terminal Console Box */}
            <div className="bg-black/90 border border-zinc-800 rounded-lg p-3 font-mono text-[11px] text-zinc-300 h-52 overflow-y-auto custom-scrollbar flex flex-col gap-1">
              {updateLogs.length === 0 && (
                <div className="text-zinc-600 italic">Hazırlanıyor...</div>
              )}
              {updateLogs.map((log, index) => (
                <div key={index} className="leading-tight break-all">
                  {log.includes('✔') ? (
                    <span className="text-emerald-400">{log}</span>
                  ) : log.includes('HATA') || log.includes('error') ? (
                    <span className="text-red-400">{log}</span>
                  ) : log.startsWith('$') ? (
                    <span className="text-blue-400 font-semibold">{log}</span>
                  ) : (
                    <span>{log}</span>
                  )}
                </div>
              ))}
              <div ref={updateLogsEndRef} />
            </div>

            {/* Status alerts */}
            {updateError && (
              <div className="bg-red-950/30 border border-red-500/30 text-red-300 p-3 rounded-md text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                <span>{updateError}</span>
              </div>
            )}

            {updateSuccess && (
              <div className="bg-emerald-950/30 border border-emerald-500/30 text-emerald-300 p-3 rounded-md text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                <span>{t('settings.system.completed')} {t('settings.system.reloading')}</span>
              </div>
            )}
          </div>

          <DialogFooter className="flex justify-end gap-2">
            {!updateRunning && (
              <Button
                type="button"
                onClick={() => setIsUpdateModalOpen(false)}
                className="border-zinc-800 bg-zinc-900 text-white hover:bg-zinc-800 text-xs px-4"
              >
                {t('common.cancel')}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Toast Notifications Container */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-3 z-[9999] pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-center gap-3 px-5 py-4 rounded-lg bg-zinc-950 text-white border border-zinc-800 shadow-xl pointer-events-auto min-w-[300px] animate-in slide-in-from-right duration-300 ${
              toast.type === 'success' ? 'border-l-4 border-l-emerald-500' : 'border-l-4 border-l-red-500'
            }`}
          >
            {toast.type === 'success' ? (
              <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
            )}
            <div className="flex-1 text-sm font-medium">{toast.message}</div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-zinc-400 hover:text-white p-1 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
