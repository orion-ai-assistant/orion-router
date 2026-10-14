'use client';

import { useEffect, useRef, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useApp } from '@/components/AppContext';

export function ArchiveAudioPlayer({ audio }: { audio: { audio_archive_id?: number; audio_base64?: string; content_type?: string } }) {
  const { t } = useApp();
  const [src, setSrc] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const player = useRef<HTMLAudioElement>(null);
  const objectUrl = useRef('');
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    setSrc(''); setError(''); setLoading(false);
    return () => {
      abort.current?.abort();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = '';
    };
  }, [audio.audio_archive_id, audio.audio_base64]);

  const play = async () => {
    setLoading(true); setError('');
    const controller = new AbortController();
    abort.current = controller;
    try {
      let url: string;
      if (audio.audio_archive_id) {
        const response = await adminFetch(`/dashboard/api/audio-archives/${audio.audio_archive_id}/audio`, { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        objectUrl.current = url;
      } else {
        url = `data:${audio.content_type || 'audio/wav'};base64,${audio.audio_base64}`;
      }
      if (!controller.signal.aborted) setSrc(url);
    } catch (err) {
      if (!controller.signal.aborted) setError(`${t('logs.audioLoadFailed')}: ${String(err)}`);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    if (src) player.current?.play().catch(() => { /* Browser may require another click after fetch. */ });
  }, [src]);

  return <div className="flex flex-col gap-2 w-full">
    {src ? <audio ref={player} controls preload="none" src={src} className="w-full h-10" onError={() => setError(t('logs.audioUnsupported'))} />
      : <Button variant="outline" disabled={loading} onClick={play}>{loading ? t('common.loading') : t('logs.playAudio')}</Button>}
    {error && <p role="alert" className="text-red-400 text-sm">{error}</p>}
  </div>;
}
