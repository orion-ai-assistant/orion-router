import { cleanFilename, mediaFilename } from './log-images';

export type LogDocument = { document_archive_id?: number; filename?: string; mime_type?: string; format?: string;
  size_bytes?: number; representation?: 'text' | 'binary'; data_url?: string; text_content?: string; external_url?: string };

export function textAttachment(value: unknown): { filename?: string; text: string } | null {
  if (typeof value !== 'string') return null;
  const match = /^(?:Ek|Attachment)\s+\d+\s*[—–-]\s*(?:Metin dosyası|Text file|Not|Note)\s*:\s*([^\r\n]+)\r?\n<file_content>(\r?\n)([\s\S]*)\2<\/file_content>$/i.exec(value);
  return match ? { filename: cleanFilename(match[1]), text: match[3] } : null;
}

export function extractLogDocuments(payload: unknown): LogDocument[] {
  const documents: LogDocument[] = [], seen = new Set<string>();
  function add(document: LogDocument) {
    const key = `${document.document_archive_id ?? document.data_url ?? document.text_content ?? document.external_url}:${document.filename || ''}`;
    if (!seen.has(key)) { seen.add(key); documents.push(document); }
  }
  const isDocumentMime = (mime: unknown): mime is string => typeof mime === 'string' && /^(text|application)\//i.test(mime);
  function candidate(value: unknown, mime?: string, filename?: string, text = false) {
    if (typeof value !== 'string') return;
    if (text) { add({ filename, text_content: value, representation: 'text', mime_type: mime === 'application/pdf' ? 'text/plain' : mime || 'text/plain' }); return; }
    if (/^https?:\/\//i.test(value)) { add({ filename, external_url: value, mime_type: mime }); return; }
    const match = /^data:((?:text|application)\/[^;,]+)(?:;[^,;]+)*;base64,([A-Za-z0-9+/=\s]*)$/i.exec(value);
    if (value.startsWith('data:') && !match || !match && !/^[A-Za-z0-9+/=\s]*$/.test(value)) return;
    add({ filename, data_url: match ? value : `data:${mime || 'application/octet-stream'};base64,${value}`, mime_type: match?.[1] || mime });
  }
  function walk(value: unknown, inheritedName?: string) {
    if (Array.isArray(value)) { value.forEach(item => walk(item,inheritedName)); return; }
    if (!value || typeof value !== 'object') return;
    const node = value as Record<string,unknown>, filename = mediaFilename(node) || inheritedName;
    if (Number.isSafeInteger(node.document_archive_id) && Number(node.document_archive_id) > 0) {
      add({ ...node, filename } as LogDocument); return;
    }
    const wrapped = node.type === 'text' ? textAttachment(node.text) : null;
    if (wrapped) add({ filename: wrapped.filename, text_content: wrapped.text, mime_type: 'text/plain', representation: 'text' });
    const mime = [node.mime_type,node.mimeType,node.media_type].find(isDocumentMime);
    if (node.isText === true && (!node.mime_type && !node.mimeType || mime)) candidate(node.data,mime,filename,true);
    else if (mime) candidate(node.data,mime,filename);
    if (node.type === 'file' || node.type === 'input_file' || filename && 'file_data' in node) {
      candidate(node.file_data ?? node.file_url,mime,filename);
    }
    for (const key of ['file','input_file','inline_data','inlineData']) {
      const child = node[key];
      if (child && typeof child === 'object') {
        const file = child as Record<string,unknown>;
        const type = [file.mime_type,file.mimeType].find(isDocumentMime);
        if (key === 'file' || key === 'input_file' || type) candidate(file.file_data ?? file.data ?? file.file_url,type,mediaFilename(file) || filename);
      }
    }
    if (node.type === 'document' && node.source && typeof node.source === 'object') {
      const source = node.source as Record<string,unknown>;
      if (source.type === 'base64') candidate(source.data,typeof source.media_type === 'string' ? source.media_type : mime,mediaFilename(source) || filename);
    }
    Object.values(node).forEach(child => walk(child,filename));
  }
  walk(payload);
  return documents;
}
