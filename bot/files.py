from __future__ import annotations

import re
import unicodedata
from pathlib import Path


ALLOWED_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".webp",
    ".mp4", ".mov",
    ".pdf", ".docx", ".xlsx", ".pptx", ".txt",
    ".mp3", ".wav", ".zip",
})

FILE_ACCEPT = ",".join(sorted(ALLOWED_EXTENSIONS))


TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "ъ": "", "ы": "y",
    "э": "e", "ё": "io",
}


def latin_slug(value: str, fallback: str = "file") -> str:
    transliterated = "".join(TRANSLIT.get(char.casefold(), char) for char in value)
    ascii_value = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug[:100] or fallback


def normalized_folder(value: str) -> str:
    raw_parts = value.replace("\\", "/").split("/")
    parts = [latin_slug(part, "folder") for part in raw_parts if part.strip() not in {"", ".", ".."}]
    if len(parts) > 8:
        raise ValueError("Дозволено не більше 8 рівнів папок")
    return "/".join(parts)


def unique_file_path(root: Path, folder: str, original_name: str) -> Path:
    target_dir = root / normalized_folder(folder)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(original_name)
    extension = source.suffix.casefold()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Цей формат файлу не підтримується")
    stem = latin_slug(source.stem, "file")
    candidate = target_dir / f"{stem}{extension}"
    number = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}-{number}{extension}"
        number += 1
    return candidate


def unique_pdf_path(root: Path, folder: str, original_name: str) -> Path:
    """Backward-compatible name used by older callers and tests."""
    name = original_name if Path(original_name).suffix.casefold() == ".pdf" else f"{original_name}.pdf"
    return unique_file_path(root, folder, name)


def validate_upload(filename: str, body: bytes) -> tuple[bool, str]:
    extension = Path(filename).suffix.casefold()
    if extension not in ALLOWED_EXTENSIONS:
        return False, "Формат файлу не підтримується."
    signatures = {
        ".jpg": body.startswith(b"\xff\xd8\xff"),
        ".jpeg": body.startswith(b"\xff\xd8\xff"),
        ".png": body.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP",
        ".mp4": len(body) >= 12 and body[4:8] == b"ftyp",
        ".mov": len(body) >= 12 and body[4:8] == b"ftyp",
        ".pdf": body.startswith(b"%PDF-"),
        ".docx": body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".xlsx": body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".pptx": body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".zip": body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".mp3": body.startswith(b"ID3") or (len(body) >= 2 and body[0] == 0xFF and body[1] & 0xE0 == 0xE0),
        ".wav": len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WAVE",
    }
    if extension == ".txt":
        try:
            body.decode("utf-8")
            valid = b"\x00" not in body
        except UnicodeDecodeError:
            valid = False
    else:
        valid = signatures.get(extension, False)
    return (True, "") if valid else (False, "Розширення не відповідає вмісту файлу.")
