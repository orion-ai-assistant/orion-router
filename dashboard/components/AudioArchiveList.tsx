'use client';

import { useEffect, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { dateTime } from '@/lib/utils';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { ArchiveAudioPlayer } from '@/components/ArchiveAudioPlayer';

type Archive = { id: number; log_id: number | null; provider: string; requested_model: string; resolved_model: string;
  created_at: string; codec: string; duration_seconds: number; archive_size_bytes: number; generation_status: string };
type ArchiveStatus = { available: boolean | null; version?: string; error?: string; last_error?: string;
  archive_relation_bytes?: number; logged_archive_errors?: number; database_error?: string;
  database_disk?: { free_bytes: number; low_space: boolean } };

export function AudioArchiveList() {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Archive[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<ArchiveStatus | null>(null);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    adminFetch(`/dashboard/api/audio-archives?limit=20&offset=${offset}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(data => { if (!controller.signal.aborted) { setRows(data.archives); setTotal(data.total); } })
      .catch(err => { if (!controller.signal.aborted) setError(String(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    adminFetch('/dashboard/api/audio-archives/status', { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(data => { if (!controller.signal.aborted) setStatus(data); })
      .catch(err => { if (!controller.signal.aborted) setError(String(err)); });
    return () => controller.abort();
  }, [open, offset, revision]);
  useEffect(() => {
    const refresh = () => setRevision(n => n + 1);
    window.addEventListener('orion-authenticated', refresh);
    return () => window.removeEventListener('orion-authenticated', refresh);
  }, []);
  return <div className="my-6">
    <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>{t('logs.audioArchiveTitle')}</Button>
    {open && <div className="mt-4 space-y-4">
      <p className="text-sm text-zinc-400">{t('logs.audioArchiveDescription')}</p>
      {status && <div className="text-xs text-zinc-400 space-y-1">
        <p>{status.version || status.error || t('logs.encoderUnknown')}</p>
        <p>{t('logs.archiveStorage')}: {((status.archive_relation_bytes || 0) / 1048576).toFixed(2)} MB · {t('logs.archiveErrors')}: {status.logged_archive_errors ?? '—'}</p>
        {status.database_disk && <p>{t('logs.databaseFreeDisk')}: {(status.database_disk.free_bytes / 1073741824).toFixed(2)} GB</p>}
        {status.database_disk?.low_space && <p role="alert" className="text-amber-400">{t('logs.databaseLowDisk')}</p>}
        {(status.database_error || status.available === false) && <p role="alert" className="text-red-400">{status.database_error || status.error}</p>}
        {status.last_error && <p className="text-amber-400">{t('logs.lastArchiveError')}: {status.last_error}</p>}
      </div>}
      <Button variant="outline" onClick={() => setRevision(n => n + 1)}>{t('logs.refresh')}</Button>
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {loading ? <p>{t('common.loading')}</p> : rows.map(row => <article key={row.id} className="p-4 border border-zinc-700 rounded-lg space-y-2">
        <p className="text-sm">#{row.id} · {row.provider} / {row.resolved_model} · {dateTime(row.created_at)}</p>
        <p className="text-xs text-zinc-400">{row.codec} · {row.duration_seconds.toFixed(1)} s · {(row.archive_size_bytes / 1024).toFixed(1)} KB · {row.generation_status} · {row.log_id === null ? t('logs.audioUnlinked') : `Log #${row.log_id}`}</p>
        <ArchiveAudioPlayer audio={{ audio_archive_id: row.id }} />
      </article>)}
      {!loading && !rows.length && <p>{t('logs.empty')}</p>}
      <div className="flex gap-3 items-center">
        <Button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>{t('access.previous')}</Button>
        <span>{offset + 1}–{Math.min(offset + 20, total)} / {total}</span>
        <Button disabled={loading || offset + 20 >= total} onClick={() => setOffset(offset + 20)}>{t('access.next')}</Button>
      </div>
    </div>}
  </div>;
}
