'use client';

import { useEffect, useState } from 'react';
import { ImageIcon, Volume2, Film, FileText, RefreshCw, Trash2 } from 'lucide-react';
import { adminFetch } from '@/lib/api';
import { dateTime } from '@/lib/utils';
import { LogAttachment } from '@/lib/log-attachments';
import { LogAttachments } from '@/components/LogAttachments';
import { DateRangeFilter, DateRangeValue } from '@/components/DateRangeFilter';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';

type Kind = LogAttachment['kind'];
type Media = { id: number; filename?: string; created_at: string; mime_type: string; format: string;
  size_bytes: number; width?: number; height?: number; duration_seconds?: number; representation?: 'text' | 'binary' };
type Result = { key: string; items: Media[]; total: number; total_bytes: number; error?: string };
const kinds = [{ kind: 'audio' as const, icon: Volume2 }, { kind: 'image' as const, icon: ImageIcon }, { kind: 'video' as const, icon: Film }, { kind: 'document' as const, icon: FileText }];

export default function ArchivesPage() {
  const { t, showToast, confirmAction } = useApp();
  const [kind, setKind] = useState<Kind>('audio');
  const [dates,setDates] = useState<DateRangeValue>({start:'',end:'',range:'all'});
  const {start,end} = dates;
  const invalidDates = !!(start && end && start > end);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [deleting, setDeleting] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const key = `${kind}:${start}:${end}:${offset}:${revision}`;
  const loading = !invalidDates && result?.key !== key;
  const rows = result?.key === key ? result.items : [];
  const error = invalidDates ? t('access.invalidDates') : result?.key === key ? result.error : '';
  const total = result?.key === key ? result.total : 0;
  const Icon = kinds.find(item => item.kind === kind)!.icon;
  useEffect(() => {
    if (invalidDates) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: '30', offset: String(offset) });
    if (start) params.set('start', new Date(`${start}T00:00:00`).toISOString());
    if (end) { const until = new Date(`${end}T00:00:00`); until.setDate(until.getDate() + 1); params.set('end', until.toISOString()); }
    adminFetch(`/dashboard/api/media-archives/${kind}?${params}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(data => { if (!controller.signal.aborted) setResult({ ...data, key }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ key, items: [], total: 0, total_bytes: 0, error: String(error) }); });
    return () => controller.abort();
  }, [key, kind, start, end, offset, invalidDates]);
  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener('orion-authenticated', refresh);
    return () => window.removeEventListener('orion-authenticated', refresh);
  }, []);
  const remove = (row: Media) => {
    confirmAction(t('archive.confirmDelete'), () => {
      const identity = `${kind}:${row.id}`;
      setDeleting(identity);
      adminFetch(`/dashboard/api/media-archives/${kind}/${row.id}`, { method: 'DELETE' })
        .then(response => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          showToast(t('archive.deleted'));
          if (rows.length === 1 && offset > 0) setOffset(value => Math.max(0, value - 30));
          setRevision(value => value + 1);
        })
        .catch(() => showToast(t('archive.deleteFailed'), 'error'))
        .finally(() => setDeleting(''));
    });
  };
  return <section className="pt-8">
    <header className="flex flex-wrap gap-4 items-end justify-between border-b border-border pb-6 mb-6">
      <div><h1 className="text-3xl font-heading font-semibold">{t('nav.archives')}</h1><p className="text-zinc-400 text-sm mt-2">{t('archive.description')}</p></div>
      <Button variant="outline" onClick={() => setRevision(value => value + 1)}><RefreshCw size={16} className={loading ? 'animate-spin' : ''} />{t('logs.refresh')}</Button>
    </header>
    <div className="mb-6 flex w-fit max-w-full flex-wrap gap-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-1" role="tablist" aria-label={t('nav.archives')} onKeyDown={event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const current = kinds.findIndex(item => item.kind === kind);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? kinds.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + kinds.length) % kinds.length;
      setKind(kinds[next].kind); setOffset(0);
      event.currentTarget.querySelectorAll('button')[next]?.focus();
    }}>
      {kinds.map(({kind: value, icon: TabIcon}) => <Button key={value} role="tab" aria-selected={value === kind} aria-controls="archive-files" tabIndex={value === kind ? 0 : -1} variant="ghost" className={`h-auto whitespace-normal px-5 py-3 ${value === kind ? 'bg-zinc-800 text-white ring-1 ring-inset ring-zinc-600' : 'text-zinc-400'}`} onClick={() => { setKind(value); setOffset(0); }}><TabIcon size={16} />{t(`archive.${value}`)}</Button>)}
    </div>
    <div className="rounded-xl border border-zinc-800 bg-black/20 p-4 mb-4"><DateRangeFilter value={dates} onChange={value => {setDates(value);setOffset(0);}} /></div>
    <p className="text-xs text-zinc-400 text-right mb-4">{loading ? t('common.loading') : t('archive.totals', { count: total, mb: ((result?.total_bytes || 0) / 1048576).toFixed(2) })}</p>
    {error && <p role="alert" className="text-red-400 mb-4">{error}</p>}
    <div id="archive-files" className="grid grid-cols-1 xl:grid-cols-2 gap-3" role="tabpanel" aria-label={t(`archive.${kind}`)}>
      {rows.map(row => {
        const filename = row.filename || `${kind}-${row.id}.${row.format}`;
        const attachment: LogAttachment = { ...row, filename, kind, direction: 'archive',
          ...(kind === 'image' ? { image_archive_id: row.id } : kind === 'audio' ? { audio_archive_id: row.id } : kind === 'video' ? { video_archive_id: row.id } : {document_archive_id:row.id}) };
        return <article key={`${kind}:${row.id}`} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3 min-w-0">
          <div className="flex items-center gap-3"><Icon size={20} className="text-zinc-400 shrink-0" /><div className="min-w-0"><p className="text-sm truncate" title={filename}>{filename}</p><p className="text-xs text-zinc-500">{dateTime(row.created_at)}</p></div></div>
          <p className="text-xs text-zinc-400">{(row.size_bytes / 1024).toFixed(1)} KB{row.width && row.height ? ` · ${row.width} × ${row.height}` : ''}{row.duration_seconds != null ? ` · ${row.duration_seconds.toFixed(1)} s` : ''} · {row.mime_type}</p>
          <div className="flex justify-between gap-2"><LogAttachments attachments={[attachment]} triggerLabel={t('archive.preview')} /><Button variant="ghost" className="text-red-400" disabled={!!deleting} onClick={() => remove(row)}><Trash2 size={15} />{t('archive.delete')}</Button></div>
        </article>;
      })}
    </div>
    {!loading && !rows.length && !error && <p className="text-zinc-400 py-10 text-center">{t('archive.empty')}</p>}
    <div className="flex flex-wrap justify-center items-center gap-4 mt-6"><Button variant="outline" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 30))}>{t('access.previous')}</Button><span className="text-sm text-zinc-400">{total ? `${offset + 1}–${Math.min(offset + 30,total)} / ${total}` : '0'}</span><Button variant="outline" disabled={loading || offset + 30 >= total} onClick={() => setOffset(value => value + 30)}>{t('access.next')}</Button></div>
  </section>;
}
