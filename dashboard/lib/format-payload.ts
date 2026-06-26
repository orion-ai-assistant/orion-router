const MAX_DISPLAY_LINES = 400;
const MAX_DISPLAY_CHARS = 32_000;

function sanitizeForDisplay(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) {
    return obj.map(sanitizeForDisplay);
  }
  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const key of Object.keys(obj as object)) {
      const val = (obj as Record<string, unknown>)[key];
      if (
        typeof val === 'string' &&
        val.length > 200 &&
        (key === 'audio_base64' ||
          key === 'b64_json' ||
          key === 'audio' ||
          key.endsWith('_base64') ||
          val.startsWith('data:image/') ||
          val.startsWith('data:audio/'))
      ) {
        result[key] = `${val.substring(0, 50)}... [truncated base64, length: ${val.length}]`;
      } else {
        result[key] = sanitizeForDisplay(val);
      }
    }
    return result;
  }
  return obj;
}

function toPrettyJson(raw: unknown): string {
  if (raw === null || raw === undefined) return '';
  if (typeof raw === 'string') {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    return String(raw);
  }
}

function truncateDisplayText(fullText: string): string {
  if (!fullText) return '—';
  let text = fullText;
  let truncated = false;

  const lines = text.split('\n');
  if (lines.length > MAX_DISPLAY_LINES) {
    text = lines.slice(0, MAX_DISPLAY_LINES).join('\n');
    truncated = true;
  }
  if (text.length > MAX_DISPLAY_CHARS) {
    text = text.slice(0, MAX_DISPLAY_CHARS);
    truncated = true;
  }
  if (truncated) {
    text += '\n\n… [truncated — Copy Full for complete payload]';
  }
  return text;
}

export interface FormattedPayload {
  displayText: string;
  displayHtml: string;
  fullText: string;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** Pre-computed syntax colors — safe for innerHTML, computed once per open */
export function highlightJsonHtml(text: string): string {
  const escaped = escapeHtml(text);
  return escaped.replace(
    /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false)\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
    (match, quoted, colon) => {
      if (quoted) {
        if (colon) {
          return `<span class="json-key">${quoted}</span>${colon}`;
        }
        return `<span class="json-string">${quoted}</span>`;
      }
      if (match === 'true' || match === 'false') {
        return `<span class="json-boolean">${match}</span>`;
      }
      if (match === 'null') {
        return `<span class="json-null">${match}</span>`;
      }
      return `<span class="json-number">${match}</span>`;
    }
  );
}

export function formatPayloadForDisplay(raw: unknown): FormattedPayload {
  let parsed: unknown = raw;
  if (typeof raw === 'string' && raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      const fullText = raw;
      const displayText = truncateDisplayText(fullText);
      return { fullText, displayText, displayHtml: highlightJsonHtml(displayText) };
    }
  }

  const fullText = toPrettyJson(parsed);
  const displayText = truncateDisplayText(toPrettyJson(sanitizeForDisplay(parsed)));
  return { fullText, displayText, displayHtml: highlightJsonHtml(displayText) };
}

export function extractTtsAudio(
  raw: unknown
): { audio_base64: string; content_type?: string } | null {
  let parsed: unknown = raw;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const data = parsed as Record<string, unknown>;
  if (typeof data.audio_base64 !== 'string') return null;
  return {
    audio_base64: data.audio_base64,
    content_type: typeof data.content_type === 'string' ? data.content_type : undefined,
  };
}
