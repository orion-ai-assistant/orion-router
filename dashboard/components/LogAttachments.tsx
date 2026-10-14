'use client';

import { useEffect, useState } from 'react';
import { Paperclip, ImageIcon, Volume2, Film, FileText, ExternalLink } from 'lucide-react';
import { LogAttachment } from '@/lib/log-attachments';
import { adminFetch } from '@/lib/api';
import { useApp } from '@/components/AppContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export function AttachmentPreview({ attachment }: { attachment: LogAttachment }) {
  const { t } = useApp();
  const [result, setResult] = useState<{ src?: string; error?: string; missing?: boolean; text?: string; truncated?: boolean; mime?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    const endpoint = attachment.image_archive_id
      ? `/dashboard/api/image-archives/${attachment.image_archive_id}/image`
      : attachment.audio_archive_id ? `/dashboard/api/audio-archives/${attachment.audio_archive_id}/audio`
      : attachment.video_archive_id ? `/dashboard/api/video-archives/${attachment.video_archive_id}/video`
      : attachment.document_archive_id ? `/dashboard/api/media-archives/document/${attachment.document_archive_id}/file` : null;
    if (endpoint || attachment.kind === 'document' && !attachment.external_url) {
      const load = async () => {
        let blob: Blob;
        if (endpoint) {
          const response = await adminFetch(endpoint,{signal:controller.signal});
          if (response.status === 404) {
            if (!controller.signal.aborted) setResult({missing:true});
            return;
          }
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          blob = await response.blob();
        } else if (attachment.text_content !== undefined) blob = new Blob([attachment.text_content],{type:attachment.mime_type || 'text/plain'});
        else if (attachment.data_url && /^data:(?:text|application)\//i.test(attachment.data_url)) {
          blob = await (await fetch(attachment.data_url,{signal:controller.signal})).blob();
        } else throw new Error('Attachment data unavailable');
        const isText = attachment.kind === 'document' && (attachment.representation === 'text' || /^(text\/|application\/(json|xml)(;|$))/i.test(blob.type));
        const text = isText ? await blob.slice(0,262144).text() : undefined;
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setResult({src:objectUrl,text,truncated:isText && blob.size > 262144,mime:blob.type});
      };
      load().catch(error => {if (!controller.signal.aborted) setResult({error:String(error)});});
    }
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [attachment]);
  if (attachment.external_url && /^https?:\/\//i.test(attachment.external_url)) return <a href={attachment.external_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-blue-300 underline"><ExternalLink size={16} />{t('logs.openMediaLink')}</a>;
  const src = attachment.kind === 'document' ? result?.src : attachment.data_url || result?.src;
  const error = result?.error;
  return <div className="flex h-full min-h-0 flex-col items-center justify-center gap-4 w-full min-w-0">
    <div className="flex flex-1 min-h-0 w-full items-center justify-center overflow-hidden">
    {result?.missing ? <p role="status" className="text-sm text-zinc-400 text-center">{t('logs.mediaNotFound')}</p> : error ? <p role="alert" className="text-red-400">{t('logs.mediaLoadFailed')}: {error}</p> : !src ? <p>{t('common.loading')}</p>
      : attachment.kind === 'image' ? (
        // Original media uses native rendering without optimization or re-encoding.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={attachment.filename || t('logs.attachmentImage')} className="h-full w-full object-contain" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />)
      : attachment.kind === 'video' ? <video controls preload="metadata" src={src} className="h-full w-full object-contain" onError={() => setResult({ error: t('logs.mediaUnsupported') })} />
      : attachment.kind === 'document' ? result?.text !== undefined ? <pre className="h-full w-full overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-zinc-300 p-2">{result.text}</pre>
        : <div className="text-center space-y-4"><FileText size={40} className="mx-auto text-zinc-500" /><p className="text-sm text-zinc-400">{t('archive.documentReady')}</p>{result?.mime === 'application/pdf' && <a href={src} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-sm underline"><ExternalLink size={16}/>{t('archive.openPdf')}</a>}</div>
      : <audio controls preload="metadata" src={src} className="w-full max-w-xl [color-scheme:dark]" style={{colorScheme:'dark'}} onError={() => setResult({ error: t('logs.mediaUnsupported') })} />}
    </div>
    {result?.truncated && <p className="text-xs text-zinc-500">{t('archive.textTruncated')}</p>}
    {attachment.representation === 'text' && /\.(pdf|docx?|xlsx?|pptx?)$/i.test(attachment.filename || '') && <p className="text-xs text-zinc-400">{t('archive.extractedText')}</p>}
    {src && <a href={src} download={attachment.filename ? attachment.representation === 'text' && /\.(pdf|docx?|xlsx?|pptx?)$/i.test(attachment.filename) ? `${attachment.filename}.txt` : attachment.filename : `attachment.${attachment.format || attachment.mime_type?.split('/')[1]?.split(';')[0] || (attachment.kind === 'audio' ? 'ogg' : 'bin')}`} className="shrink-0 text-sm text-zinc-400 underline">{t('logs.downloadMedia')}</a>}
  </div>;
}

export function LogAttachments({ attachments, triggerLabel }: { attachments: LogAttachment[]; triggerLabel?: string }) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  if (!attachments.length) return null;
  const active = attachments[selected] || attachments[0];
  const single = attachments.length === 1;
  const audioOnly = attachments.every(item => item.kind === 'audio');
  const directionLabel = (item: LogAttachment) => t(item.direction === 'archive' ? 'nav.archives' : item.direction === 'input' ? 'logs.attachmentInput' : 'logs.attachmentOutput');
  return <>
    <Button variant="outline" className="w-fit gap-2" onClick={() => setOpen(true)}><Paperclip size={16} />{triggerLabel || `${t('logs.attachments')} (${attachments.length})`}</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className={`${audioOnly ? single ? 'w-[min(94vw,600px)] max-w-[min(94vw,600px)] h-[min(80dvh,280px)]' : 'w-[min(94vw,900px)] max-w-[min(94vw,900px)] h-[min(80dvh,380px)]' : 'w-[min(94vw,1100px)] max-w-[min(94vw,1100px)] h-[min(86dvh,760px)]'} grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-[#18181b] border border-zinc-800 p-5 sm:p-6`}>
        <DialogHeader><DialogTitle>{t('logs.attachments')} ({attachments.length})</DialogTitle></DialogHeader>
        <div className={`grid min-w-0 min-h-0 gap-4 ${single ? 'grid-rows-[minmax(0,1fr)]' : 'grid-rows-[100px_minmax(0,1fr)] sm:grid-rows-1 sm:grid-cols-[220px_minmax(0,1fr)]'}`}>
          {!single && <div className="flex sm:flex-col gap-2 overflow-auto min-h-0" aria-label={t('logs.attachments')}>
            {attachments.map((item, index) => {
              const Icon = item.kind === 'image' ? ImageIcon : item.kind === 'video' ? Film : item.kind === 'document' ? FileText : Volume2;
              return <button key={index} onClick={() => setSelected(index)} aria-pressed={selected === index} className={`flex shrink-0 sm:shrink items-start gap-2 rounded-lg border p-3 text-left ${selected === index ? 'border-zinc-600 bg-zinc-800 text-white ring-1 ring-inset ring-zinc-600' : 'border-zinc-800 text-zinc-400 hover:bg-zinc-800'}`}>
                <Icon size={17} className="mt-0.5 shrink-0" /><span className="min-w-0"><span title={item.filename} className="block text-sm truncate max-w-40">{item.filename || `${t(`logs.attachment${item.kind === 'image' ? 'Image' : item.kind === 'video' ? 'Video' : item.kind === 'document' ? 'Document' : 'Audio'}`)} ${index + 1}`}</span><span className="block text-xs text-zinc-400">{directionLabel(item)}</span></span>
              </button>;
            })}
          </div>}
          <div className="min-w-0 min-h-0 rounded-lg border border-zinc-800 bg-black/20 p-4 grid grid-rows-[auto_minmax(0,1fr)] gap-4">
            <div className="text-center min-w-0"><p className="text-sm truncate" title={active.filename}>{active.filename || t('archive.unnamed')}</p><p className="text-xs text-zinc-400 truncate">{directionLabel(active)}{active.width && active.height ? ` · ${active.width} × ${active.height}` : ''}{active.size_bytes ? ` · ${(active.size_bytes / 1024).toFixed(1)} KB` : ''}{active.mime_type ? ` · ${active.mime_type}` : ''}</p></div>
            {open && <AttachmentPreview key={selected} attachment={active} />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
