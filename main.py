from __future__ import annotations

import io
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import settings
from models import (
    CostItem,
    Invoice,
    LineItem,
    format_date_full,
    format_date_short,
    normalize_desc,
    parse_user_date,
)
from pdf_gen import generate_pdf, money
from storage import (
    base_paths,
    list_invoice_json_files,
    load_invoice_json,
    paired_unique_paths,
    render_filename,
    save_invoice_json,
)


def open_local_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
    except Exception:
        pass


class Header(QWidget):
    def __init__(self, title: str, on_back):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setStyleSheet("font-size:18px; font-weight:600;")
        back = QPushButton("⟵ Back to Dashboard")
        back.clicked.connect(on_back)
        row.addWidget(label, 1)
        row.addWidget(back)


class Dashboard(QWidget):
    def __init__(self, on_new, on_edit, on_manage, on_settings, on_exit):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("BetterBilling")
        title.setStyleSheet("font-size:24px; font-weight:700;")
        subtitle = QLabel(
            "Fast, portable invoice creation. Built from the recovered Wallace-era workflow."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#666;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        row = QHBoxLayout()
        new_btn = QPushButton("➕ New Invoice")
        edit_btn = QPushButton("✏ Edit Existing")
        manage_btn = QPushButton("🗂 Manage Files")
        for btn in (new_btn, edit_btn, manage_btn):
            btn.setMinimumHeight(44)
            row.addWidget(btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        settings_btn = QPushButton("⚙ Settings")
        exit_btn = QPushButton("⏻ Exit")
        for btn in (settings_btn, exit_btn):
            btn.setMinimumHeight(44)
            row2.addWidget(btn)
        row2.addStretch(1)
        layout.addLayout(row2)
        layout.addStretch(1)

        new_btn.clicked.connect(on_new)
        edit_btn.clicked.connect(on_edit)
        manage_btn.clicked.connect(on_manage)
        settings_btn.clicked.connect(on_settings)
        exit_btn.clicked.connect(on_exit)


class ManagePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(Header("Manage Files", on_back))

        self.data_label = QLabel()
        self.pdf_label = QLabel()
        self.json_label = QLabel()
        for label in (self.data_label, self.pdf_label, self.json_label):
            label.setWordWrap(True)
            layout.addWidget(label)

        row = QHBoxLayout()
        data_btn = QPushButton("Open Data Folder")
        pdf_btn = QPushButton("Open PDFs")
        json_btn = QPushButton("Open Invoice JSON")
        row.addWidget(data_btn)
        row.addWidget(pdf_btn)
        row.addWidget(json_btn)
        layout.addLayout(row)
        layout.addStretch(1)

        data_btn.clicked.connect(lambda: open_local_path(settings.get_data_dir()))
        pdf_btn.clicked.connect(lambda: open_local_path(settings.get_export_dir()))
        json_btn.clicked.connect(lambda: open_local_path(settings.get_json_dir()))
        self.refresh()

    def refresh(self):
        self.data_label.setText(f"<b>Data:</b> {settings.get_data_dir()}")
        self.pdf_label.setText(f"<b>PDFs:</b> {settings.get_export_dir()}")
        self.json_label.setText(f"<b>JSON:</b> {settings.get_json_dir()}")


class SettingsPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self.guard = False
        layout = QVBoxLayout(self)
        layout.addWidget(Header("Settings", on_back))

        form = QFormLayout()
        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(2)
        self.rate.setRange(0.01, 9_999_999)
        self.rate.setSingleStep(25.0)

        self.explicit_zero = QCheckBox("Require explicit 0 for no-charge services")
        self.review_dedupe = QCheckBox("Remove exact duplicate services before review")
        self.thousands = QCheckBox("Use thousand separators")
        self.show_hours = QCheckBox("Show TOTAL HOURS BILLED on PDF")

        self.filename = QComboBox()
        self.filename.setEditable(True)
        self.filename.addItems(
            [
                "{client}_invoice[{date}].pdf",
                "{date}_{client}_invoice.pdf",
                "{client}-{date}.pdf",
            ]
        )

        self.letterhead = QDoubleSpinBox()
        self.letterhead.setDecimals(2)
        self.letterhead.setRange(0.0, 5.0)
        self.letterhead.setSingleStep(0.25)

        form.addRow("Default hourly rate:", self.rate)
        form.addRow("", self.explicit_zero)
        form.addRow("", self.review_dedupe)
        form.addRow("", self.thousands)
        form.addRow("", self.show_hours)
        form.addRow("PDF filename template:", self.filename)
        form.addRow("Letterhead top margin (in):", self.letterhead)
        layout.addLayout(form)

        note = QLabel(
            "Storage is intentionally project-local so the whole app can live on a USB drive or be copied to another PC."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)
        layout.addStretch(1)

        self.rate.valueChanged.connect(self.save)
        self.explicit_zero.toggled.connect(self.save)
        self.review_dedupe.toggled.connect(self.save)
        self.thousands.toggled.connect(self.save)
        self.show_hours.toggled.connect(self.save)
        self.filename.currentTextChanged.connect(self.save)
        self.letterhead.valueChanged.connect(self.save)

        self.load()

    def load(self):
        self.guard = True
        try:
            self.rate.setValue(float(settings.get("general.default_rate", 250.0)))
            self.explicit_zero.setChecked(
                bool(settings.get("invoice.require_explicit_zero_hours", True))
            )
            self.review_dedupe.setChecked(
                bool(settings.get("invoice.review_dedupe", True))
            )
            self.thousands.setChecked(
                bool(settings.get("pdf.thousand_separators", True))
            )
            self.show_hours.setChecked(
                bool(settings.get("pdf.show_total_hours", True))
            )
            template = str(
                settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf")
            )
            index = self.filename.findText(template)
            if index < 0:
                self.filename.insertItem(0, template)
                index = 0
            self.filename.setCurrentIndex(index)
            self.letterhead.setValue(
                float(settings.get("letterhead.top_margin_in", 2.5))
            )
        finally:
            self.guard = False

    def save(self, *_):
        if self.guard:
            return
        settings.set_("general.default_rate", float(self.rate.value()))
        settings.set_(
            "invoice.require_explicit_zero_hours",
            bool(self.explicit_zero.isChecked()),
        )
        settings.set_("invoice.review_dedupe", bool(self.review_dedupe.isChecked()))
        settings.set_("pdf.thousand_separators", bool(self.thousands.isChecked()))
        settings.set_("pdf.show_total_hours", bool(self.show_hours.isChecked()))
        settings.set_("pdf.file_naming_template", self.filename.currentText())
        settings.set_("letterhead.top_margin_in", float(self.letterhead.value()))


class InvoiceWorkspace(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BetterBilling — Invoice Workspace")
        self.setMinimumWidth(1000)

        self.invoice: Invoice | None = None
        self.current_json_path: Path | None = None
        self.current_pdf_path: Path | None = None
        self.edit_mode = False
        self.dirty = False

        self._service_guard = False
        self._cost_guard = False
        self._hours_dirty = False

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self._build_open_page()
        self._build_meta_page()
        self._build_services_page()
        self._build_costs_page()
        self._build_review_page()

        self.start_new_invoice()

    # ------------------------------------------------------------------
    # Build pages
    # ------------------------------------------------------------------

    def _build_open_page(self):
        self.page_open = QWidget()
        self.stack.addWidget(self.page_open)
        layout = QVBoxLayout(self.page_open)
        title = QLabel("▶ Edit Existing Invoice")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        layout.addWidget(title)

        self.invoice_list = QListWidget()
        layout.addWidget(self.invoice_list)

        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        open_folder = QPushButton("Open JSON Folder")
        new_btn = QPushButton("New Invoice Instead")
        open_btn = QPushButton("Open Selected")
        row.addWidget(refresh)
        row.addWidget(open_folder)
        row.addStretch(1)
        row.addWidget(new_btn)
        row.addWidget(open_btn)
        layout.addLayout(row)

        refresh.clicked.connect(self.refresh_invoice_list)
        open_folder.clicked.connect(lambda: open_local_path(settings.get_json_dir()))
        new_btn.clicked.connect(self.start_new_invoice)
        open_btn.clicked.connect(self.open_selected)
        self.invoice_list.itemDoubleClicked.connect(lambda _: self.open_selected())

    def _build_meta_page(self):
        self.page_meta = QWidget()
        self.stack.addWidget(self.page_meta)
        layout = QVBoxLayout(self.page_meta)

        title = QLabel("▶ Invoice Meta")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        layout.addWidget(title)

        self.mode_label = QLabel()
        self.mode_label.setStyleSheet("color:#666;")
        layout.addWidget(self.mode_label)

        form = QFormLayout()
        self.client = QLineEdit()
        self.invoice_date = QLineEdit()
        self.invoice_date.setPlaceholderText("M/D, M/D/YY, or M/D/YYYY")

        self.default_rate = QDoubleSpinBox()
        self.default_rate.setDecimals(2)
        self.default_rate.setRange(0.01, 9_999_999)
        self.default_rate.setSingleStep(25.0)

        self.rate_behavior = QComboBox()
        self.rate_behavior.addItems(
            [
                "Keep existing service rates",
                "Apply default rate to every service",
            ]
        )

        self.flat_fee = QCheckBox("Flat service fee")
        self.flat_desc = QLineEdit()
        self.flat_desc.setPlaceholderText("e.g. Attorney Fees")
        self.flat_amount = QDoubleSpinBox()
        self.flat_amount.setDecimals(2)
        self.flat_amount.setRange(0.0, 9_999_999)
        self.flat_amount.setSingleStep(50.0)

        form.addRow("Client's Name:", self.client)
        form.addRow("Invoice Date:", self.invoice_date)
        form.addRow("Default hourly rate:", self.default_rate)
        form.addRow("Rate behavior:", self.rate_behavior)
        form.addRow("", self.flat_fee)
        form.addRow("Flat fee description:", self.flat_desc)
        form.addRow("Flat fee amount:", self.flat_amount)
        layout.addLayout(form)

        row = QHBoxLayout()
        open_existing = QPushButton("← Open Existing")
        next_btn = QPushButton("Next →")
        row.addWidget(open_existing)
        row.addStretch(1)
        row.addWidget(next_btn)
        layout.addLayout(row)

        self.flat_fee.toggled.connect(self._toggle_flat_fee)
        open_existing.clicked.connect(self.go_open_page)
        next_btn.clicked.connect(self.go_services)
        self.client.returnPressed.connect(self.go_services)
        self.invoice_date.returnPressed.connect(self.go_services)
        self.default_rate.lineEdit().returnPressed.connect(self.go_services)

    def _build_services_page(self):
        self.page_services = QWidget()
        self.stack.addWidget(self.page_services)
        layout = QVBoxLayout(self.page_services)

        title = QLabel("▶ Services")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        layout.addWidget(title)

        box = QGroupBox("Add service")
        form = QFormLayout(box)
        self.s_desc = QLineEdit()
        self.s_date = QLineEdit()
        self.s_hours = QDoubleSpinBox()
        self.s_hours.setDecimals(2)
        self.s_hours.setRange(0.0, 10_000.0)
        self.s_hours.setSingleStep(0.25)
        self.s_rate = QDoubleSpinBox()
        self.s_rate.setDecimals(2)
        self.s_rate.setRange(0.0, 9_999_999)
        self.s_rate.setSingleStep(25.0)

        form.addRow("Service desc:", self.s_desc)
        form.addRow("Date:", self.s_date)
        form.addRow("Hours:", self.s_hours)
        form.addRow("Rate:", self.s_rate)

        buttons = QHBoxLayout()
        add = QPushButton("Add Service (Enter)")
        clear = QPushButton("Clear")
        buttons.addWidget(add)
        buttons.addWidget(clear)
        form.addRow(buttons)
        layout.addWidget(box)

        self.s_table = QTableWidget(0, 5)
        self.s_table.setHorizontalHeaderLabels(
            ["Date", "Description", "Hours", "Rate", "Amount"]
        )
        self.s_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.s_table)

        row = QHBoxLayout()
        back = QPushButton("← Back")
        remove = QPushButton("Remove last service")
        done = QPushButton("Done →")
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(remove)
        row.addWidget(done)
        layout.addLayout(row)

        self.s_totals = QLabel()
        self.s_totals.setAlignment(Qt.AlignRight)
        layout.addWidget(self.s_totals)

        self.s_hours.lineEdit().textEdited.connect(self._mark_hours_dirty)
        add.clicked.connect(self.add_service)
        clear.clicked.connect(self.clear_service_form)
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_meta))
        remove.clicked.connect(self.remove_last_service)
        done.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        self.s_desc.returnPressed.connect(self.add_service)
        self.s_date.returnPressed.connect(self.add_service)
        self.s_hours.lineEdit().returnPressed.connect(self.add_service)
        self.s_rate.lineEdit().returnPressed.connect(self.add_service)
        self.s_table.itemChanged.connect(self.service_item_changed)

        # Restored from the October speed-first build.
        self.setTabOrder(self.s_desc, self.s_date)
        self.setTabOrder(self.s_date, self.s_hours)
        self.setTabOrder(self.s_hours, self.s_rate)
        self.setTabOrder(self.s_rate, add)

        self.dup_service_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.page_services)
        self.dup_service_shortcut.activated.connect(self.prefill_last_service)

    def _build_costs_page(self):
        self.page_costs = QWidget()
        self.stack.addWidget(self.page_costs)
        layout = QVBoxLayout(self.page_costs)

        title = QLabel("▶ Costs")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        layout.addWidget(title)

        box = QGroupBox("Add cost")
        form = QFormLayout(box)
        self.c_desc = QLineEdit()
        self.c_qty = QDoubleSpinBox()
        self.c_qty.setDecimals(2)
        self.c_qty.setRange(0.0, 1e9)
        self.c_price = QDoubleSpinBox()
        self.c_price.setDecimals(2)
        self.c_price.setRange(0.0, 1e9)

        form.addRow("Cost desc:", self.c_desc)
        form.addRow("Quantity:", self.c_qty)
        form.addRow("Unit price:", self.c_price)

        buttons = QHBoxLayout()
        add = QPushButton("Add Cost (Enter)")
        clear = QPushButton("Clear")
        buttons.addWidget(add)
        buttons.addWidget(clear)
        form.addRow(buttons)
        layout.addWidget(box)

        self.c_table = QTableWidget(0, 4)
        self.c_table.setHorizontalHeaderLabels(
            ["Description", "Qty", "Unit Price", "Amount"]
        )
        self.c_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.c_table)

        row = QHBoxLayout()
        back = QPushButton("← Back")
        done = QPushButton("Done →")
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(done)
        layout.addLayout(row)

        self.c_totals = QLabel()
        self.c_totals.setAlignment(Qt.AlignRight)
        layout.addWidget(self.c_totals)

        add.clicked.connect(self.add_cost)
        clear.clicked.connect(self.clear_cost_form)
        back.clicked.connect(
            lambda: self.stack.setCurrentWidget(
                self.page_meta if self.flat_fee.isChecked() else self.page_services
            )
        )
        done.clicked.connect(self.go_review)
        self.c_desc.returnPressed.connect(self.add_cost)
        self.c_qty.lineEdit().returnPressed.connect(self.add_cost)
        self.c_price.lineEdit().returnPressed.connect(self.add_cost)
        self.c_table.itemChanged.connect(self.cost_item_changed)

        self.setTabOrder(self.c_desc, self.c_qty)
        self.setTabOrder(self.c_qty, self.c_price)
        self.setTabOrder(self.c_price, add)

        self.dup_cost_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.page_costs)
        self.dup_cost_shortcut.activated.connect(self.prefill_last_cost)

    def _build_review_page(self):
        self.page_review = QWidget()
        self.stack.addWidget(self.page_review)
        layout = QVBoxLayout(self.page_review)

        title = QLabel("▶ Review & Save")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        layout.addWidget(title)

        self.current_file_label = QLabel()
        self.current_file_label.setWordWrap(True)
        self.current_file_label.setStyleSheet("color:#666;")
        layout.addWidget(self.current_file_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet("font-family:Consolas, monospace; font-size:12px;")
        layout.addWidget(self.preview)

        self.filename_hint = QLabel()
        self.filename_hint.setAlignment(Qt.AlignRight)
        layout.addWidget(self.filename_hint)

        row = QHBoxLayout()
        open_existing = QPushButton("Open Existing")
        back = QPushButton("← Back")
        save = QPushButton("Save")
        save_export = QPushButton("Save + Export PDF")
        save_as = QPushButton("Save As New")
        new_btn = QPushButton("New Invoice")
        row.addWidget(open_existing)
        row.addStretch(1)
        row.addWidget(back)
        row.addWidget(save)
        row.addWidget(save_export)
        row.addWidget(save_as)
        row.addWidget(new_btn)
        layout.addLayout(row)

        open_existing.clicked.connect(self.go_open_page)
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        save.clicked.connect(self.save_current)
        save_export.clicked.connect(self.save_and_export)
        save_as.clicked.connect(self.save_as_new)
        new_btn.clicked.connect(self.start_new_invoice)

    # ------------------------------------------------------------------
    # General state
    # ------------------------------------------------------------------

    def _toggle_flat_fee(self, enabled: bool):
        self.flat_desc.setEnabled(enabled)
        self.flat_amount.setEnabled(enabled)
        self.set_dirty(True)

    def _mark_hours_dirty(self, *_):
        self._hours_dirty = True

    def set_dirty(self, dirty: bool = True):
        self.dirty = dirty
        mode = "Editing Existing" if self.edit_mode else "New Invoice"
        self.mode_label.setText(f"Mode: {mode}{' *' if dirty else ''}")
        self._update_current_file_label()

    def _update_current_file_label(self):
        if self.current_json_path:
            value = f"JSON: {self.current_json_path}"
            if self.current_pdf_path:
                value += f"\nPDF: {self.current_pdf_path}"
            self.current_file_label.setText(value)
        else:
            self.current_file_label.setText("This invoice has not been saved yet.")

    def start_new_invoice(self):
        default_rate = float(settings.get("general.default_rate", 250.0))
        today = datetime.now().strftime("%m/%d/%Y")
        self.invoice = Invoice("", today, default_rate)
        self.current_json_path = None
        self.current_pdf_path = None
        self.edit_mode = False

        self.client.clear()
        self.invoice_date.setText(today)
        self.default_rate.setValue(default_rate)
        self.rate_behavior.setCurrentIndex(0)
        self.flat_fee.setChecked(False)
        self.flat_desc.clear()
        self.flat_amount.setValue(0.0)

        self.clear_service_form()
        self.clear_cost_form()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals()
        self.set_dirty(False)
        self.stack.setCurrentWidget(self.page_meta)
        self.client.setFocus()

    def _apply_meta(self) -> bool:
        if self.invoice is None:
            return False

        client = self.client.text().strip()
        if not client:
            QMessageBox.warning(self, "Validation", "Client's Name cannot be empty.")
            return False

        try:
            date = parse_user_date(self.invoice_date.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Validation",
                "Use M/D, M/D/YY, or M/D/YYYY for the invoice date.",
            )
            return False

        rate = float(self.default_rate.value())
        if rate <= 0:
            QMessageBox.warning(self, "Validation", "Default hourly rate must be > 0.")
            return False

        if self.flat_fee.isChecked():
            desc = self.flat_desc.text().strip()
            amount = float(self.flat_amount.value())
            if not desc:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Flat fee description cannot be empty.",
                )
                return False
            if amount <= 0:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Flat fee amount must be > 0.",
                )
                return False
        else:
            desc = ""
            amount = 0.0

        old_rate = self.invoice.default_rate
        self.invoice.client_name = client
        self.invoice.invoice_date = format_date_full(date)
        self.invoice.default_rate = rate
        self.invoice_date.setText(self.invoice.invoice_date)

        if self.flat_fee.isChecked():
            self.invoice.flat_fee_desc = normalize_desc(desc)
            self.invoice.flat_fee_amount = amount
        else:
            self.invoice.flat_fee_desc = None
            self.invoice.flat_fee_amount = None

        if old_rate != rate and self.rate_behavior.currentIndex() == 1:
            self.invoice.apply_default_rate_to_all_services()

        settings.set_("general.default_rate", rate)
        return True

    def go_services(self):
        if not self._apply_meta():
            return
        self.s_rate.setValue(self.invoice.default_rate)
        self.set_dirty(True)
        if self.flat_fee.isChecked() and not self.invoice.services:
            self.stack.setCurrentWidget(self.page_costs)
        else:
            self.stack.setCurrentWidget(self.page_services)

    # ------------------------------------------------------------------
    # Existing invoices
    # ------------------------------------------------------------------

    def refresh_invoice_list(self):
        self.invoice_list.clear()
        for path in list_invoice_json_files():
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            self.invoice_list.addItem(item)

    def go_open_page(self):
        if self.dirty and self.invoice is not None:
            answer = QMessageBox.question(
                self,
                "Unsaved changes",
                "You have unsaved changes. Leave this invoice anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.refresh_invoice_list()
        self.stack.setCurrentWidget(self.page_open)

    def open_selected(self):
        item = self.invoice_list.currentItem()
        if item is None:
            QMessageBox.information(self, "No selection", "Select an invoice first.")
            return
        path = Path(str(item.data(Qt.UserRole)))
        try:
            invoice = load_invoice_json(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.invoice = invoice
        self.current_json_path = path
        expected_pdf = settings.get_export_dir() / f"{path.stem}.pdf"
        self.current_pdf_path = expected_pdf if expected_pdf.exists() else None
        self.edit_mode = True

        self.client.setText(invoice.client_name)
        self.invoice_date.setText(invoice.invoice_date)
        self.default_rate.setValue(invoice.default_rate)
        self.rate_behavior.setCurrentIndex(0)

        self.flat_fee.setChecked(invoice.flat_fee_amount is not None)
        self.flat_desc.setText(invoice.flat_fee_desc or "")
        self.flat_amount.setValue(float(invoice.flat_fee_amount or 0.0))

        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals()
        self.set_dirty(False)
        self.stack.setCurrentWidget(self.page_meta)

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def clear_service_form(self):
        self.s_desc.clear()
        self.s_date.setText(datetime.now().strftime("%m/%d/%Y"))
        self.s_hours.setValue(0.0)
        self.s_rate.setValue(float(self.default_rate.value()))
        self._hours_dirty = False
        self.s_desc.setFocus()
        self.s_desc.selectAll()

    def _rebuild_service_table(self):
        if self.invoice is None:
            return

        self._service_guard = True
        try:
            self.s_table.setRowCount(0)
            for service in sorted(self.invoice.services, key=lambda x: x.date):
                row = self.s_table.rowCount()
                self.s_table.insertRow(row)
                values = [
                    format_date_short(service.date),
                    service.desc,
                    f"{service.hours:.2f}",
                    f"{service.rate:.2f}",
                    money(service.amount),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, service.line_id)
                    self.s_table.setItem(row, col, item)
        finally:
            self._service_guard = False

    def add_service(self):
        if self.invoice is None:
            return

        desc = self.s_desc.text().strip()
        if not desc:
            QMessageBox.warning(self, "Validation", "Service description is required.")
            return

        try:
            date = parse_user_date(self.s_date.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Validation",
                "Use M/D, M/D/YY, or M/D/YYYY for the service date.",
            )
            return

        require_explicit = bool(
            settings.get("invoice.require_explicit_zero_hours", True)
        )
        if require_explicit and self.s_hours.value() == 0.0 and not self._hours_dirty:
            QMessageBox.warning(
                self,
                "Validation",
                "Hours required. Type 0 explicitly for a no-charge service.",
            )
            return

        candidate = LineItem(
            date=date,
            desc=normalize_desc(desc),
            hours=float(self.s_hours.value()),
            rate=float(self.s_rate.value()),
        )
        if self.invoice.has_duplicate_service(candidate):
            QMessageBox.warning(
                self,
                "Duplicate service",
                "That exact service line already exists.",
            )
            self.clear_service_form()
            return

        self.invoice.services.append(candidate)
        self._rebuild_service_table()
        self.clear_service_form()
        self.update_totals()
        self.set_dirty(True)

    def remove_last_service(self):
        if self.invoice is None or not self.invoice.services:
            QMessageBox.information(self, "Info", "Nothing to remove.")
            return
        self.invoice.services.pop()
        self._rebuild_service_table()
        self.update_totals()
        self.set_dirty(True)

    def prefill_last_service(self):
        if not self.invoice or not self.invoice.services:
            return
        last = self.invoice.services[-1]
        self.s_desc.setText(last.desc)
        self.s_date.setText(format_date_full(last.date))
        self.s_hours.setValue(last.hours)
        self.s_rate.setValue(last.rate)
        self._hours_dirty = True
        self.s_desc.setFocus()
        self.s_desc.selectAll()

    def service_item_changed(self, item: QTableWidgetItem):
        if self._service_guard or self.invoice is None:
            return

        line_id = str(item.data(Qt.UserRole) or "")
        service = self.invoice.find_service(line_id)
        if service is None:
            self._rebuild_service_table()
            return

        col = item.column()
        text = item.text().strip()

        # Build a tentative replacement first. This fixes the later refactor bug
        # where a duplicate edit mutated the underlying item before validation.
        candidate = LineItem(
            date=service.date,
            desc=service.desc,
            hours=service.hours,
            rate=service.rate,
            line_id=service.line_id,
        )

        try:
            if col == 0:
                candidate.date = parse_user_date(text)
            elif col == 1:
                if not text:
                    raise ValueError("Description cannot be empty")
                candidate.desc = normalize_desc(text)
            elif col == 2:
                candidate.hours = float(text)
                if candidate.hours < 0:
                    raise ValueError("Hours must be >= 0")
            elif col == 3:
                candidate.rate = float(text)
                if candidate.rate < 0:
                    raise ValueError("Rate must be >= 0")
            elif col == 4:
                self._rebuild_service_table()
                return
        except Exception as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            self._rebuild_service_table()
            return

        if self.invoice.has_duplicate_service(candidate, exclude_line_id=service.line_id):
            QMessageBox.warning(
                self,
                "Duplicate service",
                "This edit would create an exact duplicate service line.",
            )
            self._rebuild_service_table()
            return

        service.date = candidate.date
        service.desc = candidate.desc
        service.hours = candidate.hours
        service.rate = candidate.rate

        self._rebuild_service_table()
        self.update_totals()
        self.set_dirty(True)

    # ------------------------------------------------------------------
    # Costs
    # ------------------------------------------------------------------

    def clear_cost_form(self):
        self.c_desc.clear()
        self.c_qty.setValue(0.0)
        self.c_price.setValue(0.0)
        self.c_desc.setFocus()
        self.c_desc.selectAll()

    def _rebuild_cost_table(self):
        if self.invoice is None:
            return

        self._cost_guard = True
        try:
            self.c_table.setRowCount(0)
            for cost in self.invoice.costs:
                row = self.c_table.rowCount()
                self.c_table.insertRow(row)
                values = [
                    cost.desc,
                    f"{cost.qty:.2f}",
                    f"{cost.unit_price:.2f}",
                    money(cost.total),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, cost.line_id)
                    self.c_table.setItem(row, col, item)
        finally:
            self._cost_guard = False

    def add_cost(self):
        if self.invoice is None:
            return

        desc = self.c_desc.text().strip()
        if not desc:
            QMessageBox.warning(self, "Validation", "Cost description is required.")
            return

        self.invoice.add_cost(
            normalize_desc(desc),
            float(self.c_qty.value()),
            float(self.c_price.value()),
        )
        self._rebuild_cost_table()
        self.clear_cost_form()
        self.update_totals()
        self.set_dirty(True)

    def prefill_last_cost(self):
        if not self.invoice or not self.invoice.costs:
            return
        last = self.invoice.costs[-1]
        self.c_desc.setText(last.desc)
        self.c_qty.setValue(last.qty)
        self.c_price.setValue(last.unit_price)
        self.c_desc.setFocus()
        self.c_desc.selectAll()

    def cost_item_changed(self, item: QTableWidgetItem):
        if self._cost_guard or self.invoice is None:
            return

        line_id = str(item.data(Qt.UserRole) or "")
        cost = self.invoice.find_cost(line_id)
        if cost is None:
            self._rebuild_cost_table()
            return

        col = item.column()
        text = item.text().strip()
        try:
            if col == 0:
                if not text:
                    raise ValueError("Description cannot be empty")
                cost.desc = normalize_desc(text)
            elif col == 1:
                value = float(text)
                if value < 0:
                    raise ValueError("Quantity must be >= 0")
                cost.qty = value
            elif col == 2:
                value = float(text)
                if value < 0:
                    raise ValueError("Unit price must be >= 0")
                cost.unit_price = value
            elif col == 3:
                self._rebuild_cost_table()
                return
        except Exception as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            self._rebuild_cost_table()
            return

        self._rebuild_cost_table()
        self.update_totals()
        self.set_dirty(True)

    # ------------------------------------------------------------------
    # Review / save
    # ------------------------------------------------------------------

    def update_totals(self):
        if self.invoice is None:
            self.s_totals.setText("")
            self.c_totals.setText("")
            self.status.showMessage("")
            return

        service_total = self.invoice.total_services()
        cost_total = self.invoice.total_costs()
        grand = self.invoice.grand_total()
        hours = self.invoice.total_hours()

        self.s_totals.setText(
            f"Hours: {hours:.2f}    |    Service fees: {money(service_total)}"
        )
        self.c_totals.setText(
            f"Costs: {money(cost_total)}    |    GRAND TOTAL: <b>{money(grand)}</b>"
        )
        self.status.showMessage(
            f"Services: ${money(service_total)} | Hours: {hours:.2f} | "
            f"Costs: ${money(cost_total)} | Grand: ${money(grand)}"
        )

    def _preview_text(self) -> str:
        if self.invoice is None:
            return ""

        out = io.StringIO()
        inv = self.invoice
        print(f"===== Invoice for {inv.client_name} =====", file=out)
        print(f"Date: {inv.invoice_date}    Default Rate: {inv.default_rate:.2f}", file=out)
        print(file=out)

        print("SERVICES:", file=out)
        for service in sorted(inv.services, key=lambda x: x.date):
            print(
                f"{format_date_short(service.date):<10} "
                f"{service.desc:<40} "
                f"{service.hours:>6.2f} "
                f"{service.rate:>10.2f} "
                f"{service.amount:>12.2f}",
                file=out,
            )
        if inv.flat_fee_amount is not None:
            print(
                f"{'':<10} {(inv.flat_fee_desc or 'Flat service fee'):<40} "
                f"{'':>6} {'':>10} {inv.flat_fee_amount:>12.2f}",
                file=out,
            )
        print(f"TOTAL HOURS BILLED: {inv.total_hours():.2f}", file=out)
        print(f"TOTAL SERVICE FEES: {inv.total_services():.2f}", file=out)
        print(file=out)

        print("COSTS:", file=out)
        for cost in inv.costs:
            print(
                f"{cost.desc:<40} {cost.qty:>8.2f} "
                f"{cost.unit_price:>10.2f} {cost.total:>12.2f}",
                file=out,
            )
        print(f"TOTAL COSTS: {inv.total_costs():.2f}", file=out)
        print(file=out)
        print(f"GRAND TOTAL: {inv.grand_total():.2f}", file=out)
        return out.getvalue()

    def go_review(self):
        if self.invoice is None or not self._apply_meta():
            return

        if bool(settings.get("invoice.review_dedupe", True)):
            removed = self.invoice.dedupe_services()
            if removed:
                self._rebuild_service_table()
                QMessageBox.information(
                    self,
                    "Duplicates removed",
                    f"Removed {removed} exact duplicate service line(s).",
                )

        self.preview.setPlainText(self._preview_text())
        self.filename_hint.setText(
            f"Default file name: <b>{render_filename(self.invoice)}</b>"
        )
        self.update_totals()
        self._update_current_file_label()
        self.stack.setCurrentWidget(self.page_review)
        self.set_dirty(True)

    def _current_paths(self) -> tuple[Path, Path]:
        if self.invoice is None:
            raise ValueError("No invoice loaded")

        if self.edit_mode and self.current_json_path is not None:
            json_path = self.current_json_path
            pdf_path = self.current_pdf_path or (
                settings.get_export_dir() / f"{json_path.stem}.pdf"
            )
            return json_path, pdf_path

        return base_paths(self.invoice)

    def save_current(self):
        if self.invoice is None or not self._apply_meta():
            return
        try:
            json_path, pdf_path = self._current_paths()
            save_invoice_json(self.invoice, json_path)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)
            QMessageBox.information(self, "Saved", f"Saved:\n{json_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def save_and_export(self):
        if self.invoice is None or not self._apply_meta():
            return
        try:
            json_path, pdf_path = self._current_paths()
            save_invoice_json(self.invoice, json_path)
            generate_pdf(self.invoice, pdf_path)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)

            msg = QMessageBox(self)
            msg.setWindowTitle("Invoice saved")
            msg.setText(f"JSON:\n{json_path}\n\nPDF:\n{pdf_path}")
            open_pdf = msg.addButton("Open PDF", QMessageBox.AcceptRole)
            open_folder = msg.addButton("Open PDFs Folder", QMessageBox.ActionRole)
            msg.addButton("Close", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == open_pdf:
                open_local_path(pdf_path)
            elif msg.clickedButton() == open_folder:
                open_local_path(pdf_path.parent)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def save_as_new(self):
        if self.invoice is None or not self._apply_meta():
            return
        try:
            # Paired allocation fixes the old JSON/PDF "(1)" mismatch possibility.
            json_path, pdf_path = paired_unique_paths(self.invoice)
            save_invoice_json(self.invoice, json_path)
            generate_pdf(self.invoice, pdf_path)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)
            QMessageBox.information(
                self,
                "Saved As New",
                f"JSON:\n{json_path}\n\nPDF:\n{pdf_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save As New failed", str(exc))


class CreatorPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(Header("Invoice Workspace", on_back))
        self.workspace = InvoiceWorkspace()
        self.workspace.setWindowFlags(Qt.Widget)
        self.workspace.setParent(self)
        layout.addWidget(self.workspace)

    def start_new(self):
        self.workspace.start_new_invoice()

    def start_edit(self):
        self.workspace.go_open_page()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BetterBilling — Recovered Master")
        self.resize(1200, 800)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = Dashboard(
            self.go_new,
            self.go_edit,
            self.go_manage,
            self.go_settings,
            self.close,
        )
        self.creator = CreatorPage(lambda: self.stack.setCurrentWidget(self.dashboard))
        self.manage = ManagePage(lambda: self.stack.setCurrentWidget(self.dashboard))
        self.settings_page = SettingsPage(
            lambda: self.stack.setCurrentWidget(self.dashboard)
        )

        for page in (
            self.dashboard,
            self.creator,
            self.manage,
            self.settings_page,
        ):
            self.stack.addWidget(page)

        self.stack.setCurrentWidget(self.dashboard)

    def go_new(self):
        self.creator.start_new()
        self.stack.setCurrentWidget(self.creator)

    def go_edit(self):
        self.creator.start_edit()
        self.stack.setCurrentWidget(self.creator)

    def go_manage(self):
        self.manage.refresh()
        self.stack.setCurrentWidget(self.manage)

    def go_settings(self):
        self.settings_page.load()
        self.stack.setCurrentWidget(self.settings_page)


def main():
    settings.ensure_dirs()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
