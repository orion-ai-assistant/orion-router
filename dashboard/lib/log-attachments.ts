import { extractLogImages, LogImage, mediaFilename, labelFilename } from './log-images';

export type LogAttachment = LogImage & {
  kind: 'image' | 'audio' | 'video';
  direction: 'input' | 'output' | 'archive';
  audio_archive_id?: number;
  video_archive_id?: number;
  duration_seconds?: number;
  external_url?: string;
};

// Only inspect typed media fields. Text, tool output and arbitrary URLs are not attachments.
export function extractLogAttachments(request: unknown, response: unknown): LogAttachment[] {
  const attachments: LogAttachment[] = [];
  function collect(raw: unknown, direction: LogAttachment['direction']) {
    let payload = raw;
    if (typeof raw === 'string') { try { payload = JSON.parse(raw); } catch { return; } }
    const seen = new Set<string>();
    function add(item: Omit<LogAttachment, 'direction'>) {
      const key = `${item.kind}:${item.audio_archive_id || item.image_archive_id || item.video_archive_id || item.data_url || item.external_url}:${item.filename || ''}`;
      if (seen.has(key)) return;
      seen.add(key); attachments.push({ ...item, direction });
    }
    extractLogImages(payload).forEach(image => add({ ...image, kind: 'image' }));
    function candidate(value: unknown, kind: 'audio' | 'video', mime?: string, filename?: string) {
      if (typeof value !== 'string' || !value) return;
      if (/^https?:\/\//i.test(value)) { add({ kind, external_url: value, mime_type: mime, filename }); return; }
      const match = /^data:(audio|video)\/([^;,]+);base64,([A-Za-z0-9+/=\s]+)$/i.exec(value);
      if (value.startsWith('data:') && (!match || match[1].toLowerCase() !== kind)) return;
      if (!match && !/^[A-Za-z0-9+/=\s]+$/.test(value)) return;
      add({ kind, filename, mime_type: match ? `${match[1]}/${match[2]}` : mime,
        data_url: match ? value : `data:${mime || `${kind}/${kind === 'video' ? 'mp4' : 'wav'}`};base64,${value}` });
    }
    function formatMime(kind: 'audio' | 'video', format: unknown) {
      if (typeof format !== 'string') return undefined;
      if (format.startsWith(`${kind}/`)) return format;
      const aliases: Record<string, string> = { mp3: 'mpeg', mov: 'quicktime', avi: 'x-msvideo', pcm: 'pcm' };
      return `${kind}/${aliases[format.toLowerCase()] || format.toLowerCase()}`;
    }
    function walk(value: unknown, inheritedName?: string) {
      if (Array.isArray(value)) {
        let pending: string | undefined;
        value.forEach(item => { const label = labelFilename(item); walk(item, label || pending || inheritedName); pending = label; });
        return;
      }
      if (!value || typeof value !== 'object') return;
      const node = value as Record<string, unknown>;
      const filename = mediaFilename(node) || inheritedName;
      if (Number.isSafeInteger(node.video_archive_id) && Number(node.video_archive_id) > 0) {
        add({ ...node, kind: 'video', filename } as Omit<LogAttachment, 'direction'>);
        return;
      }
      if (node.type === 'image_url' || node.type === 'input_image') {
        const image = node.image_url;
        const url = typeof image === 'string' ? image : image && typeof image === 'object' ? (image as Record<string, unknown>).url : node.url;
        if (typeof url === 'string' && /^https?:\/\//i.test(url)) add({ kind: 'image', external_url: url, filename });
      }
      if (Number.isSafeInteger(node.audio_archive_id) && Number(node.audio_archive_id) > 0) {
        add({ kind: 'audio', audio_archive_id: Number(node.audio_archive_id), filename });
      }
      const mime = [node.mime_type, node.mimeType, node.media_type, node.content_type].find(v => typeof v === 'string') as string | undefined;
      if (node.isText !== true && mime && /^(audio|video)\//i.test(mime)) {
        candidate(node.data ?? node.bytes, mime.toLowerCase().startsWith('video/') ? 'video' : 'audio', mime, filename);
      }
      for (const kind of ['audio', 'video'] as const) {
        candidate(node[`${kind}_base64`], kind, mime || formatMime(kind, node.format), filename);
        for (const key of [`input_${kind}`, `${kind}_url`, kind]) {
          const media = node[key];
          if (typeof media === 'string') candidate(media, kind, mime, filename);
          else if (media && typeof media === 'object') {
            const part = media as Record<string, unknown>;
            const partMime = [part.mime_type, part.mimeType, part.media_type, part.content_type].find(value => typeof value === 'string') as string | undefined;
            candidate(part.data ?? part.url, kind, partMime || formatMime(kind, part.format) || mime, mediaFilename(part) || filename);
          }
        }
      }
      Object.values(node).forEach(child => walk(child, filename));
    }
    walk(payload);
  }
  collect(request, 'input'); collect(response, 'output');
  return attachments;
}
