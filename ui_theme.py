"""Shared presentation for BetterBilling's compact, keyboard-first interface."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

import settings


INK = "#202c3e"
BLUE = "#244e81"
BACKGROUND = "#f5f7fa"
BORDER = "#dce1e8"
MUTED = "#657286"
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "ui"


_STYLE_TEMPLATE = """
QWidget {
    color: @ink@;
    font-family: "Segoe UI";
    font-size: @body@px;
}
QMainWindow, QDialog {
    background-color: @background@;
}
QWidget#AppHeader {
    background-color: @surface@;
    border: none;
    border-bottom: 1px solid @border@;
}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QFrame#card {
    background-color: @surface@;
    border: 1px solid @border@;
    border-radius: 6px;
}
QFrame#entryPanel {
    background-color: @entry@;
    border: 1px solid @border@;
    border-radius: 6px;
}
QLabel {
    background: transparent;
    border: none;
}
QLabel[role="title"] {
    color: @ink@;
    font-size: @title@px;
    font-weight: 600;
}
QLabel[role="section"] {
    color: @ink@;
    font-size: @section@px;
    font-weight: 600;
}
QLabel[role="muted"] {
    color: @muted@;
}
QLabel[role="badge"] {
    color: @accent@;
    background-color: @selection@;
    border: 1px solid @selection_border@;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: @small@px;
    font-weight: 600;
}
QLabel[state="active"] {
    color: @on_primary@;
    background-color: @primary@;
    border: 1px solid @primary@;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}
QLabel[state="complete"] {
    color: @accent@;
    background-color: @selection@;
    border: 1px solid @selection_border@;
    border-radius: 6px;
    padding: 6px 10px;
}
QLabel[state="upcoming"] {
    color: @muted@;
    background: transparent;
    border: 1px solid @border@;
    border-radius: 6px;
    padding: 6px 10px;
}
QWidget#HelpContent {
    font-size: @help_body@px;
}
QWidget#HelpTopics {
    font-size: @help_topics@px;
}
QPushButton {
    color: @ink@;
    background-color: @surface@;
    border: 1px solid @border@;
    border-radius: 6px;
    min-height: 18px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: @hover@;
    border-color: @control_border@;
}
QPushButton:pressed {
    background-color: @pressed@;
}
QPushButton:focus {
    border: 2px solid @focus@;
    padding: 6px 13px;
}
QPushButton[kind="primary"] {
    color: @on_primary@;
    background-color: @primary@;
    border-color: @primary@;
}
QPushButton[kind="primary"]:hover {
    background-color: @primary_hover@;
    border-color: @primary_hover@;
}
QPushButton[kind="primary"]:pressed {
    background-color: @primary_pressed@;
    border-color: @primary_pressed@;
}
QPushButton[kind="primary"]:focus {
    border: 2px solid @focus_strong@;
}
QPushButton[kind="quiet"] {
    color: @muted@;
    background: transparent;
    border-color: transparent;
    font-weight: 400;
}
QPushButton[kind="quiet"]:hover {
    color: @ink@;
    background-color: @review_header@;
}
QPushButton[kind="quiet"]:focus {
    border: 2px solid @focus@;
}
QPushButton:disabled,
QPushButton[kind="primary"]:disabled,
QPushButton[kind="quiet"]:disabled {
    color: @disabled_ink@;
    background-color: @disabled_background@;
    border-color: @disabled_border@;
}
QLineEdit, QAbstractSpinBox, QComboBox {
    color: @ink@;
    background-color: @surface@;
    border: 1px solid @border@;
    border-radius: 6px;
    min-height: 18px;
    padding: 7px 10px;
    selection-background-color: @primary@;
    selection-color: @on_primary@;
}
QAbstractSpinBox, QComboBox {
    padding-right: 28px;
}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border: 2px solid @focus@;
    padding: 6px 9px;
}
QAbstractSpinBox:focus, QComboBox:focus {
    padding-right: 27px;
}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    color: @disabled_ink@;
    background-color: @disabled_field@;
    border-color: @disabled_border@;
}
QAbstractSpinBox QLineEdit {
    background: transparent;
    border: none;
    padding: 0;
    min-height: 0;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    background-color: @background@;
    border-left: 1px solid @border@;
    border-bottom: 1px solid @separator@;
    border-top-right-radius: 6px;
    margin-top: 1px;
    margin-right: 1px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    background-color: @background@;
    border-left: 1px solid @border@;
    border-bottom-right-radius: 6px;
    margin-bottom: 1px;
    margin-right: 1px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: @selection@;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: @control_pressed@;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("@CARET_UP@");
    width: 12px;
    height: 8px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("@CARET_DOWN@");
    width: 12px;
    height: 8px;
}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {
    image: url("@CARET_UP_DISABLED@");
}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {
    image: url("@CARET_DOWN_DISABLED@");
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    background-color: @background@;
    border-left: 1px solid @border@;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    margin: 1px;
}
QComboBox::down-arrow {
    image: url("@CARET_DOWN@");
    width: 12px;
    height: 8px;
}
QComboBox::down-arrow:disabled {
    image: url("@CARET_DOWN_DISABLED@");
}
QComboBox QAbstractItemView {
    color: @ink@;
    background-color: @surface@;
    border: 1px solid @border@;
    selection-background-color: @selection@;
    selection-color: @ink@;
    padding: 4px;
}
QCheckBox, QRadioButton {
    background: transparent;
    spacing: 7px;
    padding: 3px 0;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background-color: @surface@;
    border: 1px solid @control_border@;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border-color: @focus@;
}
QCheckBox::indicator:checked {
    background-color: @primary@;
    border-color: @primary@;
    image: url("@CHECK_WHITE@");
}
QCheckBox::indicator:focus {
    width: 14px;
    height: 14px;
    border: 2px solid @focus_strong@;
}
QCheckBox::indicator:disabled {
    background-color: @disabled_background@;
    border-color: @disabled_border@;
}
QCheckBox::indicator:checked:disabled {
    background-color: @disabled_check@;
    border-color: @disabled_check@;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: @disabled_ink@;
}
QTableView, QListView, QTreeView, QTextEdit, QPlainTextEdit {
    color: @ink@;
    background-color: @surface@;
    alternate-background-color: @background@;
    border: 1px solid @border@;
    border-radius: 6px;
    selection-background-color: @selection@;
    selection-color: @ink@;
}
QTableView {
    gridline-color: @separator@;
}
QTableView:focus, QListView:focus, QTreeView:focus,
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: @focus@;
}
QTableView::item {
    padding: 5px 8px;
}
QListView::item, QTreeView::item {
    min-height: 24px;
    padding: 6px 8px;
}
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected {
    color: @ink@;
    background-color: @selection@;
}
QTableView::item:focus, QListView::item:focus, QTreeView::item:focus {
    border: 1px solid @focus@;
}
QHeaderView::section {
    color: @header_ink@;
    background-color: @background@;
    border: none;
    border-right: 1px solid @separator@;
    border-bottom: 1px solid @border@;
    padding: 7px 8px;
    font-size: @body@px;
    font-weight: 600;
}
QTableCornerButton::section {
    background-color: @background@;
    border: none;
    border-bottom: 1px solid @border@;
}
QStatusBar {
    color: @muted@;
    background-color: @background@;
    border: none;
    font-size: @small@px;
}
QStatusBar::item {
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 2px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: @scroll@;
    border-radius: 3px;
    min-height: 26px;
    min-width: 26px;
}
QScrollBar::handle:hover {
    background-color: @scroll_hover@;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QToolTip {
    color: @tooltip_ink@;
    background-color: @tooltip_background@;
    border: 1px solid @tooltip_background@;
    padding: 5px 8px;
}
"""

LIGHT_COLORS = {
    "ink": "#202c3e", "background": "#f5f7fa", "surface": "#ffffff",
    "entry": "#fbfcfe", "border": "#dce1e8", "muted": "#657286",
    "accent": "#244e81", "primary": "#244e81", "on_primary": "#ffffff",
    "primary_hover": "#1d426f", "primary_pressed": "#17365c",
    "focus": "#244e81", "focus_strong": "#102b4d",
    "selection": "#eaf1f9", "selection_border": "#d7e2ef",
    "hover": "#eef3f8", "control_border": "#b9c8d9", "pressed": "#e1e9f2",
    "review_header": "#edf1f6", "header_ink": "#526176",
    "disabled_ink": "#8b95a5", "disabled_background": "#eef1f5",
    "disabled_border": "#e1e5ec", "disabled_field": "#f0f3f6",
    "separator": "#e6eaf0", "control_pressed": "#dce8f5",
    "disabled_check": "#aebacd", "scroll": "#bdc6d3", "scroll_hover": "#9eacbf",
    "tooltip_ink": "#ffffff", "tooltip_background": "#202c3e",
}
DARK_COLORS = {
    "ink": "#e6edf7", "background": "#141b25", "surface": "#1d2734",
    "entry": "#202c3a", "border": "#3b4b61", "muted": "#aab8cc",
    "accent": "#bed6f6", "primary": "#315b8f", "on_primary": "#ffffff",
    "primary_hover": "#3e6b9f", "primary_pressed": "#294e7d",
    "focus": "#9ac3f5", "focus_strong": "#b0d0f8",
    "selection": "#263e59", "selection_border": "#456386",
    "hover": "#28374a", "control_border": "#7189aa", "pressed": "#33475f",
    "review_header": "#293c52", "header_ink": "#bfccdf",
    "disabled_ink": "#90a0b5", "disabled_background": "#242f3e",
    "disabled_border": "#435068", "disabled_field": "#273241",
    "separator": "#3d4e66", "control_pressed": "#334b68",
    "disabled_check": "#566c89", "scroll": "#657a98", "scroll_hover": "#8297b5",
    "tooltip_ink": "#172131", "tooltip_background": "#e6edf7",
}


class AppearanceManager(QObject):
    changed = Signal()


def appearance_manager(app: QApplication | None = None) -> AppearanceManager:
    app = app or QApplication.instance()
    if not hasattr(app, "_billing_appearance_manager"):
        app._billing_appearance_manager = AppearanceManager(app)
    return app._billing_appearance_manager


def appearance() -> tuple[str, bool]:
    app = QApplication.instance()
    if app is not None and app.property("bb_theme") is not None:
        return app.property("bb_theme"), bool(app.property("bb_easy_reading"))
    return settings.get("appearance.theme", "light"), settings.get("appearance.easy_reading", False)


def theme_colors(mode: str | None = None) -> dict[str, str]:
    mode = mode or appearance()[0]
    return (DARK_COLORS if mode == "dark" else LIGHT_COLORS).copy()


def font_sizes(easy_reading: bool | None = None) -> dict[str, int]:
    easy = appearance()[1] if easy_reading is None else easy_reading
    return {"body": 18 if easy else 14, "title": 29 if easy else 25,
            "section": 21 if easy else 17, "small": 16 if easy else 12,
            "help_body": 20 if easy else 16, "help_topics": 18 if easy else 15,
            "row": 44 if easy else 36, "brand": 26 if easy else 22}


def build_stylesheet(mode: str = "light", easy_reading: bool = False) -> str:
    tokens = {**theme_colors(mode), **font_sizes(easy_reading)}
    tokens.update({
        "CHECK_WHITE": (ASSET_DIR / "check-white.svg").as_posix(),
        "CARET_UP": (ASSET_DIR / ("caret-up-dark.svg" if mode == "dark" else "caret-up.svg")).as_posix(),
        "CARET_DOWN": (ASSET_DIR / ("caret-down-dark.svg" if mode == "dark" else "caret-down.svg")).as_posix(),
        "CARET_UP_DISABLED": (ASSET_DIR / "caret-up-disabled.svg").as_posix(),
        "CARET_DOWN_DISABLED": (ASSET_DIR / "caret-down-disabled.svg").as_posix(),
    })
    sheet = _STYLE_TEMPLATE
    for token, value in tokens.items():
        sheet = sheet.replace(f"@{token}@", str(value))
    return sheet


# Retain the default stylesheet for consumers that only need the light design.
STYLE_SHEET = build_stylesheet()


def apply_theme(app: QApplication, mode: str | None = None, easy_reading: bool | None = None) -> None:
    """Apply saved appearance immediately, preserving widgets and invoice state."""
    mode = mode if mode is not None else settings.get("appearance.theme", "light")
    mode = mode if mode in ("light", "dark") else "light"
    easy = easy_reading if easy_reading is not None else settings.get("appearance.easy_reading", False)
    sheet = build_stylesheet(mode, easy)
    if app.styleSheet() == sheet and app.property("bb_theme") == mode and app.property("bb_easy_reading") == easy:
        return
    if not app.property("_betterbilling_theme_applied"):
        app.setStyle("Fusion")
    colors = theme_colors(mode)
    font = QFont("Segoe UI")
    font.setPixelSize(font_sizes(easy)["body"])
    app.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, colors["background"]),
        (QPalette.ColorRole.WindowText, colors["ink"]),
        (QPalette.ColorRole.Base, colors["surface"]),
        (QPalette.ColorRole.AlternateBase, colors["background"]),
        (QPalette.ColorRole.Text, colors["ink"]),
        (QPalette.ColorRole.Button, colors["surface"]),
        (QPalette.ColorRole.ButtonText, colors["ink"]),
        (QPalette.ColorRole.Highlight, colors["primary"]),
        (QPalette.ColorRole.HighlightedText, colors["on_primary"]),
        (QPalette.ColorRole.Link, colors["accent"]),
        (QPalette.ColorRole.PlaceholderText, colors["muted"]),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled_ink"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(colors["disabled_field"]))
    app.setProperty("bb_theme", mode)
    app.setProperty("bb_easy_reading", easy)
    app.setPalette(palette)
    app.setStyleSheet(sheet)
    app.setProperty("_betterbilling_theme_applied", True)
    appearance_manager(app).changed.emit()


def label(text: str, role: str = "body", parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setProperty("role", role)
    return widget


def button(text: str, kind: str = "secondary", parent: QWidget | None = None) -> QPushButton:
    widget = QPushButton(text, parent)
    widget.setProperty("kind", kind)
    return widget
