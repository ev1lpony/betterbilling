# settings.py
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "PROJECT_ROOT",
    "get_settings_path",
    "load_settings",
    "save_settings",
    "get",
    "set_",
    "get_data_dir",
    "get_export_dir",
    "get_json_dir",
    "get_letterheads_dir",
    "get_folder",
]

# -----------------------------------------------------------------------------
# Portable / project-local settings
# -----------------------------------------------------------------------------
# This app is meant to run portably from the project folder (including USB
# drives), so settings and generated files should live inside the project.
#
# Expected layout:
#   betterbilling/
#       main.py
#       invoice_create.py
#       settings.py
#       ...
#       data/
#           pdfs/
#           json/
#           letterheads/
#       .betterbilling_settings.json
# -----------------------------------------------------------------------------

FILE_NAME = ".betterbilling_settings.json"

# Directory containing this settings.py file
PROJECT_ROOT = Path(__file__).resolve().parent

# Centralized local folders
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PDF_DIR = DEFAULT_DATA_DIR / "pdfs"
DEFAULT_JSON_DIR = DEFAULT_DATA_DIR / "json"
DEFAULT_LETTERHEAD_DIR = DEFAULT_DATA_DIR / "letterheads"

DEFAULTS: Dict[str, Any] = {
    "version": 2,
    "general": {
        "default_rate": 250.0,
        "data_dir": str(DEFAULT_DATA_DIR),
        "default_export_dir": str(DEFAULT_PDF_DIR),
        "default_json_dir": str(DEFAULT_JSON_DIR),
        "launch_page": "dashboard",
        "portable_mode": True,
    },
    "invoice": {
        "require_explicit_zero_hours": True,
    },
    "pdf": {
        "file_naming_template": "{client}_invoice[{date}].pdf",
        "thousand_separators": True,
    },
    "letterhead": {
        "top_margin_in": 2.5,
        "default_name": None,
        "library_dir": str(DEFAULT_LETTERHEAD_DIR),
        "library": [],
    },
    "ui": {
        "discard_warning": True,
    },
}

# -----------------------------------------------------------------------------
# Path helpers
# -----------------------------------------------------------------------------

def get_settings_path() -> Path:
    """
    Store the settings file inside the project folder so the app remains fully
    portable across computers and USB drives.
    """
    _ensure_dir(PROJECT_ROOT)
    return PROJECT_ROOT / FILE_NAME


def get_data_dir(create: bool = True) -> Path:
    p = Path(str(get("general.data_dir", str(DEFAULT_DATA_DIR))))
    if create:
        _ensure_dir(p)
    return p


def get_export_dir(create: bool = True) -> Path:
    """
    Returns the PDF export directory path.
    """
    p = Path(str(get("general.default_export_dir", str(DEFAULT_PDF_DIR))))
    if create:
        _ensure_dir(p)
    return p


def get_json_dir(create: bool = True) -> Path:
    """
    Returns the invoice JSON storage directory path.
    """
    p = Path(str(get("general.default_json_dir", str(DEFAULT_JSON_DIR))))
    if create:
        _ensure_dir(p)
    return p


def get_letterheads_dir(create: bool = True) -> Path:
    """
    Returns the letterheads directory path.
    """
    p = Path(str(get("letterhead.library_dir", str(DEFAULT_LETTERHEAD_DIR))))
    if create:
        _ensure_dir(p)
    return p


def get_folder(name: str, create: bool = True) -> Path:
    """
    Convenience helper for common portable folders.
    Valid names:
      - "data"
      - "pdfs"
      - "json"
      - "letterheads"
    """
    key = name.strip().lower()

    if key == "data":
        p = get_data_dir(create=False)
    elif key == "pdfs":
        p = get_export_dir(create=False)
    elif key == "json":
        p = get_json_dir(create=False)
    elif key == "letterheads":
        p = get_letterheads_dir(create=False)
    else:
        raise ValueError(f"Unknown folder name: {name}")

    if create:
        _ensure_dir(p)
    return p


# -----------------------------------------------------------------------------
# Core load/save
# -----------------------------------------------------------------------------

_cache: Optional[Dict[str, Any]] = None


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge missing keys from src into dst recursively.
    Existing dst values win.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst.setdefault(k, v)
    return dst


def _is_project_local_path(value: Any) -> bool:
    """
    True if the given path is inside the current project root.
    """
    try:
        p = Path(str(value)).resolve()
        root = PROJECT_ROOT.resolve()
        return p == root or root in p.parents
    except Exception:
        return False


def _normalize_all_paths(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Force all important paths to stay inside the project folder for portability.
    If an older config points to an old machine path, reset it to local folders.
    """
    general = data.setdefault("general", {})
    letterhead = data.setdefault("letterhead", {})

    data_dir = general.get("data_dir", str(DEFAULT_DATA_DIR))
    if not _is_project_local_path(data_dir):
        data_dir = str(DEFAULT_DATA_DIR)
    general["data_dir"] = str(Path(data_dir))

    export_dir = general.get("default_export_dir", str(DEFAULT_PDF_DIR))
    if not _is_project_local_path(export_dir):
        export_dir = str(Path(general["data_dir"]) / "pdfs")
    general["default_export_dir"] = str(Path(export_dir))

    json_dir = general.get("default_json_dir", str(DEFAULT_JSON_DIR))
    if not _is_project_local_path(json_dir):
        json_dir = str(Path(general["data_dir"]) / "json")
    general["default_json_dir"] = str(Path(json_dir))

    library_dir = letterhead.get("library_dir", str(DEFAULT_LETTERHEAD_DIR))
    if not _is_project_local_path(library_dir):
        library_dir = str(Path(general["data_dir"]) / "letterheads")
    letterhead["library_dir"] = str(Path(library_dir))

    general["portable_mode"] = True
    return data


def _migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old schemas to the current settings structure and normalize paths.
    """
    data = dict(data) if isinstance(data, dict) else {}
    version = int(data.get("version", 0))

    if version < 1:
        data = _deep_merge(data, DEFAULTS)

    if version < 2:
        general = data.setdefault("general", {})
        letterhead = data.setdefault("letterhead", {})
        general.setdefault("data_dir", str(DEFAULT_DATA_DIR))
        general.setdefault("default_export_dir", str(DEFAULT_PDF_DIR))
        general.setdefault("default_json_dir", str(DEFAULT_JSON_DIR))
        general.setdefault("portable_mode", True)
        letterhead.setdefault("library_dir", str(DEFAULT_LETTERHEAD_DIR))
        data["version"] = 2

    data = _deep_merge(data, DEFAULTS)
    data = _normalize_all_paths(data)
    data["version"] = DEFAULTS["version"]
    return data


def _ensure_default_dirs(data: Dict[str, Any]) -> None:
    _ensure_dir(PROJECT_ROOT)
    _ensure_dir(Path(str(data["general"]["data_dir"])))
    _ensure_dir(Path(str(data["general"]["default_export_dir"])))
    _ensure_dir(Path(str(data["general"]["default_json_dir"])))
    _ensure_dir(Path(str(data["letterhead"]["library_dir"])))


def load_settings() -> Dict[str, Any]:
    """
    Load settings from disk (cached), merge defaults, migrate old values,
    and ensure all required project-local folders exist.
    """
    global _cache
    if _cache is not None:
        return _cache

    path = get_settings_path()

    if not path.exists():
        data = json.loads(json.dumps(DEFAULTS))
        data = _migrate(data)
        _ensure_default_dirs(data)
        save_settings(data)
        _cache = data
        return _cache

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        data = _migrate(raw)
    except Exception:
        data = json.loads(json.dumps(DEFAULTS))
        data = _migrate(data)

    _ensure_default_dirs(data)
    _cache = data
    return _cache


def save_settings(data: Dict[str, Any]) -> None:
    """
    Persist settings to disk atomically and update the in-process cache.
    """
    global _cache

    path = get_settings_path()
    _ensure_dir(path.parent)

    data = _migrate(data)
    _ensure_default_dirs(data)

    fd, tmp = tempfile.mkstemp(
        prefix="bb_settings_",
        suffix=".json",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

    _cache = data


# -----------------------------------------------------------------------------
# Convenience getters/setters
# -----------------------------------------------------------------------------

def get(path: str, default: Any = None) -> Any:
    """
    Read a settings value by dot-path.
    Example:
      get("general.default_rate", 250.0)
    """
    data = load_settings()
    node: Any = data

    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]

    return node


def set_(path: str, value: Any) -> None:
    """
    Write a settings value by dot-path, creating intermediate dicts if needed.
    Example:
      set_("general.default_rate", 350.0)
    """
    data = load_settings()
    node = data
    parts = path.split(".")

    for key in parts[:-1]:
        existing = node.setdefault(key, {})
        if not isinstance(existing, dict):
            raise TypeError(f"Cannot set {path}: {key} is not a dict in settings.")
        node = existing

    node[parts[-1]] = value
    save_settings(data)


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------

def _ensure_dir(p: Path) -> None:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass