'use client';

import { useEffect, useState } from 'react';
import { Paperclip, ImageIcon, Volume2, Film, ExternalLink } from 'lucide-react';
import { LogAttachment } from '@/lib/log-attachments';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export function AttachmentPreview({ attachment }: { attachment: LogAttachment }) {
  const { t } = useApp();
  const [result, setResult] = useState<{ src?: string; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    const endpoint = attachment.image_archive_id
      ? `/dashboard/api/image-archives/${attachment.image_archive_id}/image`
      : attachment.audio_archive_id ? `/dashboard/api/audio-archives/${attachment.audio_archive_id}/audio`
      : attachment.video_archive_id ? `/dashboard/api/video-archives/${attachment.video_archive_id}/video` : null;
    if (endpoint) {
      adminFetch(endpoint, { signal: controller.signal })
        .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.blob(); })
        .then(blob => {
          if (controller.signal.aborted) return;
          objectUrl = URL.createObjectURL(blob); setResult({ src: objectUrl });
        })
        .catch(error => { if (!controller.signal.aborted) setResult({ error: String(error) }); });
    }
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [attachment]);
  if (attachment.external_url) return <a href={attachment.external_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-blue-300 underline"><ExternalLink size={16} />{t('logs.openMediaLink')}</a>;
  const src = attachment.data_url || result?.src;
  const error = result?.error;
  return <div className="flex h-full min-h-0 flex-col items-center justify-center gap-4 w-full min-w-0">
    <div className="flex flex-1 min-h-0 w-full items-center justify-center overflow-hidden">
    {error ? <p role="alert" className="text-red-400">{t('logs.mediaLoadFailed')}: {error}</p> : !src ? <p>{t('common.loading')}</p>
      : attachment.kind === 'image' ? (
        // Original media uses native rendering without optimization or re-encoding.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={attachment.filename || t('logs.attachmentImage')} className="h-full w-full object-contain" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />)
      : attachment.kind === 'video' ? <video controls preload="metadata" src={src} className="h-full w-full object-contain" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />
      : <audio controls preload="metadata" src={src} className="w-full max-w-xl" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />}
    </div>
    {src && <a href={src} download={attachment.filename || `attachment.${attachment.format || attachment.mime_type?.split('/')[1]?.split(';')[0] || (attachment.kind === 'audio' ? 'ogg' : 'bin')}`} className="shrink-0 text-sm text-zinc-400 underline">{t('logs.downloadMedia')}</a>}
  </div>;
}

export function LogAttachments({ attachments, triggerLabel }: { attachments: LogAttachment[]; triggerLabel?: string }) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  if (!attachments.length) return null;
  const active = attachments[selected] || attachments[0];
  const directionLabel = (item: LogAttachment) => t(item.direction === 'archive' ? 'nav.archives' : item.direction === 'input' ? 'logs.attachmentInput' : 'logs.attachmentOutput');
  return <>
    <Button variant="outline" className="w-fit gap-2" onClick={() => setOpen(true)}><Paperclip size={16} />{triggerLabel || `${t('logs.attachments')} (${attachments.length})`}</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="w-[min(94vw,1100px)] max-w-[min(94vw,1100px)] h-[min(86dvh,760px)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-[#18181b] border border-zinc-800 p-5 sm:p-6">
        <DialogHeader><DialogTitle>{t('logs.attachments')} ({attachments.length})</DialogTitle></DialogHeader>
        <div className="grid min-w-0 min-h-0 gap-4 grid-rows-[100px_minmax(0,1fr)] sm:grid-rows-1 sm:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex sm:flex-col gap-2 overflow-auto min-h-0" aria-label={t('logs.attachments')}>
            {attachments.map((item, index) => {
              const Icon = item.kind === 'image' ? ImageIcon : item.kind === 'video' ? Film : Volume2;
              return <button key={index} onClick={() => setSelected(index)} aria-pressed={selected === index} className={`flex shrink-0 sm:shrink items-start gap-2 rounded-lg border p-3 text-left ${selected === index ? 'border-purple-500/60 bg-purple-500/10' : 'border-zinc-800 hover:bg-zinc-800'}`}>
                <Icon size={17} className="mt-0.5 shrink-0" /><span className="min-w-0"><span title={item.filename} className="block text-sm truncate max-w-40">{item.filename || `${t(`logs.attachment${item.kind === 'image' ? 'Image' : item.kind === 'video' ? 'Video' : 'Audio'}`)} ${index + 1}`}</span><span className="block text-xs text-zinc-400">{directionLabel(item)}</span></span>
              </button>;
            })}
          </div>
          <div className="min-w-0 min-h-0 rounded-lg border border-zinc-800 bg-black/20 p-4 grid grid-rows-[auto_minmax(0,1fr)] gap-4">
            <div className="text-center min-w-0"><p className="text-sm truncate" title={active.filename}>{active.filename || t('archive.unnamed')}</p><p className="text-xs text-zinc-400 truncate">{directionLabel(active)}{active.width && active.height ? ` · ${active.width} × ${active.height}` : ''}{active.size_bytes ? ` · ${(active.size_bytes / 1024).toFixed(1)} KB` : ''}{active.mime_type ? ` · ${active.mime_type}` : ''}</p></div>
            {open && <AttachmentPreview key={selected} attachment={active} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
