"""Turn input files into text (or an image for vision models)."""
from __future__ import annotations

from pathlib import Path

TEXT_EXT = {".txt", ".md"}
PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED = TEXT_EXT | PDF_EXT | IMAGE_EXT


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXT:
        return path.read_text(encoding="utf-8")
    if suffix in PDF_EXT:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        # layout mode keeps table columns on one line, which matters for line-item parsing
        return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    raise ValueError(f"Cannot read text from {path.name}; images need a vision-capable LLM provider")


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXT


def iter_inputs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
