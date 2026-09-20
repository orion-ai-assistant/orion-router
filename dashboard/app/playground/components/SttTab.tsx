'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { adminFetch, getAdminKey } from '@/lib/api';
import { Mic, Square, Upload, Play, Copy, Check, Trash2, FileAudio, Sparkles, Loader2 } from 'lucide-react';

interface RouteOption {
  value: string;
  label: string;
  provider: string;
}

interface LanguageOption {
  code: string;
  name: string;
}

interface SttTabProps {
  models: any[];
  groups: any[];
}

const DEFAULT_FALLBACK_LANGUAGES: LanguageOption[] = [
  { code: '', name: 'Otomatik Algıla (Auto Detect)' },
  { code: 'af', name: 'Afrikaans (af)' },
  { code: 'sq', name: 'Albanian (sq)' },
  { code: 'am', name: 'Amharic (am)' },
  { code: 'ar', name: 'Arabic (ar)' },
  { code: 'hy', name: 'Armenian (hy)' },
  { code: 'as', name: 'Assamese (as)' },
  { code: 'az', name: 'Azerbaijani (az)' },
  { code: 'ba', name: 'Bashkir (ba)' },
  { code: 'eu', name: 'Basque (eu)' },
  { code: 'be', name: 'Belarusian (be)' },
  { code: 'bn', name: 'Bengali (bn)' },
  { code: 'bs', name: 'Bosnian (bs)' },
  { code: 'br', name: 'Breton (br)' },
  { code: 'bg', name: 'Bulgarian (bg)' },
  { code: 'my', name: 'Burmese (my)' },
  { code: 'yue', name: 'Cantonese (yue)' },
  { code: 'ca', name: 'Catalan (ca)' },
  { code: 'zh', name: 'Chinese (zh)' },
  { code: 'hr', name: 'Croatian (hr)' },
  { code: 'cs', name: 'Czech (cs)' },
  { code: 'da', name: 'Danish (da)' },
  { code: 'nl', name: 'Dutch (nl)' },
  { code: 'en', name: 'English (en)' },
  { code: 'et', name: 'Estonian (et)' },
  { code: 'fo', name: 'Faroese (fo)' },
  { code: 'fi', name: 'Finnish (fi)' },
  { code: 'fr', name: 'French (fr)' },
  { code: 'gl', name: 'Galician (gl)' },
  { code: 'ka', name: 'Georgian (ka)' },
  { code: 'de', name: 'German (de)' },
  { code: 'el', name: 'Greek (el)' },
  { code: 'gu', name: 'Gujarati (gu)' },
  { code: 'ht', name: 'Haitian Creole (ht)' },
  { code: 'ha', name: 'Hausa (ha)' },
  { code: 'haw', name: 'Hawaiian (haw)' },
  { code: 'he', name: 'Hebrew (he)' },
  { code: 'hi', name: 'Hindi (hi)' },
  { code: 'hu', name: 'Hungarian (hu)' },
  { code: 'is', name: 'Icelandic (is)' },
  { code: 'id', name: 'Indonesian (id)' },
  { code: 'it', name: 'Italian (it)' },
  { code: 'ja', name: 'Japanese (ja)' },
  { code: 'jw', name: 'Javanese (jw)' },
  { code: 'kn', name: 'Kannada (kn)' },
  { code: 'kk', name: 'Kazakh (kk)' },
  { code: 'km', name: 'Khmer (km)' },
  { code: 'ko', name: 'Korean (ko)' },
  { code: 'lo', name: 'Lao (lo)' },
  { code: 'la', name: 'Latin (la)' },
  { code: 'lv', name: 'Latvian (lv)' },
  { code: 'ln', name: 'Lingala (ln)' },
  { code: 'lt', name: 'Lithuanian (lt)' },
  { code: 'lb', name: 'Luxembourgish (lb)' },
  { code: 'mk', name: 'Macedonian (mk)' },
  { code: 'mg', name: 'Malagasy (mg)' },
  { code: 'ms', name: 'Malay (ms)' },
  { code: 'ml', name: 'Malayalam (ml)' },
  { code: 'mt', name: 'Maltese (mt)' },
  { code: 'mi', name: 'Maori (mi)' },
  { code: 'mr', name: 'Marathi (mr)' },
  { code: 'mn', name: 'Mongolian (mn)' },
  { code: 'ne', name: 'Nepali (ne)' },
  { code: 'nn', name: 'Nynorsk (nn)' },
  { code: 'no', name: 'Norwegian (no)' },
  { code: 'oc', name: 'Occitan (oc)' },
  { code: 'ps', name: 'Pashto (ps)' },
  { code: 'fa', name: 'Persian (fa)' },
  { code: 'pl', name: 'Polish (pl)' },
  { code: 'pt', name: 'Portuguese (pt)' },
  { code: 'pa', name: 'Punjabi (pa)' },
  { code: 'ro', name: 'Romanian (ro)' },
  { code: 'ru', name: 'Russian (ru)' },
  { code: 'sa', name: 'Sanskrit (sa)' },
  { code: 'sr', name: 'Serbian (sr)' },
  { code: 'sn', name: 'Shona (sn)' },
  { code: 'sd', name: 'Sindhi (sd)' },
  { code: 'si', name: 'Sinhala (si)' },
  { code: 'sk', name: 'Slovak (sk)' },
  { code: 'sl', name: 'Slovenian (sl)' },
  { code: 'so', name: 'Somali (so)' },
  { code: 'es', name: 'Spanish (es)' },
  { code: 'su', name: 'Sundanese (su)' },
  { code: 'sw', name: 'Swahili (sw)' },
  { code: 'sv', name: 'Swedish (sv)' },
  { code: 'tl', name: 'Tagalog (tl)' },
  { code: 'tg', name: 'Tajik (tg)' },
  { code: 'ta', name: 'Tamil (ta)' },
  { code: 'tt', name: 'Tatar (tt)' },
  { code: 'te', name: 'Telugu (te)' },
  { code: 'th', name: 'Thai (th)' },
  { code: 'bo', name: 'Tibetan (bo)' },
  { code: 'tr', name: 'Turkish (tr)' },
  { code: 'tk', name: 'Turkmen (tk)' },
  { code: 'uk', name: 'Ukrainian (uk)' },
  { code: 'ur', name: 'Urdu (ur)' },
  { code: 'uz', name: 'Uzbek (uz)' },
  { code: 'vi', name: 'Vietnamese (vi)' },
  { code: 'cy', name: 'Welsh (cy)' },
  { code: 'yi', name: 'Yiddish (yi)' },
  { code: 'yo', name: 'Yoruba (yo)' },
];

export default function SttTab({ models, groups }: SttTabProps) {
  const { showToast, locale, t } = useApp();

  const getSavedState = (key: string, defaultVal: string) => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || defaultVal;
    }
    return defaultVal;
  };

  // Model & Router Settings
  const [sttModel, setSttModel] = useState(getSavedState('pg_sttModel', ''));
  const [language, setLanguage] = useState(getSavedState('pg_sttLanguage', ''));
  const [promptHint, setPromptHint] = useState(getSavedState('pg_sttPrompt', ''));
  const [languagesByProvider, setLanguagesByProvider] = useState<Record<string, LanguageOption[]>>({});

  // Audio Input State
  const [audioFile, setAudioFile] = useState<File | Blob | null>(null);
  const [audioFileName, setAudioFileName] = useState<string>('');
  const [audioUrl, setAudioUrl] = useState<string>('');
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);

  // Execution State
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [transcriptionText, setTranscriptionText] = useState<string>('');
  const [rawResponseJson, setRawResponseJson] = useState<string>('');
  const [sttError, setSttError] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<any>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch STT languages dynamically from Orion Router API
  useEffect(() => {
    const fetchLanguages = async () => {
      try {
        const res = await adminFetch('/dashboard/api/stt-languages');
        if (res.ok) {
          const data = await res.json();
          setLanguagesByProvider(data.languages || {});
        }
      } catch (err) {
        console.error('Failed to load STT languages from API:', err);
      }
    };
    fetchLanguages();
  }, []);

  const routeOptions = useMemo<RouteOption[]>(() => {
    const options: RouteOption[] = [];
    groups.forEach((g) => {
      if (g.capability === 'stt' && g.is_active) {
        const firstProvider = g.items?.[0]?.provider || 'group';
        options.push({
          value: g.name,
          label: `${t('playground.groupPrefix')} ${g.name}`,
          provider: firstProvider,
        });
      }
    });
    models.forEach((m) => {
      if (m.capability === 'stt' && m.is_active) {
        options.push({
          value: m.name,
          label: `${m.name} (${m.provider})`,
          provider: m.provider,
        });
      }
    });
    return options;
  }, [models, groups, t]);

  // Selected option and provider
  const selectedRoute = useMemo(() => {
    return routeOptions.find((o) => o.value === sttModel);
  }, [sttModel, routeOptions]);

  const activeProvider = selectedRoute?.provider || '';
  const isLocalModel = activeProvider === 'local';

  // Dynamic languages for the active provider
  const availableLanguages = useMemo<LanguageOption[]>(() => {
    if (activeProvider && languagesByProvider[activeProvider]) {
      return languagesByProvider[activeProvider];
    }
    // Check if any provider has languages loaded
    const allProviderKeys = Object.keys(languagesByProvider);
    if (allProviderKeys.length > 0 && languagesByProvider[allProviderKeys[0]]) {
      return languagesByProvider[allProviderKeys[0]];
    }
    return DEFAULT_FALLBACK_LANGUAGES;
  }, [activeProvider, languagesByProvider]);

  // Update default model on models/groups load
  useEffect(() => {
    if (routeOptions.length > 0 && (!sttModel || !routeOptions.find((o) => o.value === sttModel))) {
      setSttModel(routeOptions[0].value);
    }
  }, [routeOptions, sttModel]);

  // Persist selections
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('pg_sttModel', sttModel);
      localStorage.setItem('pg_sttLanguage', language);
      localStorage.setItem('pg_sttPrompt', promptHint);
    }
  }, [sttModel, language, promptHint]);

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioUrl]);

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

  // Handle file upload
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      selectAudioFile(file, file.name);
    }
  };

  const selectAudioFile = (fileOrBlob: File | Blob, name: string) => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    const newUrl = URL.createObjectURL(fileOrBlob);
    setAudioFile(fileOrBlob);
    setAudioFileName(name);
    setAudioUrl(newUrl);
    setSttError('');
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      selectAudioFile(file, file.name);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Microphone recording
  const startRecording = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('Microphone access is not supported by your browser.', 'error');
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg';

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        const ext = recorder.mimeType.includes('ogg') ? 'ogg' : 'webm';
        selectAudioFile(audioBlob, `recording_${new Date().toISOString().slice(11, 19).replace(/:/g, '-')}.${ext}`);
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(100);
      setIsRecording(true);
      setRecordingDuration(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      console.error('Error starting recording:', err);
      showToast(err.message || 'Microphone access denied', 'error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    }
  };

  const clearAudio = () => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setAudioFile(null);
    setAudioFileName('');
    setAudioUrl('');
    setTranscriptionText('');
    setRawResponseJson('');
    setSttError('');
    setLatencyMs(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Perform transcription
  const handleTranscribe = async () => {
    if (!audioFile) {
      showToast('Lütfen önce bir ses dosyası yükleyin veya kaydedin.', 'error');
      return;
    }

    if (!sttModel) {
      showToast('Lütfen bir STT modeli veya grubu seçin.', 'error');
      return;
    }

    setSttError('');
    setTranscriptionText('');
    setRawResponseJson('');
    setLatencyMs(null);
    setIsTranscribing(true);

    const startTime = performance.now();
    const adminKey = getAdminKey();
    const apiBaseUrl = getApiBaseUrl();

    try {
      abortControllerRef.current = new AbortController();

      const formData = new FormData();
      const filename = audioFileName || 'audio.wav';
      formData.append('file', audioFile, filename);
      formData.append('model', sttModel);

      if (language.trim()) {
        formData.append('language', language.trim());
      }
      if (isLocalModel && promptHint.trim()) {
        formData.append('prompt', promptHint.trim());
      }

      const res = await fetch(`${apiBaseUrl}/v1/audio/transcriptions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminKey}`,
          'Accept-Language': locale,
        },
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      const elapsed = Math.round(performance.now() - startTime);
      setLatencyMs(elapsed);

      if (!res.ok) {
        let errorDetail = res.statusText;
        try {
          const errData = await res.json();
          errorDetail = errData.detail || errData.error?.message || JSON.stringify(errData);
        } catch {}
        throw new Error(errorDetail);
      }

      const jsonResult = await res.json();
      setRawResponseJson(JSON.stringify(jsonResult, null, 2));
      setTranscriptionText(jsonResult.text || '');

      showToast('Sesten metne dönüştürme başarıyla tamamlandı!');
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        console.error('Transcription error:', e);
        setSttError(e.message || 'Transkripsiyon işlemi başarısız oldu.');
      }
    } finally {
      setIsTranscribing(false);
      abortControllerRef.current = null;
    }
  };

  const handleCopy = () => {
    if (!transcriptionText) return;
    navigator.clipboard.writeText(transcriptionText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    showToast('Metin panoya kopyalandı!');
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <div className="playground-layout flex flex-col md:flex-row gap-4 animate-in fade-in duration-200">
      {/* Settings Sidebar */}
      <div className="pg-sidebar md:w-[270px] p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-3 shrink-0">
        <h3 className="panel-title text-white font-heading font-semibold pb-1.5 border-b border-zinc-850 text-xs tracking-wide">
          {t('playground.sttSettings') || 'Sesten Metne (STT) Ayarları'}
        </h3>

        {/* Model or Group Selection */}
        <div className="flex flex-col gap-1">
          <label className="text-zinc-400 text-[10px] font-semibold">{t('playground.modelOrGroup')}</label>
          <div className="custom-select-wrapper select-wrapper w-full">
            <select
              value={sttModel}
              onChange={(e) => setSttModel(e.target.value)}
              className="orion-native-select orion-native-select-sm"
            >
              {routeOptions.map((route) => (
                <option key={route.value} value={route.value}>
                  {route.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Language Selection (Fetched from API for active provider) */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <label className="text-zinc-400 text-[10px] font-semibold">{t('playground.language') || 'Dil'}</label>
            {activeProvider && (
              <span className="text-[9px] text-zinc-500 font-mono capitalize">{activeProvider}</span>
            )}
          </div>
          <div className="custom-select-wrapper select-wrapper w-full">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="orion-native-select orion-native-select-sm"
            >
              {availableLanguages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Context / Prompt Hint (Only for Whisper / Local) */}
        {isLocalModel && (
          <div className="flex flex-col gap-1 animate-in fade-in duration-150">
            <div className="flex items-center justify-between">
              <label className="text-zinc-400 text-[10px] font-semibold">
                {t('playground.promptHint') || 'İpucu / Terim Listesi'}
              </label>
              <span className="text-[9px] text-purple-400 font-mono">Whisper</span>
            </div>
            <Textarea
              value={promptHint}
              onChange={(e) => setPromptHint(e.target.value)}
              placeholder="Örn: Orion, CTranslate2, WebRTC (modelin doğru telaffuz etmesini istediğiniz terimler)..."
              className="bg-black/40 border border-zinc-850 text-white rounded p-2.5 text-xs h-20 resize-none custom-scrollbar"
            />
            <span className="text-[10px] text-zinc-500">
              Whisper modelinin doğru yazması için terim veya özel isim ipuçları.
            </span>
          </div>
        )}
      </div>

      {/* Main Area */}
      <div className="pg-main-area flex-1 p-4 glass-panel bg-[#18181b] border border-zinc-850 rounded-lg flex flex-col gap-4">
        {/* Audio Input Box: Upload or Live Mic */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          className="border border-dashed border-zinc-700/80 hover:border-zinc-500 rounded-xl p-5 bg-black/20 flex flex-col items-center justify-center gap-3 transition-colors"
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="audio/*,.wav,.mp3,.ogg,.m4a,.flac,.webm"
            className="hidden"
          />

          {audioUrl ? (
            <div className="w-full flex flex-col gap-3">
              <div className="flex items-center justify-between bg-zinc-900/90 border border-zinc-800 rounded-lg p-3">
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
                    <FileAudio className="w-5 h-5" />
                  </div>
                  <div className="truncate">
                    <div className="text-sm font-medium text-white truncate">{audioFileName}</div>
                    <div className="text-[11px] text-zinc-400">
                      {audioFile ? `${(audioFile.size / 1024).toFixed(1)} KB` : 'Dönüştürülmeye hazır'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={clearAudio}
                    className="border-zinc-800 text-zinc-400 hover:text-red-400 hover:bg-zinc-800/60 h-8 px-2.5"
                    title="Sesi Kaldır"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              {/* Audio Player Preview */}
              <audio controls src={audioUrl} className="w-full h-10 rounded-lg bg-zinc-900" />
            </div>
          ) : (
            <div className="flex flex-col items-center text-center gap-2 py-4">
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  className="border-zinc-750 bg-zinc-900/90 text-white hover:bg-zinc-800 hover:text-white rounded-lg flex items-center gap-2 px-4 py-2 text-xs"
                >
                  <Upload className="w-4 h-4 text-purple-400" />
                  {t('playground.uploadAudio') || 'Ses Yükle'}
                </Button>

                <span className="text-zinc-500 text-xs font-semibold">VEYA</span>

                {isRecording ? (
                  <Button
                    type="button"
                    onClick={stopRecording}
                    className="bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2 px-4 py-2 text-xs animate-pulse"
                  >
                    <Square className="w-4 h-4" />
                    {t('playground.stopRecording') || 'Kaydı Durdur'} ({formatSeconds(recordingDuration)})
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={startRecording}
                    className="border-zinc-750 bg-zinc-900/90 text-white hover:bg-zinc-800 hover:text-white rounded-lg flex items-center gap-2 px-4 py-2 text-xs"
                  >
                    <Mic className="w-4 h-4 text-red-400" />
                    {t('playground.recordMic') || 'Mikrofondan Kaydet'}
                  </Button>
                )}
              </div>
              <p className="text-[11px] text-zinc-500 mt-1">
                Ses dosyasını buraya sürükleyip bırakabilirsiniz (.wav, .mp3, .m4a, .ogg, .flac, .webm)
              </p>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              onClick={handleTranscribe}
              disabled={isTranscribing || !audioFile}
              className="bg-purple-600 hover:bg-purple-500 text-white font-medium px-5 py-2 rounded-lg flex items-center gap-2 text-xs disabled:opacity-50"
            >
              {isTranscribing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t('playground.transcribing') || 'Dönüştürülüyor...'}
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  {t('playground.transcribeAudio') || 'Sesi Metne Çevir'}
                </>
              )}
            </Button>

            {isTranscribing && (
              <Button
                variant="outline"
                onClick={() => abortControllerRef.current?.abort()}
                className="border-zinc-800 text-zinc-400 hover:text-white text-xs h-8"
              >
                {t('playground.stop')}
              </Button>
            )}
          </div>

          {latencyMs !== null && (
            <div className="text-[11px] text-zinc-400 font-mono">
              ⏱ {latencyMs} ms
            </div>
          )}
        </div>

        {/* Error Alert */}
        {sttError && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-xs">
            ❌ {sttError}
          </div>
        )}

        {/* Transcribed Result Panel */}
        <div className="flex-1 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="text-zinc-400 text-xs font-semibold">
              {t('playground.transcriptionResult') || 'Transkripsiyon Sonucu'}
            </label>
            {transcriptionText && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-zinc-500 font-mono">
                  {transcriptionText.length} karakter | {transcriptionText.split(/\s+/).filter(Boolean).length} kelime
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopy}
                  className="border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800 text-xs h-7 px-2.5 flex items-center gap-1.5"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Kopyalandı' : 'Metni Kopyala'}
                </Button>
              </div>
            )}
          </div>

          <div className="flex-1 min-h-[160px] bg-black/40 border border-zinc-850 rounded-lg p-4 font-sans text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed custom-scrollbar overflow-y-auto select-text">
            {transcriptionText || (
              <span className="text-zinc-600 italic select-none">
                {isTranscribing ? 'Ses çözümleniyor...' : 'Çözümlenen metin burada görüntülenecektir...'}
              </span>
            )}
          </div>
        </div>

        {/* Raw JSON View */}
        {rawResponseJson && (
          <details className="text-xs group">
            <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300 transition-colors font-mono py-1">
              ▶ Ham JSON Çıktısı (Raw Output)
            </summary>
            <pre className="mt-2 p-3 bg-black/60 border border-zinc-850 rounded-lg font-mono text-[11px] text-zinc-300 overflow-x-auto max-h-60 custom-scrollbar">
              {rawResponseJson}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
