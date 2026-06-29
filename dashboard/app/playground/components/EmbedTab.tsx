'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { getAdminKey } from '@/lib/api';

interface RouteOption {
  value: string;
  label: string;
}

interface EmbedTabProps {
  models: any[];
  groups: any[];
}

export default function EmbedTab({ models, groups }: EmbedTabProps) {
  const { showToast, locale, t } = useApp();

  const getSavedState = (key: string, defaultVal: string) => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || defaultVal;
    }
    return defaultVal;
  };

  // Embed State
  const [embedModel, setEmbedModel] = useState(getSavedState('pg_embedModel', ''));
  const [embedInput, setEmbedInput] = useState('');
  const [embedError, setEmbedError] = useState('');
  const [embedPreview, setEmbedPreview] = useState('');
  const [embedDim, setEmbedDim] = useState('');
  const [embedJson, setEmbedJson] = useState('');
  const [isGeneratingEmbed, setIsGeneratingEmbed] = useState(false);
  const embedAbortControllerRef = useRef<AbortController | null>(null);

  // Update dropdown targets on models/groups load
  useEffect(() => {
    if (models.length > 0 || groups.length > 0) {
      const embedOpts = getRouteOptions('embed');
      if (embedOpts.length > 0 && (!embedModel || !embedOpts.find(o => o.value === embedModel))) {
        setEmbedModel(embedOpts[0].value);
      }
    }
  }, [models, groups]);

  // Save states to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('pg_embedModel', embedModel);
    }
  }, [embedModel]);

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

  return (
    <div className="playground-layout flex flex-col md:flex-row gap-4 animate-in fade-in duration-200">
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
  );
}
