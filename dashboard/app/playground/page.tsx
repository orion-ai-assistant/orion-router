'use client';

import React, { useState, useEffect, useRef } from 'react';
import { adminFetch, getAdminKey } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

interface RouteOption {
  value: string;
  label: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  type: 'content' | 'thinking';
  html: string;
}

export default function PlaygroundPage() {
  const { showToast, locale, t } = useApp();
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
  const [voicesByProvider, setVoicesByProvider] = useState<Record<string, string[]>>({});
  const [voices, setVoices] = useState<string[]>([]);
  const [languagesByProvider, setLanguagesByProvider] = useState<Record<string, string[]>>({});
  const [languages, setLanguages] = useState<string[]>([]);

  // Chat State
  const [chatModel, setChatModel] = useState(getSavedState('pg_chatModel', ''));
  const savedChatModel = getSavedState('pg_chatModel', '');
  const initialChatModelRef = useRef<string | null>(savedChatModel);
  const [chatTemp, setChatTemp] = useState(getSavedState('pg_chatTemp', ''));
  const [chatThinking, setChatThinking] = useState(getSavedState('pg_chatThinking', ''));
  const [chatSystemPrompt, setChatSystemPrompt] = useState(getSavedState('pg_chatSystemPrompt', ''));
  const [chatMessages, setChatMessages] = useState<Message[]>((() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pg_chatMessages');
      if (saved) {
        try { return JSON.parse(saved); } catch (e) { }
      }
    }
    return [];
  })());
  const [chatInput, setChatInput] = useState(getSavedState('pg_chatInput', ''));
  const [isGenerating, setIsGenerating] = useState(false);
  const chatMessagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

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
    voices: string[];
    languages: string[];
  }>({ active: false, engine: null, voices: [], languages: [] });

  const ttsHasPersona = !!ttsVoice && ttsVoice.toLowerCase() !== 'none';

  // Embed State
  const [embedModel, setEmbedModel] = useState(getSavedState('pg_embedModel', ''));
  const [embedInput, setEmbedInput] = useState('');
  const [embedError, setEmbedError] = useState('');
  const [embedPreview, setEmbedPreview] = useState('');
  const [embedDim, setEmbedDim] = useState('');
  const [embedJson, setEmbedJson] = useState('');
  const [isGeneratingEmbed, setIsGeneratingEmbed] = useState(false);
  const [loading, setLoading] = useState(true);
  const embedAbortControllerRef = useRef<AbortController | null>(null);

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
      }
    } catch (e) {
      console.error('Failed to load local TTS info:', e);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await Promise.all([
        loadModels(),
        loadGroups(),
        loadVoices(),
        loadLanguages(),
        loadLocalTtsInfo()
      ]);
      setLoading(false);
    };
    initData();

    const interval = setInterval(() => {
      loadLocalTtsInfo();
      loadVoices();
      loadLanguages();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  // Update dropdown targets on data load
  useEffect(() => {
    if (models.length > 0 || groups.length > 0) {
      const chatOpts = getRouteOptions('chat');
      if (chatOpts.length > 0 && (!chatModel || !chatOpts.find(o => o.value === chatModel))) {
        setChatModel(chatOpts[0].value);
      }

      const ttsOpts = getRouteOptions('tts');
      if (ttsOpts.length > 0 && (!ttsModel || !ttsOpts.find(o => o.value === ttsModel))) {
        setTtsModel(ttsOpts[0].value);
      }

      const embedOpts = getRouteOptions('embed');
      if (embedOpts.length > 0 && (!embedModel || !embedOpts.find(o => o.value === embedModel))) {
        setEmbedModel(embedOpts[0].value);
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
    if (isLocal) {
      if (localTtsInfo.active && localTtsInfo.engine === resolvedEngine) {
        nextVoices = localTtsInfo.voices;
      } else {
        nextVoices = []; // Will show manual text input instead
      }
    } else {
      if (provider && voicesByProvider[provider]) {
        nextVoices = voicesByProvider[provider].filter(v => v.toLowerCase() !== 'none');
      } else {
        nextVoices = Object.values(voicesByProvider).flat().filter(v => v.toLowerCase() !== 'none');
      }
    }

    setVoices(nextVoices);
    setIsLocalTts(isLocal);

    // Languages list:
    let nextLangs: string[] = [];
    if (isLocal) {
      if (resolvedEngine === 'omnivoice') {
        if (localTtsInfo.active && localTtsInfo.engine === 'omnivoice' && localTtsInfo.languages && localTtsInfo.languages.length > 0) {
          nextLangs = localTtsInfo.languages;
        } else {
          nextLangs = []; // Show manual text input when offline or empty
        }
      } else {
        nextLangs = []; // Will show manual text input for voxcpm2
      }
    } else {
      if (provider && languagesByProvider[provider]) {
        nextLangs = languagesByProvider[provider];
      } else {
        nextLangs = ['Auto', 'Turkish', 'English'];
      }
    }
    setLanguages(nextLangs);

    const isInitialLoadForSavedModel = initialTtsModelRef.current === ttsModel;
    const isModelChanged = lastTtsModelRef.current !== ttsModel;

    if (isInitialLoadForSavedModel) {
      // Keeping values loaded from localStorage on page refresh
      if (isLocal) {
        if (ttsVoice !== '' && nextVoices.length > 0 && !nextVoices.includes(ttsVoice)) {
          setTtsVoice('');
        }
      } else {
        if (!nextVoices.includes(ttsVoice)) {
          setTtsVoice(nextVoices[0] || '');
        }
      }

      if (!isLocal) {
        if (provider && languagesByProvider[provider]) {
          const providerLangs = languagesByProvider[provider];
          if (providerLangs.length > 0 && !providerLangs.includes(ttsLanguage)) {
            setTtsLanguage(providerLangs[0]);
          }
        }
      }

      initialTtsModelRef.current = null;
      lastTtsModelRef.current = ttsModel;
    } else if (isModelChanged) {
      lastTtsModelRef.current = ttsModel;
      // Apply default configuration values for the selected model
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

      // 1. Voice
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

      // 2. Language
      const defLang = getVal('language', nextLangs[0] || 'Auto');
      setTtsLanguage(defLang);

      // 3. Temperature
      const defTemp = getVal('temperature', '');
      setTtsTemp(defTemp);

      // 4. Speed
      const defSpeed = getVal('speed', '1.0');
      setTtsSpeed(defSpeed);

      // 5. Steps
      const defSteps = getVal('steps', '15');
      setTtsSteps(defSteps);

      // 6. Seed
      const defSeed = getVal('seed', '-1');
      setTtsSeed(defSeed);

      // 7. Gender
      const defGender = getVal('gender', 'Auto');
      setTtsGender(defGender);

      // 8. Age
      const defAge = getVal('age', 'Auto');
      setTtsAge(defAge);

      // 9. Pitch
      const defPitch = getVal('pitch', 'Auto');
      setTtsPitch(defPitch);

      // 10. Style
      const defStyle = getVal('style', 'Auto');
      setTtsStyle(defStyle);

      // 11. Accent
      const defAccent = getVal('accent', 'Auto');
      setTtsAccent(defAccent);

      // 12. tts_instruct
      const defInstruct = getVal('tts_instruct', '');
      setTtsInstruct(defInstruct);
    }
  }, [ttsModel, groups, models, voicesByProvider, languagesByProvider, localTtsInfo]);

  // Update Chat settings when model selection changes
  useEffect(() => {
    if (!chatModel) return;

    const isInitialLoadForSavedModel = initialChatModelRef.current === chatModel;

    if (isInitialLoadForSavedModel) {
      initialChatModelRef.current = null;
    } else {
      // Apply defaults
      const group = groups.find((g) => g.name === chatModel && g.capability === 'chat');
      let defaults: any = {};
      if (group) {
        const primaryItem = group.items?.[0];
        if (primaryItem) {
          const modelDetail = models.find((m) => m.name === primaryItem.name && m.capability === 'chat');
          defaults = {
            temperature: modelDetail?.temperature ?? null,
            thinking_level: primaryItem.thinking_level || modelDetail?.thinking_level || null,
            system_prompt: primaryItem.system_prompt || modelDetail?.system_prompt || null,
          };
        }
      } else {
        const model = models.find((m) => m.name === chatModel && m.capability === 'chat');
        if (model) {
          defaults = {
            temperature: model.temperature ?? null,
            thinking_level: model.thinking_level || null,
            system_prompt: model.system_prompt || null,
          };
        }
      }

      setChatTemp(defaults.temperature !== undefined && defaults.temperature !== null ? String(defaults.temperature) : '');
      setChatThinking(defaults.thinking_level !== undefined && defaults.thinking_level !== null ? String(defaults.thinking_level) : '');
      setChatSystemPrompt(defaults.system_prompt !== undefined && defaults.system_prompt !== null ? String(defaults.system_prompt) : '');
    }
  }, [chatModel, groups, models]);

  // Save states to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('pg_activeTab', activeTab);
      localStorage.setItem('pg_chatModel', chatModel);
      localStorage.setItem('pg_chatTemp', chatTemp);
      localStorage.setItem('pg_chatThinking', chatThinking);
      localStorage.setItem('pg_chatSystemPrompt', chatSystemPrompt);
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
      localStorage.setItem('pg_embedModel', embedModel);
      localStorage.setItem('pg_chatMessages', JSON.stringify(chatMessages));
      localStorage.setItem('pg_chatInput', chatInput);
    }
  }, [activeTab, chatModel, chatTemp, chatThinking, chatSystemPrompt, ttsModel, ttsVoice, ttsTemp, ttsSpeed, ttsLanguage, ttsSteps, ttsSeed, ttsGender, ttsAge, ttsPitch, ttsStyle, ttsAccent, ttsDialect, ttsInstruct, embedModel, chatMessages, chatInput]);

  // Scroll chat window to bottom on new messages
  useEffect(() => {
    if (chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages]);

  const getResolvedDefaults = () => {
    if (!chatModel) return { temperature: null, thinking_level: null, system_prompt: null };

    // Check if it's a group
    const group = groups.find((g) => g.name === chatModel && g.capability === 'chat');
    if (group) {
      const primaryItem = group.items?.[0];
      if (primaryItem) {
        const modelDetail = models.find((m) => m.name === primaryItem.name && m.capability === 'chat');
        return {
          temperature: modelDetail?.temperature ?? null,
          thinking_level: primaryItem.thinking_level || modelDetail?.thinking_level || null,
          system_prompt: primaryItem.system_prompt || modelDetail?.system_prompt || null,
        };
      }
      return { temperature: null, thinking_level: null, system_prompt: null };
    }

    // Check if it's a single model
    const model = models.find((m) => m.name === chatModel && m.capability === 'chat');
    if (model) {
      return {
        temperature: model.temperature ?? null,
        thinking_level: model.thinking_level || null,
        system_prompt: model.system_prompt || null,
      };
    }

    return { temperature: null, thinking_level: null, system_prompt: null };
  };

  const getResolvedTtsDefaults = () => {
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
  };

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

  const renderDefaultIndicator = (field: string, userValue: string, isChat: boolean = false) => {
    let defVal = '';
    if (isChat) {
      const defaults = resolvedDefaults || {};
      const val = defaults[field as keyof typeof resolvedDefaults];
      if (val !== undefined && val !== null && val !== '') {
        defVal = String(val);
      }
    } else {
      defVal = getTtsFieldDefault(field);
    }

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
    } else if (field === 'temperature' || field === 'thinking_level' || field === 'system_prompt') {
      if (!defVal) {
        displayVal = '-';
      } else if (field === 'system_prompt') {
        displayVal = defVal.length > 15 ? defVal.slice(0, 15) + '...' : defVal;
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
        options.push({ value: g.name, label: `[Group] ${g.name}` });
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
      return `http://localhost:${port}`;
    }
    return '';
  };

  const escapeHtml = (text: string): string => {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  const handleSendChat = async () => {
    const text = chatInput.trim();
    if (!text) return;

    const userMsg: Message = {
      id: 'user-' + Date.now() + '-' + Math.random(),
      role: 'user',
      type: 'content',
      html: escapeHtml(text).replace(/\n/g, '<br />'),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput('');

    const newMessagesForPayload = [...chatMessages, userMsg]
      .filter((m) => !m.id.startsWith('err-') && m.type !== 'thinking')
      .map((m) => ({
        role: m.role,
        content: m.html.replace(/<br \/>/g, '\n').replace(/🤔 /g, ''),
      }));

    const payload: any = {
      model: chatModel,
      messages: newMessagesForPayload,
      stream: true,
    };

    const parsedTemp = parseFloat(chatTemp);
    if (!isNaN(parsedTemp)) {
      payload.temperature = parsedTemp;
    }

    const trimmedThinking = chatThinking.trim();
    if (trimmedThinking && trimmedThinking.toLowerCase() !== 'none') {
      payload.thinking_level = trimmedThinking;
    }

    const trimmedSystemPrompt = chatSystemPrompt.trim();
    if (trimmedSystemPrompt) {
      payload.system_prompt = trimmedSystemPrompt;
    }

    const adminKey = getAdminKey();
    const apiBaseUrl = getApiBaseUrl();

    try {
      setIsGenerating(true);
      abortControllerRef.current = new AbortController();

      const res = await fetch(`${apiBaseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminKey}`,
          'Accept-Language': locale,
        },
        body: JSON.stringify(payload),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        let displayError = errText;
        try {
          const parsed = JSON.parse(errText);
          displayError = parsed.error?.message || parsed.detail || errText;
        } catch (_) {}
        setChatMessages((prev) => [
          ...prev,
          {
            id: 'err-' + Date.now(),
            role: 'assistant',
            type: 'content',
            html: `Error: ${res.status} - ${displayError}`,
          },
        ]);
        return;
      }

      if (!res.body) return;

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      const thinkingMsgId = 'think-' + Date.now() + '-' + Math.random();
      const contentMsgId = 'content-' + Date.now() + '-' + Math.random();

      let hasThinking = false;
      let hasContent = false;

      const handleDataLine = (line: string) => {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) return;

        const dataStr = trimmed.slice(5).trim();
        if (!dataStr || dataStr === '[DONE]') return;

        let data: any;
        try {
          data = JSON.parse(dataStr);
        } catch (e) {
          return;
        }

        if (data.error) {
          const errMsg = typeof data.error === 'string'
            ? data.error
            : data.error.message || JSON.stringify(data.error);

          setChatMessages((prev) => {
            const updated = [...prev];
            const lastUserIdx = updated.map(m => m.id).lastIndexOf(userMsg.id);
            if (lastUserIdx !== -1) {
              updated[lastUserIdx] = { ...updated[lastUserIdx], id: 'err-user-' + updated[lastUserIdx].id };
            }
            return [
              ...updated,
              {
                id: 'err-' + Date.now() + '-' + Math.random(),
                role: 'assistant',
                type: 'content',
                html: `<span class="text-red-500 font-semibold">Error:</span> <pre class="whitespace-pre-wrap text-[10px] mt-1 bg-red-950/20 border border-red-500/30 p-2 rounded">${escapeHtml(errMsg)}</pre>`,
              },
            ];
          });
          abortControllerRef.current?.abort();
          return;
        }

        const delta = data.choices?.[0]?.delta || null;
        if (!delta) return;

        if (delta.reasoning_content) {
          const escaped = escapeHtml(delta.reasoning_content).replace(/\n/g, '<br />');
          if (!hasThinking) {
            hasThinking = true;
            setChatMessages((prev) => [
              ...prev,
              {
                id: thinkingMsgId,
                role: 'assistant',
                type: 'thinking',
                html: '🤔 ' + escaped,
              },
            ]);
          } else {
            setChatMessages((prev) =>
              prev.map((msg) =>
                msg.id === thinkingMsgId ? { ...msg, html: msg.html + escaped } : msg
              )
            );
          }
        }

        if (delta.content) {
          const escaped = escapeHtml(delta.content).replace(/\n/g, '<br />');
          if (!hasContent) {
            hasContent = true;
            setChatMessages((prev) => [
              ...prev,
              {
                id: contentMsgId,
                role: 'assistant',
                type: 'content',
                html: escaped,
              },
            ]);
          } else {
            setChatMessages((prev) =>
              prev.map((msg) =>
                msg.id === contentMsgId ? { ...msg, html: msg.html + escaped } : msg
              )
            );
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';

        for (const line of lines) {
          handleDataLine(line);
        }
      }

      if (buffer.trim()) {
        handleDataLine(buffer);
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setChatMessages((prev) => {
          const updated = [...prev];
          const lastUserIdx = updated.map(m => m.id).lastIndexOf(userMsg.id);
          if (lastUserIdx !== -1) {
            updated[lastUserIdx] = { ...updated[lastUserIdx], id: 'err-user-' + updated[lastUserIdx].id };
          }
          return [
            ...updated,
            {
              id: 'err-' + Date.now() + '-' + Math.random(),
              role: 'assistant',
              type: 'content',
              html: '<span class="text-red-500 font-semibold">Connection error:</span> ' + escapeHtml(e.message),
            },
          ];
        });
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
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

  const handleGenerateEmbedding = async () => {
    const text = embedInput.trim();
    if (!text) {
      showToast(t('playground.toast.enterText'), 'error');
      return;
    }

    setEmbedError('');
    setEmbedPreview('');
    setEmbedDim('');
    setEmbedJson('');

    const adminKey = getAdminKey();
    const apiBaseUrl = getApiBaseUrl();

    try {
      setIsGeneratingEmbed(true);
      embedAbortControllerRef.current = new AbortController();

      const res = await fetch(`${apiBaseUrl}/v1/embeddings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminKey}`,
          'Accept-Language': locale,
        },
        body: JSON.stringify({ model: embedModel, input: text }),
        signal: embedAbortControllerRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error?.message || err.detail || res.statusText);
      }

      const data = await res.json();
      const vector = data.data?.[0]?.embedding || [];
      const dim = vector.length;

      setEmbedDim(`📐 Dimensions: ${dim} | Model: ${data.model}`);

      const previewVec = vector.slice(0, 8).map((v: number) => v.toFixed(6)).join(', ');
      setEmbedPreview(`[${previewVec}${dim > 8 ? ', ...' : ''}]`);

      const truncated = {
        ...data,
        data: [
          {
            ...data.data[0],
            embedding: vector.slice(0, 32).concat(['... (truncated)']),
          },
        ],
      };
      setEmbedJson(JSON.stringify(truncated, null, 2));
      showToast(t('playground.toast.embeddingSuccess'));
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setEmbedError('❌ Error: ' + e.message);
      }
    } finally {
      setIsGeneratingEmbed(false);
      embedAbortControllerRef.current = null;
    }
  };

  const resolvedDefaults = getResolvedDefaults();
  const resolvedTtsDefaults = getResolvedTtsDefaults();
  const resolvedTtsEngine = (() => {
    if (!isLocalTts) return 'omnivoice';
    return localTtsInfo.active && localTtsInfo.engine ? localTtsInfo.engine : 'omnivoice';
  })();

  const selectedChatGroup = groups.find((g) => g.name === chatModel && g.capability === 'chat');
  const selectedTtsGroup = groups.find((g) => g.name === ttsModel && g.capability === 'tts');

  const hasTempOverride = chatTemp !== '';
  const hasThinkingOverride = chatThinking !== '';
  const hasSystemPromptOverride = chatSystemPrompt !== '';
  const hasTtsTempOverride = ttsTemp !== '';

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
          {/* CHAT TAB */}
          {activeTab === 'chat' && (
            <div className="playground-layout flex flex-col md:flex-row gap-4">
              {/* Settings Sidebar */}
              <div className="pg-sidebar md:w-[250px] p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3 shrink-0">
                <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide capitalize">{t('playground.config')}</h3>
                <div className="flex flex-col gap-1">
                  <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.modelOrGroup')}</label>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={chatModel}
                      onChange={(e) => setChatModel(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      {getRouteOptions('chat').map((route) => (
                        <option key={route.value} value={route.value}>
                          {route.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-1 relative group">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.temperature')}</label>
                    {selectedChatGroup ? (
                      <>
                        <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help ${hasTempOverride
                          ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                          : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                          }`}>
                          {t('playground.defaultGroup')}
                        </span>
                        <div className="absolute top-full right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-2.5 rounded shadow-xl whitespace-pre-wrap max-h-48 overflow-y-auto custom-scrollbar pointer-events-none min-w-[220px]">
                          <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">Group Temperature:</div>
                          <div className="flex flex-col gap-1">
                            {selectedChatGroup.items?.map((item: any, idx: number) => {
                              const mDetail = models.find((m) => m.name === item.name && m.capability === 'chat');
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
                            {(!selectedChatGroup.items || selectedChatGroup.items.length === 0) && (
                              <span className="text-zinc-500 text-[9px]">No models in this group</span>
                            )}
                          </div>
                        </div>
                      </>
                    ) : (
                      renderDefaultIndicator('temperature', chatTemp, true)
                    )}
                  </div>
                  <Input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={chatTemp}
                    onChange={(e) => setChatTemp(e.target.value)}
                    placeholder={t('playground.optionalTemp')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-1 relative group">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.thinking')}</label>
                    {selectedChatGroup ? (
                      <>
                        <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help ${hasThinkingOverride
                          ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                          : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                          }`}>
                          {t('playground.defaultGroup')}
                        </span>
                        <div className="absolute top-full right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-2.5 rounded shadow-xl whitespace-pre-wrap max-h-48 overflow-y-auto custom-scrollbar pointer-events-none min-w-[220px]">
                          <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">Group Thinking:</div>
                          <div className="flex flex-col gap-1">
                            {selectedChatGroup.items?.map((item: any, idx: number) => {
                              const mDetail = models.find((m) => m.name === item.name && m.capability === 'chat');
                              const thinkVal = item.thinking_level || mDetail?.thinking_level || null;
                              return (
                                <div key={item.id} className="flex justify-between items-center gap-2 border-b border-zinc-800/50 pb-1 last:border-0 last:pb-0">
                                  <span className="text-zinc-400 font-mono text-[8px] truncate whitespace-nowrap block max-w-[145px]" title={item.name}>{idx + 1}. {item.name}</span>
                                  <span className="text-white font-mono text-[8px] shrink-0 whitespace-nowrap">
                                    {thinkVal !== null ? thinkVal : '-'}
                                  </span>
                                </div>
                              );
                            })}
                            {(!selectedChatGroup.items || selectedChatGroup.items.length === 0) && (
                              <span className="text-zinc-500 text-[9px]">No models in this group</span>
                            )}
                          </div>
                        </div>
                      </>
                    ) : (
                      renderDefaultIndicator('thinking_level', chatThinking, true)
                    )}
                  </div>
                  <Input
                    value={chatThinking}
                    onChange={(e) => setChatThinking(e.target.value)}
                    placeholder={t('playground.optionalThinking')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center mb-1 relative group">
                    <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.systemPrompt')}</label>
                    {selectedChatGroup ? (
                      <>
                        <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help ${hasSystemPromptOverride
                          ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                          : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                          }`}>
                          {t('playground.defaultGroup')}
                        </span>
                        <div className="absolute top-full right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-2.5 rounded shadow-xl whitespace-pre-wrap max-h-48 overflow-y-auto custom-scrollbar pointer-events-none min-w-[220px]">
                          <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">Group System Prompt:</div>
                          <div className="flex flex-col gap-1">
                            {selectedChatGroup.items?.map((item: any, idx: number) => {
                              const mDetail = models.find((m) => m.name === item.name && m.capability === 'chat');
                              const sysPrompt = item.system_prompt || mDetail?.system_prompt || null;
                              const displayPrompt = sysPrompt
                                ? (sysPrompt.length > 8 ? `"${sysPrompt.slice(0, 8)}..."` : `"${sysPrompt}"`)
                                : '-';
                              return (
                                <div key={item.id} className="flex justify-between items-center gap-2 border-b border-zinc-800/50 pb-1 last:border-0 last:pb-0">
                                  <span className="text-zinc-400 font-mono text-[8px] truncate whitespace-nowrap block max-w-[145px]" title={item.name}>{idx + 1}. {item.name}</span>
                                  <span className="text-white font-mono text-[8px] shrink-0 max-w-[60px] truncate whitespace-nowrap" title={sysPrompt || undefined}>
                                    {displayPrompt}
                                  </span>
                                </div>
                              );
                            })}
                            {(!selectedChatGroup.items || selectedChatGroup.items.length === 0) && (
                              <span className="text-zinc-500 text-[9px]">No models in this group</span>
                            )}
                          </div>
                        </div>
                      </>
                    ) : resolvedDefaults.system_prompt ? (
                      <>
                        <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help truncate max-w-[120px] block ${hasSystemPromptOverride
                          ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                          : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                          }`}>
                          {t('playground.default')}: {resolvedDefaults.system_prompt.length > 15 ? resolvedDefaults.system_prompt.slice(0, 15) + '...' : resolvedDefaults.system_prompt}
                        </span>
                        <div className="absolute top-full left-0 right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-3 rounded shadow-xl whitespace-pre-wrap max-h-40 overflow-y-auto custom-scrollbar pointer-events-none">
                          <div className="font-semibold text-[9px] text-purple-400 mb-1 uppercase tracking-wide">{t('playground.default')}:</div>
                          {resolvedDefaults.system_prompt}
                        </div>
                      </>
                    ) : (
                      renderDefaultIndicator('system_prompt', chatSystemPrompt, true)
                    )}
                  </div>
                  <Textarea
                    value={chatSystemPrompt}
                    onChange={(e) => setChatSystemPrompt(e.target.value)}
                    placeholder={t('playground.systemPromptPlaceholder')}
                    className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs h-20 resize-none custom-scrollbar overflow-y-auto no-field-sizing placeholder:text-zinc-600"
                  />
                </div>
              </div>

              {/* Main Area */}
              <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col min-h-[380px] h-[calc(100vh-340px)]">
                <div className="chat-messages flex-1 overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar mb-3">
                  {chatMessages.length === 0 ? (
                    <div className="text-zinc-500 text-xs flex items-center justify-center h-full">
                      {t('playground.noMessages')}
                    </div>
                  ) : (
                    chatMessages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`max-w-[85%] rounded-lg p-3 text-xs leading-relaxed ${msg.role === 'user'
                          ? 'bg-zinc-800 text-white self-end rounded-br-none'
                          : msg.type === 'thinking'
                            ? 'bg-purple-950/20 border border-purple-500/10 text-purple-300 self-start rounded-bl-none font-mono text-xs'
                            : 'bg-black/30 border border-zinc-850 text-zinc-100 self-start rounded-bl-none'
                          }`}
                        dangerouslySetInnerHTML={{ __html: msg.html }}
                      />
                    ))
                  )}
                  <div ref={chatMessagesEndRef} />
                </div>

                <div className="flex gap-2 items-end">
                  <Textarea
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!isGenerating) {
                          handleSendChat();
                        }
                      }
                    }}
                    placeholder={t('playground.chatPlaceholder')}
                    className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-2.5 text-xs h-10 min-h-10 resize-none custom-scrollbar"
                  />
                  <Button
                    onClick={() => setChatMessages([])}
                    className="bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700 font-medium px-4 h-10 text-xs rounded-lg"
                    title={t('playground.clearChat')}
                  >
                    {t('common.clear')}
                  </Button>
                  {isGenerating ? (
                    <Button
                      onClick={() => abortControllerRef.current?.abort()}
                      className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 h-10 text-xs rounded-lg min-w-[70px]"
                    >
                      {t('playground.stop')}
                    </Button>
                  ) : (
                    <Button
                      onClick={handleSendChat}
                      className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 h-10 text-xs rounded-lg min-w-[70px]"
                    >
                      {t('common.send')}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TTS TAB */}
          {activeTab === 'tts' && (
            <div className="playground-layout flex flex-col md:flex-row gap-4">
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
                  {!isLocalTts || (localTtsInfo.active && localTtsInfo.engine === resolvedTtsEngine && voices.length > 0) ? (
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
                      {isLocalTts ? t('playground.temperature') + ' (Yaratıcılık)' : t('playground.temperature')}
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
                          <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">Group Temperature:</div>
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
                              <span className="text-zinc-500 text-[9px]">No models in this group</span>
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
                {isLocalTts && resolvedTtsEngine === 'voxcpm2' && (
                  <div className={`flex flex-col gap-1 border-t border-zinc-855 pt-3 mt-1 ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}>
                    <div className="flex justify-between items-center mb-0.5">
                      <div className="flex items-center gap-2">
                        <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.speech.style')}</label>
                        {ttsHasPersona && (
                          <span className="text-[8px] text-zinc-600 font-medium bg-black/40 px-1 py-0.5 rounded border border-zinc-800 normal-case">{t('tts.persona.active')}</span>
                        )}
                      </div>
                      {renderDefaultIndicator('tts_instruct', ttsInstruct)}
                    </div>
                    <Textarea
                      value={ttsInstruct}
                      onChange={(e) => setTtsInstruct(e.target.value)}
                      placeholder={t('tts.speech.style.placeholder')}
                      className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs h-20 resize-none custom-scrollbar overflow-y-auto"
                    />
                  </div>
                )}

                {isLocalTts && resolvedTtsEngine === 'omnivoice' && (
                  <div className="flex flex-col gap-3 pt-3 mt-1 border-t border-zinc-850">
                    {/* Karakter Tasarımı - Collapsible */}
                    <button
                      type="button"
                      onClick={() => setShowCharacterDesign(!showCharacterDesign)}
                      className={`flex items-center justify-between text-left text-[10px] font-semibold uppercase tracking-wider py-1 cursor-pointer transition-colors w-full ${ttsHasPersona
                          ? 'text-zinc-500 hover:text-zinc-400'
                          : 'text-zinc-300 hover:text-white'
                        }`}
                    >
                      <span className="flex items-center gap-2">
                        {t('tts.character.design')}
                        {ttsHasPersona && (
                          <span className="text-[8px] text-zinc-600 font-medium bg-black/40 px-1 py-0.5 rounded border border-zinc-800 normal-case">{t('tts.persona.active')}</span>
                        )}
                      </span>
                      <span>{showCharacterDesign ? '▼' : '►'}</span>
                    </button>

                    {showCharacterDesign && (
                      <div className={`flex flex-col gap-3 pl-1 border-l border-zinc-800 ${ttsHasPersona ? 'opacity-50 pointer-events-none' : ''}`}>
                        {/* Cinsiyet */}
                        <div className="flex flex-col gap-1">
                          <div className="flex justify-between items-center mb-0.5">
                            <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.gender')}</label>
                            {renderDefaultIndicator('gender', ttsGender)}
                          </div>
                          <div className="custom-select-wrapper select-wrapper w-full">
                            <select
                              value={ttsGender}
                              onChange={(e) => setTtsGender(e.target.value)}
                              className="orion-native-select orion-native-select-sm"
                            >
                              <option value="Auto">{t('tts.gender.auto')}</option>
                              <option value="male">{t('tts.gender.male')}</option>
                              <option value="female">{t('tts.gender.female')}</option>
                            </select>
                          </div>
                        </div>

                        {/* Yaş Grubu */}
                        <div className="flex flex-col gap-1">
                          <div className="flex justify-between items-center mb-0.5">
                            <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.age')}</label>
                            {renderDefaultIndicator('age', ttsAge)}
                          </div>
                          <div className="custom-select-wrapper select-wrapper w-full">
                            <select
                              value={ttsAge}
                              onChange={(e) => setTtsAge(e.target.value)}
                              className="orion-native-select orion-native-select-sm"
                            >
                              <option value="Auto">{t('tts.age.auto')}</option>
                              <option value="child">{t('tts.age.child')}</option>
                              <option value="teenager">{t('tts.age.teenager')}</option>
                              <option value="young adult">{t('tts.age.young_adult')}</option>
                              <option value="middle-aged">{t('tts.age.middle_aged')}</option>
                              <option value="elderly">{t('tts.age.elderly')}</option>
                            </select>
                          </div>
                        </div>

                        {/* Ton */}
                        <div className="flex flex-col gap-1">
                          <div className="flex justify-between items-center mb-0.5">
                            <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.pitch')}</label>
                            {renderDefaultIndicator('pitch', ttsPitch)}
                          </div>
                          <div className="custom-select-wrapper select-wrapper w-full">
                            <select
                              value={ttsPitch}
                              onChange={(e) => setTtsPitch(e.target.value)}
                              className="orion-native-select orion-native-select-sm"
                            >
                              <option value="Auto">{t('tts.pitch.auto')}</option>
                              <option value="very high pitch">{t('tts.pitch.very_high')}</option>
                              <option value="high pitch">{t('tts.pitch.high')}</option>
                              <option value="moderate pitch">{t('tts.pitch.moderate')}</option>
                              <option value="low pitch">{t('tts.pitch.low')}</option>
                              <option value="very low pitch">{t('tts.pitch.very_low')}</option>
                            </select>
                          </div>
                        </div>

                        {/* Stil */}
                        <div className="flex flex-col gap-1">
                          <div className="flex justify-between items-center mb-0.5">
                            <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.style')}</label>
                            {renderDefaultIndicator('style', ttsStyle)}
                          </div>
                          <div className="custom-select-wrapper select-wrapper w-full">
                            <select
                              value={ttsStyle}
                              onChange={(e) => setTtsStyle(e.target.value)}
                              className="orion-native-select orion-native-select-sm"
                            >
                              <option value="Auto">{t('tts.style.auto')}</option>
                              <option value="whisper">{t('tts.style.whisper')}</option>
                            </select>
                          </div>
                        </div>

                        {/* Aksan ve Lehçe */}
                        <div className="grid grid-cols-2 gap-2">
                          <div className="flex flex-col gap-1">
                            <div className="flex justify-between items-center mb-0.5">
                              <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.accent')}</label>
                              {renderDefaultIndicator('accent', ttsAccent)}
                            </div>
                            <div className="custom-select-wrapper select-wrapper w-full">
                              <select
                                value={ttsAccent}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setTtsAccent(val);
                                  if (val !== 'Auto') setTtsDialect('Auto');
                                }}
                                className="orion-native-select orion-native-select-sm"
                              >
                                <option value="Auto">{t('tts.accent.auto')}</option>
                                <option value="american accent">{t('tts.accent.american')}</option>
                                <option value="australian accent">{t('tts.accent.australian')}</option>
                                <option value="british accent">{t('tts.accent.british')}</option>
                                <option value="canadian accent">{t('tts.accent.canadian')}</option>
                                <option value="chinese accent">{t('tts.accent.chinese')}</option>
                                <option value="indian accent">{t('tts.accent.indian')}</option>
                                <option value="japanese accent">{t('tts.accent.japanese')}</option>
                                <option value="korean accent">{t('tts.accent.korean')}</option>
                                <option value="portuguese accent">{t('tts.accent.portuguese')}</option>
                                <option value="russian accent">{t('tts.accent.russian')}</option>
                              </select>
                            </div>
                          </div>

                          <div className="flex flex-col gap-1">
                            <div className="flex justify-between items-center mb-0.5">
                              <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.dialect')}</label>
                              {renderDefaultIndicator('dialect', ttsDialect)}
                            </div>
                            <div className="custom-select-wrapper select-wrapper w-full">
                              <select
                                value={ttsDialect}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setTtsDialect(val);
                                  if (val !== 'Auto') setTtsAccent('Auto');
                                }}
                                className="orion-native-select orion-native-select-sm"
                              >
                                <option value="Auto">{t('tts.dialect.auto')}</option>
                                <option value="东北话">Dongbei (东北话)</option>
                                <option value="云南话">Yunnan (云南话)</option>
                                <option value="四川话">Sichuan (四川话)</option>
                                <option value="宁夏话">Ningxia (宁夏话)</option>
                                <option value="桂林话">Guilin (桂林话)</option>
                                <option value="河南话">Henan (河南话)</option>
                                <option value="济南话">Jinan (济南话)</option>
                                <option value="甘肃话">Gansu (甘肃话)</option>
                                <option value="石家庄话">Shijiazhuang (石家庄话)</option>
                                <option value="贵州话">Guizhou (贵州话)</option>
                                <option value="陕西话">Shaanxi (陕西话)</option>
                                <option value="青岛话">Qingdao (青岛话)</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 🌊 Streaming Ayarları */}
                <button
                  type="button"
                  onClick={() => setShowStreamingSettings(!showStreamingSettings)}
                  className="flex items-center justify-between text-left text-zinc-300 text-[10px] font-semibold uppercase tracking-wider mt-2 py-1 border-t border-zinc-850 cursor-pointer hover:text-white transition-colors w-full"
                >
                  <span>{t('tts.streaming.settings')}</span>
                  <span>{showStreamingSettings ? '▼' : '►'}</span>
                </button>

                {showStreamingSettings && (
                  <div className="flex flex-col gap-2 pl-1 border-l border-zinc-800">
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

                {/* ⚙️ Gelişmiş Ayarlar */}
                <button
                  type="button"
                  onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
                  className="flex items-center justify-between text-left text-zinc-300 text-[10px] font-semibold uppercase tracking-wider mt-1 py-1 border-t border-zinc-855 cursor-pointer hover:text-white transition-colors w-full"
                >
                  <span>{t('tts.advanced.settings')}</span>
                  <span>{showAdvancedSettings ? '▼' : '►'}</span>
                </button>

                {showAdvancedSettings && (
                  <div className="flex flex-col gap-3 pl-1 border-l border-zinc-800">
                    {!(isLocalTts && resolvedTtsEngine === 'voxcpm2') && (
                      <div className="flex flex-col gap-1">
                        <div className="flex justify-between items-center mb-0.5">
                          <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.language')}</label>
                          {renderDefaultIndicator('language', ttsLanguage)}
                        </div>
                        {!isLocalTts || (resolvedTtsEngine === 'omnivoice' && localTtsInfo.active && localTtsInfo.engine === 'omnivoice' && languages.length > 0) ? (
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

                    <div className="flex flex-col gap-1">
                      <div className="flex justify-between items-center mb-0.5">
                        <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('tts.speed.speech')}</label>
                        {renderDefaultIndicator('speed', ttsSpeed)}
                      </div>
                      <Input
                        type="number"
                        min="0.1"
                        max="5"
                        step="0.1"
                        value={ttsSpeed}
                        onChange={(e) => setTtsSpeed(e.target.value)}
                        placeholder={getTtsFieldDefault('speed')}
                        className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
                      />
                    </div>

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
                  </div>
                )}
              </div>

              {/* Main Area */}
              <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3">
                <div className="flex flex-col gap-1 flex-1">
                  <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.textToSynthesize')}</label>
                  <Textarea
                    value={ttsInput}
                    onChange={(e) => setTtsInput(e.target.value)}
                    placeholder={t('playground.textToSynthesizePlaceholder')}
                    className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-3 text-xs min-h-[120px] max-h-[220px]"
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
          )}

          {/* EMBEDDING TAB */}
          {activeTab === 'embed' && (
            <div className="playground-layout flex flex-col md:flex-row gap-4">
              {/* Settings Sidebar */}
              <div className="pg-sidebar md:w-[250px] p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3 shrink-0">
                <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide capitalize">{t('playground.embeddingSettings')}</h3>
                <div className="flex flex-col gap-1">
                  <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.modelOrGroup')}</label>
                  <div className="custom-select-wrapper select-wrapper w-full">
                    <select
                      value={embedModel}
                      onChange={(e) => setEmbedModel(e.target.value)}
                      className="orion-native-select orion-native-select-sm"
                    >
                      {getRouteOptions('embed').map((route) => (
                        <option key={route.value} value={route.value}>
                          {route.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Main Area */}
              <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3">
                <div className="flex flex-col gap-1 flex-1">
                  <label className="text-zinc-400 text-[10px] font-semibold capitalize">{t('playground.textToEmbed')}</label>
                  <Textarea
                    value={embedInput}
                    onChange={(e) => setEmbedInput(e.target.value)}
                    placeholder={t('playground.textToEmbedPlaceholder')}
                    className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-3 text-xs min-h-[120px] max-h-[220px]"
                  />
                </div>

                <div className="flex justify-end">
                  {isGeneratingEmbed ? (
                    <Button
                      onClick={() => embedAbortControllerRef.current?.abort()}
                      className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 py-2 rounded-lg text-xs min-w-[70px]"
                    >
                      {t('playground.stop')}
                    </Button>
                  ) : (
                    <Button
                      onClick={handleGenerateEmbedding}
                      className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 py-2 rounded-lg text-xs"
                    >
                      {t('playground.generateVector')}
                    </Button>
                  )}
                </div>

                {embedError && (
                  <div className="text-red-500 bg-red-950/20 border border-red-500/30 rounded p-3 text-xs">
                    {embedError}
                  </div>
                )}

                {embedPreview && (
                  <div className="p-4 bg-black/30 border border-zinc-855 rounded-lg flex flex-col gap-2">
                    <div className="inline-flex max-w-max text-[9px] bg-zinc-800 text-zinc-300 font-semibold tracking-wide uppercase px-2 py-0.5 rounded">
                      {embedDim}
                    </div>
                    <div className="font-mono text-xs text-purple-400 break-all select-all">
                      {embedPreview}
                    </div>
                    <pre className="custom-scrollbar bg-black/50 border border-zinc-850 p-3 rounded text-[11px] font-mono overflow-auto max-h-[180px] text-zinc-300 whitespace-pre">
                      {embedJson}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
