from __future__ import annotations

import re
import unicodedata


WORD_RE = re.compile(r"[\wґЄєІіЇї']+", re.UNICODE)


def words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return WORD_RE.findall(normalized)


def contains_any_word(value: str, accepted: set[str] | frozenset[str]) -> bool:
    accepted_normalized = {word.casefold() for word in accepted}
    return any(word in accepted_normalized for word in words(value))
