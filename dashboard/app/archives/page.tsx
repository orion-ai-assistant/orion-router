'use client';

import { Fragment, useEffect, useState } from 'react';
import { ImageIcon, Volume2, Film, FileText, RefreshCw, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import { adminFetch } from '@/lib/api';
import { dateTime } from '@/lib/utils';
import { LogAttachment } from '@/lib/log-attachments';
import { LogAttachments } from '@/components/LogAttachments';
import { DateRangeFilter, DateRangeValue } from '@/components/DateRangeFilter';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

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
  const [jump, setJump] = useState('');
  const [revision, setRevision] = useState(0);
  const [deleting, setDeleting] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const key = `${kind}:${start}:${end}:${offset}:${revision}`;
  const loading = !invalidDates && result?.key !== key;
  const rows = result?.key === key ? result.items : [];
  const error = invalidDates ? t('access.invalidDates') : result?.key === key ? result.error : '';
  const total = result?.key === key ? result.total : 0;
  const page = offset / 30 + 1;
  const pageCount = Math.max(1, Math.ceil(total / 30));
  const pages = Array.from(new Set([1, pageCount, page - 1, page, page + 1,
    ...(page < 4 ? [2, 3, 4] : []),
    ...(page > pageCount - 3 ? [pageCount - 3, pageCount - 2, pageCount - 1] : []),
  ])).filter(n => n >= 1 && n <= pageCount).sort((a, b) => a - b);
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
        return <article key={`${kind}:${row.id}`} className="flex min-w-0 flex-col gap-5 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex flex-wrap items-start gap-3">
            <div className="flex min-w-0 flex-1 basis-48 items-center gap-3"><Icon size={20} className="text-zinc-400 shrink-0" /><div className="min-w-0"><p className="text-sm truncate" title={filename}>{filename}</p><p className="text-xs text-zinc-500">{dateTime(row.created_at)}</p></div></div>
            <div className="ml-auto max-w-full text-right text-xs text-zinc-400">
              <p>{(row.size_bytes / 1024).toFixed(1)} KB{row.width && row.height ? ` · ${row.width} × ${row.height}` : ''}{row.duration_seconds != null ? ` · ${row.duration_seconds.toFixed(1)} s` : ''}</p>
              <p className="mt-1 break-all">{row.mime_type}</p>
            </div>
          </div>
          <div className="mt-auto flex items-center justify-between gap-4"><Button variant="ghost" className="text-red-400" disabled={!!deleting} onClick={() => remove(row)}><Trash2 size={15} />{t('archive.delete')}</Button><LogAttachments attachments={[attachment]} triggerLabel={t('archive.preview')} /></div>
        </article>;
      })}
    </div>
    {!loading && !rows.length && !error && <p className="text-zinc-400 py-10 text-center">{t('archive.empty')}</p>}
    <nav aria-label={t('access.pagination')} className="mt-6 flex flex-col items-center gap-3 pb-6">
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <Button variant="outline" size="icon" aria-label={t('access.previous')} disabled={page === 1 || loading} onClick={() => setOffset(value => Math.max(0, value - 30))}><ChevronLeft /></Button>
        {pages.map((n, index) => <Fragment key={n}>
          {index > 0 && n - pages[index - 1] > 1 && <span className="px-2 text-zinc-500">…</span>}
          <Button variant={n === page ? 'secondary' : 'ghost'} className={n === page ? 'border border-purple-500/30 bg-purple-500/15 text-purple-300' : ''} aria-current={n === page ? 'page' : undefined} disabled={loading} onClick={() => setOffset((n - 1) * 30)}>{n}</Button>
        </Fragment>)}
        <Button variant="outline" size="icon" aria-label={t('access.next')} disabled={page >= pageCount || loading} onClick={() => setOffset(value => value + 30)}><ChevronRight /></Button>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-zinc-500">
        <span>{t('access.logCount', { total, pages: pageCount })}</span>
        <form className="flex items-center gap-2" onSubmit={event => {
          event.preventDefault();
          const target = Number(jump);
          if (!loading && Number.isInteger(target) && target >= 1 && target <= pageCount) {
            setOffset((target - 1) * 30);
            setJump('');
          }
        }}>
          <Input aria-label={t('access.goPage')} className="h-8 w-20" placeholder={t('access.page')} type="number" min={1} max={pageCount} value={jump} onChange={event => setJump(event.target.value)} />
          <Button type="submit" size="sm" variant="outline" disabled={loading}>{t('access.go')}</Button>
        </form>
      </div>
    </nav>
  </section>;
}
