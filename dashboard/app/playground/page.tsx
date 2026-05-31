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
  const { showToast } = useApp();
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

  // Chat State
  const [chatModel, setChatModel] = useState(getSavedState('pg_chatModel', ''));
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
  const [ttsVoice, setTtsVoice] = useState(getSavedState('pg_ttsVoice', 'alloy'));
  const [ttsTemp, setTtsTemp] = useState(getSavedState('pg_ttsTemp', ''));
  const [ttsInput, setTtsInput] = useState('');
  const [ttsUrl, setTtsUrl] = useState('');
  const [ttsError, setTtsError] = useState('');
  const [isGeneratingTTS, setIsGeneratingTTS] = useState(false);
  const ttsAbortControllerRef = useRef<AbortController | null>(null);

  // Embed State
  const [embedModel, setEmbedModel] = useState(getSavedState('pg_embedModel', ''));
  const [embedInput, setEmbedInput] = useState('');
  const [embedError, setEmbedError] = useState('');
  const [embedPreview, setEmbedPreview] = useState('');
  const [embedDim, setEmbedDim] = useState('');
  const [embedJson, setEmbedJson] = useState('');
  const [isGeneratingEmbed, setIsGeneratingEmbed] = useState(false);
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

  useEffect(() => {
    const initData = async () => {
      await loadModels();
      await loadGroups();
      await loadVoices();
    };
    initData();
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

  // Update TTS voices persona when model selection changes
  useEffect(() => {
    if (!ttsModel) {
      setVoices([]);
      return;
    }

    let provider = '';
    const group = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
    if (group && group.items && group.items.length > 0) {
      provider = group.items[0].provider;
    } else {
      const model = models.find((m) => m.name === ttsModel && m.capability === 'tts');
      if (model) {
        provider = model.provider;
      }
    }

    if (provider && voicesByProvider[provider]) {
      const providerVoices = voicesByProvider[provider];
      setVoices(providerVoices);
      if (providerVoices.length > 0 && !providerVoices.includes(ttsVoice)) {
        setTtsVoice(providerVoices[0]);
      }
    } else {
      const allVoices = Object.values(voicesByProvider).flat();
      setVoices(allVoices);
      if (allVoices.length > 0 && !allVoices.includes(ttsVoice)) {
        setTtsVoice(allVoices[0]);
      }
    }
  }, [ttsModel, groups, models, voicesByProvider]);

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
      localStorage.setItem('pg_embedModel', embedModel);
      localStorage.setItem('pg_chatMessages', JSON.stringify(chatMessages));
      localStorage.setItem('pg_chatInput', chatInput);
    }
  }, [activeTab, chatModel, chatTemp, chatThinking, chatSystemPrompt, ttsModel, ttsVoice, ttsTemp, embedModel, chatMessages, chatInput]);

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

    const group = groups.find((g) => g.name === ttsModel && g.capability === 'tts');
    if (group) {
      const primaryItem = group.items?.[0];
      if (primaryItem) {
        const modelDetail = models.find((m) => m.name === primaryItem.name && m.capability === 'tts');
        return {
          temperature: modelDetail?.temperature ?? null,
        };
      }
      return { temperature: null };
    }

    const model = models.find((m) => m.name === ttsModel && m.capability === 'tts');
    if (model) {
      return {
        temperature: model.temperature ?? null,
      };
    }

    return { temperature: null };
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
        },
        body: JSON.stringify(payload),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        setChatMessages((prev) => [
          ...prev,
          {
            id: 'err-' + Date.now(),
            role: 'assistant',
            type: 'content',
            html: `Error: ${res.status} - ${errText}`,
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
      showToast('Please enter text.', 'error');
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

    try {
      setIsGeneratingTTS(true);
      ttsAbortControllerRef.current = new AbortController();

      const res = await fetch(`${apiBaseUrl}/v1/audio/speech`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminKey}`,
        },
        body: JSON.stringify(payload),
        signal: ttsAbortControllerRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
      }

      const blob = await res.blob();
      setTtsUrl(URL.createObjectURL(blob));
      showToast('Audio synthesized successfully!');
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
      showToast('Please enter text.', 'error');
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
        },
        body: JSON.stringify({ model: embedModel, input: text }),
        signal: embedAbortControllerRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || res.statusText);
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
      showToast('Embedding vector generated!');
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

  const hasTempOverride = chatTemp !== '';
  const hasThinkingOverride = chatThinking !== '';
  const hasSystemPromptOverride = chatSystemPrompt !== '';
  const hasTtsTempOverride = ttsTemp !== '';

  return (
    <section id="playground" className="tab-content active block pt-4">
      <header className="flex justify-between items-end mb-4 pb-4 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">Playground</h1>
          <p className="text-zinc-400 text-xs mt-0.5">Test registered models without typing provider names</p>
        </div>
      </header>

      {/* Segmented Controls for Sub-tabs */}
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
            {tab === 'chat' ? 'Chat' : tab === 'tts' ? 'Text-to-Speech' : 'Embeddings'}
          </button>
        ))}
      </div>

      {/* CHAT TAB */}
      {activeTab === 'chat' && (
        <div className="playground-layout flex flex-col md:flex-row gap-4">
          {/* Settings Sidebar */}
          <div className="pg-sidebar md:w-[250px] p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3 shrink-0">
            <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide uppercase">Configuration</h3>
            <div className="flex flex-col gap-1">
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Model or Group</label>
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
              <div className="flex justify-between items-center mb-1">
                <label className="text-zinc-400 text-[10px] font-semibold uppercase">Temperature</label>
                {resolvedDefaults.temperature !== null ? (
                  <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all ${hasTempOverride
                      ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                      : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                    }`} title={hasTempOverride ? "Default is overridden by your input" : "Database default value for this model"}>
                    Default: {resolvedDefaults.temperature}
                  </span>
                ) : (
                  <span className={`text-[9px] font-medium transition-all ${hasTempOverride ? 'text-zinc-700 line-through opacity-50' : 'text-zinc-500'
                    }`}>
                    Default: Provider choice
                  </span>
                )}
              </div>
              <Input
                type="number"
                min="0"
                max="2"
                step="0.1"
                value={chatTemp}
                onChange={(e) => setChatTemp(e.target.value)}
                placeholder="optional (e.g. 0.7)"
                className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
              />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex justify-between items-center mb-1">
                <label className="text-zinc-400 text-[10px] font-semibold uppercase">Thinking</label>
                {resolvedDefaults.thinking_level ? (
                  <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all ${hasThinkingOverride
                      ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                      : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                    }`} title={hasThinkingOverride ? "Default is overridden by your input" : "Database default value for this model"}>
                    Default: {resolvedDefaults.thinking_level}
                  </span>
                ) : (
                  <span className={`text-[9px] font-medium transition-all ${hasThinkingOverride ? 'text-zinc-700 line-through opacity-50' : 'text-zinc-500'
                    }`}>
                    Default: None
                  </span>
                )}
              </div>
              <Input
                value={chatThinking}
                onChange={(e) => setChatThinking(e.target.value)}
                placeholder="optional (e.g. low, 1024)"
                className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
              />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex justify-between items-center mb-1 relative group">
                <label className="text-zinc-400 text-[10px] font-semibold uppercase">System Prompt</label>
                {resolvedDefaults.system_prompt ? (
                  <>
                    <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all cursor-help truncate max-w-[120px] block ${hasSystemPromptOverride
                        ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                        : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                      }`}>
                      Default: {resolvedDefaults.system_prompt.length > 15 ? resolvedDefaults.system_prompt.slice(0, 15) + '...' : resolvedDefaults.system_prompt}
                    </span>
                    <div className="absolute top-full left-0 right-0 mt-1 hidden group-hover:block z-50 bg-[#242427]/98 border border-zinc-700/60 text-zinc-200 text-[10px] p-3 rounded shadow-xl whitespace-pre-wrap max-h-40 overflow-y-auto custom-scrollbar pointer-events-none">
                      <div className="font-semibold text-[9px] text-purple-400 mb-1 uppercase tracking-wide">Default:</div>
                      {resolvedDefaults.system_prompt}
                    </div>
                  </>
                ) : (
                  <span className={`text-[9px] font-medium transition-all ${hasSystemPromptOverride ? 'text-zinc-700 line-through opacity-50' : 'text-zinc-500'
                    }`}>
                    Default: None
                  </span>
                )}
              </div>
              <Textarea
                value={chatSystemPrompt}
                onChange={(e) => setChatSystemPrompt(e.target.value)}
                placeholder="Enter system instructions..."
                className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs h-20 resize-none custom-scrollbar overflow-y-auto no-field-sizing placeholder:text-zinc-600"
              />
            </div>
          </div>

          {/* Main Area */}
          <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col min-h-[380px] h-[calc(100vh-340px)]">
            <div className="chat-messages flex-1 overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar mb-3">
              {chatMessages.length === 0 ? (
                <div className="text-zinc-500 text-xs flex items-center justify-center h-full">
                  No messages yet. Send a query to test your routing setup.
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
                placeholder="Type a message to the AI..."
                className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-2.5 text-xs h-10 min-h-10 resize-none custom-scrollbar"
              />
              <Button
                onClick={() => setChatMessages([])}
                className="bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700 font-medium px-4 h-10 text-xs rounded-lg"
                title="Clear Chat"
              >
                Clear
              </Button>
              {isGenerating ? (
                <Button
                  onClick={() => abortControllerRef.current?.abort()}
                  className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 h-10 text-xs rounded-lg min-w-[70px]"
                >
                  Stop
                </Button>
              ) : (
                <Button
                  onClick={handleSendChat}
                  className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 h-10 text-xs rounded-lg min-w-[70px]"
                >
                  Send
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
            <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide uppercase">Audio Settings</h3>
            <div className="flex flex-col gap-1">
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Model or Group</label>
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
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Voice Persona</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={ttsVoice}
                  onChange={(e) => setTtsVoice(e.target.value)}
                  className="orion-native-select orion-native-select-sm"
                >
                  {voices.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex justify-between items-center mb-1">
                <label className="text-zinc-400 text-[10px] font-semibold uppercase">Temperature</label>
                {resolvedTtsDefaults.temperature !== null ? (
                  <span className={`text-[9px] font-medium px-1 py-0.5 rounded border transition-all ${hasTtsTempOverride
                      ? 'text-zinc-600 border-zinc-800/40 line-through opacity-50'
                      : 'text-purple-400 bg-purple-950/20 border-purple-500/10'
                    }`} title={hasTtsTempOverride ? "Default is overridden by your input" : "Database default value for this model"}>
                    Default: {resolvedTtsDefaults.temperature}
                  </span>
                ) : (
                  <span className={`text-[9px] font-medium transition-all ${hasTtsTempOverride ? 'text-zinc-700 line-through opacity-50' : 'text-zinc-500'
                    }`}>
                    Default: Provider choice
                  </span>
                )}
              </div>
              <Input
                type="number"
                min="0"
                max="2"
                step="0.1"
                value={ttsTemp}
                onChange={(e) => setTtsTemp(e.target.value)}
                placeholder="optional"
                className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs placeholder:text-zinc-600"
              />
            </div>
          </div>

          {/* Main Area */}
          <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3">
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Text to synthesize</label>
              <Textarea
                value={ttsInput}
                onChange={(e) => setTtsInput(e.target.value)}
                placeholder="Text to synthesize..."
                className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-3 text-xs min-h-[120px] max-h-[220px]"
              />
            </div>

            <div className="flex justify-end">
              {isGeneratingTTS ? (
                <Button
                  onClick={() => ttsAbortControllerRef.current?.abort()}
                  className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 py-2 rounded-lg text-xs min-w-[70px]"
                >
                  Stop
                </Button>
              ) : (
                <Button
                  onClick={handleGenerateTTS}
                  className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 py-2 rounded-lg text-xs"
                >
                  Generate Audio
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
                  Download
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
            <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide uppercase">Embedding Settings</h3>
            <div className="flex flex-col gap-1">
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Model or Group</label>
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
              <label className="text-zinc-400 text-[10px] font-semibold uppercase">Text to embed</label>
              <Textarea
                value={embedInput}
                onChange={(e) => setEmbedInput(e.target.value)}
                placeholder="Text to embed..."
                className="flex-1 bg-black/40 border border-zinc-850 text-white rounded p-3 text-xs min-h-[120px] max-h-[220px]"
              />
            </div>

            <div className="flex justify-end">
              {isGeneratingEmbed ? (
                <Button
                  onClick={() => embedAbortControllerRef.current?.abort()}
                  className="bg-red-600 text-white hover:bg-red-700 font-semibold px-5 py-2 rounded-lg text-xs min-w-[70px]"
                >
                  Stop
                </Button>
              ) : (
                <Button
                  onClick={handleGenerateEmbedding}
                  className="bg-white text-black hover:bg-zinc-200 font-semibold px-5 py-2 rounded-lg text-xs"
                >
                  Generate Vector
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
    </section>
  );
}
