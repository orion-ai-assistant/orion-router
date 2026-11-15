// "Tam kopyala": put the archived files back into a logged payload as Base64, at copy time only.
// The stored log keeps small references ({image_archive_id, sha256, ...}); this never writes anything back.

const ENDPOINTS: Array<[string, (id: number) => string]> = [
  ['image_archive_id', id => `/dashboard/api/image-archives/${id}/image`],
  ['input_audio_archive_id', id => `/dashboard/api/media-archives/input-audio/${id}/file`],
  ['audio_archive_id', id => `/dashboard/api/audio-archives/${id}/audio`],
  ['video_archive_id', id => `/dashboard/api/video-archives/${id}/video`],
  ['document_archive_id', id => `/dashboard/api/media-archives/document/${id}/file`],
];

// Keys whose original value was a full data URL rather than bare Base64.
const DATA_URL_KEYS = new Set(['url', 'image_url', 'file_data', 'audio_url', 'video_url']);

export type FetchBytes = (endpoint: string) => Promise<Uint8Array | null>;

export function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function archiveRef(value: unknown): { endpoint: string; ref: Record<string, unknown> } | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const ref = value as Record<string, unknown>;
  for (const [key, endpoint] of ENDPOINTS) {
    const id = ref[key];
    if (Number.isSafeInteger(id) && Number(id) > 0 && typeof ref.sha256 === 'string') return { endpoint: endpoint(Number(id)), ref };
  }
  return null;
}

// Returns the payload text with every archive reference replaced by its file; unavailable files stay as references.
export async function inlineArchivedMedia(payload: string, fetchBytes: FetchBytes): Promise<string> {
  let root: unknown;
  try { root = JSON.parse(payload); } catch { return payload; }
  const jobs: Array<() => Promise<void>> = [];
  const cache = new Map<string, Promise<Uint8Array | null>>();
  const load = (endpoint: string) => {
    if (!cache.has(endpoint)) cache.set(endpoint, fetchBytes(endpoint).catch(() => null));
    return cache.get(endpoint)!;
  };
  function visit(container: Record<string, unknown> | unknown[], key: string | number) {
    const value = (container as Record<string | number, unknown>)[key];
    const found = archiveRef(value);
    if (found) {
      jobs.push(async () => {
        const bytes = await load(found.endpoint);
        if (!bytes) return;
        const mime = typeof found.ref.mime_type === 'string' ? found.ref.mime_type : 'application/octet-stream';
        (container as Record<string | number, unknown>)[key] = found.ref.representation === 'text'
          ? new TextDecoder().decode(bytes)
          : DATA_URL_KEYS.has(String(key)) ? `data:${mime};base64,${toBase64(bytes)}` : toBase64(bytes);
      });
      return;
    }
    if (value && typeof value === 'object') {
      for (const childKey of Array.isArray(value) ? value.map((_, i) => i) : Object.keys(value)) visit(value as Record<string, unknown> | unknown[], childKey);
    }
  }
  const holder: Record<string, unknown> = { root };
  visit(holder, 'root');
  for (let i = 0; i < jobs.length; i += 4) await Promise.all(jobs.slice(i, i + 4).map(job => job()));
  return JSON.stringify(holder.root, null, 2);
}
