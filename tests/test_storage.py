from datetime import datetime
from pathlib import Path

import pytest

import pdf_gen
import settings
import storage
from models import Invoice


def invoice():
    inv = Invoice("Synthetic Client", "04/30/2025", 250)
    inv.add_service(datetime(2025, 4, 1), "Synthetic work", 1)
    return inv


def test_default_filename_and_client_sanitization():
    inv = invoice()
    inv.client_name = '  Smith / Test:*?  '
    assert storage.render_filename(inv) == "Smith_Test_invoice[04-30-2025].pdf"
    assert storage.sanitize_client("***") == "invoice"
    assert storage.sanitize_client("NUL") == "_NUL"


@pytest.mark.parametrize("template", ["../escape.pdf", "folder\\escape.pdf", "C:\\escape.pdf", "/escape.pdf"])
def test_template_cannot_escape_storage_folders(template):
    settings._cache["pdf"]["file_naming_template"] = template
    with pytest.raises(ValueError, match="filename"):
        storage.base_paths(invoice())


@pytest.mark.parametrize("template,expected", [
    ("CON.pdf", "_CON.pdf"),
    ("lpt1.PDF", "_lpt1.pdf"),
    ("COM¹.pdf", "_COM¹.pdf"),
    ("CON .txt.pdf", "_CON .txt.pdf"),
    ('bad:name*?.pdf', "bad_name__.pdf"),
    ("invoice", "invoice.pdf"),
    ("invoice.PDF", "invoice.pdf"),
])
def test_windows_names_and_pdf_suffix_are_safe(template, expected):
    settings._cache["pdf"]["file_naming_template"] = template
    assert storage.render_filename(invoice()) == expected


def test_bad_format_template_falls_back_to_default():
    settings._cache["pdf"]["file_naming_template"] = "{unknown}.pdf"
    assert storage.render_filename(invoice()) == "Synthetic_Client_invoice[04-30-2025].pdf"


def test_long_filename_leaves_room_for_pair_suffixes():
    inv = invoice()
    inv.client_name = "A" * 500
    filename = storage.render_filename(inv)
    assert len(filename.encode("utf-16-le")) < 510


@pytest.mark.parametrize("date", ["../../outside", "C:\\outside\\record", "../NUL:*?"])
def test_filename_date_cannot_introduce_path_components(date):
    inv = invoice()
    inv.invoice_date = date
    json_path, pdf_path = storage.base_paths(inv)
    assert json_path.parent == settings.JSON_DIR
    assert pdf_path.parent == settings.PDF_DIR
    assert not any(char in pdf_path.name for char in '<>:"/\\|?*')


def test_paired_allocation_skips_json_and_pdf_only_collisions():
    inv = invoice()
    json_path, pdf_path = storage.base_paths(inv)
    json_path.write_text("existing", encoding="utf-8")
    pdf_path.with_stem(pdf_path.stem + " (1)").write_bytes(b"existing")
    paired_json, paired_pdf = storage.paired_unique_paths(inv)
    assert paired_json.stem == paired_pdf.stem == pdf_path.stem + " (2)"
    assert paired_json.parent == settings.JSON_DIR
    assert paired_pdf.parent == settings.PDF_DIR


def test_json_roundtrip_and_utf8_bom(tmp_path):
    path = tmp_path / "invoice.json"
    inv = invoice()
    storage.save_invoice_json(inv, path)
    assert storage.load_invoice_json(path).to_dict() == inv.to_dict()
    payload = path.read_text(encoding="utf-8")
    path.write_text(payload, encoding="utf-8-sig")
    assert storage.load_invoice_json(path).to_dict() == inv.to_dict()


def test_new_json_save_refuses_preexisting_record_using_real_os_primitive(tmp_path):
    path = tmp_path / "invoice.json"
    path.write_bytes(b"existing record")
    with pytest.raises(FileExistsError):
        storage.save_invoice_json(invoice(), path, overwrite=False)
    assert path.read_bytes() == b"existing record"
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_new_json_save_refuses_collision_after_staging(tmp_path, monkeypatch):
    path = tmp_path / "invoice.json"
    original_stage = storage._stage_invoice_json

    def stage_then_create_competing_record(inv, destination):
        staged = original_stage(inv, destination)
        path.write_bytes(b"competing JSON")
        return staged

    monkeypatch.setattr(storage, "_stage_invoice_json", stage_then_create_competing_record)
    with pytest.raises(FileExistsError):
        storage.save_invoice_json(invoice(), path, overwrite=False)
    assert path.read_bytes() == b"competing JSON"
    assert not list(tmp_path.glob(".bb_invoice_*"))


@pytest.mark.parametrize("collision_side", ["json", "pdf"])
def test_new_pair_save_refuses_collision_during_pdf_staging_without_partial_pair(monkeypatch, collision_side):
    inv = invoice()
    json_path, pdf_path = storage.paired_unique_paths(inv)
    competing = json_path if collision_side == "json" else pdf_path

    def render_then_create_competing_record(inv, destination):
        Path(destination).write_bytes(b"synthetic complete PDF")
        competing.write_bytes(b"competing record")

    monkeypatch.setattr(pdf_gen, "generate_pdf", render_then_create_competing_record)
    with pytest.raises(FileExistsError):
        storage.save_invoice_pair(inv, json_path, pdf_path, overwrite=False)
    assert competing.read_bytes() == b"competing record"
    other = pdf_path if collision_side == "json" else json_path
    assert not other.exists()
    assert not list(json_path.parent.glob(".bb_invoice_*"))
    assert not list(pdf_path.parent.glob(".bb_invoice_*"))


def test_successful_no_overwrite_pair_cleans_staging_files(tmp_path):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    inv = invoice()
    storage.save_invoice_pair(inv, json_path, pdf_path, overwrite=False)
    assert storage.load_invoice_json(json_path).to_dict() == inv.to_dict()
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_json_replace_failure_keeps_original_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / "invoice.json"
    original = b"original record"
    path.write_bytes(original)

    def fail_replace(*args):
        raise PermissionError("Synthetic replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        storage.save_invoice_json(invoice(), path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_invalid_invoice_never_replaces_existing_json(tmp_path):
    path = tmp_path / "invoice.json"
    path.write_bytes(b"original record")
    inv = invoice()
    inv.services[0].hours = float("nan")
    with pytest.raises(ValueError):
        storage.save_invoice_json(inv, path)
    assert path.read_bytes() == b"original record"


def test_failed_pdf_render_preserves_both_existing_records(tmp_path, monkeypatch):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    json_path.write_bytes(b"original JSON")
    pdf_path.write_bytes(b"original PDF")

    def fail_render(inv, destination):
        Path(destination).write_bytes(b"partial PDF")
        raise ValueError("Synthetic render failure")

    monkeypatch.setattr(pdf_gen, "generate_pdf", fail_render)
    with pytest.raises(ValueError, match="render failure"):
        storage.save_invoice_pair(invoice(), json_path, pdf_path)
    assert json_path.read_bytes() == b"original JSON"
    assert pdf_path.read_bytes() == b"original PDF"
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_pair_backup_failure_preserves_originals(tmp_path, monkeypatch):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    json_path.write_bytes(b"original JSON")
    pdf_path.write_bytes(b"original PDF")

    def fake_render(inv, destination):
        Path(destination).write_bytes(b"synthetic complete PDF")

    def fail_backup(*args):
        raise PermissionError("Synthetic backup failure")

    monkeypatch.setattr(pdf_gen, "generate_pdf", fake_render)
    monkeypatch.setattr(storage.shutil, "copyfile", fail_backup)
    with pytest.raises(PermissionError, match="backup failure"):
        storage.save_invoice_pair(invoice(), json_path, pdf_path)
    assert json_path.read_bytes() == b"original JSON"
    assert pdf_path.read_bytes() == b"original PDF"
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_failed_rollback_retains_original_recovery_copy(tmp_path, monkeypatch):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    json_path.write_bytes(b"original JSON")
    pdf_path.write_bytes(b"original PDF")

    def fake_render(inv, destination):
        Path(destination).write_bytes(b"synthetic complete PDF")

    original_replace = storage.os.replace
    commit_count = 0

    def fail_commit_and_rollback(source, destination):
        nonlocal commit_count
        commit_count += 1
        if commit_count >= 2:
            raise PermissionError("Synthetic replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(pdf_gen, "generate_pdf", fake_render)
    monkeypatch.setattr(storage.os, "replace", fail_commit_and_rollback)
    with pytest.raises(OSError, match="recovery copies retained"):
        storage.save_invoice_pair(invoice(), json_path, pdf_path)
    recovery = list(tmp_path.glob(".bb_invoice_*.recovery"))
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"original JSON"
    assert pdf_path.read_bytes() == b"original PDF"


@pytest.mark.parametrize("existing", [False, True])
def test_second_commit_failure_rolls_back_first_record(tmp_path, monkeypatch, existing):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    if existing:
        json_path.write_bytes(b"original JSON")
        pdf_path.write_bytes(b"original PDF")

    def fake_render(inv, destination):
        Path(destination).write_bytes(b"synthetic complete PDF")

    original_replace = storage.os.replace

    def fail_pdf_replace(source, destination):
        if Path(destination) == pdf_path:
            raise PermissionError("Synthetic PDF replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(pdf_gen, "generate_pdf", fake_render)
    monkeypatch.setattr(storage.os, "replace", fail_pdf_replace)
    with pytest.raises(PermissionError, match="PDF replace failure"):
        storage.save_invoice_pair(invoice(), json_path, pdf_path)
    if existing:
        assert json_path.read_bytes() == b"original JSON"
        assert pdf_path.read_bytes() == b"original PDF"
    else:
        assert not json_path.exists()
        assert not pdf_path.exists()
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_successful_pair_contains_matching_invoice_and_real_pdf(tmp_path):
    json_path, pdf_path = tmp_path / "invoice.json", tmp_path / "invoice.pdf"
    inv = invoice()
    storage.save_invoice_pair(inv, json_path, pdf_path)
    assert storage.load_invoice_json(json_path).to_dict() == inv.to_dict()
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert not list(tmp_path.glob(".bb_invoice_*"))


def test_corrupt_json_is_unchanged_after_load_failure(tmp_path):
    path = tmp_path / "invoice.json"
    contents = b'{"services": [123]}'
    path.write_bytes(contents)
    with pytest.raises(ValueError):
        storage.load_invoice_json(path)
    assert path.read_bytes() == contents


def test_invoice_discovery_ignores_recovery_and_staging_files():
    settings.JSON_DIR.mkdir(parents=True)
    first = settings.JSON_DIR / "first.json"
    first.write_text("{}", encoding="utf-8")
    (settings.JSON_DIR / ".bb_invoice_synthetic.json.tmp").write_text("{}", encoding="utf-8")
    (settings.JSON_DIR / ".bb_invoice_synthetic.recovery").write_text("{}", encoding="utf-8")
    assert storage.list_invoice_json_files() == [first]
