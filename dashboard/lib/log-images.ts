export type LogImage = {
  image_archive_id?: number;
  data_url?: string;
  mime_type?: string;
  format?: string;
  size_bytes?: number;
  width?: number;
  height?: number;
};

// Match image fields only; do not interpret ordinary message text as media.
export function extractLogImages(...payloads: unknown[]): LogImage[] {
  const images: LogImage[] = [];
  const seen = new Set<string>();
  function candidate(value: unknown, mime?: string) {
    if (typeof value !== 'string' || !value || /^https?:\/\//i.test(value)) return;
    if (value.startsWith('data:') && !/^data:image\/[^;,]+;base64,/i.test(value)) return;
    // Avoid rendering arbitrary URI schemes or SVG from a legacy log.
    if (/^data:image\/svg/i.test(value) || mime?.toLowerCase() === 'image/svg+xml' || (!value.startsWith('data:') && !/^[A-Za-z0-9+/=\s]+$/.test(value))) return;
    const url = value.startsWith('data:') ? value : `data:${mime?.startsWith('image/') ? mime : 'image/jpeg'};base64,${value}`;
    if (seen.has(url)) return;
    seen.add(url); images.push({ data_url: url, mime_type: mime });
  }
  function walk(value: unknown) {
    if (Array.isArray(value)) { value.forEach(walk); return; }
    if (!value || typeof value !== 'object') return;
    const node = value as Record<string, unknown>;
    if (Number.isSafeInteger(node.image_archive_id) && Number(node.image_archive_id) > 0) {
      const key = `archive:${node.image_archive_id}`;
      if (!seen.has(key)) { seen.add(key); images.push(node as LogImage); }
      return;
    }
    const mime = typeof node.mime_type === 'string' ? node.mime_type : typeof node.mimeType === 'string' ? node.mimeType : undefined;
    candidate(node.b64_json, mime);
    candidate(node.image_base64, mime);
    if (node.type === 'image_url' || node.type === 'input_image') {
      candidate(node.url, mime);
      if (typeof node.image_url === 'string') candidate(node.image_url);
      else if (node.image_url && typeof node.image_url === 'object') candidate((node.image_url as Record<string,unknown>).url);
      if (node.input_image && typeof node.input_image === 'object') {
        const image = node.input_image as Record<string,unknown>;
        candidate(image.data, typeof image.format === 'string' ? (image.format.startsWith('image/') ? image.format : `image/${image.format}`) : undefined);
      }
    }
    if (node.type === 'image' && node.source && typeof node.source === 'object') {
      const source = node.source as Record<string,unknown>;
      if (source.type === 'base64') candidate(source.data, typeof source.media_type === 'string' ? source.media_type : undefined);
    }
    if (mime?.startsWith('image/') && node.isText !== true) candidate(node.data, mime);
    if (Array.isArray(node.images)) node.images.forEach(item => candidate(item));
    Object.values(node).forEach(walk);
  }
  for (const raw of payloads) {
    if (typeof raw === 'string') { try { walk(JSON.parse(raw)); } catch { /* Legacy malformed log. */ } }
    else walk(raw);
  }
  return images;
}
