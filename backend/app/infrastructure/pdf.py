"""C-13 minimal deterministic PDF writer (no third-party dependency).

The consent PDF only needs to be readable and stable: a single page with
Helvetica text. Determinism matters because ``pdf_sha256`` is persisted and
verified, so the same payload must render the same bytes (no timestamps).
A richer writer can replace ``SimplePdfWriter`` behind ``PdfWriter`` later.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 50
FONT_SIZE = 11
LINE_HEIGHT = 14
MAX_CHARS = 92
MAX_LINES = 50


class PdfWriter(Protocol):
    """Render text lines into PDF bytes."""

    def render(self, lines: Sequence[str]) -> bytes: ...


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(line: str, width: int = MAX_CHARS) -> list[str]:
    if not line:
        return [""]
    return [line[index : index + width] for index in range(0, len(line), width)]


def _content_stream(lines: Sequence[str]) -> bytes:
    parts = ["BT", f"/F1 {FONT_SIZE} Tf", f"{MARGIN} {PAGE_HEIGHT - MARGIN} Td"]
    parts.append(f"{LINE_HEIGHT} TL")
    for index, line in enumerate(lines[:MAX_LINES]):
        if index:
            parts.append("T*")
        parts.append(f"({_escape(line)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", errors="replace")


def _build_pdf(stream: bytes) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} "
            f"{PAGE_HEIGHT}] /Resources << /Font << /F1 4 0 R >> >> "
            f"/Contents 5 0 R >>"
        ).encode("ascii"),
        (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
        + stream
        + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return bytes(output)


class SimplePdfWriter:
    """Single-page Helvetica PDF, deterministic for the same input lines."""

    def render(self, lines: Sequence[str]) -> bytes:
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(_wrap(line))
        return _build_pdf(_content_stream(wrapped))
