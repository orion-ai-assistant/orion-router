export type LogImage = {
  filename?: string;
  image_archive_id?: number;
  data_url?: string;
  mime_type?: string;
  format?: string;
  size_bytes?: number;
  width?: number;
  height?: number;
};

export function cleanFilename(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  return value.replace(/\\/g, '/').split('/').pop()?.replace(/[\x00-\x1f\x7f]/g, '').trim().slice(0,255) || undefined;
}

export function mediaFilename(node: Record<string, unknown>): string | undefined {
  return cleanFilename(node.filename) || cleanFilename(node.file_name) || cleanFilename(node.original_filename)
    || (['data','url','mime_type','mimeType'].some(key => key in node) ? cleanFilename(node.name) : undefined);
}

export function labelFilename(node: unknown): string | undefined {
  if (!node || typeof node !== 'object') return undefined;
  const item = node as Record<string,unknown>;
  if (item.type !== 'text' || typeof item.text !== 'string') return undefined;
  const match = /^(?:Ek|Attachment)\s+\d+\s*[—–-]\s*(?:Görsel|Ses|Video|Image|Audio)\s*:\s*([^\r\n]+)$/i.exec(item.text);
  return match ? cleanFilename(match[1]) : undefined;
}

// Match image fields only; do not interpret ordinary message text as media.
export function extractLogImages(...payloads: unknown[]): LogImage[] {
  const images: LogImage[] = [];
  const seen = new Set<string>();
  function candidate(value: unknown, mime?: string, filename?: string) {
    if (typeof value !== 'string' || !value || /^https?:\/\//i.test(value)) return;
    if (value.startsWith('data:') && !/^data:image\/[^;,]+;base64,/i.test(value)) return;
    // Avoid rendering arbitrary URI schemes or SVG from a legacy log.
    if (/^data:image\/svg/i.test(value) || mime?.toLowerCase() === 'image/svg+xml' || (!value.startsWith('data:') && !/^[A-Za-z0-9+/=\s]+$/.test(value))) return;
    const url = value.startsWith('data:') ? value : `data:${mime?.startsWith('image/') ? mime : 'image/jpeg'};base64,${value}`;
    if (seen.has(url)) return;
    seen.add(url); images.push({ data_url: url, mime_type: mime, ...(filename ? { filename } : {}) });
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
    const imageCandidate = (value: unknown, mime?: string, name = filename) => candidate(value, mime, name);
    if (Number.isSafeInteger(node.image_archive_id) && Number(node.image_archive_id) > 0) {
      const key = `archive:${node.image_archive_id}:${filename || ''}`;
      if (!seen.has(key)) { seen.add(key); images.push({ ...node, ...(filename ? { filename } : {}) } as LogImage); }
      return;
    }
    const mime = typeof node.mime_type === 'string' ? node.mime_type : typeof node.mimeType === 'string' ? node.mimeType : undefined;
    imageCandidate(node.b64_json, mime);
    imageCandidate(node.image_base64, mime);
    if (node.type === 'image_url' || node.type === 'input_image') {
      imageCandidate(node.url, mime);
      if (typeof node.image_url === 'string') imageCandidate(node.image_url);
      else if (node.image_url && typeof node.image_url === 'object') {
        const image = node.image_url as Record<string,unknown>;
        imageCandidate(image.url, undefined, mediaFilename(image) || filename);
      }
      if (node.input_image && typeof node.input_image === 'object') {
        const image = node.input_image as Record<string,unknown>;
        imageCandidate(image.data, typeof image.format === 'string' ? (image.format.startsWith('image/') ? image.format : `image/${image.format}`) : undefined, mediaFilename(image) || filename);
      }
    }
    if (node.type === 'image' && node.source && typeof node.source === 'object') {
      const source = node.source as Record<string,unknown>;
      if (source.type === 'base64') imageCandidate(source.data, typeof source.media_type === 'string' ? source.media_type : undefined, mediaFilename(source) || filename);
    }
    if (mime?.startsWith('image/') && node.isText !== true) imageCandidate(node.data, mime);
    if (Array.isArray(node.images)) node.images.forEach(item => imageCandidate(item));
    Object.values(node).forEach(child => walk(child, filename));
  }
  for (const raw of payloads) {
    if (typeof raw === 'string') { try { walk(JSON.parse(raw)); } catch { /* Legacy malformed log. */ } }
    else walk(raw);
  }
  return images;
}
