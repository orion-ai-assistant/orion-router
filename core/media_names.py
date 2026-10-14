"""Attachment names only: never copy prompts or arbitrary neighboring text."""
import re


def clean_filename(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f\x7f]", "", value.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return value[:255] or None


def media_filename(node):
    if not isinstance(node, dict):
        return None
    for key in ("filename", "file_name", "original_filename"):
        if name := clean_filename(node.get(key)):
            return name
    if any(key in node for key in ("data", "url", "mime_type", "mimeType")):
        return clean_filename(node.get("name"))
    return None


def label_filename(node):
    if not isinstance(node, dict) or node.get("type") != "text":
        return None
    text = node.get("text")
    match = re.fullmatch(r"(?:Ek|Attachment)\s+\d+\s*[—–-]\s*(?:Görsel|Ses|Video|Image|Audio)\s*:\s*([^\r\n]+)", text, re.IGNORECASE) if isinstance(text, str) else None
    return clean_filename(match[1]) if match else None
