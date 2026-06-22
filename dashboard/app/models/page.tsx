'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { adminFetch } from '@/lib/api';
import { money } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Trash2 } from 'lucide-react';

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  capability: 'chat' | 'tts' | 'embed';
  temperature: number | null;
  is_active: boolean;
  input_price: number | string;
  output_price: number | string;
  think_price: number | string;
  thinking_level?: string | null;
  system_prompt?: string | null;
  default_config?: Record<string, any>;
  _original?: {
    name: string;
    provider: string;
    capability: 'chat' | 'tts' | 'embed';
    temperature: number | null;
    is_active: boolean;
    input_price: number;
    output_price: number;
    think_price: number;
    thinking_level?: string | null;
    system_prompt?: string | null;
    default_config?: Record<string, any>;
  };
}

class TTSDefaultConfig {
  voice: string;
  gender: string;
  age: string;
  pitch: string;
  style: string;
  accent: string;
  language: string;
  speed: string;
  steps: string;
  seed: string;
  engine: string;
  tts_instruct: string;

  constructor(data?: Partial<TTSDefaultConfig>) {
    this.voice = data?.voice || '';
    this.gender = data?.gender || 'Auto';
    this.age = data?.age || 'Auto';
    this.pitch = data?.pitch || 'Auto';
    this.style = data?.style || 'Auto';
    this.accent = data?.accent || 'Auto';
    this.language = data?.language || 'Auto';
    this.speed = data?.speed ? String(data.speed) : '';
    this.steps = data?.steps ? String(data.steps) : '';
    this.seed = data?.seed ? String(data.seed) : '';
    this.engine = data?.engine || 'omnivoice';
    this.tts_instruct = data?.tts_instruct || '';
  }

  static fromObject(obj: any): TTSDefaultConfig {
    if (!obj) {
      return new TTSDefaultConfig();
    }
    if (typeof obj === 'string') {
      try {
        obj = JSON.parse(obj);
      } catch (e) {
        return new TTSDefaultConfig();
      }
    }
    if (typeof obj !== 'object') {
      return new TTSDefaultConfig();
    }
    return new TTSDefaultConfig({
      voice: obj.voice,
      gender: obj.gender,
      age: obj.age,
      pitch: obj.pitch,
      style: obj.style,
      accent: obj.accent,
      language: obj.language,
      speed: obj.speed,
      steps: obj.steps,
      seed: obj.seed,
      engine: obj.engine,
      tts_instruct: obj.tts_instruct,
    });
  }

  toObject(): Record<string, any> {
    const obj: Record<string, any> = {};
    if (this.voice) obj.voice = this.voice;
    if (this.gender && this.gender !== 'Auto') obj.gender = this.gender;
    if (this.age && this.age !== 'Auto') obj.age = this.age;
    if (this.pitch && this.pitch !== 'Auto') obj.pitch = this.pitch;
    if (this.style && this.style !== 'Auto') obj.style = this.style;
    if (this.accent && this.accent !== 'Auto') obj.accent = this.accent;
    if (this.language && this.language !== 'Auto') obj.language = this.language;
    if (this.speed) obj.speed = this.speed;
    if (this.steps) obj.steps = this.steps;
    if (this.seed) obj.seed = this.seed;
    if (this.engine) obj.engine = this.engine;
    if (this.tts_instruct) obj.tts_instruct = this.tts_instruct;
    return obj;
  }
}

const formatPriceForInput = (val: number | string | null | undefined): string => {
  if (val === null || val === undefined || val === '') return '';
  const num = Number(val);
  if (isNaN(num)) return '';
  if (num === 0) return '0';
  const str = num.toString();
  if (str.includes('e') || str.includes('E')) {
    return num.toFixed(20).replace(/\.?0+$/, '');
  }
  return str;
};

const cleanNumberInput = (val: string): string => {
  if (val === '') return '';
  if (val.includes('e') || val.includes('E')) {
    const num = Number(val);
    if (!isNaN(num)) {
      return num.toFixed(20).replace(/\.?0+$/, '');
    }
  }
  return val;
};

export default function ModelsPage() {
  const { showToast, confirmAction, t } = useApp();
  const [models, setModels] = useState<ModelItem[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [voicesByProvider, setVoicesByProvider] = useState<Record<string, string[]>>({});
  const [languagesByProvider, setLanguagesByProvider] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [localTtsInfo, setLocalTtsInfo] = useState<{
    active: boolean;
    engine: string | null;
    voices: string[];
    languages: string[];
  }>({ active: false, engine: null, voices: [], languages: [] });

  // Modals visibility
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showEditModal, setShowEditModal] = useState<boolean>(false);

  // Form states
  const [addForm, setAddForm] = useState({
    name: '',
    provider: '',
    capability: 'chat' as 'chat' | 'tts' | 'embed',
    temperature: '' as string | number,
    input_price: '0' as string | number,
    output_price: '0' as string | number,
    think_price: '0' as string | number,
    thinking_level: '',
    system_prompt: '',
    default_config: {} as Record<string, any>,
  });

  const [editingModel, setEditingModel] = useState<ModelItem>({
    id: '',
    name: '',
    provider: '',
    capability: 'chat',
    temperature: null,
    is_active: true,
    input_price: '0',
    output_price: '0',
    think_price: '0',
    thinking_level: null,
    system_prompt: null,
  });

  const [showAddTtsDefaults, setShowAddTtsDefaults] = useState(false);
  const [showEditTtsDefaults, setShowEditTtsDefaults] = useState(false);

  const loadProviders = async () => {
    try {
      const res = await adminFetch('/dashboard/api/providers');
      if (res.ok) {
        const data = await res.json();
        const pNames = Object.keys(data.providers || {});
        setProviders(pNames);
        if (pNames.length > 0) {
          setAddForm((prev) => ({ ...prev, provider: pNames[0] }));
        }
      }
    } catch (e) {
      console.error('Failed to load providers:', e);
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

  const loadModels = async () => {
    try {
      const res = await adminFetch('/dashboard/api/models');
      if (res.ok) {
        const data = await res.json();
        const loadedModels = (data.models || []).map((model: any) => {
          const name = model.name || '';
          const provider = model.provider || '';
          const capability = model.capability || 'chat';
          const temperature = model.temperature !== null ? parseFloat(model.temperature) : null;
          const is_active = !!model.is_active;
          const input_price = model.input_price || 0;
          const output_price = model.output_price || 0;
          const think_price = model.think_price || 0;
          const thinking_level = model.thinking_level || null;
          const system_prompt = model.system_prompt || null;
          const default_config = TTSDefaultConfig.fromObject(model.default_config).toObject();

          return {
            ...model,
            name,
            provider,
            capability,
            temperature,
            is_active,
            input_price,
            output_price,
            think_price,
            thinking_level,
            system_prompt,
            default_config,
            _original: {
              name,
              provider,
              capability,
              temperature,
              is_active,
              input_price,
              output_price,
              think_price,
              thinking_level,
              system_prompt,
              default_config,
            },
          };
        });
        setModels(loadedModels);
      }
    } catch (err) {
      console.error('Failed to load models:', err);
      showToast(t('models.toast.loadFailed'), 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initData = async () => {
      await loadProviders();
      await loadVoices();
      await loadLanguages();
      await loadLocalTtsInfo();
      await loadModels();
    };
    initData();

    const handleAuth = () => {
      initData();
    };
    window.addEventListener('orion-authenticated', handleAuth);
    return () => {
      window.removeEventListener('orion-authenticated', handleAuth);
    };
  }, []);

  // Grouped models by provider, sorted alphabetically by name
  const groupedModels = useMemo(() => {
    const groups: Record<string, ModelItem[]> = {};
    models.forEach(m => {
      if (!groups[m.provider]) groups[m.provider] = [];
      groups[m.provider].push(m);
    });
    // Sort each group by name
    Object.keys(groups).forEach(p => {
      groups[p].sort((a, b) => a.name.localeCompare(b.name));
    });
    return groups;
  }, [models]);

  const getAvailableVoices = (provider: string) => {
    let nextVoices: string[] = [];
    if (provider && voicesByProvider[provider]) {
      nextVoices = voicesByProvider[provider].filter(v => v.toLowerCase() !== 'none');
    }
    return nextVoices;
  };

  const getAvailableLanguages = (provider: string) => {
    if (provider && languagesByProvider[provider]) {
      return languagesByProvider[provider];
    }
    return [];
  };

  const normalizeTemperature = (value: string | number | null | undefined): number | null => {
    if (value === '' || value === null || value === undefined) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const updateDefaultConfig = (
    formState: any,
    setFormState: Function,
    key: keyof TTSDefaultConfig,
    value: any
  ) => {
    const config = TTSDefaultConfig.fromObject(formState.default_config);
    (config as any)[key] = value;
    setFormState({
      ...formState,
      default_config: config.toObject()
    });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = addForm.name.trim();
    const provider = addForm.provider.trim();
    const capability = addForm.capability;

    if (!name || !provider) {
      showToast(t('models.toast.enterNameSelectProvider'), 'error');
      return;
    }

    const tempVal = normalizeTemperature(addForm.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast(t('models.toast.invalidTemperature'), 'error');
      return;
    }

    try {
      let configObj = {};
      if (capability === 'tts') {
        const config = TTSDefaultConfig.fromObject(addForm.default_config);
        if (!config.voice && provider !== 'local') {
          const providerVoices = getAvailableVoices(provider);
          if (providerVoices.length > 0) {
            config.voice = providerVoices[0];
          }
        }
        configObj = config.toObject();
      }

      const res = await adminFetch('/dashboard/api/models', {
        method: 'POST',
        body: JSON.stringify({
          name,
          provider,
          capability,
          temperature: tempVal,
          is_active: true,
          input_price: parseFloat(addForm.input_price as string) || 0,
          output_price: parseFloat(addForm.output_price as string) || 0,
          think_price: parseFloat(addForm.think_price as string) || 0,
          thinking_level: addForm.thinking_level || null,
          system_prompt: addForm.system_prompt || null,
          default_config: configObj,
        }),
      });
      if (res.ok) {
        setAddForm({
          name: '',
          provider: providers[0] || '',
          capability: 'chat',
          temperature: '',
          input_price: '0',
          output_price: '0',
          think_price: '0',
          thinking_level: '',
          system_prompt: '',
          default_config: {},
        });
        setShowAddModal(false);
        showToast(t('models.toast.addSuccess'));
        await loadModels();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('models.toast.addFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('models.toast.addFailed'), 'error');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = editingModel.name.trim();
    const provider = editingModel.provider.trim();

    if (!name || !provider) {
      showToast(t('models.toast.nameProviderEmpty'), 'error');
      return;
    }

    const tempVal = normalizeTemperature(editingModel.temperature);
    if (tempVal !== null && (tempVal < 0 || tempVal > 2)) {
      showToast(t('models.toast.invalidTemperature'), 'error');
      return;
    }

    try {
      let configObj = {};
      if (editingModel.capability === 'tts') {
        const config = TTSDefaultConfig.fromObject(editingModel.default_config);
        if (!config.voice && provider !== 'local') {
          const providerVoices = getAvailableVoices(provider);
          if (providerVoices.length > 0) {
            config.voice = providerVoices[0];
          }
        }
        configObj = config.toObject();
      }

      const res = await adminFetch(`/dashboard/api/models/${editingModel.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name,
          provider,
          capability: editingModel.capability,
          temperature: tempVal,
          is_active: !!editingModel.is_active,
          input_price: parseFloat(editingModel.input_price as string) || 0,
          output_price: parseFloat(editingModel.output_price as string) || 0,
          think_price: parseFloat(editingModel.think_price as string) || 0,
          thinking_level: editingModel.thinking_level || null,
          system_prompt: editingModel.system_prompt || null,
          default_config: configObj,
        }),
      });
      if (res.ok) {
        showToast(t('models.toast.updateSuccess'));
        setShowEditModal(false);
        await loadModels();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('models.toast.updateFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('models.toast.updateFailed'), 'error');
    }
  };

  const handleDelete = async (modelId: string, confirmed = false) => {
    if (!confirmed) {
      confirmAction(t('common.confirm.deleteModel'), () =>
        handleDelete(modelId, true)
      );
      return;
    }
    try {
      const res = await adminFetch(`/dashboard/api/models/${modelId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setShowEditModal(false);
        showToast(t('models.toast.deleteSuccess'));
        await loadModels();
      } else {
        const err = await res.json();
        showToast(t('common.error') + ': ' + (err.detail || t('models.toast.deleteFailed')), 'error');
      }
    } catch (err) {
      console.error(err);
      showToast(t('models.toast.deleteFailed'), 'error');
    }
  };

  const isModelDirty = (model: ModelItem) => {
    if (!model || !model._original) return false;
    return (
      model.name !== model._original.name ||
      model.provider !== model._original.provider ||
      model.capability !== model._original.capability ||
      normalizeTemperature(model.temperature) !== model._original.temperature ||
      !!model.is_active !== model._original.is_active ||
      Number(model.input_price || 0) !== Number(model._original.input_price || 0) ||
      Number(model.output_price || 0) !== Number(model._original.output_price || 0) ||
      Number(model.think_price || 0) !== Number(model._original.think_price || 0) ||
      (model.thinking_level || null) !== (model._original.thinking_level || null) ||
      (model.system_prompt || null) !== (model._original.system_prompt || null) ||
      JSON.stringify(model.default_config || {}) !== JSON.stringify(model._original.default_config || {})
    );
  };

  const openEditModal = (model: ModelItem) => {
    setEditingModel({
      ...model,
      temperature: model.temperature === null ? '' : (model.temperature as any),
      input_price: formatPriceForInput(model.input_price),
      output_price: formatPriceForInput(model.output_price),
      think_price: formatPriceForInput(model.think_price),
    });
    setShowEditTtsDefaults(false);
    setShowEditModal(true);
  };

  const renderTtsDefaults = (formState: any, setFormState: Function, showDefaults: boolean, setShowDefaults: Function) => {
    if (formState.capability !== 'tts') return null;

    const isLocal = formState.provider === 'local';
    const selectedEngine = isLocal ? (formState.default_config?.engine || 'omnivoice') : 'omnivoice';

    // Determine voice selection mode
    let voices: string[] = [];
    let showVoiceSelect = false;
    if (isLocal) {
      if (localTtsInfo.active && localTtsInfo.engine === selectedEngine) {
        voices = localTtsInfo.voices;
        showVoiceSelect = voices.length > 0;
      } else {
        showVoiceSelect = false;
      }
    } else {
      voices = getAvailableVoices(formState.provider);
      showVoiceSelect = voices.length > 0;
    }

    // Determine language selection mode
    let languages: string[] = [];
    let showLangSelect = false;
    if (isLocal) {
      if (selectedEngine === 'omnivoice') {
        if (localTtsInfo.active && localTtsInfo.engine === 'omnivoice') {
          languages = localTtsInfo.languages;
        } else {
          languages = ['Auto', 'Turkish', 'English'];
        }
        showLangSelect = true;
      } else {
        showLangSelect = false;
      }
    } else {
      languages = getAvailableLanguages(formState.provider);
      showLangSelect = languages.length > 0;
    }

    const hasPersona = !!formState.default_config?.voice;

    return (
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => setShowDefaults(!showDefaults)}
          className="flex items-center justify-between text-left text-zinc-300 text-[11px] font-semibold uppercase tracking-wider py-1.5 cursor-pointer hover:text-white transition-colors w-full border-t border-zinc-800 pt-3"
        >
          <span>🎛️ TTS Ayarları (Varsayılan)</span>
          <span className="text-[10px]">{showDefaults ? '▼' : '►'}</span>
        </button>

        {showDefaults && (
          <div className="flex flex-col gap-3 pl-2 border-l border-zinc-800">
            {isLocal && (
              <div className="flex flex-col gap-1">
                <div className="flex justify-between items-center">
                  <label className="text-zinc-500 text-[11px] font-medium">Yerel Motor (Engine)</label>
                  {localTtsInfo.active ? (
                    <span className="text-[9px] text-zinc-400">
                      Aktif: <strong className="text-emerald-400">{localTtsInfo.engine}</strong>
                    </span>
                  ) : (
                    <span className="text-[9px] text-red-400 font-semibold">Servis Çevrimdışı</span>
                  )}
                </div>
                <div className="custom-select-wrapper select-wrapper w-full">
                  <select
                    value={formState.default_config?.engine || 'omnivoice'}
                    onChange={(e) => updateDefaultConfig(formState, setFormState, 'engine', e.target.value)}
                    className="orion-native-select"
                  >
                    <option value="omnivoice">Omni Voice (omnivoice)</option>
                    <option value="voxcpm2">VOXCPM2 (voxcpm2)</option>
                  </select>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 text-[11px] font-medium">Voice Persona (Kişi)</label>
              {showVoiceSelect ? (
                <div className="custom-select-wrapper select-wrapper w-full">
                  <select
                    value={formState.default_config?.voice || (isLocal ? '' : (voices[0] || ''))}
                    onChange={(e) => updateDefaultConfig(formState, setFormState, 'voice', e.target.value)}
                    className="orion-native-select"
                  >
                    {isLocal && <option value="">None</option>}
                    {voices.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <Input
                  value={formState.default_config?.voice || ''}
                  onChange={(e) => updateDefaultConfig(formState, setFormState, 'voice', e.target.value)}
                  placeholder={isLocal ? "Ses adını elle yazın (Klon/Persona)..." : "alloy, nova, vs."}
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                />
              )}
            </div>

            {isLocal && selectedEngine === 'voxcpm2' && (
              <div className="flex flex-col gap-1">
                <label className="text-zinc-500 text-[11px] font-medium">Konuşma Tarzı Açıklaması (tts_instruct)</label>
                <Textarea
                  value={formState.default_config?.tts_instruct || ''}
                  onChange={(e) => updateDefaultConfig(formState, setFormState, 'tts_instruct', e.target.value)}
                  placeholder="Karakteri betimleyin. Örn: A young girl with a soft, sweet voice. Speaks slowly with a melancholic tone."
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs h-16 resize-none custom-scrollbar"
                />
              </div>
            )}

            {isLocal && selectedEngine === 'omnivoice' && (
              <>
                <div className={`flex flex-col gap-3 ${hasPersona ? 'opacity-50 pointer-events-none' : ''}`}>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-zinc-400 text-[10px] font-semibold uppercase">🎭 Karakter Tasarımı</span>
                    {hasPersona && (
                      <span className="text-[8px] text-zinc-600 font-medium bg-black/40 px-1 py-0.5 rounded border border-zinc-800 normal-case">Persona Aktif</span>
                    )}
                  </div>
                  
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-zinc-500 text-[10px]">Cinsiyet (Gender)</label>
                      <div className="custom-select-wrapper select-wrapper w-full">
                        <select
                           value={formState.default_config?.gender || 'Auto'}
                           onChange={(e) => updateDefaultConfig(formState, setFormState, 'gender', e.target.value)}
                           className="orion-native-select orion-native-select-sm"
                        >
                          <option value="Auto">Auto</option>
                          <option value="male">male (Erkek)</option>
                          <option value="female">female (Kadın)</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-zinc-500 text-[10px]">Yaş Grubu (Age)</label>
                      <div className="custom-select-wrapper select-wrapper w-full">
                        <select
                          value={formState.default_config?.age || 'Auto'}
                          onChange={(e) => updateDefaultConfig(formState, setFormState, 'age', e.target.value)}
                          className="orion-native-select orion-native-select-sm"
                        >
                          <option value="Auto">Auto</option>
                          <option value="child">child (Çocuk)</option>
                          <option value="teenager">teenager (Genç)</option>
                          <option value="young adult">young adult (Genç Yt.)</option>
                          <option value="middle-aged">middle-aged (Orta)</option>
                          <option value="elderly">elderly (Yaşlı)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-zinc-500 text-[10px]">Ton (Pitch)</label>
                      <div className="custom-select-wrapper select-wrapper w-full">
                        <select
                          value={formState.default_config?.pitch || 'Auto'}
                          onChange={(e) => updateDefaultConfig(formState, setFormState, 'pitch', e.target.value)}
                          className="orion-native-select orion-native-select-sm"
                        >
                          <option value="Auto">Auto</option>
                          <option value="very high pitch">very high (Çok Tiz)</option>
                          <option value="high pitch">high (Tiz)</option>
                          <option value="moderate pitch">moderate (Normal)</option>
                          <option value="low pitch">low (Pes)</option>
                          <option value="very low pitch">very low (Çok Pes)</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-zinc-500 text-[10px]">Stil (Style)</label>
                      <div className="custom-select-wrapper select-wrapper w-full">
                        <select
                          value={formState.default_config?.style || 'Auto'}
                          onChange={(e) => updateDefaultConfig(formState, setFormState, 'style', e.target.value)}
                          className="orion-native-select orion-native-select-sm"
                        >
                          <option value="Auto">Auto</option>
                          <option value="whisper">whisper (Fısıltı)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-zinc-500 text-[10px]">Aksan (Accent)</label>
                    <div className="custom-select-wrapper select-wrapper w-full">
                      <select
                        value={formState.default_config?.accent || 'Auto'}
                        onChange={(e) => updateDefaultConfig(formState, setFormState, 'accent', e.target.value)}
                        className="orion-native-select orion-native-select-sm"
                      >
                        <option value="Auto">Auto</option>
                        <option value="american accent">american accent</option>
                        <option value="australian accent">australian accent</option>
                        <option value="british accent">british accent</option>
                        <option value="canadian accent">canadian accent</option>
                        <option value="chinese accent">chinese accent</option>
                        <option value="indian accent">indian accent</option>
                        <option value="japanese accent">japanese accent</option>
                        <option value="korean accent">korean accent</option>
                        <option value="portuguese accent">portuguese accent</option>
                        <option value="russian accent">russian accent</option>
                      </select>
                    </div>
                  </div>
                </div>
              </>
            )}

            {isLocal && (
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-zinc-800/50">
                <span className="text-zinc-400 text-[10px] font-semibold uppercase">⚙️ Gelişmiş Ayarlar</span>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 text-[11px] font-medium">Dil (Language)</label>
              {showLangSelect ? (
                <div className="custom-select-wrapper select-wrapper w-full">
                  <select
                    value={formState.default_config?.language || 'Auto'}
                    onChange={(e) => updateDefaultConfig(formState, setFormState, 'language', e.target.value)}
                    className="orion-native-select"
                  >
                    <option value="Auto">Auto</option>
                    {languages.map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </div>
              ) : (
                <Input
                  value={formState.default_config?.language || ''}
                  onChange={(e) => updateDefaultConfig(formState, setFormState, 'language', e.target.value)}
                  placeholder="Auto, English, Turkish..."
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                />
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-zinc-500 text-[11px] font-medium">Hız (Speed)</label>
                <Input
                  type="number" min="0.1" max="5" step="0.1"
                  value={formState.default_config?.speed || ''}
                  onChange={(e) => updateDefaultConfig(formState, setFormState, 'speed', e.target.value)}
                  placeholder="1.0"
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-zinc-500 text-[11px] font-medium">Adım (Steps)</label>
                <Input
                  type="number" min="1" max="50" step="1"
                  value={formState.default_config?.steps || ''}
                  onChange={(e) => updateDefaultConfig(formState, setFormState, 'steps', e.target.value)}
                  placeholder="15"
                  className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-zinc-500 text-[11px] font-medium">Seed (-1: Rastgele)</label>
              <Input
                type="number"
                value={formState.default_config?.seed || ''}
                onChange={(e) => updateDefaultConfig(formState, setFormState, 'seed', e.target.value)}
                placeholder="-1"
                className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
              />
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <section id="models" className="tab-content active block pt-8">
      <header className="flex justify-between items-end mb-8 pb-6 border-b border-border">
        <div className="header-titles">
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{t('models.title')}</h1>
          <p className="text-zinc-400 text-sm mt-1">{t('models.description')}</p>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Yerel TTS Motoru:</span>
            {localTtsInfo.active ? (
              <Badge className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px] font-medium tracking-wide rounded px-2 py-0.5 uppercase">
                🟢 {localTtsInfo.engine?.toUpperCase() || 'BİLİNMİYOR'} AKTİF
              </Badge>
            ) : (
              <Badge className="bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] font-medium tracking-wide rounded px-2 py-0.5 uppercase">
                🔴 ÇEVRİMDİŞİ / BULUNAMADI
              </Badge>
            )}
          </div>
        </div>
        <Button
          onClick={() => setShowAddModal(true)}
          className="bg-white text-black hover:bg-zinc-200 font-medium px-6 py-2.5 rounded-full transition-all duration-200 shadow-md hover:shadow-lg flex items-center gap-1.5"
        >
          + {t('models.addModel')}
        </Button>
      </header>

      {/* Provider Group List */}
      <div className="group-list flex flex-col gap-6">
        {loading ? (
          <div className="glass-panel p-8 text-center text-zinc-400">{t('models.loading')}</div>
        ) : Object.keys(groupedModels).length === 0 ? (
          <div className="glass-panel p-8 text-center text-zinc-400">
            {t('models.empty')}
          </div>
        ) : (
          Object.entries(groupedModels).map(([provider, providerModels]) => (
            <div key={provider} className="glass-panel group-card p-6 bg-[#18181b] border border-zinc-800 rounded-md shadow-xl">
              <div className="group-card-header mb-5">
                <div className="group-card-title-section flex items-center gap-3 w-full">
                  <Badge className="bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-medium tracking-wide rounded uppercase px-2.5 py-0.5 capitalize">
                    {provider}
                  </Badge>
                  <h3 className="font-heading text-lg font-semibold text-white capitalize">{provider} {t('models.providerModels')}</h3>
                  <div className="flex gap-2 ml-auto items-center text-xs text-zinc-500">
                    {providerModels.length} {providerModels.length === 1 ? t('models.modelCount') : t('models.modelsCount')}
                  </div>
                </div>
              </div>

              <div className="group-items flex flex-col gap-2">
                {providerModels.map((model) => (
                  <div
                    key={model.id}
                    className="model-item-row bg-black/20 border border-zinc-850 rounded px-4 py-3 min-h-[52px] grid grid-cols-[minmax(172px,302px)_280px_80px_1fr_auto] gap-4 items-center hover:border-zinc-600 hover:bg-black/35"
                  >
                    <div className="font-semibold text-sm font-mono text-white select-all truncate">
                      {model.name}
                    </div>
                    
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <Badge className="bg-zinc-800 text-zinc-300 border border-zinc-700/50 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0">
                        {model.capability}
                      </Badge>
                      {model.thinking_level && (
                        <Badge className="bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 normal-case">
                          {t('models.think')}: {model.thinking_level}
                        </Badge>
                      )}
                      {model.system_prompt && (
                        <Badge className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[9px] font-normal tracking-wide rounded normal-case px-1.5 py-0">
                          {t('models.systemPrompt')}
                        </Badge>
                      )}
                      {model.temperature !== null && (
                        <Badge className="bg-orange-500/10 text-orange-300 border border-orange-500/20 text-[9px] font-normal tracking-wide rounded uppercase px-1.5 py-0 normal-case">
                          {t('models.temp')}: {model.temperature}
                        </Badge>
                      )}
                    </div>

                    <div className="flex items-center">
                      {!model.is_active && (
                        <Badge className="bg-red-500/10 text-red-500 border border-red-500/20 text-[9px] font-semibold tracking-wide uppercase px-1.5 py-0 rounded">
                          {t('models.inactive')}
                        </Badge>
                      )}
                    </div>
                    
                    <div className="pricing-container flex items-center gap-4">
                      {(model.capability === 'chat' || model.capability === 'tts' || model.capability === 'embed') && (
                        <div className="flex flex-col items-center justify-center gap-0.5">
                          <span className="text-[9px] font-semibold text-zinc-500 capitalize tracking-wider">{t('models.in')}</span>
                          <span className="text-xs font-mono text-zinc-300">{money(model.input_price)}</span>
                        </div>
                      )}
                      {(model.capability === 'chat' || model.capability === 'tts') && (
                        <div className="flex flex-col items-center justify-center gap-0.5">
                          <span className="text-[9px] font-semibold text-zinc-500 capitalize tracking-wider">{t('models.out')}</span>
                          <span className="text-xs font-mono text-zinc-300">{money(model.output_price)}</span>
                        </div>
                      )}
                      {model.capability === 'chat' && Number(model.think_price) > 0 && (
                        <div className="flex flex-col items-center justify-center gap-0.5">
                          <span className="text-[9px] font-semibold text-zinc-500 capitalize tracking-wider">{t('models.thinkPrice')}</span>
                          <span className="text-xs font-mono text-zinc-300">{money(model.think_price)}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-end gap-1.5">
                      <Button
                        variant="outline"
                        onClick={() => openEditModal(model)}
                        className="border-zinc-850 text-white hover:bg-zinc-800/50 hover:text-white text-xs px-3 py-1 h-8 rounded"
                        title="Edit Model"
                      >
                        {t('common.edit')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Model Dialog */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('models.addModalTitle')}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleCreate} noValidate className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.modelName')}</label>
              <Input
                value={addForm.name}
                onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                required
                placeholder={t('models.modelNamePlaceholder')}
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.provider')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={addForm.provider}
                  onChange={(e) => setAddForm({ ...addForm, provider: e.target.value })}
                  required
                  className="orion-native-select"
                >
                  {providers.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.capability')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={addForm.capability}
                  onChange={(e) =>
                    setAddForm({
                      ...addForm,
                      capability: e.target.value as any,
                      temperature: (e.target.value === 'chat' || e.target.value === 'tts') ? addForm.temperature : '',
                    })
                  }
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            {((addForm.capability === 'chat') || (addForm.capability === 'tts')) && (
              <div className="flex gap-3">
                {addForm.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.thinkingLevel')}</label>
                    <Input
                      value={addForm.thinking_level}
                      onChange={(e) => setAddForm({ ...addForm, thinking_level: e.target.value })}
                      placeholder={t('models.thinkingLevelPlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                    />
                  </div>
                )}

                {(addForm.capability === 'chat' || addForm.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.temperature')}</label>
                    <Input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={addForm.temperature}
                      onChange={(e) => setAddForm({ ...addForm, temperature: e.target.value })}
                      placeholder={t('models.temperaturePlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                    />
                  </div>
                )}
              </div>
            )}

            {(addForm.capability === 'chat') && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">{t('models.systemPrompt')}</label>
                <Textarea
                  value={addForm.system_prompt || ''}
                  onChange={(e) => setAddForm({ ...addForm, system_prompt: e.target.value })}
                  placeholder={t('models.systemPromptPlaceholder')}
                  className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3 h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                />
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.pricing')}</label>
              <div className="flex gap-3">
                {(addForm.capability === 'chat' || addForm.capability === 'tts' || addForm.capability === 'embed') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Input</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={addForm.input_price}
                      onChange={(e) => setAddForm({ ...addForm, input_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}

                {(addForm.capability === 'chat' || addForm.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Output</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={addForm.output_price}
                      onChange={(e) => setAddForm({ ...addForm, output_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}

                {addForm.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Think</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={addForm.think_price}
                      onChange={(e) => setAddForm({ ...addForm, think_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}
              </div>
            </div>

            {renderTtsDefaults(addForm, setAddForm, showAddTtsDefaults, setShowAddTtsDefaults)}

            <DialogFooter className="mt-4 flex gap-3 justify-end">
              <Button
                variant="outline"
                type="button"
                onClick={() => setShowAddModal(false)}
                className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                className="bg-white text-black hover:bg-zinc-200 rounded font-medium"
              >
                {t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Model Dialog */}
      <Dialog open={showEditModal} onOpenChange={setShowEditModal}>
        <DialogContent className="max-w-[400px] border border-border bg-zinc-950 p-8 rounded-2xl glass-panel text-white shadow-2xl overflow-y-auto max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-heading font-semibold text-white">{t('models.editModalTitle')}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleUpdate} noValidate className="flex flex-col gap-4 my-2">
            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.modelName')}</label>
              <Input
                value={editingModel.name}
                onChange={(e) => setEditingModel({ ...editingModel, name: e.target.value })}
                required
                className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.provider')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingModel.provider}
                  onChange={(e) => setEditingModel({ ...editingModel, provider: e.target.value })}
                  required
                  disabled
                  className="orion-native-select"
                >
                  {providers.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.capability')}</label>
              <div className="custom-select-wrapper select-wrapper w-full">
                <select
                  value={editingModel.capability}
                  onChange={(e) =>
                    setEditingModel({
                      ...editingModel,
                      capability: e.target.value as any,
                      temperature: (e.target.value === 'chat' || e.target.value === 'tts') ? editingModel.temperature : null,
                    })
                  }
                  className="orion-native-select"
                >
                  <option value="chat">chat</option>
                  <option value="tts">tts</option>
                  <option value="embed">embed</option>
                </select>
              </div>
            </div>

            {((editingModel.capability === 'chat') || (editingModel.capability === 'tts')) && (
              <div className="flex gap-3">
                {editingModel.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.thinkingLevel')}</label>
                    <Input
                      value={editingModel.thinking_level || ''}
                      onChange={(e) => setEditingModel({ ...editingModel, thinking_level: e.target.value })}
                      placeholder={t('models.thinkingLevelPlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                    />
                  </div>
                )}

                {(editingModel.capability === 'chat' || editingModel.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-2">
                    <label className="text-zinc-400 text-sm font-medium">{t('models.temperature')}</label>
                    <Input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={editingModel.temperature === null ? '' : editingModel.temperature}
                      onChange={(e) => setEditingModel({ ...editingModel, temperature: e.target.value === '' ? null : parseFloat(e.target.value) })}
                      placeholder={t('models.temperaturePlaceholder')}
                      className="bg-black/40 border border-zinc-855 text-white rounded px-2 py-2 text-sm placeholder:text-xs"
                    />
                  </div>
                )}
              </div>
            )}

            {(editingModel.capability === 'chat') && (
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-sm font-medium">{t('models.systemPrompt')}</label>
                <Textarea
                  value={editingModel.system_prompt || ''}
                  onChange={(e) => setEditingModel({ ...editingModel, system_prompt: e.target.value })}
                  placeholder={t('models.systemPromptPlaceholder')}
                  className="bg-black/40 border border-zinc-850 text-white rounded px-4 py-3 h-14 resize-none custom-scrollbar overflow-y-auto no-field-sizing"
                />
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-zinc-400 text-sm font-medium">{t('models.pricing')}</label>
              <div className="flex gap-3">
                {(editingModel.capability === 'chat' || editingModel.capability === 'tts' || editingModel.capability === 'embed') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Input</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={editingModel.input_price ?? ''}
                      onChange={(e) => setEditingModel({ ...editingModel, input_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}

                {(editingModel.capability === 'chat' || editingModel.capability === 'tts') && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Output</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={editingModel.output_price ?? ''}
                      onChange={(e) => setEditingModel({ ...editingModel, output_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}

                {editingModel.capability === 'chat' && (
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[11px] text-zinc-500 font-semibold">Think</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={editingModel.think_price ?? ''}
                      onChange={(e) => setEditingModel({ ...editingModel, think_price: cleanNumberInput(e.target.value) })}
                      placeholder="0.0"
                      className="bg-black/40 border border-zinc-855 text-white text-xs px-3 py-2 rounded"
                    />
                  </div>
                )}
              </div>
            </div>

            {renderTtsDefaults(editingModel, setEditingModel, showEditTtsDefaults, setShowEditTtsDefaults)}

            <div
              onClick={() => setEditingModel({ ...editingModel, is_active: !editingModel.is_active })}
              className={`flex items-center justify-between p-4 rounded-lg cursor-pointer border transition-all duration-200 ${
                editingModel.is_active
                  ? 'bg-purple-950/10 border-purple-500/25'
                  : 'bg-white/3 border-zinc-800'
              }`}
            >
              <div className="flex flex-col gap-0.5">
                <span className={`font-semibold text-sm ${editingModel.is_active ? 'text-purple-400' : 'text-white'}`}>{t('common.activeStatus')}</span>
              </div>
              <Switch
                checked={editingModel.is_active}
                onCheckedChange={(checked) => setEditingModel({ ...editingModel, is_active: checked })}
              />
            </div>

            <DialogFooter className="mt-4 flex justify-between w-full gap-3">
              <Button
                onClick={() => handleDelete(editingModel.id)}
                type="button"
                className="bg-transparent border border-red-500/20 text-red-500 hover:bg-red-500/10 rounded font-medium flex items-center gap-1.5"
              >
                <Trash2 className="w-4 h-4" /> {t('common.delete')}
              </Button>
              <div className="flex gap-3 justify-end">
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="border-zinc-800 text-white hover:bg-zinc-900 rounded font-medium"
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  disabled={!isModelDirty(editingModel)}
                  className="bg-white text-black hover:bg-zinc-200 rounded font-medium disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t('common.saveChanges')}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
