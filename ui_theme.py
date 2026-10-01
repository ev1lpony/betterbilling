"""Shared presentation for BetterBilling's compact, keyboard-first interface."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget


INK = "#202c3e"
BLUE = "#244e81"
BACKGROUND = "#f5f7fa"
BORDER = "#dce1e8"
MUTED = "#657286"
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "ui"


STYLE_SHEET = """
QWidget {
    color: #202c3e;
    font-family: "Segoe UI";
    font-size: 14px;
}
QMainWindow, QDialog {
    background-color: #f5f7fa;
}
QWidget#AppHeader {
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #dce1e8;
}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QFrame#card {
    background-color: #ffffff;
    border: 1px solid #dce1e8;
    border-radius: 6px;
}
QFrame#entryPanel {
    background-color: #fbfcfe;
    border: 1px solid #dce1e8;
    border-radius: 6px;
}
QLabel {
    background: transparent;
    border: none;
}
QLabel[role="title"] {
    color: #202c3e;
    font-size: 25px;
    font-weight: 600;
}
QLabel[role="section"] {
    color: #202c3e;
    font-size: 17px;
    font-weight: 600;
}
QLabel[role="muted"] {
    color: #657286;
}
QLabel[role="badge"] {
    color: #244e81;
    background-color: #eaf1f9;
    border: 1px solid #d7e2ef;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
}
QLabel[state="active"] {
    color: #ffffff;
    background-color: #244e81;
    border: 1px solid #244e81;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}
QLabel[state="complete"] {
    color: #244e81;
    background-color: #eaf1f9;
    border: 1px solid #d7e2ef;
    border-radius: 6px;
    padding: 6px 10px;
}
QLabel[state="upcoming"] {
    color: #657286;
    background: transparent;
    border: 1px solid #dce1e8;
    border-radius: 6px;
    padding: 6px 10px;
}
QWidget#HelpContent {
    font-size: 16px;
}
QWidget#HelpTopics {
    font-size: 15px;
}
QPushButton {
    color: #202c3e;
    background-color: #ffffff;
    border: 1px solid #dce1e8;
    border-radius: 6px;
    min-height: 18px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #eef3f8;
    border-color: #b9c8d9;
}
QPushButton:pressed {
    background-color: #e1e9f2;
}
QPushButton:focus {
    border: 2px solid #244e81;
    padding: 6px 13px;
}
QPushButton[kind="primary"] {
    color: #ffffff;
    background-color: #244e81;
    border-color: #244e81;
}
QPushButton[kind="primary"]:hover {
    background-color: #1d426f;
    border-color: #1d426f;
}
QPushButton[kind="primary"]:pressed {
    background-color: #17365c;
    border-color: #17365c;
}
QPushButton[kind="primary"]:focus {
    border: 2px solid #102b4d;
}
QPushButton[kind="quiet"] {
    color: #657286;
    background: transparent;
    border-color: transparent;
    font-weight: 400;
}
QPushButton[kind="quiet"]:hover {
    color: #202c3e;
    background-color: #edf1f6;
}
QPushButton[kind="quiet"]:focus {
    border: 2px solid #244e81;
}
QPushButton:disabled,
QPushButton[kind="primary"]:disabled,
QPushButton[kind="quiet"]:disabled {
    color: #8b95a5;
    background-color: #eef1f5;
    border-color: #e1e5ec;
}
QLineEdit, QAbstractSpinBox, QComboBox {
    color: #202c3e;
    background-color: #ffffff;
    border: 1px solid #dce1e8;
    border-radius: 6px;
    min-height: 18px;
    padding: 7px 10px;
    selection-background-color: #244e81;
    selection-color: #ffffff;
}
QAbstractSpinBox, QComboBox {
    padding-right: 28px;
}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border: 2px solid #244e81;
    padding: 6px 9px;
}
QAbstractSpinBox:focus, QComboBox:focus {
    padding-right: 27px;
}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    color: #8b95a5;
    background-color: #f0f3f6;
    border-color: #e1e5ec;
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
    background-color: #f5f7fa;
    border-left: 1px solid #dce1e8;
    border-bottom: 1px solid #e6eaf0;
    border-top-right-radius: 6px;
    margin-top: 1px;
    margin-right: 1px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    background-color: #f5f7fa;
    border-left: 1px solid #dce1e8;
    border-bottom-right-radius: 6px;
    margin-bottom: 1px;
    margin-right: 1px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #eaf1f9;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: #dce8f5;
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
    background-color: #f5f7fa;
    border-left: 1px solid #dce1e8;
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
    color: #202c3e;
    background-color: #ffffff;
    border: 1px solid #dce1e8;
    selection-background-color: #eaf1f9;
    selection-color: #202c3e;
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
    background-color: #ffffff;
    border: 1px solid #b9c8d9;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border-color: #244e81;
}
QCheckBox::indicator:checked {
    background-color: #244e81;
    border-color: #244e81;
    image: url("@CHECK_WHITE@");
}
QCheckBox::indicator:focus {
    width: 14px;
    height: 14px;
    border: 2px solid #102b4d;
}
QCheckBox::indicator:disabled {
    background-color: #edf0f4;
    border-color: #d6dde6;
}
QCheckBox::indicator:checked:disabled {
    background-color: #aebacd;
    border-color: #aebacd;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: #8b95a5;
}
QTableView, QListView, QTreeView, QTextEdit, QPlainTextEdit {
    color: #202c3e;
    background-color: #ffffff;
    alternate-background-color: #f5f7fa;
    border: 1px solid #dce1e8;
    border-radius: 6px;
    selection-background-color: #eaf1f9;
    selection-color: #202c3e;
}
QTableView {
    gridline-color: #e6eaf0;
}
QTableView:focus, QListView:focus, QTreeView:focus,
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #244e81;
}
QTableView::item {
    padding: 5px 8px;
}
QListView::item, QTreeView::item {
    min-height: 24px;
    padding: 6px 8px;
}
QTableView::item:selected, QListView::item:selected, QTreeView::item:selected {
    color: #202c3e;
    background-color: #eaf1f9;
}
QTableView::item:focus, QListView::item:focus, QTreeView::item:focus {
    border: 1px solid #244e81;
}
QHeaderView::section {
    color: #526176;
    background-color: #f5f7fa;
    border: none;
    border-right: 1px solid #e6eaf0;
    border-bottom: 1px solid #dce1e8;
    padding: 7px 8px;
    font-size: 14px;
    font-weight: 600;
}
QTableCornerButton::section {
    background-color: #f5f7fa;
    border: none;
    border-bottom: 1px solid #dce1e8;
}
QStatusBar {
    color: #657286;
    background-color: #f5f7fa;
    border: none;
    font-size: 12px;
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
    background-color: #bdc6d3;
    border-radius: 3px;
    min-height: 26px;
    min-width: 26px;
}
QScrollBar::handle:hover {
    background-color: #9eacbf;
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
    color: #ffffff;
    background-color: #202c3e;
    border: 1px solid #202c3e;
    padding: 5px 8px;
}
"""

for placeholder, filename in (
    ("@CHECK_WHITE@", "check-white.svg"),
    ("@CARET_UP@", "caret-up.svg"),
    ("@CARET_DOWN@", "caret-down.svg"),
    ("@CARET_UP_DISABLED@", "caret-up-disabled.svg"),
    ("@CARET_DOWN_DISABLED@", "caret-down-disabled.svg"),
):
    STYLE_SHEET = STYLE_SHEET.replace(placeholder, (ASSET_DIR / filename).as_posix())


def apply_theme(app: QApplication) -> None:
    """Apply the shared palette once, including widgets created afterwards."""
    if app.property("_betterbilling_theme_applied") and app.styleSheet() == STYLE_SHEET:
        return
    app.setStyle("Fusion")
    font = QFont("Segoe UI")
    font.setPixelSize(14)
    app.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, BACKGROUND),
        (QPalette.ColorRole.WindowText, INK),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, BACKGROUND),
        (QPalette.ColorRole.Text, INK),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.ButtonText, INK),
        (QPalette.ColorRole.Highlight, BLUE),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.Link, BLUE),
        (QPalette.ColorRole.PlaceholderText, MUTED),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#8b95a5"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#f0f3f6"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE_SHEET)
    app.setProperty("_betterbilling_theme_applied", True)


def label(text: str, role: str = "body", parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setProperty("role", role)
    return widget


def button(text: str, kind: str = "secondary", parent: QWidget | None = None) -> QPushButton:
    widget = QPushButton(text, parent)
    widget.setProperty("kind", kind)
    return widget
