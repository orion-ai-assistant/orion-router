'use client';

import { useEffect, useState } from 'react';
import { Paperclip, ImageIcon, Volume2, Film, ExternalLink } from 'lucide-react';
import { LogAttachment } from '@/lib/log-attachments';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

function AttachmentPreview({ attachment }: { attachment: LogAttachment }) {
  const { t } = useApp();
  const [result, setResult] = useState<{ src?: string; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    const endpoint = attachment.image_archive_id
      ? `/dashboard/api/image-archives/${attachment.image_archive_id}/image`
      : attachment.audio_archive_id ? `/dashboard/api/audio-archives/${attachment.audio_archive_id}/audio` : null;
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
  return <div className="flex flex-col items-center justify-center gap-4 w-full min-w-0">
    {error ? <p role="alert" className="text-red-400">{t('logs.mediaLoadFailed')}: {error}</p> : !src ? <p>{t('common.loading')}</p>
      : attachment.kind === 'image' ? (
        // Original media uses native rendering without optimization or re-encoding.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={t('logs.attachmentImage')} className="max-h-[55dvh] max-w-full object-contain" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />)
      : attachment.kind === 'video' ? <video controls preload="metadata" src={src} className="max-h-[55dvh] max-w-full" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />
      : <audio controls preload="metadata" src={src} className="w-full max-w-xl" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />}
    {src && <a href={src} download={`attachment.${attachment.format || attachment.mime_type?.split('/')[1]?.split(';')[0] || (attachment.kind === 'audio' ? 'ogg' : 'bin')}`} className="text-sm text-zinc-400 underline">{t('logs.downloadMedia')}</a>}
  </div>;
}

export function LogAttachments({ attachments }: { attachments: LogAttachment[] }) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  if (!attachments.length) return null;
  const active = attachments[selected] || attachments[0];
  return <>
    <Button variant="outline" className="w-fit gap-2" onClick={() => setOpen(true)}><Paperclip size={16} />{t('logs.attachments')} ({attachments.length})</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="w-[min(94vw,1100px)] max-w-[min(94vw,1100px)] max-h-[90dvh] overflow-auto bg-[#18181b] border border-zinc-800 p-5 sm:p-6">
        <DialogHeader><DialogTitle>{t('logs.attachments')} ({attachments.length})</DialogTitle></DialogHeader>
        <div className="grid min-w-0 gap-4 sm:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex sm:flex-col gap-2 overflow-auto max-h-[65dvh]" aria-label={t('logs.attachments')}>
            {attachments.map((item, index) => {
              const Icon = item.kind === 'image' ? ImageIcon : item.kind === 'video' ? Film : Volume2;
              return <button key={index} onClick={() => setSelected(index)} aria-pressed={selected === index} className={`flex shrink-0 sm:shrink items-start gap-2 rounded-lg border p-3 text-left ${selected === index ? 'border-purple-500/60 bg-purple-500/10' : 'border-zinc-800 hover:bg-zinc-800'}`}>
                <Icon size={17} className="mt-0.5 shrink-0" /><span className="min-w-0"><span className="block text-sm">{t(`logs.attachment${item.kind === 'image' ? 'Image' : item.kind === 'video' ? 'Video' : 'Audio'}`)} {index + 1}</span><span className="block text-xs text-zinc-400">{t(item.direction === 'input' ? 'logs.attachmentInput' : 'logs.attachmentOutput')}</span></span>
              </button>;
            })}
          </div>
          <div className="min-w-0 rounded-lg border border-zinc-800 bg-black/20 p-4 flex flex-col justify-center gap-4 min-h-48">
            <p className="text-xs text-zinc-400 text-center">{t(active.direction === 'input' ? 'logs.attachmentInput' : 'logs.attachmentOutput')}{active.width && active.height ? ` · ${active.width} × ${active.height}` : ''}{active.size_bytes ? ` · ${(active.size_bytes / 1024).toFixed(1)} KB` : ''}{active.mime_type ? ` · ${active.mime_type}` : ''}</p>
            {open && <AttachmentPreview key={selected} attachment={active} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
