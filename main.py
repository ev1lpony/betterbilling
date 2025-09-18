# main.py
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFormLayout, QLineEdit,
    QDoubleSpinBox, QCheckBox, QFileDialog, QComboBox
)

# Modules
from invoice_create import InvoiceWizard
import settings


# ---------- Reusable header with Back ----------
class Header(QWidget):
    def __init__(self, title: str, on_back):
        super().__init__()
        h = QHBoxLayout(self)
        lbl = QLabel(title)
        lbl.setStyleSheet("font-size:18px; font-weight:600;")
        back = QPushButton("⟵ Back to Dashboard")
        back.clicked.connect(on_back)
        h.addWidget(lbl, 1)
        h.addWidget(back, 0, Qt.AlignRight)


# ---------- Dashboard ----------
class Dashboard(QWidget):
    def __init__(self, on_new, on_manage, on_settings, on_exit):
        super().__init__()
        v = QVBoxLayout(self)

        title = QLabel("BetterBilling — Dashboard")
        title.setStyleSheet("font-size:22px; font-weight:700;")
        v.addWidget(title)
        v.addSpacing(12)

        row = QHBoxLayout()
        btn_new = QPushButton("➕  New Invoice")
        btn_manage = QPushButton("🗂️  Manage Invoices")
        btn_settings = QPushButton("⚙️  Settings")
        btn_exit = QPushButton("⏻  Exit")
        for b in (btn_new, btn_manage, btn_settings, btn_exit):
            b.setMinimumHeight(44)
            row.addWidget(b)
        v.addLayout(row)
        v.addStretch(1)

        btn_new.clicked.connect(on_new)
        btn_manage.clicked.connect(on_manage)
        btn_settings.clicked.connect(on_settings)
        btn_exit.clicked.connect(on_exit)


# ---------- Manage placeholder (kept minimal) ----------
class ManagePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        v = QVBoxLayout(self)
        v.addWidget(Header("Manage Invoices", on_back))
        v.addSpacing(8)
        v.addWidget(QLabel("Placeholder: list/search invoices will land here after SQLite."))
        v.addStretch(1)


# ---------- Settings page (reads/writes settings.py) ----------
class SettingsPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self._guard = False  # suppress feedback loops while initializing

        v = QVBoxLayout(self)
        v.addWidget(Header("Settings", on_back))
        v.addSpacing(8)

        form = QFormLayout()
        # General: default rate
        self.in_default_rate = QDoubleSpinBox()
        self.in_default_rate.setDecimals(2)
        self.in_default_rate.setMinimum(0.01)
        self.in_default_rate.setMaximum(9999999.0)
        self.in_default_rate.setSingleStep(25.0)
        form.addRow("Default hourly rate:", self.in_default_rate)

        # General: export folder
        h = QHBoxLayout()
        self.in_export_dir = QLineEdit()
        self.in_export_dir.setReadOnly(True)
        btn_pick = QPushButton("Choose…")
        h.addWidget(self.in_export_dir, 1)
        h.addWidget(btn_pick)
        form.addRow("Export folder:", h)

        # Invoice: require explicit 0 hours
        self.chk_explicit0 = QCheckBox("Require explicit '0' for no-charge services")
        form.addRow("", self.chk_explicit0)

        # PDF: filename template
        self.sel_filename_template = QComboBox()
        # Provide your default and a couple of safe alternatives
        self.sel_filename_template.addItems([
            "{client}_invoice[{date}].pdf",            # your current default
            "{date}_{client}_invoice.pdf",
            "{client}-{date}.pdf"
        ])
        form.addRow("File naming template:", self.sel_filename_template)

        # PDF: thousand separators (money only)
        self.chk_thousands = QCheckBox("Use thousand separators for money")
        form.addRow("", self.chk_thousands)

        # Letterhead: top margin (inches)
        self.in_letterhead_top = QDoubleSpinBox()
        self.in_letterhead_top.setDecimals(2)
        self.in_letterhead_top.setMinimum(0.00)
        self.in_letterhead_top.setMaximum(5.00)
        self.in_letterhead_top.setSingleStep(0.25)
        form.addRow("Letterhead top margin (in):", self.in_letterhead_top)

        v.addLayout(form)
        v.addStretch(1)

        # Load current settings into controls
        self.load_into_controls()

        # Wire events (save immediately)
        self.in_default_rate.valueChanged.connect(self._save_default_rate)
        btn_pick.clicked.connect(self._pick_export_dir)
        self.chk_explicit0.toggled.connect(self._save_explicit_zero)
        self.sel_filename_template.currentTextChanged.connect(self._save_filename_template)
        self.chk_thousands.toggled.connect(self._save_thousands)
        self.in_letterhead_top.valueChanged.connect(self._save_letterhead_top)

    # ---- load/save helpers ----
    def load_into_controls(self):
        self._guard = True
        try:
            self.in_default_rate.setValue(float(settings.get("general.default_rate", 250.0)))
            self.in_export_dir.setText(str(settings.get("general.default_export_dir", "")))
            self.chk_explicit0.setChecked(bool(settings.get("invoice.require_explicit_zero_hours", True)))
            # filename template: try match one of the options, else insert custom
            current_tpl = str(settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf"))
            idx = self.sel_filename_template.findText(current_tpl)
            if idx == -1:
                self.sel_filename_template.insertItem(0, current_tpl)
                idx = 0
            self.sel_filename_template.setCurrentIndex(idx)
            self.chk_thousands.setChecked(bool(settings.get("pdf.thousand_separators", True)))
            self.in_letterhead_top.setValue(float(settings.get("letterhead.top_margin_in", 2.5)))
        finally:
            self._guard = False

    def _save_default_rate(self):
        if self._guard: return
        settings.set_("general.default_rate", float(self.in_default_rate.value()))

    def _pick_export_dir(self):
        start = self.in_export_dir.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose export folder", start)
        if not chosen:
            return
        self.in_export_dir.setText(chosen)
        settings.set_("general.default_export_dir", chosen)

    def _save_explicit_zero(self):
        if self._guard: return
        settings.set_("invoice.require_explicit_zero_hours", bool(self.chk_explicit0.isChecked()))

    def _save_filename_template(self):
        if self._guard: return
        settings.set_("pdf.file_naming_template", self.sel_filename_template.currentText())

    def _save_thousands(self):
        if self._guard: return
        settings.set_("pdf.thousand_separators", bool(self.chk_thousands.isChecked()))

    def _save_letterhead_top(self):
        if self._guard: return
        settings.set_("letterhead.top_margin_in", float(self.in_letterhead_top.value()))


# ---------- Creator embedded ----------
class CreatorPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(Header("Create Invoice", on_back))

        # Create and embed the existing wizard
        self.wizard = InvoiceWizard()
        self.wizard.setWindowFlags(Qt.Widget)
        self.wizard.setParent(self)
        self.wizard.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self.wizard)


# ---------- Shell ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BetterBilling")
        self.resize(1100, 720)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.page_dashboard = Dashboard(
            on_new=lambda: self.stack.setCurrentWidget(self.page_creator),
            on_manage=lambda: self.stack.setCurrentWidget(self.page_manage),
            on_settings=lambda: self.stack.setCurrentWidget(self.page_settings),
            on_exit=self.close,
        )
        self.page_creator = CreatorPage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))
        self.page_manage = ManagePage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))
        self.page_settings = SettingsPage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))

        for p in (self.page_dashboard, self.page_creator, self.page_manage, self.page_settings):
            self.stack.addWidget(p)

        # Launch behavior: always dashboard (per your rule)
        self.stack.setCurrentWidget(self.page_dashboard)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
