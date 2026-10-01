from __future__ import annotations

import json
import re
from pathlib import Path

import settings
from models import Invoice


def sanitize_client(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    return re.sub(r"\s+", "_", value) or "invoice"


def date_for_filename(invoice_date: str) -> str:
    return invoice_date.replace("/", "-")


def render_filename(inv: Invoice) -> str:
    template = str(
        settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf")
    )
    try:
        return template.format(
            client=sanitize_client(inv.client_name),
            date=date_for_filename(inv.invoice_date),
        )
    except Exception:
        return (
            f"{sanitize_client(inv.client_name)}"
            f"_invoice[{date_for_filename(inv.invoice_date)}].pdf"
        )


def base_paths(inv: Invoice) -> tuple[Path, Path]:
    pdf_name = render_filename(inv)
    json_name = Path(pdf_name).with_suffix(".json").name
    return (
        settings.get_json_dir(create=True) / json_name,
        settings.get_export_dir(create=True) / pdf_name,
    )


def paired_unique_paths(inv: Invoice) -> tuple[Path, Path]:
    json_base, pdf_base = base_paths(inv)
    json_dir = json_base.parent
    pdf_dir = pdf_base.parent
    stem = pdf_base.stem
    pdf_suffix = pdf_base.suffix or ".pdf"

    n = 0
    while True:
        extra = "" if n == 0 else f" ({n})"
        json_path = json_dir / f"{stem}{extra}.json"
        pdf_path = pdf_dir / f"{stem}{extra}{pdf_suffix}"
        if not json_path.exists() and not pdf_path.exists():
            return json_path, pdf_path
        n += 1


def save_invoice_json(inv: Invoice, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inv.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_invoice_json(path: Path) -> Invoice:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invoice JSON root must be an object")
    return Invoice.from_dict(raw)


def list_invoice_json_files() -> list[Path]:
    folder = settings.get_json_dir(create=True)
    return sorted(
        folder.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
