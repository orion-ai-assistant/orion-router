'use client';

import { useEffect, useRef, useState } from 'react';
import { adminFetch } from '@/lib/api';
import { LogImage } from '@/lib/log-images';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';

function ImagePreview({ image, index }: { image: LogImage; index: number }) {
  const { t } = useApp();
  const [src, setSrc] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const objectUrl = useRef('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => {
    controller.current?.abort();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
  }, []);
  const show = async () => {
    setLoading(true); setError('');
    const request = new AbortController(); controller.current = request;
    try {
      if (image.image_archive_id) {
        const response = await adminFetch(`/dashboard/api/image-archives/${image.image_archive_id}/image`, { signal: request.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        if (request.signal.aborted) return;
        objectUrl.current = URL.createObjectURL(blob); setSrc(objectUrl.current);
      } else if (image.data_url) setSrc(image.data_url);
    } catch (err) {
      if (!request.signal.aborted) setError(`${t('logs.imageLoadFailed')}: ${String(err)}`);
    } finally { if (!request.signal.aborted) setLoading(false); }
  };
  return <figure className="min-w-0 rounded-lg border border-zinc-700 p-3 space-y-2">
    <figcaption className="text-xs text-zinc-400">
      {t('logs.imageLabel', { index: index + 1 })}
      {image.image_archive_id ? ` #${image.image_archive_id}` : ''}
      {image.width && image.height ? ` · ${image.width} × ${image.height}` : ''}
      {image.size_bytes ? ` · ${(image.size_bytes / 1024).toFixed(1)} KB` : ''}
      {image.format ? ` · ${image.format.toUpperCase()}` : ''}
    </figcaption>
    {src ? (
      // Original blob/data URLs use native rendering; no image optimization or re-encoding.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt={t('logs.imageLabel', { index: index + 1 })} className="max-w-full max-h-96 object-contain" onError={() => setError(t('logs.imageLoadFailed'))} />)
      : <Button variant="outline" disabled={loading} onClick={show}>{loading ? t('common.loading') : t('logs.showImage')}</Button>}
    {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
  </figure>;
}

export function LogImageGallery({ images }: { images: LogImage[] }) {
  if (!images.length) return null;
  return <div className="my-4 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[50vh] overflow-auto">
    {images.map((image, index) => <ImagePreview key={`${image.image_archive_id || 'legacy'}:${index}`} image={image} index={index} />)}
  </div>;
}
