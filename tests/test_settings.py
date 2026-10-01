import json
from copy import deepcopy

import pytest

import settings


def reload_settings():
    settings._cache = None
    return settings.load_settings()


def test_load_missing_settings_defaults_and_portable_dirs_without_write():
    data = reload_settings()
    assert data == settings.DEFAULTS
    assert not settings.SETTINGS_FILE.exists()
    assert all(path.is_dir() for path in (settings.DATA_DIR, settings.PDF_DIR, settings.JSON_DIR, settings.LETTERHEAD_DIR))


def test_legacy_settings_merge_preserves_preferences_and_unknown_values():
    legacy = {"version": 2, "general": {"default_rate": 325, "portable_mode": False}, "pdf": {"thousand_separators": False}, "custom": {"keep": "value"}}
    settings.SETTINGS_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    data = reload_settings()
    assert data["version"] == 3
    assert data["general"]["default_rate"] == 325
    assert data["general"]["portable_mode"] is True
    assert data["pdf"]["thousand_separators"] is False
    assert data["invoice"]["review_dedupe"] is True
    assert data["custom"] == {"keep": "value"}
    assert json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8")) == legacy
    settings.set_("pdf.show_total_hours", False)
    persisted = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert persisted["custom"] == {"keep": "value"}
    assert persisted["general"]["default_rate"] == 325


@pytest.mark.parametrize("contents", [b"broken JSON", b"[1, 2, 3]", b"null"])
def test_malformed_settings_survive_load_and_are_backed_up_on_save(contents):
    settings.SETTINGS_FILE.write_bytes(contents)
    data = reload_settings()
    assert data == settings.DEFAULTS
    assert settings.SETTINGS_FILE.read_bytes() == contents
    assert not list(settings.PROJECT_ROOT.glob("bb_settings_recovery_*.json"))
    settings.set_("general.default_rate", 300)
    backups = list(settings.PROJECT_ROOT.glob("bb_settings_recovery_*.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == contents
    assert settings.get("general.default_rate") == 300


def test_invalid_preferences_use_safe_defaults_in_memory():
    invalid = {"general": {"default_rate": "NaN"}, "letterhead": {"top_margin_in": "bad"}, "invoice": {"review_dedupe": "false"}, "pdf": {"file_naming_template": None}}
    settings.SETTINGS_FILE.write_text(json.dumps(invalid), encoding="utf-8")
    data = reload_settings()
    assert data["general"]["default_rate"] == 250
    assert data["letterhead"]["top_margin_in"] == 2.5
    assert data["invoice"]["review_dedupe"] is True
    assert data["pdf"]["file_naming_template"] == settings.DEFAULTS["pdf"]["file_naming_template"]
    assert json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8")) == invalid


def test_failed_settings_replace_preserves_original_and_cached_value(monkeypatch):
    settings.save_settings(deepcopy(settings.DEFAULTS))
    contents = settings.SETTINGS_FILE.read_bytes()

    def fail_replace(*args):
        raise PermissionError("Synthetic settings replace failure")

    monkeypatch.setattr(settings.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        settings.set_("general.default_rate", 500)
    assert settings.SETTINGS_FILE.read_bytes() == contents
    assert settings.get("general.default_rate") == 250
    assert not list(settings.PROJECT_ROOT.glob("bb_settings_*.json"))


def test_utf8_bom_settings_are_accepted():
    settings.SETTINGS_FILE.write_text(json.dumps({"general": {"default_rate": 300}}), encoding="utf-8-sig")
    assert reload_settings()["general"]["default_rate"] == 300


def test_zero_default_rate_is_preserved_for_no_charge_invoices():
    settings.set_("general.default_rate", 0)
    assert reload_settings()["general"]["default_rate"] == 0


def test_large_default_rate_and_extra_precision_are_preserved():
    settings.set_("general.default_rate", 20_000_000.125)
    assert reload_settings()["general"]["default_rate"] == 20_000_000.125
