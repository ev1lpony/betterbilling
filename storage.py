from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import settings
from models import Invoice


_RESERVED_NAMES = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:[ .]|$)", re.IGNORECASE)


def _safe_filename(value: str) -> str:
    """Return one Windows-safe PDF filename, never a path from a template."""
    if not value or any(char in value for char in ("/", "\\")) or Path(value).is_absolute():
        raise ValueError("Invoice filename template must produce a filename, not a folder or path")
    value = re.sub(r'[<>:"|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
    if value in ("", ".", ".."):
        value = "invoice"
    # Use a consistent suffix so reopened JSON files always find their PDF.
    if value.lower().endswith(".pdf"):
        value = value[:-4].rstrip(". ") or "invoice"
    if _RESERVED_NAMES.match(value):
        value = "_" + value
    # NTFS allows 255 UTF-16 code units per component; leave room for collision
    # suffixes and avoid splitting a surrogate pair when truncating Unicode.
    while len(value.encode("utf-16-le")) > 440:
        value = value[:-1]
    return value + ".pdf"


def sanitize_client(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    value = re.sub(r"\s+", "_", value) or "invoice"
    return "_" + value if _RESERVED_NAMES.match(value) else value


def date_for_filename(invoice_date: str) -> str:
    return re.sub(r'[<>:"|?*\\\x00-\x1f]', "_", invoice_date.replace("/", "-")).strip().rstrip(". ")


def render_filename(inv: Invoice) -> str:
    template = str(
        settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf")
    )
    try:
        filename = template.format(
            client=sanitize_client(inv.client_name),
            date=date_for_filename(inv.invoice_date),
        )
    except Exception:
        filename = (
            f"{sanitize_client(inv.client_name)}"
            f"_invoice[{date_for_filename(inv.invoice_date)}].pdf"
        )
    return _safe_filename(filename)


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


def save_invoice_json(inv: Invoice, path: Path, *, overwrite: bool = True) -> None:
    """Commit a complete JSON record, optionally refusing an existing path."""
    path = Path(path)
    staged = _stage_invoice_json(inv, path)
    try:
        _commit_staged(staged, path, overwrite=overwrite)
    finally:
        staged.unlink(missing_ok=True)


def _commit_staged(source: Path, destination: Path, *, overwrite: bool) -> None:
    if overwrite:
        os.replace(source, destination)
    elif os.name == "nt":
        # Unlike POSIX rename, Windows rename refuses an existing destination.
        # It also works on portable FAT/exFAT drives without hardlink support.
        os.rename(source, destination)
    else:
        # Creating a link is an atomic no-clobber operation. Both paths are in
        # one directory; the staging link is removed by the caller afterward.
        # Non-Windows new saves require a filesystem supporting hardlinks.
        os.link(source, destination)


def _temporary_path(destination: Path, suffix: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".bb_invoice_", suffix=suffix, dir=destination.parent)
    os.close(fd)
    return Path(name)


def _stage_invoice_json(inv: Invoice, destination: Path) -> Path:
    payload = json.dumps(inv.to_dict(), indent=2, ensure_ascii=False, allow_nan=False)
    staged = _temporary_path(destination, ".json.tmp")
    try:
        with staged.open("w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def save_invoice_pair(
    inv: Invoice, json_path: Path, pdf_path: Path, *, overwrite: bool = True
) -> None:
    """Stage both records and roll back ordinary replacement failures.

    Each final replacement is atomic. Two separate files cannot be committed
    atomically across a process crash or power loss; recovery copies protect
    existing records while the running process handles ordinary I/O failures.
    New saves use overwrite=False so simultaneous filename allocation cannot
    replace another invoice. Windows uses no-overwrite rename; other platforms
    require hardlink support for the equivalent exclusive commit.
    """
    from pdf_gen import generate_pdf

    json_path, pdf_path = Path(json_path), Path(pdf_path)
    if json_path.resolve() == pdf_path.resolve():
        raise ValueError("JSON and PDF destinations must be different files")
    for destination in (json_path, pdf_path):
        if destination.exists() and not destination.is_file():
            raise ValueError(f"Invoice destination is not a file: {destination}")

    staged_files: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    retain_backups: set[Path] = set()
    try:
        staged_files[json_path] = _stage_invoice_json(inv, json_path)
        staged_pdf = _temporary_path(pdf_path, ".pdf")
        staged_files[pdf_path] = staged_pdf
        generate_pdf(inv, staged_pdf)
        if staged_pdf.stat().st_size == 0:
            raise ValueError("PDF generation produced an empty file")
        with staged_pdf.open("r+b") as fh:
            os.fsync(fh.fileno())

        for destination in (json_path, pdf_path):
            if overwrite and destination.exists():
                backup = _temporary_path(destination, ".recovery")
                backups[destination] = backup
                shutil.copyfile(destination, backup)

        try:
            for destination in (json_path, pdf_path):
                _commit_staged(staged_files[destination], destination, overwrite=overwrite)
                committed.append(destination)
        except OSError as exc:
            rollback_errors: list[str] = []
            for destination in reversed(committed):
                try:
                    backup = backups.get(destination)
                    if backup is None:
                        destination.unlink(missing_ok=True)
                    else:
                        os.replace(backup, destination)
                except OSError as rollback_exc:
                    if destination in backups:
                        retain_backups.add(backups[destination])
                    rollback_errors.append(f"{destination}: {rollback_exc}")
            if rollback_errors:
                locations = ", ".join(str(path) for path in retain_backups)
                raise OSError(
                    f"Invoice save failed ({exc}); recovery also failed: {'; '.join(rollback_errors)}. "
                    f"Original recovery copies retained at: {locations or 'none'}"
                ) from exc
            raise
    finally:
        for temporary in list(staged_files.values()) + list(backups.values()):
            if temporary not in retain_backups:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def load_invoice_json(path: Path) -> Invoice:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
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
