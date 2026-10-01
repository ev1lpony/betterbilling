"""Run every test against temporary storage, never personal billing records."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / ".betterbilling_settings.json")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "PDF_DIR", tmp_path / "data" / "pdfs")
    monkeypatch.setattr(settings, "JSON_DIR", tmp_path / "data" / "json")
    monkeypatch.setattr(settings, "LETTERHEAD_DIR", tmp_path / "data" / "letterheads")
    monkeypatch.setattr(settings, "_cache", deepcopy(settings.DEFAULTS))
    yield


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
