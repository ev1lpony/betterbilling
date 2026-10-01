from __future__ import annotations

import json
import os
import tempfile
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = PROJECT_ROOT / ".betterbilling_settings.json"

DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
JSON_DIR = DATA_DIR / "json"
LETTERHEAD_DIR = DATA_DIR / "letterheads"

DEFAULTS: dict[str, Any] = {
    "version": 3,
    "general": {
        "default_rate": 250.0,
        "portable_mode": True,
    },
    "invoice": {
        "require_explicit_zero_hours": True,
        "review_dedupe": True,
    },
    "pdf": {
        "file_naming_template": "{client}_invoice[{date}].pdf",
        "thousand_separators": True,
        "show_total_hours": True,
    },
    "letterhead": {
        "top_margin_in": 2.5,
    },
}


def ensure_dirs() -> None:
    for path in (DATA_DIR, PDF_DIR, JSON_DIR, LETTERHEAD_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _deep_merge(existing: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if isinstance(value, dict):
            node = existing.setdefault(key, {})
            if not isinstance(node, dict):
                existing[key] = {}
                node = existing[key]
            _deep_merge(node, value)
        else:
            existing.setdefault(key, value)
    return existing


_cache: dict[str, Any] | None = None


def _validate_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Repair invalid individual preferences without losing unknown keys."""
    from models import validate_nonnegative_number

    data = _deep_merge(data, deepcopy(DEFAULTS))
    for section, key, minimum, maximum in (
        ("general", "default_rate", 0.0, float("inf")),
        ("letterhead", "top_margin_in", 0.0, 5.0),
    ):
        try:
            value = validate_nonnegative_number(data[section][key], f"{section}.{key}")
            if not minimum <= value <= maximum:
                raise ValueError("Out of range")
            data[section][key] = value
        except ValueError:
            data[section][key] = DEFAULTS[section][key]
    for section, key in (
        ("invoice", "require_explicit_zero_hours"),
        ("invoice", "review_dedupe"),
        ("pdf", "thousand_separators"),
        ("pdf", "show_total_hours"),
    ):
        if not isinstance(data[section][key], bool):
            data[section][key] = DEFAULTS[section][key]
    template = data["pdf"]["file_naming_template"]
    if not isinstance(template, str) or not template.strip():
        data["pdf"]["file_naming_template"] = DEFAULTS["pdf"]["file_naming_template"]
    data["version"] = DEFAULTS["version"]
    data["general"]["portable_mode"] = True
    return data


def load_settings() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache

    ensure_dirs()
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, ValueError):
            raw = {}
    else:
        raw = {}

    # Loading must not erase a damaged preference file. Migrations/defaults are
    # applied in memory and written only when a preference is explicitly saved.
    data = _validate_settings(raw)
    _cache = data
    return data


def save_settings(data: dict[str, Any]) -> None:
    global _cache
    ensure_dirs()
    if not isinstance(data, dict):
        raise ValueError("Settings must be an object")
    data = _validate_settings(deepcopy(data))

    fd, temp_name = tempfile.mkstemp(
        prefix="bb_settings_",
        suffix=".json",
        dir=str(PROJECT_ROOT),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        if SETTINGS_FILE.exists():
            try:
                original = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
                needs_backup = not isinstance(original, dict)
            except ValueError:
                needs_backup = True
            # An unreadable original must stay in place if it cannot be backed
            # up. Let the write fail with an actionable error in that case.
            if needs_backup:
                backup_fd, backup_name = tempfile.mkstemp(
                    prefix="bb_settings_recovery_", suffix=".json", dir=str(PROJECT_ROOT)
                )
                os.close(backup_fd)
                try:
                    shutil.copyfile(SETTINGS_FILE, backup_name)
                except OSError:
                    Path(backup_name).unlink(missing_ok=True)
                    raise
        os.replace(temp_name, SETTINGS_FILE)
    finally:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except Exception:
                pass

    _cache = data


def get(path: str, default: Any = None) -> Any:
    node: Any = load_settings()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_(path: str, value: Any) -> None:
    data = deepcopy(load_settings())
    node = data
    parts = path.split(".")
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise TypeError(f"Cannot set {path}: {part} is not an object")
        node = child
    node[parts[-1]] = value
    save_settings(data)


def get_data_dir(create: bool = True) -> Path:
    if create:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_export_dir(create: bool = True) -> Path:
    if create:
        PDF_DIR.mkdir(parents=True, exist_ok=True)
    return PDF_DIR


def get_json_dir(create: bool = True) -> Path:
    if create:
        JSON_DIR.mkdir(parents=True, exist_ok=True)
    return JSON_DIR


def get_letterheads_dir(create: bool = True) -> Path:
    if create:
        LETTERHEAD_DIR.mkdir(parents=True, exist_ok=True)
    return LETTERHEAD_DIR
