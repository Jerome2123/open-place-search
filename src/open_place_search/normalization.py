from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

_NON_WORD_PATTERN = re.compile(r"[^a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PHONE_DIGITS_PATTERN = re.compile(r"\D+")


def normalize_text(value: str | None) -> str:
    """Return a stable lowercase ASCII-ish key for place matching and aliases."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    without_punctuation = _NON_WORD_PATTERN.sub(" ", ascii_text.lower())
    return _WHITESPACE_PATTERN.sub(" ", without_punctuation).strip()


def dedupe_text(values: list[str], *, exclude: str | None = None) -> list[str]:
    excluded = normalize_text(exclude)
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        key = normalize_text(cleaned)
        if not cleaned or not key or key == excluded or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def phone_key(value: str | None) -> str | None:
    if not value:
        return None
    digits = _PHONE_DIGITS_PATTERN.sub("", value)
    if len(digits) < 7:
        return None
    return digits[-10:]


def website_host(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def stable_hash64(value: object) -> int:
    if value is None or value == "":
        return 0
    digest = hashlib.blake2b(str(value).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False) & ((1 << 63) - 1)


def canonical_key(provider: str, provider_id: str) -> str:
    return f"{normalize_text(provider).replace(' ', '_')}:{provider_id.strip()}"

