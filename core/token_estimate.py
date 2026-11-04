"""A rough token count for a chat the provider never reported (stopped before its usage chunk).

Tokenizers differ per model, so this only aims close: about 4 characters per token for Latin text, 2 for other
alphabets (Cyrillic, Greek, Arabic, Hebrew, Indic, Thai), and 1 per character for Chinese, Japanese and Korean.
Messages count by their text plus a few tokens each for the role; tool definitions count as compact JSON, as the
provider reads their names, descriptions and schema rather than our spacing and quoting.
"""
import json
import math
from typing import Any

PER_MESSAGE = 4  # Role and separators around each message.


def _weight(char: str) -> float:
    code = ord(char)
    if (0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF
            or 0xAC00 <= code <= 0xD7AF or 0xF900 <= code <= 0xFAFF or 0xFF00 <= code <= 0xFFEF
            or 0x20000 <= code <= 0x2FFFF):
        return 1.0  # Kana, CJK ideographs, Hangul, full-width forms.
    if 0x0370 <= code <= 0x0FFF:
        return 0.5  # Greek, Cyrillic, Armenian, Hebrew, Arabic, Indic, Thai…
    return 0.25


def text_tokens(text: str | None) -> int:
    if not text:
        return 0
    return math.ceil(sum(_weight(char) for char in text))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # Multimodal parts: only their text is countable here.
        return ' '.join(part['text'] for part in content if isinstance(part, dict) and part.get('text'))
    return ''


def prompt_tokens(messages: list[dict[str, Any]] | None, tools: list[Any] | None = None) -> int:
    total = 0
    for message in messages or []:
        total += PER_MESSAGE + text_tokens(_content_text(message.get('content')))
        if message.get('tool_calls'):
            total += text_tokens(json.dumps(message['tool_calls'], ensure_ascii=False, separators=(',', ':')))
    if tools:
        total += text_tokens(json.dumps(tools, ensure_ascii=False, separators=(',', ':')))
    return max(1, total)
