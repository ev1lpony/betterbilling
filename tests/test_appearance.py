"""Appearance changes must preserve invoices, entry focus, and saving behavior."""
from copy import deepcopy
from datetime import datetime
import json

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QStyle, QStyleOptionSpinBox

import main
import settings
from ui_theme import apply_theme, build_stylesheet, font_sizes, theme_colors


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    app_window = main.MainWindow()
    app_window.show()
    app_window.activateWindow()
    qapp.processEvents()
    yield app_window
    app_window.close()
    app_window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    apply_theme(qapp, "light", False)


def select_appearance(window, mode, easy):
    page = window.settings_page
    page.theme.setCurrentIndex(page.theme.findData(mode))
    page.easy_reading.setChecked(easy)


def fill_invoice(window):
    window.go_new()
    workspace = window.creator.workspace
    workspace.client.setText("Test Client")
    workspace.invoice_date.setText("10/1/2026")
    workspace.go_services()
    workspace.invoice.add_service(datetime(2026, 9, 28), "Review file", 1.25, 250)
    workspace._rebuild_service_table()
    workspace.update_totals()
    workspace.s_desc.setText("Unfinished entry")
    workspace.s_hours.setValue(0.75)
    workspace.set_dirty(True)
    return workspace


def global_rect(widget):
    return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())


def test_new_and_legacy_settings_default_to_light_compact_without_rewriting():
    settings._cache = None
    assert settings.load_settings()["appearance"] == {"theme": "light", "easy_reading": False}
    legacy = {"version": 3, "general": {"default_rate": 350}, "custom": "preserve"}
    settings.SETTINGS_FILE.write_text(json.dumps(legacy), encoding="utf-8")
    settings._cache = None
    loaded = settings.load_settings()
    assert loaded["appearance"] == {"theme": "light", "easy_reading": False}
    assert loaded["general"]["default_rate"] == 350
    assert json.loads(settings.SETTINGS_FILE.read_text()) == legacy


@pytest.mark.parametrize("appearance", [None, [], {"theme": "system", "easy_reading": "false"}, {"theme": {}, "easy_reading": 1}])
def test_invalid_appearance_recovers_to_safe_defaults(appearance):
    data = deepcopy(settings.DEFAULTS)
    data["appearance"] = appearance
    settings.SETTINGS_FILE.write_text(json.dumps(data), encoding="utf-8")
    settings._cache = None
    assert settings.load_settings()["appearance"] == {"theme": "light", "easy_reading": False}


@pytest.mark.parametrize("mode,easy", [("light", False), ("dark", False), ("light", True), ("dark", True)])
def test_controls_apply_immediately_and_preferences_survive_reload(window, qapp, mode, easy):
    window.go_settings()
    select_appearance(window, mode, easy)
    qapp.processEvents()
    assert qapp.palette().color(QPalette.Window).name() == theme_colors(mode)["background"]
    assert qapp.property("bb_theme") == mode
    assert qapp.font().pixelSize() == (18 if easy else 14)
    assert window.settings_page.rate.font().pixelSize() == (18 if easy else 14)
    # Explicit save covers the untouched Light/compact combination too.
    window.settings_page.save()
    settings._cache = None
    assert settings.load_settings()["appearance"] == {"theme": mode, "easy_reading": easy}
    second = main.MainWindow()
    assert second.settings_page.theme.currentData() == mode
    assert second.settings_page.easy_reading.isChecked() is easy
    second.close()
    second.deleteLater()


def test_failed_appearance_write_keeps_previous_controls_palette_and_cache(window, qapp, monkeypatch):
    calls = []
    before_cache = deepcopy(settings.load_settings())
    before_sheet = qapp.styleSheet()

    def fail_save(*args):
        raise PermissionError("Synthetic settings failure")

    monkeypatch.setattr(settings, "save_settings", fail_save)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: calls.append(args))
    window.settings_page.theme.setCurrentIndex(window.settings_page.theme.findData("dark"))
    assert calls
    assert settings.load_settings() == before_cache
    assert window.settings_page.theme.currentData() == "light"
    assert qapp.styleSheet() == before_sheet


@pytest.mark.parametrize("mode,easy", [("light", False), ("dark", False), ("light", True), ("dark", True)])
def test_switch_preserves_pending_draft_ids_dirty_page_and_focus(window, qapp, mode, easy):
    workspace = fill_invoice(window)
    workspace.s_desc.setFocus()
    workspace.s_desc.setSelection(0, 10)
    qapp.processEvents()
    invoice = workspace.invoice
    before = invoice.to_dict()
    page = workspace.stack.currentWidget()
    dirty = workspace.dirty
    select_appearance(window, mode, easy)
    qapp.processEvents()
    assert workspace.invoice is invoice
    assert invoice.to_dict() == before
    assert workspace.stack.currentWidget() is page
    assert workspace.dirty == dirty
    assert workspace.s_desc.text() == "Unfinished entry"
    assert workspace.s_desc.selectedText() == "Unfinished"
    assert workspace.s_desc.hasFocus()
    assert workspace.s_hours.value() == 0.75
    assert workspace.s_table.rowHeight(0) == font_sizes(easy)["row"]


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_easy_reading_keeps_add_visible_and_shortcuts_work_in_small_window(window, qapp, mode):
    workspace = fill_invoice(window)
    select_appearance(window, mode, True)
    window.resize(1000, 700)
    qapp.processEvents()
    qapp.processEvents()
    assert global_rect(workspace.entry_scrolls[0].viewport()).contains(global_rect(workspace.s_add_button))
    assert global_rect(workspace.s_rate).bottom() < global_rect(workspace.s_add_button).top()
    QTest.keyClick(workspace.s_desc, Qt.Key_Return)
    assert len(workspace.invoice.services) == 2
    QTest.keyClick(workspace.s_desc, Qt.Key_Return, Qt.ControlModifier)
    assert workspace.stack.currentWidget() is workspace.page_costs
    QTest.keyClick(workspace.c_desc, Qt.Key_Return, Qt.ControlModifier)
    assert workspace.stack.currentWidget() is workspace.page_review
    qapp.processEvents()
    assert workspace.review_totals.isVisible()
    assert global_rect(workspace.page_review).contains(global_rect(workspace.review_totals))
    assert workspace.preview.horizontalScrollBar().maximum() == 0


def test_existing_review_and_help_recolor_and_enlarge_without_changing_text(window, qapp):
    workspace = fill_invoice(window)
    workspace.go_review()
    workspace.show_help("services")
    help_dialog = workspace.help_dialog
    preview_text = workspace.preview.toPlainText()
    help_text = help_dialog.content.toPlainText()
    before = workspace.invoice.to_dict()
    select_appearance(window, "dark", True)
    qapp.processEvents()
    assert workspace.preview.toPlainText() == preview_text
    assert help_dialog.content.toPlainText() == help_text
    assert workspace.invoice.to_dict() == before
    assert theme_colors("dark")["ink"] in workspace._preview_html()
    assert "font-size:18px" in workspace._preview_html()
    paragraph = help_dialog.content.document().begin().next()
    assert paragraph.begin().fragment().charFormat().fontPointSize() == 15
    assert theme_colors("dark")["ink"] in help_dialog.content.document().defaultStyleSheet()
    help_dialog.reject()


def test_dark_reading_number_arrows_still_accept_mouse_input(window, qapp):
    workspace = fill_invoice(window)
    select_appearance(window, "dark", True)
    qapp.processEvents()
    option = QStyleOptionSpinBox()
    workspace.s_hours.initStyleOption(option)
    up = workspace.s_hours.style().subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxUp, workspace.s_hours)
    QTest.mouseClick(workspace.s_hours, Qt.LeftButton, pos=up.center())
    assert workspace.s_hours.value() == 1


@pytest.mark.parametrize("backwards", [False, True])
def test_settings_back_returns_to_same_invoice_field_and_selection(window, qapp, backwards):
    workspace = fill_invoice(window)
    workspace.s_desc.setFocus()
    workspace.s_desc.setSelection(10, -10) if backwards else workspace.s_desc.setSelection(0, 10)
    cursor = workspace.s_desc.cursorPosition()
    qapp.processEvents()
    before = workspace.invoice.to_dict()
    QTest.mouseClick(window.settings_button, Qt.LeftButton)
    qapp.processEvents()
    assert window.stack.currentWidget() is window.settings_page
    select_appearance(window, "dark", True)
    QTest.mouseClick(window.settings_page.header.back_button, Qt.LeftButton)
    qapp.processEvents()
    assert window.stack.currentWidget() is window.creator
    assert workspace.stack.currentWidget() is workspace.page_services
    assert workspace.s_desc.hasFocus()
    assert workspace.s_desc.selectedText() == "Unfinished"
    assert workspace.s_desc.cursorPosition() == cursor
    assert workspace.invoice.to_dict() == before


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_primary_and_body_text_have_readable_contrast_and_styles_resolve(mode):
    def luminance(color):
        components = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in components]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    colors = theme_colors(mode)
    for foreground, background in (("ink", "surface"), ("muted", "background"),
                                   ("muted", "entry"), ("on_primary", "primary"),
                                   ("on_primary", "primary_hover"), ("header_ink", "background")):
        values = sorted([luminance(colors[foreground]), luminance(colors[background])])
        assert (values[1] + 0.05) / (values[0] + 0.05) >= 4.5
    for easy in (False, True):
        assert "@" not in build_stylesheet(mode, easy)
