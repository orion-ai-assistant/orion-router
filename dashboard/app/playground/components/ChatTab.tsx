'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { getAdminKey } from '@/lib/api';

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

interface ChatTabProps {
  models: any[];
  groups: any[];
}

export default function ChatTab({ models, groups }: ChatTabProps) {
  const { showToast, locale, t } = useApp();

  const getSavedState = (key: string, defaultVal: string) => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || defaultVal;
    }
    return defaultVal;
  };

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

  // Update dropdown targets on models/groups load
  useEffect(() => {
    if (models.length > 0 || groups.length > 0) {
      const chatOpts = getRouteOptions('chat');
      if (chatOpts.length > 0 && (!chatModel || !chatOpts.find(o => o.value === chatModel))) {
        setChatModel(chatOpts[0].value);
      }
    }
  }, [models, groups]);

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
      localStorage.setItem('pg_chatModel', chatModel);
      localStorage.setItem('pg_chatTemp', chatTemp);
      localStorage.setItem('pg_chatThinking', chatThinking);
      localStorage.setItem('pg_chatSystemPrompt', chatSystemPrompt);
      localStorage.setItem('pg_chatMessages', JSON.stringify(chatMessages));
      localStorage.setItem('pg_chatInput', chatInput);
    }
  }, [chatModel, chatTemp, chatThinking, chatSystemPrompt, chatMessages, chatInput]);

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

  const renderDefaultIndicator = (field: string, userValue: string, isChat: boolean = false) => {
    let defVal = '';
    const defaults = getResolvedDefaults();
    const val = defaults[field as keyof typeof defaults];
    if (val !== undefined && val !== null && val !== '') {
      defVal = String(val);
    }

    let isOverridden = userValue !== defVal;

    let displayVal = defVal;
    if (!defVal) {
      displayVal = '-';
    } else if (field === 'system_prompt') {
      displayVal = defVal.length > 15 ? defVal.slice(0, 15) + '...' : defVal;
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

  const selectedChatGroup = groups.find((g) => g.name === chatModel && g.capability === 'chat');
  const resolvedDefaults = getResolvedDefaults();
  const hasTempOverride = chatTemp !== '';
  const hasThinkingOverride = chatThinking !== '';
  const hasSystemPromptOverride = chatSystemPrompt !== '';

  return (
    <div className="playground-layout flex flex-col md:flex-row gap-4 animate-in fade-in duration-200">
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
                  <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">{t('playground.groupTemperature')}</div>
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
                      <span className="text-zinc-500 text-[9px]">{t('playground.noModelsInGroup')}</span>
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
                  <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">{t('playground.groupThinking')}</div>
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
                      <span className="text-zinc-500 text-[9px]">{t('playground.noModelsInGroup')}</span>
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
        <div className="flex flex-col gap-1 flex-1 min-h-0">
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
                  <div className="font-semibold text-[9px] text-purple-400 mb-1.5 uppercase tracking-wide">{t('playground.groupSystemPrompt')}</div>
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
                      <span className="text-zinc-500 text-[9px]">{t('playground.noModelsInGroup')}</span>
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
            className="bg-black/40 border border-zinc-850 text-white rounded px-2.5 py-1.5 text-xs h-20 resize-none custom-scrollbar overflow-y-auto no-field-sizing placeholder:text-zinc-600 flex-1"
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
                className={`max-w-[85%] rounded-lg p-3 text-xs leading-relaxed break-all ${msg.role === 'user'
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
  );
}
