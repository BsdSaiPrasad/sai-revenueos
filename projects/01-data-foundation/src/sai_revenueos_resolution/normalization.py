"""Normalize identity evidence without turning it into authoritative truth."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Set
from urllib.parse import urlsplit


_COMPANY_SUFFIXES = {
    "co", "company", "corp", "corporation", "inc", "incorporated", "llc",
    "limited", "ltd", "plc",
}


def _words(value: Optional[str]) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return re.findall(r"[a-z0-9]+", text)


def normalize_company_name(value: Optional[str]) -> str:
    """Return a comparison form while preserving the original staged value."""
    words = _words(value)
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_person_name(value: Optional[str]) -> str:
    """Return a case- and punctuation-insensitive person-name comparison form."""
    return " ".join(_words(value))


def normalize_email(value: Optional[str]) -> str:
    """Normalize an email conservatively without provider-specific rewriting."""
    result = unicodedata.normalize("NFKC", value or "").strip().casefold()
    if result.count("@") != 1 or any(character.isspace() for character in result):
        return ""
    local, domain = result.split("@", 1)
    return result if local and domain else ""


def normalize_domain(value: Optional[str]) -> str:
    """Normalize a web domain while retaining subdomains as meaningful evidence."""
    raw = unicodedata.normalize("NFKC", value or "").strip().casefold()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else "//" + raw)
    host = (parsed.hostname or "").rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def token_similarity(left: Optional[str], right: Optional[str]) -> float:
    """Calculate deterministic Jaccard similarity between normalized word sets."""
    left_tokens: Set[str] = set(_words(left))
    right_tokens: Set[str] = set(_words(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(len(left_tokens | right_tokens))


def has_shared_value(values: Iterable[str]) -> bool:
    """Return whether an iterable contains at least one non-empty value."""
    return any(bool(value) for value in values)
