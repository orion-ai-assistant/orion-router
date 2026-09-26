const MAX_DISPLAY_LINES = 400;
const MAX_DISPLAY_CHARS = 32_000;

const KEY_PRIORITY: Record<string, number> = {
  // 1. Identifiers & Targets
  id: 10,
  object: 11,
  model: 20,

  // 2. Input / Messages / Prompts
  messages: 30,
  input: 31,
  prompt: 32,

  // 3. Core Sampling Parameters (kept closely grouped together)
  temperature: 40,
  top_p: 41,
  top_k: 42,
  min_p: 43,
  repeat_penalty: 44,
  presence_penalty: 45,
  frequency_penalty: 46,
  max_tokens: 47,
  max_completion_tokens: 48,
  seed: 49,
  stop: 50,

  // 4. Thinking & Reasoning Parameters
  reasoning_effort: 60,
  thinking_budget_tokens: 61,
  chat_template_kwargs: 62,

  // 5. Stream Options & Control
  stream: 70,
  stream_options: 71,

  // 6. Tools & Functions (placed near bottom so large tool schemas don't scatter other keys)
  tools: 80,
  tool_choice: 81,
  functions: 82,
  function_call: 83,

  // 7. Response Structure
  choices: 90,
  role: 91,
  content: 92,
  reasoning_content: 93,
  tool_calls: 94,
  usage: 100,
  metrics: 110,
  error: 120,
};

function orderKeysForDisplay(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) {
    return obj.map(orderKeysForDisplay);
  }
  if (typeof obj === 'object') {
    const sortedObj: Record<string, unknown> = {};
    const keys = Object.keys(obj as object);

    keys.sort((a, b) => {
      const pA = KEY_PRIORITY[a] ?? 500;
      const pB = KEY_PRIORITY[b] ?? 500;
      if (pA !== pB) return pA - pB;
      return a.localeCompare(b);
    });

    for (const key of keys) {
      sortedObj[key] = orderKeysForDisplay((obj as Record<string, unknown>)[key]);
    }
    return sortedObj;
  }
  return obj;
}

function isTruncatableMediaString(
  val: string,
  key?: string,
  parent?: Record<string, unknown>
): boolean {
  if (typeof val !== 'string' || val.length <= 200) return false;

  // 1. Any Data URI (video, audio, image, document, etc.)
  if (
    val.startsWith('data:image/') ||
    val.startsWith('data:audio/') ||
    val.startsWith('data:video/') ||
    val.startsWith('data:application/') ||
    val.startsWith('data:')
  ) {
    return true;
  }

  // 2. Specific base64 payload keys
  if (key) {
    const k = key.toLowerCase();
    if (
      k === 'audio_base64' ||
      k === 'video_base64' ||
      k === 'image_base64' ||
      k === 'input_audio' ||
      k === 'input_video' ||
      k === 'input_image' ||
      k === 'b64_json' ||
      k === 'audio' ||
      k.endsWith('_base64') ||
      k.endsWith('_b64')
    ) {
      return true;
    }

    // 3. Structured media objects (e.g. OpenAI input_audio/video { data, format }, Gemini inline_data, Anthropic source)
    if (k === 'data' || k === 'bytes') {
      if (
        (parent && (
          typeof parent.format === 'string' ||
          typeof parent.mime_type === 'string' ||
          typeof parent.mimeType === 'string' ||
          typeof parent.media_type === 'string' ||
          parent.type === 'base64' ||
          parent.encoding === 'base64'
        )) ||
        /^[A-Za-z0-9+/=\r\n]{150,}$/.test(val.slice(0, 300))
      ) {
        return true;
      }
    }
  }

  return false;
}

function sanitizeForDisplay(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj === 'string') {
    if (isTruncatableMediaString(obj)) {
      return `${obj.substring(0, 50)}... [truncated base64, length: ${obj.length}]`;
    }
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(sanitizeForDisplay);
  }
  if (typeof obj === 'object') {
    const record = obj as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    for (const key of Object.keys(record)) {
      const val = record[key];
      if (typeof val === 'string' && isTruncatableMediaString(val, key, record)) {
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

  const ordered = orderKeysForDisplay(parsed);
  const fullText = toPrettyJson(ordered);
  const displayText = truncateDisplayText(toPrettyJson(sanitizeForDisplay(ordered)));
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
