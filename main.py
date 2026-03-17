# main.py
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from invoice_create import InvoiceWizard
import settings


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def open_local_path(path: Path) -> None:
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Reusable header
# -----------------------------------------------------------------------------

class Header(QWidget):
    def __init__(self, title: str, on_back):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size:18px; font-weight:600;")

        back = QPushButton("⟵ Back to Dashboard")
        back.clicked.connect(on_back)

        h.addWidget(lbl, 1)
        h.addWidget(back, 0, Qt.AlignRight)


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------

class Dashboard(QWidget):
    def __init__(self, on_new, on_edit, on_manage, on_settings, on_exit):
        super().__init__()
        v = QVBoxLayout(self)

        title = QLabel("BetterBilling — Dashboard")
        title.setStyleSheet("font-size:22px; font-weight:700;")
        v.addWidget(title)

        subtitle = QLabel(
            "Portable invoice builder. PDFs, JSON invoice data, and settings stay inside this project folder."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#666;")
        v.addWidget(subtitle)
        v.addSpacing(12)

        row1 = QHBoxLayout()
        btn_new = QPushButton("➕  New Invoice")
        btn_edit = QPushButton("✏️  Edit Existing Invoice")
        btn_manage = QPushButton("🗂️  Manage Files")

        for b in (btn_new, btn_edit, btn_manage):
            b.setMinimumHeight(44)
            row1.addWidget(b)

        v.addLayout(row1)

        row2 = QHBoxLayout()
        btn_settings = QPushButton("⚙️  Settings")
        btn_exit = QPushButton("⏻  Exit")

        for b in (btn_settings, btn_exit):
            b.setMinimumHeight(44)
            row2.addWidget(b)

        row2.addStretch(1)
        v.addLayout(row2)

        v.addStretch(1)

        btn_new.clicked.connect(on_new)
        btn_edit.clicked.connect(on_edit)
        btn_manage.clicked.connect(on_manage)
        btn_settings.clicked.connect(on_settings)
        btn_exit.clicked.connect(on_exit)


# -----------------------------------------------------------------------------
# Manage files page
# -----------------------------------------------------------------------------

class ManagePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        v = QVBoxLayout(self)

        v.addWidget(Header("Manage Files", on_back))
        v.addSpacing(8)

        self.data_dir_lbl = QLabel()
        self.pdf_dir_lbl = QLabel()
        self.json_dir_lbl = QLabel()

        for lbl in (self.data_dir_lbl, self.pdf_dir_lbl, self.json_dir_lbl):
            lbl.setWordWrap(True)

        v.addWidget(QLabel("Project-local storage folders:"))
        v.addWidget(self.data_dir_lbl)
        v.addWidget(self.pdf_dir_lbl)
        v.addWidget(self.json_dir_lbl)

        v.addSpacing(8)

        row = QHBoxLayout()
        self.btn_open_data = QPushButton("Open Data Folder")
        self.btn_open_pdfs = QPushButton("Open PDFs Folder")
        self.btn_open_json = QPushButton("Open JSON Folder")
        row.addWidget(self.btn_open_data)
        row.addWidget(self.btn_open_pdfs)
        row.addWidget(self.btn_open_json)
        v.addLayout(row)

        note = QLabel(
            "Invoices are stored as JSON in the portable project folder so they can be opened and edited later. "
            "Generated PDFs are stored separately in the PDFs folder."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        v.addSpacing(8)
        v.addWidget(note)
        v.addStretch(1)

        self.btn_open_data.clicked.connect(lambda: open_local_path(settings.get_data_dir()))
        self.btn_open_pdfs.clicked.connect(lambda: open_local_path(settings.get_export_dir()))
        self.btn_open_json.clicked.connect(lambda: open_local_path(settings.get_json_dir()))

        self.refresh_labels()

    def refresh_labels(self):
        self.data_dir_lbl.setText(f"<b>Data:</b> {settings.get_data_dir(create=True)}")
        self.pdf_dir_lbl.setText(f"<b>PDFs:</b> {settings.get_export_dir(create=True)}")
        self.json_dir_lbl.setText(f"<b>JSON:</b> {settings.get_json_dir(create=True)}")


# -----------------------------------------------------------------------------
# Settings page
# -----------------------------------------------------------------------------

class SettingsPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self._guard = False

        v = QVBoxLayout(self)
        v.addWidget(Header("Settings", on_back))
        v.addSpacing(8)

        form = QFormLayout()

        self.in_default_rate = QDoubleSpinBox()
        self.in_default_rate.setDecimals(2)
        self.in_default_rate.setMinimum(0.01)
        self.in_default_rate.setMaximum(9999999.0)
        self.in_default_rate.setSingleStep(25.0)
        form.addRow("Default hourly rate:", self.in_default_rate)

        self.in_data_dir = QLineEdit()
        self.in_data_dir.setReadOnly(True)
        form.addRow("Project data folder:", self.in_data_dir)

        self.in_export_dir = QLineEdit()
        self.in_export_dir.setReadOnly(True)
        form.addRow("PDF folder:", self.in_export_dir)

        self.in_json_dir = QLineEdit()
        self.in_json_dir.setReadOnly(True)
        form.addRow("Invoice JSON folder:", self.in_json_dir)

        self.chk_explicit0 = QCheckBox("Require explicit '0' for no-charge services")
        form.addRow("", self.chk_explicit0)

        self.sel_filename_template = QComboBox()
        self.sel_filename_template.setEditable(True)
        self.sel_filename_template.addItems([
            "{client}_invoice[{date}].pdf",
            "{date}_{client}_invoice.pdf",
            "{client}-{date}.pdf",
        ])
        form.addRow("File naming template:", self.sel_filename_template)

        self.chk_thousands = QCheckBox("Use thousand separators for money")
        form.addRow("", self.chk_thousands)

        self.in_letterhead_top = QDoubleSpinBox()
        self.in_letterhead_top.setDecimals(2)
        self.in_letterhead_top.setMinimum(0.00)
        self.in_letterhead_top.setMaximum(5.00)
        self.in_letterhead_top.setSingleStep(0.25)
        form.addRow("Letterhead top margin (in):", self.in_letterhead_top)

        v.addLayout(form)
        v.addSpacing(10)

        btn_row = QHBoxLayout()
        self.btn_open_data = QPushButton("Open Data Folder")
        self.btn_reset_portable = QPushButton("Reset Portable Folders")
        btn_row.addWidget(self.btn_open_data)
        btn_row.addWidget(self.btn_reset_portable)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        note = QLabel(
            "Folder paths are locked to the project so this app stays portable on any computer or USB drive."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        v.addWidget(note)
        v.addStretch(1)

        self.load_into_controls()

        self.in_default_rate.valueChanged.connect(self._save_default_rate)
        self.chk_explicit0.toggled.connect(self._save_explicit_zero)
        self.sel_filename_template.currentTextChanged.connect(self._save_filename_template)
        self.chk_thousands.toggled.connect(self._save_thousands)
        self.in_letterhead_top.valueChanged.connect(self._save_letterhead_top)

        self.btn_open_data.clicked.connect(lambda: open_local_path(settings.get_data_dir()))
        self.btn_reset_portable.clicked.connect(self._reset_portable_folders)

    def load_into_controls(self):
        self._guard = True
        try:
            self.in_default_rate.setValue(float(settings.get("general.default_rate", 250.0)))
            self.in_data_dir.setText(str(settings.get_data_dir(create=True)))
            self.in_export_dir.setText(str(settings.get_export_dir(create=True)))
            self.in_json_dir.setText(str(settings.get_json_dir(create=True)))

            self.chk_explicit0.setChecked(bool(settings.get("invoice.require_explicit_zero_hours", True)))

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
        if self._guard:
            return
        settings.set_("general.default_rate", float(self.in_default_rate.value()))

    def _save_explicit_zero(self):
        if self._guard:
            return
        settings.set_("invoice.require_explicit_zero_hours", bool(self.chk_explicit0.isChecked()))

    def _save_filename_template(self):
        if self._guard:
            return
        settings.set_("pdf.file_naming_template", self.sel_filename_template.currentText())

    def _save_thousands(self):
        if self._guard:
            return
        settings.set_("pdf.thousand_separators", bool(self.chk_thousands.isChecked()))

    def _save_letterhead_top(self):
        if self._guard:
            return
        settings.set_("letterhead.top_margin_in", float(self.in_letterhead_top.value()))

    def _reset_portable_folders(self):
        try:
            data_dir = settings.PROJECT_ROOT / "data"
            pdf_dir = data_dir / "pdfs"
            json_dir = data_dir / "json"
            letterheads_dir = data_dir / "letterheads"

            settings.set_("general.data_dir", str(data_dir))
            settings.set_("general.default_export_dir", str(pdf_dir))
            settings.set_("general.default_json_dir", str(json_dir))
            settings.set_("letterhead.library_dir", str(letterheads_dir))

            self.load_into_controls()
            QMessageBox.information(
                self,
                "Portable folders reset",
                "Project-local folders were reset successfully.",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to reset portable folders:\n{e}",
            )


# -----------------------------------------------------------------------------
# Editor/creator page
# -----------------------------------------------------------------------------

class CreatorPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(Header("Invoice Workspace", on_back))

        self.wizard = InvoiceWizard()
        self.wizard.setWindowFlags(Qt.Widget)
        self.wizard.setParent(self)
        self.wizard.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self.wizard)

    def start_new_invoice(self):
        self.wizard.start_new_invoice()

    def start_edit_existing(self):
        self.wizard.go_to_open_page()


# -----------------------------------------------------------------------------
# Main shell
# -----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BetterBilling")
        self.resize(1180, 760)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.page_dashboard = Dashboard(
            on_new=self._go_new_invoice,
            on_edit=self._go_edit_invoice,
            on_manage=self._go_manage,
            on_settings=self._go_settings,
            on_exit=self.close,
        )
        self.page_creator = CreatorPage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))
        self.page_manage = ManagePage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))
        self.page_settings = SettingsPage(on_back=lambda: self.stack.setCurrentWidget(self.page_dashboard))

        for p in (self.page_dashboard, self.page_creator, self.page_manage, self.page_settings):
            self.stack.addWidget(p)

        self.stack.setCurrentWidget(self.page_dashboard)

    def _go_new_invoice(self):
        self.page_creator.start_new_invoice()
        self.stack.setCurrentWidget(self.page_creator)

    def _go_edit_invoice(self):
        self.page_creator.start_edit_existing()
        self.stack.setCurrentWidget(self.page_creator)

    def _go_manage(self):
        self.page_manage.refresh_labels()
        self.stack.setCurrentWidget(self.page_manage)

    def _go_settings(self):
        self.page_settings.load_into_controls()
        self.stack.setCurrentWidget(self.page_settings)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()