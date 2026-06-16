'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { getAdminKey, setAdminKey, UNAUTHORIZED_EVENT } from '@/lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AlertCircle, CheckCircle, AlertTriangle, X } from 'lucide-react';
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

  const t = createTranslator(translations, fallbackTranslations);

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

  return (
    <AppContext.Provider value={{ adminKey, isAuthenticated, isDefaultPassword, showToast, confirmAction, logout, updateAdminKey, locale, setLocale, t }}>
      {children}

      {/* Admin Login Dialog */}
      <Dialog open={showLogin} onOpenChange={() => {}} modal>
        <DialogContent
          showCloseButton={false}
          className="max-w-[440px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl"
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
              <div className="mt-3 text-zinc-500 text-[11px] text-center leading-relaxed">
                {t('auth.defaultPasswordInfo')} <code className="ml-1.5 px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-white font-mono text-[11px] cursor-pointer hover:bg-zinc-800 hover:border-zinc-700 transition-colors active:scale-95 duration-100 inline-block align-middle" title={t('common.copy')} onClick={() => { navigator.clipboard.writeText(defaultPasswordValue); showToast(t('common.copied'), 'success'); }}>{defaultPasswordValue}</code>
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
