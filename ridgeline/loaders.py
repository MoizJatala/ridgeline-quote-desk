"""Stage 1: turn each RFQ file into plain text."""

from pathlib import Path

import openpyxl
import pdfplumber

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic"}


class UnsupportedFile(Exception):
    pass


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def _xlsx_text(path: Path) -> str:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    lines = []
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v).strip() for v in row]
                while cells and cells[-1] == "":
                    cells.pop()
                if cells:
                    lines.append("\t".join(cells))
    finally:
        wb.close()
    return "\n".join(lines)


def _pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix == ".xlsx":
        return _xlsx_text(path)
    raise UnsupportedFile(f"unsupported file type: {suffix or '(none)'}")


def list_rfqs(rfq_dir: Path) -> list[Path]:
    return sorted(p for p in rfq_dir.iterdir() if p.is_file() and not p.name.startswith("."))
