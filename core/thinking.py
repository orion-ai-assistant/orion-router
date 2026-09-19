"""
core/thinking.py
----------------
Thinking (Reasoning) parametrelerini normalize eden hafif değer nesnesi.
Gereksiz alias karmaşasından uzak, net ve doğrudan (pass-through) mimari:
  - Kapalı: 0, "0", "off", "none", "false", False
  - Sayısal bütçe: Pozitif tam sayı ("1024", 1024 vb.)
  - Seviye / Metin: Doğrudan string ("low", "medium", "high", "xhigh", "minimal" vb.)
"""
from dataclasses import dataclass
from typing import Any, Optional

# Kapatma için yalnızca standart ve net değerler
_DISABLED_VALUES = {"0", "off", "none", "false"}


@dataclass(frozen=True)
class ThinkingConfig:
    raw_value: Any = None
    is_unspecified: bool = False
    is_disabled: bool = False
    budget: Optional[int] = None
    level: Optional[str] = None

    @classmethod
    def from_value(cls, val: Any) -> "ThinkingConfig":
        """Gelen parametreyi kapatma / bütçe / string seviye olarak ayrıştırır."""
        if val is None:
            return cls(raw_value=val, is_unspecified=True)

        if isinstance(val, bool):
            if not val:
                return cls(raw_value=val, is_disabled=True, budget=0)
            return cls(raw_value=val, level="true")

        if isinstance(val, (int, float)):
            int_val = int(val)
            if int_val <= 0:
                return cls(raw_value=val, is_disabled=True, budget=0)
            return cls(raw_value=val, budget=int_val)

        s_val = str(val).strip()
        if not s_val:
            return cls(raw_value=val, is_unspecified=True)

        # 1. Kapatma ("0", "off", "none", "false")
        if s_val.lower() in _DISABLED_VALUES:
            return cls(raw_value=val, is_disabled=True, budget=0)

        # 2. Sayısal token bütçesi ("1024", "4096")
        if s_val.isdigit():
            return cls(raw_value=val, budget=int(s_val))

        # 3. Seviye / String ("low", "medium", "high", "xhigh", "minimal" vb.)
        # Kullanıcının verdiği string doğrudan korunur, yapay alias dönüşümü yapılmaz, harf büyüklüğü bile değiştirilmez
        return cls(raw_value=val, level=s_val)

    @property
    def is_active(self) -> bool:
        return not self.is_unspecified and not self.is_disabled
