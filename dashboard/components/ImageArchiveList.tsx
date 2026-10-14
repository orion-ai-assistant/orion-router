'use client';

import { useEffect, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { LogImage } from '@/lib/log-images';
import { LogImageGallery } from '@/components/LogImageGallery';
import { Button } from '@/components/ui/button';
import { useApp } from '@/components/AppContext';

type ArchiveResult = { key: string; images: LogImage[]; total: number; totalBytes: number; error: string };

export function ImageArchiveList() {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<ArchiveResult | null>(null);
  const queryKey = `${offset}:${revision}`;
  const loading = open && result?.key !== queryKey;
  const images = result?.key === queryKey ? result.images : [];
  const error = result?.key === queryKey ? result.error : '';
  const total = result?.total ?? 0;
  const totalBytes = result?.totalBytes ?? 0;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    adminFetch(`/dashboard/api/image-archives?limit=20&offset=${offset}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(data => {
        if (controller.signal.aborted) return;
        setResult({ key: queryKey, images: data.images.map((image: LogImage & { id: number }) => ({ ...image, image_archive_id: image.id })),
          total: Number(data.total), totalBytes: Number(data.total_bytes), error: '' });
      })
      .catch(err => {
        if (!controller.signal.aborted) setResult(previous => ({ key: queryKey, images: [],
          total: previous?.total ?? 0, totalBytes: previous?.totalBytes ?? 0, error: String(err) }));
      });
    return () => controller.abort();
  }, [open, offset, queryKey]);
  useEffect(() => {
    const refresh = () => setRevision(n => n + 1);
    window.addEventListener('orion-authenticated', refresh);
    return () => window.removeEventListener('orion-authenticated', refresh);
  }, []);
  return <div className="my-6">
    <Button variant="outline" onClick={() => { setOpen(!open); if (!open) setRevision(n => n + 1); }} aria-expanded={open}>{t('logs.imageArchiveTitle')}</Button>
    {open && <div className="mt-3 space-y-3">
      <p className="text-sm text-zinc-400">{t('logs.imageArchiveDescription')}</p>
      <p className="text-xs text-zinc-400">{t('logs.imageArchiveTotals', { count: total, mb: (totalBytes / 1048576).toFixed(2) })}</p>
      <Button variant="outline" onClick={() => setRevision(n => n + 1)}>{t('logs.refresh')}</Button>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {loading ? <p>{t('common.loading')}</p> : <LogImageGallery images={images} />}
      {!loading && !images.length && <p>{t('logs.empty')}</p>}
      <div className="flex gap-3">
        <Button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>{t('access.previous')}</Button>
        <Button disabled={loading || offset + 20 >= total} onClick={() => setOffset(offset + 20)}>{t('access.next')}</Button>
      </div>
    </div>}
  </div>;
}
