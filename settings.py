# settings.py
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "get_settings_path",
    "load_settings",
    "save_settings",
    "get",
    "set_",
    "get_export_dir",
]

# ---- location & defaults ----------------------------------------------------

APP_NAME = "betterbilling"
FILE_NAME = ".betterbilling_settings.json"

DEFAULTS: Dict[str, Any] = {
    "version": 1,
    "general": {
        "default_rate": 250.0,
        "default_export_dir": str(Path.home() / "Documents" / "BetterBilling" / "exports"),
        "launch_page": "dashboard",  # fixed for now (not exposed)
    },
    "invoice": {
        "require_explicit_zero_hours": True,
    },
    "pdf": {
        "file_naming_template": "{client}_invoice[{date}].pdf",
        "thousand_separators": True,
        # bottom margin is enforced in code, NOT in settings
    },
    "letterhead": {
        "top_margin_in": 2.5,
        "default_name": None,
        "library": [],  # future: [{ "name": "Firm A", "path": "C:/..." }, ...]
    },
    "ui": {
        "discard_warning": True,  # warn when leaving a dirty invoice
    },
}

# ---- path helpers -----------------------------------------------------------

def get_settings_path() -> Path:
    """
    Returns the full path to the settings JSON file.
    Windows: C:\\Users\\<user>\\AppData\\Roaming\\betterbilling\\<FILE_NAME>
    macOS:   ~/Library/Application Support/betterbilling/<FILE_NAME>
    Linux:   ~/.config/betterbilling/<FILE_NAME>
    """
    base: Path
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif sys_platform() == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME

    base.mkdir(parents=True, exist_ok=True)
    return base / FILE_NAME


def sys_platform() -> str:
    # Lazy import to keep imports tight at the top
    import sys
    return sys.platform


# ---- core load/save (with atomic write & simple migration hook) --------------

_cache: Optional[Dict[str, Any]] = None  # in-process cache


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """merge missing keys from src into dst (dst wins when keys already exist)."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst.setdefault(k, v)
    return dst


def _migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old schemas to current DEFAULTS["version"].
    Keep this lightweight; we only add migrations when version bumps.
    """
    current = DEFAULTS["version"]
    version = int(data.get("version", 0))

    if version == 0:
        # Treat unknown as new install -> overwrite with defaults merged over provided.
        data = _deep_merge(dict(data), DEFAULTS)

    # Example future migrations:
    # if version < 2:
    #     ... transform keys ...
    #     data["version"] = 2

    # Ensure all new defaults exist even after migrations
    data = _deep_merge(data, DEFAULTS)
    data["version"] = current
    return data


def load_settings() -> Dict[str, Any]:
    """Load settings from disk (cached), merging defaults and applying migrations."""
    global _cache
    if _cache is not None:
        return _cache

    path = get_settings_path()
    if not path.exists():
        _cache = json.loads(json.dumps(DEFAULTS))  # deep copy
        # ensure export dir exists
        _ensure_dir(Path(_cache["general"]["default_export_dir"]))
        # write the initial file
        save_settings(_cache)
        return _cache

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data = _migrate(data if isinstance(data, dict) else {})
    except Exception:
        # fall back to defaults on any read/parse error (don't clobber the bad file)
        data = json.loads(json.dumps(DEFAULTS))

    _cache = data
    # ensure export dir exists
    _ensure_dir(Path(_cache["general"]["default_export_dir"]))
    return _cache


def save_settings(data: Dict[str, Any]) -> None:
    """Persist settings to disk atomically and update cache."""
    global _cache
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # keep a migrated, default-merged version on write
    data = _migrate(dict(data))

    # atomic write
    fd, tmp = tempfile.mkstemp(prefix="bb_settings_", suffix=".json", dir=str(path.parent))
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


# ---- convenience getters/setters --------------------------------------------

def get(path: str, default: Any = None) -> Any:
    """
    Read a settings value by 'dot.path', e.g.:
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
    Write a settings value by 'dot.path', creating intermediate dicts if needed.
    Example:
      set_("general.default_rate", 350.0)
    """
    data = load_settings()
    node = data
    parts = path.split(".")
    for key in parts[:-1]:
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise TypeError(f"Cannot set {path}: {key} is not a dict in settings.")
    node[parts[-1]] = value
    save_settings(data)


def get_export_dir(create: bool = True) -> Path:
    """
    Returns the export directory Path (ensures exists if create=True).
    """
    p = Path(str(get("general.default_export_dir", DEFAULTS["general"]["default_export_dir"])))
    if create:
        _ensure_dir(p)
    return p


# ---- internals ---------------------------------------------------------------

def _ensure_dir(p: Path) -> None:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        # best-effort; caller can handle UI errors if they need to pick a new path
        pass
