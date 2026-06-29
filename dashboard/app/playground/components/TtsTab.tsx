'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { adminFetch, getAdminKey } from '@/lib/api';

interface RouteOption {
  value: string;
  label: string;
}

interface TtsTabProps {
  models: any[];
  groups: any[];
}

export default function TtsTab({ models, groups }: TtsTabProps) {
  const { showToast, locale, t } = useApp();

  const getSavedState = (key: string, defaultVal: string) => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || defaultVal;
    }
    return defaultVal;
  };

  // TTS State
  const [ttsModel, setTtsModel] = useState(getSavedState('pg_ttsModel', ''));
  const savedTtsModel = getSavedState('pg_ttsModel', '');
  const initialTtsModelRef = useRef<string | null>(savedTtsModel);
  const lastTtsModelRef = useRef<string | null>(savedTtsModel);
  const [ttsVoice, setTtsVoice] = useState(getSavedState('pg_ttsVoice', 'alloy'));
  const [ttsTemp, setTtsTemp] = useState(getSavedState('pg_ttsTemp', ''));
  const [ttsSpeed, setTtsSpeed] = useState(getSavedState('pg_ttsSpeed', '1.0'));
  const [ttsLanguage, setTtsLanguage] = useState(getSavedState('pg_ttsLanguage', 'Auto'));
  const [ttsSteps, setTtsSteps] = useState(getSavedState('pg_ttsSteps', '15'));
  const [ttsSeed, setTtsSeed] = useState(getSavedState('pg_ttsSeed', '-1'));
  const [ttsGender, setTtsGender] = useState(getSavedState('pg_ttsGender', 'Auto'));
  const [ttsAge, setTtsAge] = useState(getSavedState('pg_ttsAge', 'Auto'));
  const [ttsPitch, setTtsPitch] = useState(getSavedState('pg_ttsPitch', 'Auto'));
  const [ttsStyle, setTtsStyle] = useState(getSavedState('pg_ttsStyle', 'Auto'));
  const [ttsAccent, setTtsAccent] = useState(getSavedState('pg_ttsAccent', 'Auto'));
  const [ttsDialect, setTtsDialect] = useState(getSavedState('pg_ttsDialect', 'Auto'));
  const [showCharacterDesign, setShowCharacterDesign] = useState(false);
  const [showStreamingSettings, setShowStreamingSettings] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [showSpeechStyle, setShowSpeechStyle] = useState(true);
  const [isLocalTts, setIsLocalTts] = useState(false);
  const [ttsInput, setTtsInput] = useState('');
  const [ttsUrl, setTtsUrl] = useState('');
  const [ttsError, setTtsError] = useState('');
  const [isGeneratingTTS, setIsGeneratingTTS] = useState(false);
  const ttsAbortControllerRef = useRef<AbortController | null>(null);

  // Custom tts_instruct and active engine info state for local TTS
  const [ttsInstruct, setTtsInstruct] = useState(getSavedState('pg_ttsInstruct', ''));
  const [localTtsInfo, setLocalTtsInfo] = useState<{
    active: boolean;
    engine: string | null;
  }>({ active: false, engine: null });

  const [voicesByProvider, setVoicesByProvider] = useState<Record<string, string[]>>({});
  const [voices, setVoices] = useState<string[]>([]);
  const [languagesByProvider, setLanguagesByProvider] = useState<Record<string, string[]>>({});
  const [languages, setLanguages] = useState<string[]>([]);
  const [tabLoading, setTabLoading] = useState(true);

  const ttsHasPersona = !!ttsVoice && ttsVoice.toLowerCase() !== 'none';

  const loadVoices = async () => {
    try {
      const res = await adminFetch('/dashboard/api/voices');
      if (res.ok) {
        const data = await res.json();
        setVoicesByProvider(data.voices || {});
      }
    } catch (e) {
      console.error('Failed to load voices:', e);
    }
  };

  const loadLanguages = async () => {
    try {
      const res = await adminFetch('/dashboard/api/tts-languages');
      if (res.ok) {
        const data = await res.json();
        setLanguagesByProvider(data.languages || {});
      }
    } catch (e) {
      console.error('Failed to load languages:', e);
    }
  };

  const loadLocalTtsInfo = async () => {
    try {
      const res = await adminFetch('/dashboard/api/local-tts-info');
      if (res.ok) {
        const data = await res.json();
        setLocalTtsInfo(data);
        return data.active;
      }
    } catch (e) {
      console.error('Failed to load local TTS info:', e);
    }
    return false;
  };

  // Mount logic specific to TTS
  useEffect(() => {
    let previousActive = false;

    const initTtsData = async () => {
      try {
        const fetchPromise = Promise.all([
          loadVoices(),
          loadLanguages(),
          loadLocalTtsInfo()
        ]);
        
        const timeoutPromise = new Promise((resolve) => setTimeout(resolve, 1000));
        
        const results = await Promise.race([fetchPromise, timeoutPromise]);
        
        if (Array.isArray(results)) {
          const ttsActive = results[2];
          previousActive = !!ttsActive;
        }
      } catch (e) {
        console.error('Failed to load initial TTS data:', e);
      } finally {
        setTabLoading(false);
      }
    };
    initTtsData();

    // 2-second timeout & polling interval
    const interval = setInterval(async () => {
      try {
        const res = await adminFetch('/dashboard/api/local-tts-info');
        if (res.ok) {
          const data = await res.json();
          setLocalTtsInfo(data);
          
          if (data.active && !previousActive) {
             loadVoices();
             loadLanguages();
          }
          previousActive = data.active;
        }
      } catch (e) {}
    }, 2000);

    return () => {
      clearInterval(interval);
    };
  }, []);

  // Update dropdown targets on models/groups load
  useEffect(() => {
    if (models.length > 0 || groups.length > 0) {
      const ttsOpts = getRouteOptions('tts');
      if (ttsOpts.length > 0 && (!ttsModel || !ttsOpts.find(o => o.value === ttsModel))) {
        setTtsModel(ttsOpts[0].value);
      }
    }
  }, [models, groups]);

  // Update TTS voices persona and languages when model selection changes
  useEffect(() => {
    if (!ttsModel) {
      setVoices([]);
      setLanguages([]);
      setIsLocalTts(false);
      return;
    }

    let provider = '';
    let selectedModelObj: any = null;
    const group = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
    if (group && group.items && group.items.length > 0) {
      provider = group.items[0].provider;
      selectedModelObj = models.find((m) => m.name === group.items[0].name && m.capability === 'tts');
    } else {
      const model = models.find((m) => m.name === ttsModel && m.capability === 'tts');
      if (model) {
        provider = model.provider;
        selectedModelObj = model;
      }
    }

    const isLocal = provider === 'local';
    const resolvedEngine = isLocal ? (localTtsInfo.active && localTtsInfo.engine ? localTtsInfo.engine : 'omnivoice') : 'omnivoice';

    let nextVoices: string[] = [];
    const localVoices = voicesByProvider['local'] || [];
    if (isLocal) {
      if (localTtsInfo.active && localTtsInfo.engine === resolvedEngine) {
        nextVoices = Array.isArray(localVoices) ? localVoices : [];
      } else {
        nextVoices = []; // Will show manual text input instead
      }
    } else {
      if (provider && Array.isArray(voicesByProvider[provider])) {
        nextVoices = voicesByProvider[provider].filter(v => typeof v === 'string' && v.toLowerCase() !== 'none');
      } else {
        nextVoices = Object.values(voicesByProvider)
          .filter(val => Array.isArray(val))
          .flat()
          .filter(v => typeof v === 'string' && v.toLowerCase() !== 'none');
      }
    }

    setVoices(nextVoices);
    setIsLocalTts(isLocal);

    // Languages list:
    let nextLangs: string[] = [];
    const localLangs = languagesByProvider['local'] || [];
    if (isLocal) {
      if (resolvedEngine === 'omnivoice') {
        if (localTtsInfo.active && localTtsInfo.engine === 'omnivoice' && Array.isArray(localLangs) && localLangs.length > 0) {
          nextLangs = localLangs;
        } else {
          nextLangs = []; // Show manual text input when offline or empty
        }
      } else {
        nextLangs = []; // Will show manual text input for voxcpm2
      }
    } else {
      if (provider && Array.isArray(languagesByProvider[provider])) {
        nextLangs = languagesByProvider[provider];
      } else {
        nextLangs = ['Auto', 'Turkish', 'English'];
      }
    }
    setLanguages(nextLangs);

    const isInitialLoadForSavedModel = initialTtsModelRef.current === ttsModel;
    const isModelChanged = lastTtsModelRef.current !== ttsModel;

    if (isInitialLoadForSavedModel) {
      initialTtsModelRef.current = null;
      lastTtsModelRef.current = ttsModel;
    } else if (isModelChanged) {
      lastTtsModelRef.current = ttsModel;
      
      const findModelConfig = (mName: string) => {
        const modelDetail = models.find((m) => m.name === mName && m.capability === 'tts');
        return {
          temperature: modelDetail?.temperature ?? null,
          ...(modelDetail?.default_config || {})
        };
      };

      let defaults: any = {};
      if (group) {
        const primaryItem = group.items?.[0];
        if (primaryItem) {
          defaults = findModelConfig(primaryItem.name);
        }
      } else {
        defaults = findModelConfig(ttsModel);
      }

      const getVal = (field: string, fallback: string) => {
        if (defaults[field] !== undefined && defaults[field] !== null && defaults[field] !== '') {
          return String(defaults[field]);
        }
        return fallback;
      };

      const defVoice = getVal('voice', '');
      if (defVoice && defVoice.toLowerCase() !== 'none') {
        setTtsVoice(defVoice);
      } else {
        if (isLocal) {
          setTtsVoice('');
        } else {
          setTtsVoice(nextVoices[0] || '');
        }
      }

      const defLang = getVal('language', nextLangs[0] || 'Auto');
      setTtsLanguage(defLang);

      const defTemp = getVal('temperature', '');
      setTtsTemp(defTemp);

      const defSpeed = getVal('speed', '1.0');
      setTtsSpeed(defSpeed);

      const defSteps = getVal('steps', '15');
      setTtsSteps(defSteps);

      const defSeed = getVal('seed', '-1');
      setTtsSeed(defSeed);

      const defGender = getVal('gender', 'Auto');
      setTtsGender(defGender);

      const defAge = getVal('age', 'Auto');
      setTtsAge(defAge);

      const defPitch = getVal('pitch', 'Auto');
      setTtsPitch(defPitch);

      const defStyle = getVal('style', 'Auto');
      setTtsStyle(defStyle);

      const defAccent = getVal('accent', 'Auto');
      setTtsAccent(defAccent);

      const defInstruct = getVal('tts_instruct', '');
      setTtsInstruct(defInstruct);
    }
  }, [ttsModel, groups, models, voicesByProvider, languagesByProvider, localTtsInfo]);

  // Save states to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('pg_ttsModel', ttsModel);
      localStorage.setItem('pg_ttsVoice', ttsVoice);
      localStorage.setItem('pg_ttsTemp', ttsTemp);
      localStorage.setItem('pg_ttsSpeed', ttsSpeed);
      localStorage.setItem('pg_ttsLanguage', ttsLanguage);
      localStorage.setItem('pg_ttsSteps', ttsSteps);
      localStorage.setItem('pg_ttsSeed', ttsSeed);
      localStorage.setItem('pg_ttsGender', ttsGender);
      localStorage.setItem('pg_ttsAge', ttsAge);
      localStorage.setItem('pg_ttsPitch', ttsPitch);
      localStorage.setItem('pg_ttsStyle', ttsStyle);
      localStorage.setItem('pg_ttsAccent', ttsAccent);
      localStorage.setItem('pg_ttsDialect', ttsDialect);
      localStorage.setItem('pg_ttsInstruct', ttsInstruct);
    }
  }, [ttsModel, ttsVoice, ttsTemp, ttsSpeed, ttsLanguage, ttsSteps, ttsSeed, ttsGender, ttsAge, ttsPitch, ttsStyle, ttsAccent, ttsDialect, ttsInstruct]);

  const resolvedTtsDefaults = (() => {
    if (!ttsModel) return { temperature: null };

    const findModelConfig = (mName: string) => {
      const modelDetail = models.find((m) => m.name === mName && m.capability === 'tts');
      return {
        temperature: modelDetail?.temperature ?? null,
        ...(modelDetail?.default_config || {})
      };
    };

    const group = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
    if (group) {
      const primaryItem = group.items?.[0];
      if (primaryItem) {
        return findModelConfig(primaryItem.name);
      }
      return { temperature: null };
    }

    return findModelConfig(ttsModel);
  })();

  const resolvedTtsEngine = (() => {
    if (!isLocalTts) return 'omnivoice';
    return localTtsInfo.active && localTtsInfo.engine ? localTtsInfo.engine : 'omnivoice';
  })();

  const getTtsFieldDefault = (field: string) => {
    const defaults = resolvedTtsDefaults || {};
    if (defaults[field] !== undefined && defaults[field] !== null && defaults[field] !== '') {
      return String(defaults[field]);
    }
    switch (field) {
      case 'voice':
        {
          let provider = '';
          const model = models.find((m) => m.name === ttsModel && m.capability === 'tts');
          if (model) {
            provider = model.provider;
          } else {
            const group = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
            if (group && group.items && group.items.length > 0) {
              provider = group.items[0].provider;
            }
          }
          if (provider === 'openai') return 'alloy';
          if (provider === 'gemini') return 'Achernar';
          return '';
        }
      case 'gender':
      case 'age':
      case 'pitch':
      case 'style':
      case 'accent':
      case 'dialect':
      case 'language':
        return 'Auto';
      case 'speed':
        return '1.0';
      case 'steps':
        return '15';
      case 'seed':
        return '-1';
      default:
        return '';
    }
  };

  const renderDefaultIndicator = (field: string, userValue: string) => {
    let defVal = getTtsFieldDefault(field);
    let isOverridden = false;
    if (field === 'voice') {
      const normUser = (userValue || '').toLowerCase();
      const normDef = (defVal || '').toLowerCase();
      const isUserNone = normUser === '' || normUser === 'none';
      const isDefNone = normDef === '' || normDef === 'none';
      isOverridden = (isUserNone && isDefNone) ? false : (normUser !== normDef);
    } else {
      isOverridden = userValue !== defVal;
    }

    let displayVal = defVal;
    if (field === 'voice') {
      if (!defVal || defVal.toLowerCase() === 'none') {
        displayVal = 'None';
      }
    } else if (field === 'temperature') {
      if (!defVal) {
        displayVal = '-';
      }
    }

    return (
      <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all ${isOverridden
          ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
          : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
        }`}>
        {t('playground.default')}: {displayVal}
      </span>
    );
  };

  const getRouteOptions = (capability: string): RouteOption[] => {
    const options: RouteOption[] = [];
    groups.forEach((g) => {
      if (g.capability === capability && g.is_active) {
        options.push({ value: g.name, label: `${t('playground.groupPrefix')} ${g.name}` });
      }
    });
    models.forEach((m) => {
      if (m.capability === capability && m.is_active) {
        options.push({ value: m.name, label: `${m.name} (${m.provider})` });
      }
    });
    return options;
  };

  const getApiBaseUrl = () => {
    if (process.env.NODE_ENV === 'development') {
      const port = process.env.NEXT_PUBLIC_ROUTER_PORT || '20129';
      if (typeof window !== 'undefined') {
        return `http://${window.location.hostname}:${port}`;
      }
      return `http://127.0.0.1:${port}`;
    }
    return '';
  };

  const handleGenerateTTS = async () => {
    const text = ttsInput.trim();
    if (!text) {
      showToast(t('playground.toast.enterText'), 'error');
      return;
    }

    setTtsError('');
    setTtsUrl('');

    const adminKey = getAdminKey();
    const apiBaseUrl = getApiBaseUrl();
    const payload: any = { model: ttsModel, input: text, voice: ttsVoice };

    const parsedTemp = parseFloat(ttsTemp);
    if (!isNaN(parsedTemp)) {
      payload.temperature = parsedTemp;
    }

    if (isLocalTts) {
      payload.speed = parseFloat(ttsSpeed) || 1.0;
      payload.language = ttsLanguage || 'Auto';
      payload.steps = parseInt(ttsSteps, 10) || 15;
      payload.seed = parseInt(ttsSeed, 10) || -1;

      // Construct character design instructs (only when no persona is selected)
      const hasPersona = !!ttsVoice && ttsVoice.toLowerCase() !== 'none';
      if (!hasPersona) {
        if (resolvedTtsEngine === 'voxcpm2') {
          payload.tts_instruct = ttsInstruct || '';
        } else {
          const instructs: string[] = [];
          if (ttsGender && ttsGender !== 'Auto') instructs.push(ttsGender);
          if (ttsAge && ttsAge !== 'Auto') instructs.push(ttsAge);
          if (ttsPitch && ttsPitch !== 'Auto') instructs.push(ttsPitch);
          if (ttsStyle && ttsStyle !== 'Auto') instructs.push(ttsStyle);
          if (ttsAccent && ttsAccent !== 'Auto') instructs.push(ttsAccent);
          if (ttsDialect && ttsDialect !== 'Auto') instructs.push(ttsDialect);
          payload.tts_instruct = instructs.length > 0 ? instructs.join(', ') : '';
        }
      } else {
        payload.tts_instruct = '';
      }
    }

    try {
      setIsGeneratingTTS(true);
      ttsAbortControllerRef.current = new AbortController();

      const res = await fetch(`${apiBaseUrl}/v1/audio/speech`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminKey}`,
          'Accept-Language': locale,
        },
        body: JSON.stringify(payload),
        signal: ttsAbortControllerRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error?.message || err.detail || res.statusText);
      }

      const blob = await res.blob();
      setTtsUrl(URL.createObjectURL(blob));
      showToast(t('playground.toast.audioSuccess'));
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setTtsError('❌ Error: ' + e.message);
      }
    } finally {
      setIsGeneratingTTS(false);
      ttsAbortControllerRef.current = null;
    }
  };

  const selectedTtsGroup = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
  const hasTtsTempOverride = ttsTemp !== '';

  if (tabLoading) {
    return (
      <div className="glass-panel p-8 text-center text-zinc-400">
        {t('playground.loading')}
      </div>
    );
  }

  return (
    <div className="playground-layout flex flex-col md:flex-row gap-4 animate-in fade-in duration-200">
      {/* Settings Sidebar */}
      <div className="pg-sidebar md:w-[250px] p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3 shrink-0">
        <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide capitalize">{t('playground.audioSettings')}</h3>

        {isLocalTts && (
          <div className="flex flex-col gap-1 border-b border-zinc-850 pb-2 mb-1">
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 text-[10px] font-semibold uppercase tracking-wider">{t('tts.engine.model')}</span>
              {localTtsInfo.active ? (
                <span className="text-[10px] text-zinc-300 flex items-center gap-1.5 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  {resolvedTtsEngine}
                </span>
              ) : (
                <span className="text-[10px] text-red-400 font-semibold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
                  {t('tts.engine.offline')}
                </span>
              )}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.modelOrGroup')}</label>
          <div className="custom-select-wrapper select-wrapper w-full">
            <select
              value={ttsModel}
              onChange={(e) => setTtsModel(e.target.value)}
              className="orion-native-select orion-native-select-sm"
            >
              {getRouteOptions('tts').map((route) => (
                <option key={route.value} value={route.value}>
                  {route.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex justify-between items-center mb-0.5">
            <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.voicePersona')}</label>
            {renderDefaultIndicator('voice', ttsVoice)}
          </div>
          {!isLocalTts || (localTtsInfo.active && voices.length > 0) ? (
            <div className="custom-select-wrapper select-wrapper w-full">
              <select
                value={ttsVoice}
                onChange={(e) => setTtsVoice(e.target.value)}
                className="orion-native-select orion-native-select-sm"
              >
                {isLocalTts && <option value="">{t('common.none')}</option>}
                {ttsVoice && !voices.includes(ttsVoice) && ttsVoice.toLowerCase() !== 'none' && (
                  <option value={ttsVoice}>{ttsVoice} ⚠️</option>
                )}
                {voices.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <Input
              value={ttsVoice}
              onChange={(e) => setTtsVoice(e.target.value)}
              placeholder={t('tts.voice.placeholder.manual')}
              className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs"
            />
          )}
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex justify-between items-center mb-1 relative group">
            <label className="text-zinc-400 text-[10px] font-semibold capitalize">
              {t('playground.temperature')}
            </label>
            {selectedTtsGroup ? (
              <>
                <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help ${hasTtsTempOverride
                  ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                  : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                  }`}>
                  {t('playground.defaultGroup')}
                </span>
                <div className="absolute top-full right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-2.5 rounded shadow-xl whitespace-pre-wrap max-h-48 overflow-y-auto custom-scrollbar pointer-events-none min-w-[220px]">
                  <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">{t('playground.groupTemperature')}</div>
                  <div className="flex flex-col gap-1">
                    {selectedTtsGroup.items?.map((item: any, idx: number) => {
                      const mDetail = models.find((m) => m.name === item.name && m.capability === 'tts');
                      const tVal = item.temperature !== undefined && item.temperature !== null
                        ? item.temperature
                        : (mDetail?.temperature ?? null);
                      return (
                        <div key={item.id} className="flex justify-between items-center gap-2 border-b border-zinc-800/50 pb-1 last:border-0 last:pb-0">
                          <span className="text-zinc-400 font-mono text-[8px] truncate whitespace-nowrap block max-w-[145px]" title={item.name}>{idx + 1}. {item.name}</span>
                          <span className="text-white font-mono text-[8px] shrink-0 whitespace-nowrap">
                            {tVal !== null ? tVal : '-'}
                          </span>
                        </div>
                      );
                    })}
                    {(!selectedTtsGroup.items || selectedTtsGroup.items.length === 0) && (
                      <span className="text-zinc-500 text-[9px]">{t('playground.noModelsInGroup')}</span>
                    )}
                  </div>
                </div>
              </>
            ) : (
              renderDefaultIndicator('temperature', ttsTemp)
            )}
          </div>
          <Input
            type="number"
            min="0"
            max="2"
            step="0.1"
            value={ttsTemp}
            onChange={(e) => setTtsTemp(e.target.value)}
            placeholder={t('playground.optional')}
            className="bg-black/40 border border-zinc-855 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
          />
        </div>


        {/* 🌊 Streaming Ayarları (Gizlendi - Desteklenmiyor) */}
        {false && (
          <>
            <button
              type="button"
              onClick={() => setShowStreamingSettings(!showStreamingSettings)}
              className="flex items-center justify-between text-left text-zinc-400 text-[10px] font-semibold uppercase tracking-wider mt-4 py-2 px-2 bg-zinc-900/30 hover:bg-zinc-800/40 rounded cursor-pointer transition-colors w-full"
            >
              <span>{t('tts.streaming.settings')}</span>
              <span>{showStreamingSettings ? '▼' : '►'}</span>
            </button>

            {showStreamingSettings && (
              <div className="flex flex-col gap-2 pl-2 mt-2 border-l-2 border-zinc-800/50">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    disabled
                    checked={false}
                    className="rounded border-zinc-800 bg-black/40 text-purple-600 focus:ring-purple-600 focus:ring-offset-black"
                  />
                  <label className="text-zinc-500 text-[10px] select-none">
                    {t('tts.streaming.stream')}
                  </label>
                </div>
              </div>
            )}
          </>
        )}

        {/* ⚙️ Gelişmiş Ayarlar */}
        {isLocalTts && (
          <>
            <button
              type="button"
              onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
              className="flex items-center justify-between text-left text-zinc-400 text-[10px] font-semibold uppercase tracking-wider mt-2 py-2 px-2 bg-zinc-900/30 hover:bg-zinc-800/40 rounded cursor-pointer transition-colors w-full"
            >
              <span>{t('tts.advanced.settings')}</span>
              <span>{showAdvancedSettings ? '▼' : '►'}</span>
            </button>

            {showAdvancedSettings && (
              <div className="flex flex-col gap-3 pl-2 mt-2 border-l-2 border-zinc-800/50">
            {isLocalTts && resolvedTtsEngine === 'omnivoice' && (
              <div className="flex flex-col gap-1">
                <div className="flex justify-between items-center mb-0.5">
                  <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.language')}</label>
                  {renderDefaultIndicator('language', ttsLanguage)}
                </div>
                {!isLocalTts || (resolvedTtsEngine === 'omnivoice' && localTtsInfo.active && languages.length > 0) ? (
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsLanguage}
                      onChange={(e) => setTtsLanguage(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      {languages.length > 0 ? (
                        languages.map((lang) => (
                          <option key={lang} value={lang}>
                            {lang === 'Auto' ? t('tts.language.auto') : lang}
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="Auto">{t('tts.language.auto')}</option>
                          <option value="Turkish">{t('tts.language.turkish')}</option>
                          <option value="English">{t('tts.language.english')}</option>
                        </>
                      )}
                    </select>
                  </div>
                ) : (
                  <Input
                    value={ttsLanguage}
                    onChange={(e) => setTtsLanguage(e.target.value)}
                    placeholder={t('tts.language.placeholder.manual')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs"
                  />
                )}
              </div>
            )}

            {isLocalTts && (
              <>
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-0.5">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.steps.quality')}</label>
                    {renderDefaultIndicator('steps', ttsSteps)}
                  </div>
                  <Input
                    type="number"
                    min="1"
                    max="50"
                    step="1"
                    value={ttsSteps}
                    onChange={(e) => setTtsSteps(e.target.value)}
                    placeholder={getTtsFieldDefault('steps')}
                    className="bg-black/40 border border-zinc-855 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-0.5">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.speed.speech')}</label>
                    {renderDefaultIndicator('speed', ttsSpeed)}
                  </div>
                  <Input
                    type="number"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={ttsSpeed}
                    onChange={(e) => setTtsSpeed(e.target.value)}
                    placeholder={getTtsFieldDefault('speed')}
                    className="bg-black/40 border border-zinc-855 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-0.5">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.seed.fixed')}</label>
                    {renderDefaultIndicator('seed', ttsSeed)}
                  </div>
                  <Input
                    type="number"
                    value={ttsSeed}
                    onChange={(e) => setTtsSeed(e.target.value)}
                    placeholder={getTtsFieldDefault('seed')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                  />
                </div>
              </>
            )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Main Area */}
      <div className="pg-main flex-grow glass-panel p-5 bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-4">
        {isLocalTts && resolvedTtsEngine === 'voxcpm2' && (
          <div className="flex flex-col gap-3.5 border-b border-zinc-855 pb-4 animate-in fade-in duration-200">
            <div
              onClick={() => !ttsHasPersona && setShowSpeechStyle(!showSpeechStyle)}
              className={`flex items-center justify-between cursor-pointer group/header ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-semibold text-zinc-300 group-hover/header:text-white transition-colors">{t('tts.speech.style')}</h4>
                {ttsHasPersona && (
                  <span className="text-[8px] text-zinc-500 font-medium bg-black/40 px-1 py-0.5 rounded border border-zinc-800 normal-case">{t('tts.persona.active')}</span>
                )}
              </div>
              <span className={`text-[10px] text-zinc-500 transition-transform ${showSpeechStyle ? 'rotate-90' : ''}`}>▶</span>
            </div>

            {showSpeechStyle && (
              <div className={`flex flex-col gap-1.5 animate-in fade-in duration-200 ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}>
                <div className="flex justify-end">
                  {!ttsHasPersona && renderDefaultIndicator('tts_instruct', ttsInstruct)}
                </div>
                <Textarea
                  value={ttsInstruct}
                  onChange={(e) => setTtsInstruct(e.target.value)}
                  placeholder={t('tts.speech.style.placeholder')}
                  disabled={ttsHasPersona}
                  className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-2 text-xs placeholder:text-zinc-600 w-full"
                />
              </div>
            )}
          </div>
        )}

        {isLocalTts && resolvedTtsEngine === 'omnivoice' && (
          <div className="flex flex-col gap-3.5 border-b border-zinc-855 pb-4">
            <div
              onClick={() => !ttsHasPersona && setShowCharacterDesign(!showCharacterDesign)}
              className={`flex items-center justify-between cursor-pointer group/header ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-semibold text-zinc-300 group-hover/header:text-white transition-colors">{t('tts.character.design')}</h4>
                {ttsHasPersona && (
                  <span className="text-[8px] text-zinc-500 font-medium bg-black/40 px-1 py-0.5 rounded border border-zinc-800 normal-case">{t('tts.persona.active')}</span>
                )}
              </div>
              <span className={`text-[10px] text-zinc-500 transition-transform ${showCharacterDesign ? 'rotate-90' : ''}`}>▶</span>
            </div>

            {showCharacterDesign && (
              <div className={`grid grid-cols-2 md:grid-cols-3 gap-3.5 animate-in fade-in duration-200 ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}>
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-zinc-400 text-[9px] font-medium uppercase tracking-wider">{t('tts.char.gender')}</label>
                    {renderDefaultIndicator('gender', ttsGender)}
                  </div>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsGender}
                      onChange={(e) => setTtsGender(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      <option value="Auto">Auto</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-zinc-400 text-[9px] font-medium uppercase tracking-wider">{t('tts.char.age')}</label>
                    {renderDefaultIndicator('age', ttsAge)}
                  </div>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsAge}
                      onChange={(e) => setTtsAge(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      <option value="Auto">Auto</option>
                      <option value="Child">Child</option>
                      <option value="Teenager">Teenager</option>
                      <option value="YoungAdult">YoungAdult</option>
                      <option value="MiddleAged">MiddleAged</option>
                      <option value="Elderly">Elderly</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-zinc-400 text-[9px] font-medium uppercase tracking-wider">{t('tts.char.pitch')}</label>
                    {renderDefaultIndicator('pitch', ttsPitch)}
                  </div>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsPitch}
                      onChange={(e) => setTtsPitch(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      <option value="Auto">Auto</option>
                      <option value="VeryLow">VeryLow</option>
                      <option value="Low">Low</option>
                      <option value="Moderate">Moderate</option>
                      <option value="High">High</option>
                      <option value="VeryHigh">VeryHigh</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-zinc-400 text-[9px] font-medium uppercase tracking-wider">{t('tts.char.style')}</label>
                    {renderDefaultIndicator('style', ttsStyle)}
                  </div>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsStyle}
                      onChange={(e) => setTtsStyle(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      <option value="Auto">Auto</option>
                      <option value="Whispering">Whispering</option>
                      <option value="Soft">Soft</option>
                      <option value="Normal">Normal</option>
                      <option value="Excited">Excited</option>
                      <option value="Shouting">Shouting</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-zinc-400 text-[9px] font-medium uppercase tracking-wider">{t('tts.char.accent')}</label>
                    {renderDefaultIndicator('accent', ttsAccent)}
                  </div>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={ttsAccent}
                      onChange={(e) => setTtsAccent(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      <option value="Auto">Auto</option>
                      <option value="American">American</option>
                      <option value="British">British</option>
                      <option value="Australian">Australian</option>
                      <option value="Indian">Indian</option>
                      <option value="TurkishAccent">TurkishAccent</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-col gap-1.5 flex-grow">
          <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.textToSynthesize')}</label>
          <Textarea
            value={ttsInput}
            onChange={(e) => setTtsInput(e.target.value)}
            placeholder={t('playground.textToSynthesizePlaceholder')}
            className="flex-1 bg-black/40 border border-zinc-855 text-white rounded p-3 text-xs min-h-[120px] max-h-[220px] resize-none"
          />
        </div>

        <div className="flex justify-end">
          {isGeneratingTTS ? (
            <Button
              onClick={() => ttsAbortControllerRef.current?.abort()}
              className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 py-2 rounded-lg text-xs min-w-[70px]"
            >
              {t('playground.stop')}
            </Button>
          ) : (
            <Button
              onClick={handleGenerateTTS}
              className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 py-2 rounded-lg text-xs"
            >
              {t('playground.generateAudio')}
            </Button>
          )}
        </div>

        {ttsError && (
          <div className="text-red-500 bg-red-950/20 border border-red-500/30 rounded p-3 text-xs">
            {ttsError}
          </div>
        )}

        {ttsUrl && (
          <div className="p-3 bg-white/5 border border-zinc-800 rounded-lg flex items-center justify-between gap-3 mt-1">
            <audio src={ttsUrl} controls className="flex-grow max-w-[400px] h-8" />
            <a
              href={ttsUrl}
              download="speech.wav"
              className="bg-zinc-800 text-white border border-zinc-700 hover:bg-zinc-700 font-medium px-3 py-1.5 text-[10px] rounded transition-colors"
            >
              {t('playground.download')}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
