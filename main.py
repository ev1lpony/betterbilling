from __future__ import annotations

import io
import os
import sys
from html import escape
from copy import deepcopy
from decimal import Decimal
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
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import settings
from ui_theme import apply_theme, button, label
from help_ui import HelpDialog
from models import (
    CostItem,
    Invoice,
    LineItem,
    format_date_full,
    format_date_short,
    normalize_desc,
    parse_user_date,
    validate_nonnegative_number,
)
from pdf_gen import money
from storage import (
    list_invoice_json_files,
    load_invoice_json,
    paired_unique_paths,
    render_filename,
    save_invoice_pair,
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


def set_numeric_value(field: QDoubleSpinBox, value: float, base_max: float) -> None:
    """Display imported values without silently changing their precision/range."""
    decimals = max(2, -Decimal(str(value)).as_tuple().exponent)
    field.setDecimals(decimals)
    field.setMaximum(max(base_max, value))
    field.setValue(value)


class Header(QWidget):
    def __init__(self, title: str, on_back):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        heading = label(title, "title")
        back = button("Back to home", "quiet")
        back.clicked.connect(on_back)
        row.addWidget(heading, 1)
        row.addWidget(back)


def add_field(layout: QVBoxLayout, title: str, field: QWidget, hint: str = "") -> None:
    caption = label(title)
    caption.setBuddy(field)
    field.setAccessibleName(title)
    layout.addWidget(caption)
    layout.addWidget(field)
    if hint:
        note = label(hint, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
    layout.addSpacing(4)


def page_heading(layout, title: str, description: str) -> None:
    layout.addWidget(label(title, "title"))
    note = label(description, "muted")
    note.setWordWrap(True)
    layout.addWidget(note)
    layout.addSpacing(8)


def configure_table(table: QTableWidget, description_column: int) -> None:
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for column in range(table.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.Interactive)
        table.setColumnWidth(column, 94 if column == 0 else 82)
    header.setSectionResizeMode(description_column, QHeaderView.Stretch)
    table.setColumnWidth(table.columnCount() - 1, 106)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(36)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setWordWrap(False)
    table.setAccessibleName("Invoice lines. Double-click a cell to edit it.")


class Dashboard(QWidget):
    def __init__(self, on_new, on_edit, on_manage, on_settings, on_exit):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        page_heading(layout, "Your billing, without the busywork.",
                     "Create an invoice, enter your services and costs, then save and export your PDF.")
        layout.addSpacing(16)
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(680)
        actions = QVBoxLayout(card)
        actions.setContentsMargins(24, 24, 24, 24)
        actions.setSpacing(12)
        actions.addWidget(label("Start an invoice", "section"))
        actions.addWidget(label("Have your time entries ready. We’ll take it one step at a time.", "muted"))
        row = QHBoxLayout()
        new_btn = button("New invoice", "primary")
        edit_btn = button("Open an invoice")
        new_btn.setMinimumHeight(42)
        edit_btn.setMinimumHeight(42)
        row.addWidget(new_btn)
        row.addWidget(edit_btn)
        row.addStretch()
        actions.addLayout(row)
        layout.addWidget(card)
        layout.addSpacing(20)
        layout.addWidget(label("A simple, familiar path", "section"))
        layout.addWidget(label("1  Invoice details     ›     2  Services     ›     3  Costs     ›     4  Review & save", "muted"))
        layout.addSpacing(12)
        row2 = QHBoxLayout()
        manage_btn = button("Invoice files", "quiet")
        settings_btn = button("Settings", "quiet")
        exit_btn = button("Exit", "quiet")
        for btn in (manage_btn, settings_btn, exit_btn):
            row2.addWidget(btn)
        row2.addStretch()
        layout.addLayout(row2)
        layout.addStretch(1)
        layout.addWidget(label("Need a hand? Open Help at the top of any screen, or press F1.", "muted"))

        new_btn.clicked.connect(on_new)
        edit_btn.clicked.connect(on_edit)
        manage_btn.clicked.connect(on_manage)
        settings_btn.clicked.connect(on_settings)
        exit_btn.clicked.connect(on_exit)


class ManagePage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(Header("Manage Files", on_back))
        note = label("Editable invoices and exported PDFs are stored on this computer. Keep both when backing up.", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addSpacing(12)

        self.data_label = QLabel()
        self.pdf_label = QLabel()
        self.json_label = QLabel()
        for path_label in (self.data_label, self.pdf_label, self.json_label):
            path_label.setWordWrap(True)
            layout.addWidget(path_label)

        row = QHBoxLayout()
        data_btn = button("Open all invoice files")
        pdf_btn = button("Open PDF folder", "primary")
        json_btn = button("Open editable invoices")
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
        self.data_label.setText(f"<b>All invoice files</b><br>{escape(str(settings.get_data_dir()))}")
        self.pdf_label.setText(f"<b>PDFs to send or print</b><br>{escape(str(settings.get_export_dir()))}")
        self.json_label.setText(f"<b>Editable invoices (JSON)</b><br>{escape(str(settings.get_json_dir()))}")


class SettingsPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self.guard = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(Header("Settings", on_back))
        layout.addWidget(label("Changes are saved as you make them. These preferences apply to future entries and exports.", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setMaximumWidth(850)
        form = QFormLayout(body)
        form.setContentsMargins(0, 20, 20, 20)
        form.setVerticalSpacing(16)
        scroll.setWidget(body)
        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(2)
        self.rate.setRange(0.0, 9_999_999)
        self.rate.setSingleStep(25.0)

        self.explicit_zero = QCheckBox("Require typing 0 hours for a no-charge service")
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
        form.addRow("PDF filename pattern:", self.filename)
        form.addRow("Letterhead space, in inches:", self.letterhead)
        pattern_note = label("Use {client} for the client name and {date} for the invoice date. Example: {client}-{date}.pdf", "muted")
        pattern_note.setWordWrap(True)
        form.addRow(pattern_note)
        layout.addWidget(scroll, 1)

        note = QLabel(
            "Storage is intentionally project-local so the whole app can live on a USB drive or be copied to another PC."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)

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
            set_numeric_value(self.rate, float(settings.get("general.default_rate", 250.0)), 9_999_999)
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
        data = deepcopy(settings.load_settings())
        data["general"]["default_rate"] = float(self.rate.value())
        data["invoice"]["require_explicit_zero_hours"] = self.explicit_zero.isChecked()
        data["invoice"]["review_dedupe"] = self.review_dedupe.isChecked()
        data["pdf"]["thousand_separators"] = self.thousands.isChecked()
        data["pdf"]["show_total_hours"] = self.show_hours.isChecked()
        data["pdf"]["file_naming_template"] = self.filename.currentText()
        data["letterhead"]["top_margin_in"] = float(self.letterhead.value())
        try:
            settings.save_settings(data)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Settings not saved", str(exc))


class InvoiceWorkspace(QMainWindow):
    def __init__(self):
        super().__init__()
        apply_theme(QApplication.instance())
        self.setWindowTitle("BetterBilling — Invoice")
        self.setMinimumSize(1000, 650)
        self.resize(1200, 760)
        self.invoice: Invoice | None = None
        self.current_json_path: Path | None = None
        self.current_pdf_path: Path | None = None
        self.edit_mode = False
        self.dirty = False
        self._loading = False
        self._service_guard = False
        self._cost_guard = False
        self._hours_dirty = False
        self.help_dialog = None

        central = QWidget()
        shell = QVBoxLayout(central)
        shell.setContentsMargins(24, 14, 24, 8)
        shell.setSpacing(10)
        self.step_bar = QWidget()
        steps_row = QHBoxLayout(self.step_bar)
        steps_row.setContentsMargins(0, 0, 0, 0)
        steps_row.setSpacing(12)
        self.steps = []
        for number, title in enumerate(("Invoice details", "Services", "Costs", "Review & save"), 1):
            step = label(f"{number}  {title}")
            step.setProperty("role", "step")
            steps_row.addWidget(step)
            self.steps.append(step)
        steps_row.addStretch()
        self.help_button = button("Help  ·  F1")
        self.help_button.setFocusPolicy(Qt.NoFocus)
        self.help_button.clicked.connect(lambda: self.show_help())
        steps_row.addWidget(self.help_button)
        shell.addWidget(self.step_bar)
        context_row = QHBoxLayout()
        self.context_label = label("", "muted")
        self.context_label.setTextFormat(Qt.PlainText)
        self.mode_label = label("", "badge")
        context_row.addWidget(self.context_label, 1)
        context_row.addWidget(self.mode_label)
        shell.addLayout(context_row)
        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)

        self._build_open_page()
        self._build_meta_page()
        self._build_services_page()
        self._build_costs_page()
        self._build_review_page()
        self.stack.currentChanged.connect(self._update_steps)
        self.help_shortcut = QShortcut(QKeySequence("F1"), self)
        self.help_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.help_shortcut.activated.connect(self.show_help)

        for field in (self.client, self.invoice_date, self.flat_desc, self.s_desc, self.s_date, self.c_desc):
            field.textEdited.connect(lambda *_: self.set_dirty())
        for field in (self.default_rate, self.flat_amount, self.s_hours, self.s_rate, self.c_qty, self.c_price):
            field.valueChanged.connect(lambda *_: self.set_dirty())
        self.rate_behavior.currentIndexChanged.connect(lambda *_: self.set_dirty())
        self.start_new_invoice()

    def _page(self):
        page = QWidget()
        self.stack.addWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        return page, layout

    def _update_steps(self, *_):
        pages = (self.page_meta, self.page_services, self.page_costs, self.page_review)
        current = self.stack.currentWidget()
        self.step_bar.setVisible(current is not self.page_open)
        index = pages.index(current) if current in pages else -1
        for number, step in enumerate(self.steps):
            state = "active" if number == index else "complete" if number < index else "upcoming"
            step.setProperty("state", state)
            step.style().unpolish(step)
            step.style().polish(step)
        self._update_context()

    def _update_context(self):
        name = self.client.text().strip() or "New invoice"
        self.context_label.setText(f"{name}  ·  {self.invoice_date.text()}")

    def show_help(self, topic=None):
        if topic is None:
            topic = {self.page_services: "services", self.page_costs: "costs",
                     self.page_review: "saving", self.page_open: "saving"}.get(
                         self.stack.currentWidget(), "first_invoice")
        if self.help_dialog is None:
            self.help_dialog = HelpDialog(self)
        self.help_dialog.show_topic(topic)

    def _build_open_page(self):
        self.page_open, layout = self._page()
        page_heading(layout, "Open an invoice", "Choose an editable invoice to continue working. Double-click an invoice to open it.")
        self.invoice_list = QListWidget()
        self.invoice_list.setAccessibleName("Saved editable invoices")
        layout.addWidget(self.invoice_list, 1)
        row = QHBoxLayout()
        refresh = button("Refresh")
        open_folder = button("Open invoice folder", "quiet")
        new_btn = button("New invoice")
        open_btn = button("Open selected invoice", "primary")
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
        self.page_meta, layout = self._page()
        page_heading(layout, "Invoice details", "Start with the client, invoice date and hourly rate.")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setMaximumWidth(640)
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 24, 8)
        form.setSpacing(5)
        self.client = QLineEdit()
        self.client.setPlaceholderText("Client or business name")
        self.invoice_date = QLineEdit()
        self.invoice_date.setPlaceholderText("M/D, M/D/YY, or M/D/YYYY")
        self.default_rate = QDoubleSpinBox()
        self.default_rate.setDecimals(2)
        self.default_rate.setRange(0.0, 9_999_999)
        self.default_rate.setSingleStep(25.0)
        self.rate_behavior = QComboBox()
        self.rate_behavior.addItems(["Keep existing service rates", "Apply default rate to every service"])
        self.flat_fee = QCheckBox("Include a flat service fee")
        self.flat_desc = QLineEdit()
        self.flat_desc.setPlaceholderText("e.g. Attorney fees")
        self.flat_amount = QDoubleSpinBox()
        self.flat_amount.setDecimals(2)
        self.flat_amount.setRange(0.0, 9_999_999)
        self.flat_amount.setSingleStep(50.0)
        add_field(form, "Client name", self.client)
        add_field(form, "Invoice date", self.invoice_date)
        add_field(form, "Default hourly rate ($)", self.default_rate)
        add_field(form, "When changing the default rate", self.rate_behavior)
        form.addWidget(self.flat_fee)
        flat_fields = QWidget()
        self.flat_fields = flat_fields
        flat_form = QVBoxLayout(flat_fields)
        flat_form.setContentsMargins(0, 4, 0, 0)
        flat_form.setSpacing(5)
        add_field(flat_form, "Flat fee description", self.flat_desc)
        add_field(flat_form, "Flat fee amount ($)", self.flat_amount)
        form.addWidget(flat_fields)
        form.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        row = QHBoxLayout()
        open_existing = button("Open an invoice", "quiet")
        next_btn = button("Continue", "primary")
        row.addWidget(open_existing)
        row.addStretch(1)
        row.addWidget(next_btn)
        layout.addLayout(row)
        self.flat_fee.toggled.connect(self._toggle_flat_fee)
        self.flat_desc.setEnabled(False)
        self.flat_amount.setEnabled(False)
        self.flat_fields.hide()
        open_existing.clicked.connect(self.go_open_page)
        next_btn.clicked.connect(self.go_services)
        self.client.returnPressed.connect(self.go_services)
        self.invoice_date.returnPressed.connect(self.go_services)
        self.default_rate.lineEdit().returnPressed.connect(self.go_services)
        for first, second in zip(
            (self.client, self.invoice_date, self.default_rate, self.rate_behavior, self.flat_fee, self.flat_desc, self.flat_amount),
            (self.invoice_date, self.default_rate, self.rate_behavior, self.flat_fee, self.flat_desc, self.flat_amount, next_btn),
        ):
            self.setTabOrder(first, second)

    def _entry_column(self, content, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(310)
        panel = QFrame()
        panel.setObjectName("entryPanel")
        fields = QVBoxLayout(panel)
        fields.setContentsMargins(16, 14, 16, 14)
        fields.setSpacing(5)
        fields.addWidget(label(title, "section"))
        fields.addSpacing(5)
        scroll.setWidget(panel)
        content.addWidget(scroll)
        return panel, fields

    def _build_services_page(self):
        self.page_services, layout = self._page()
        page_heading(layout, "Services", "Enter a time entry, then add it to the invoice. Double-click a line below to edit it.")
        content = QHBoxLayout()
        content.setSpacing(18)
        self.s_entry_panel, form = self._entry_column(content, "Add a service")
        self.s_desc = QLineEdit()
        self.s_desc.setPlaceholderText("Work performed")
        self.s_date = QLineEdit()
        self.s_date.setPlaceholderText("M/D, M/D/YY, or M/D/YYYY")
        self.s_hours = QDoubleSpinBox()
        self.s_hours.setDecimals(2)
        self.s_hours.setRange(0.0, 10_000.0)
        self.s_hours.setSingleStep(0.25)
        self.s_rate = QDoubleSpinBox()
        self.s_rate.setDecimals(2)
        self.s_rate.setRange(0.0, 9_999_999)
        self.s_rate.setSingleStep(25.0)
        add_field(form, "Description", self.s_desc)
        add_field(form, "Date", self.s_date)
        add_field(form, "Hours", self.s_hours)
        add_field(form, "Hourly rate ($)", self.s_rate)
        self.s_add_button = button("Add service  ·  Enter", "primary")
        form.addWidget(self.s_add_button)
        buttons = QHBoxLayout()
        repeat = button("Use last entry", "quiet")
        repeat.setToolTip("Fill these fields from the last service (Ctrl+D). Edit, then Add.")
        clear = button("Clear", "quiet")
        buttons.addWidget(repeat)
        buttons.addWidget(clear)
        form.addLayout(buttons)
        tip = label("Tab moves through fields. Enter adds.\nCtrl+D fills the last entry.", "muted")
        tip.setWordWrap(True)
        form.addWidget(tip)
        form.addStretch()
        right = QVBoxLayout()
        right.setSpacing(8)
        self.s_lines_label = label("Invoice services", "section")
        right.addWidget(self.s_lines_label)
        self.s_table = QTableWidget(0, 5)
        self.s_table.setHorizontalHeaderLabels(["Date", "Description", "Hours", "Rate ($)", "Amount ($)"])
        configure_table(self.s_table, 1)
        right.addWidget(self.s_table, 1)
        self.s_totals = label("", "section")
        self.s_totals.setAlignment(Qt.AlignRight)
        right.addWidget(self.s_totals)
        content.addLayout(right, 1)
        layout.addLayout(content, 1)
        row = QHBoxLayout()
        back = button("Back to details")
        remove = button("Remove last service", "quiet")
        done = button("Continue to costs", "primary")
        row.addWidget(back)
        row.addWidget(remove)
        row.addStretch(1)
        row.addWidget(done)
        layout.addLayout(row)
        self.s_hours.lineEdit().textEdited.connect(self._mark_hours_dirty)
        self.s_add_button.clicked.connect(self.add_service)
        repeat.clicked.connect(self.prefill_last_service)
        clear.clicked.connect(self.clear_service_form)
        back.clicked.connect(lambda: self._show_page(self.page_meta, self.client))
        remove.clicked.connect(self.remove_last_service)
        done.clicked.connect(self.go_costs)
        self.s_desc.returnPressed.connect(self.add_service)
        self.s_date.returnPressed.connect(self.add_service)
        self.s_hours.lineEdit().returnPressed.connect(self.add_service)
        self.s_rate.lineEdit().returnPressed.connect(self.add_service)
        self.s_table.itemChanged.connect(self.service_item_changed)
        self.setTabOrder(self.s_desc, self.s_date)
        self.setTabOrder(self.s_date, self.s_hours)
        self.setTabOrder(self.s_hours, self.s_rate)
        self.setTabOrder(self.s_rate, self.s_add_button)
        self.dup_service_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.page_services)
        self.dup_service_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.dup_service_shortcut.activated.connect(self.prefill_last_service)
        self.next_service_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.page_services)
        self.next_service_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.next_service_shortcut.activated.connect(self.go_costs)
        done.setToolTip("Continue to costs (Ctrl+Enter). Add the current entry first if you want to include it.")

    def _build_costs_page(self):
        self.page_costs, layout = self._page()
        page_heading(layout, "Costs", "Enter expenses to include on the invoice, or continue if there are none.")
        content = QHBoxLayout()
        content.setSpacing(18)
        self.c_entry_panel, form = self._entry_column(content, "Add a cost")
        self.c_desc = QLineEdit()
        self.c_desc.setPlaceholderText("e.g. Certified mail")
        self.c_qty = QDoubleSpinBox()
        self.c_qty.setDecimals(2)
        self.c_qty.setRange(0.0, 1e9)
        self.c_price = QDoubleSpinBox()
        self.c_price.setDecimals(2)
        self.c_price.setRange(0.0, 1e9)
        add_field(form, "Description", self.c_desc)
        add_field(form, "Quantity", self.c_qty)
        add_field(form, "Unit price ($)", self.c_price)
        self.c_add_button = button("Add cost  ·  Enter", "primary")
        form.addWidget(self.c_add_button)
        buttons = QHBoxLayout()
        repeat = button("Use last entry", "quiet")
        repeat.setToolTip("Fill these fields from the last cost (Ctrl+D). Edit, then Add.")
        clear = button("Clear", "quiet")
        buttons.addWidget(repeat)
        buttons.addWidget(clear)
        form.addLayout(buttons)
        tip = label("Tab moves through fields. Enter adds.\nCtrl+D fills the last entry.", "muted")
        tip.setWordWrap(True)
        form.addWidget(tip)
        form.addStretch()
        right = QVBoxLayout()
        right.setSpacing(8)
        self.c_lines_label = label("Invoice costs", "section")
        right.addWidget(self.c_lines_label)
        self.c_table = QTableWidget(0, 4)
        self.c_table.setHorizontalHeaderLabels(["Description", "Quantity", "Unit price ($)", "Amount ($)"])
        configure_table(self.c_table, 0)
        self.c_table.setColumnWidth(2, 106)
        right.addWidget(self.c_table, 1)
        self.c_totals = label("", "section")
        self.c_totals.setAlignment(Qt.AlignRight)
        right.addWidget(self.c_totals)
        content.addLayout(right, 1)
        layout.addLayout(content, 1)
        row = QHBoxLayout()
        back = button("Back")
        done = button("Review invoice", "primary")
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(done)
        layout.addLayout(row)
        self.c_add_button.clicked.connect(self.add_cost)
        repeat.clicked.connect(self.prefill_last_cost)
        clear.clicked.connect(self.clear_cost_form)
        back.clicked.connect(lambda: self._show_page(
            self.page_meta if self.flat_fee.isChecked() and not self.invoice.services else self.page_services,
            self.client if self.flat_fee.isChecked() and not self.invoice.services else self.s_desc,
        ))
        done.clicked.connect(self.go_review)
        self.c_desc.returnPressed.connect(self.add_cost)
        self.c_qty.lineEdit().returnPressed.connect(self.add_cost)
        self.c_price.lineEdit().returnPressed.connect(self.add_cost)
        self.c_table.itemChanged.connect(self.cost_item_changed)
        self.setTabOrder(self.c_desc, self.c_qty)
        self.setTabOrder(self.c_qty, self.c_price)
        self.setTabOrder(self.c_price, self.c_add_button)
        self.dup_cost_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.page_costs)
        self.dup_cost_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.dup_cost_shortcut.activated.connect(self.prefill_last_cost)
        self.next_cost_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.page_costs)
        self.next_cost_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.next_cost_shortcut.activated.connect(self.go_review)
        done.setToolTip("Continue to review (Ctrl+Enter). Add the current entry first if you want to include it.")

    def _build_review_page(self):
        self.page_review, layout = self._page()
        page_heading(layout, "Review & save", "Check the invoice below, then save and export a PDF to send or print.")
        self.current_file_label = label("", "muted")
        self.current_file_label.setWordWrap(True)
        layout.addWidget(self.current_file_label)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("Invoice review")
        self.preview.setObjectName("InvoiceReview")
        self.preview.document().setDocumentMargin(16)
        layout.addWidget(self.preview, 1)
        self.review_totals = label("", "section")
        self.review_totals.setAlignment(Qt.AlignRight)
        layout.addWidget(self.review_totals)
        self.filename_hint = label("", "muted")
        self.filename_hint.setWordWrap(True)
        layout.addWidget(self.filename_hint)
        utilities = QHBoxLayout()
        open_existing = button("Open an invoice", "quiet")
        save_as = button("Save as new")
        new_btn = button("New invoice")
        utilities.addWidget(open_existing)
        utilities.addStretch()
        utilities.addWidget(save_as)
        utilities.addWidget(new_btn)
        layout.addLayout(utilities)
        row = QHBoxLayout()
        back = button("Back to costs")
        save = button("Save")
        save.setToolTip("Save the editable invoice only. Use Save + Export PDF to create the PDF too.")
        self.save_export_button = button("Save + Export PDF", "primary")
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(save)
        row.addWidget(self.save_export_button)
        layout.addLayout(row)
        open_existing.clicked.connect(self.go_open_page)
        back.clicked.connect(self.go_costs)
        save.clicked.connect(self.save_current)
        self.save_export_button.clicked.connect(self.save_and_export)
        save_as.clicked.connect(self.save_as_new)
        new_btn.clicked.connect(self.start_new_invoice)

    # ------------------------------------------------------------------
    # General state
    # ------------------------------------------------------------------

    def _toggle_flat_fee(self, enabled: bool):
        self.flat_desc.setEnabled(enabled)
        self.flat_amount.setEnabled(enabled)
        self.flat_fields.setVisible(enabled)
        self.set_dirty(True)

    def _mark_hours_dirty(self, *_):
        self._hours_dirty = True

    def set_dirty(self, dirty: bool = True):
        if dirty and self._loading:
            return
        self.dirty = dirty
        self.mode_label.setText("Unsaved changes" if dirty else "Saved invoice" if self.edit_mode else "New invoice")
        self.mode_label.setProperty("state", "dirty" if dirty else "saved")
        self.mode_label.style().unpolish(self.mode_label)
        self.mode_label.style().polish(self.mode_label)
        self._update_context()
        self._update_current_file_label()

    def _update_current_file_label(self):
        if self.current_json_path:
            self.current_file_label.setText(f"Editing saved invoice: {self.current_json_path.name}")
            self.current_file_label.setToolTip(str(self.current_json_path))
        else:
            self.current_file_label.setText("This invoice has not been saved yet.")
            self.current_file_label.setToolTip("")

    def confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        return QMessageBox.question(
            self,
            "Unsaved changes",
            "Discard unsaved changes to this invoice?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def closeEvent(self, event):
        if self.confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    def _show_page(self, page, focus):
        self.stack.setCurrentWidget(page)
        focus.setFocus()
        if isinstance(focus, QLineEdit):
            focus.selectAll()

    def go_costs(self):
        self._show_page(self.page_costs, self.c_desc)

    def _has_pending_entries(self) -> bool:
        return bool(self.s_desc.text().strip() or self.c_desc.text().strip())

    def start_new_invoice(self) -> bool:
        if not self.confirm_discard_changes():
            return False
        self._loading = True
        default_rate = float(settings.get("general.default_rate", 250.0))
        today = datetime.now().strftime("%m/%d/%Y")
        self.invoice = Invoice("", today, default_rate)
        self.current_json_path = None
        self.current_pdf_path = None
        self.edit_mode = False

        self.client.clear()
        self.invoice_date.setText(today)
        set_numeric_value(self.default_rate, default_rate, 9_999_999)
        self.rate_behavior.setCurrentIndex(0)
        self.flat_fee.setChecked(False)
        self.flat_desc.clear()
        self.flat_amount.setDecimals(2)
        self.flat_amount.setMaximum(9_999_999)
        self.flat_amount.setValue(0.0)

        self.clear_service_form(reset_date=True)
        self.clear_cost_form()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals()
        self._loading = False
        self.set_dirty(False)
        self._show_page(self.page_meta, self.client)
        return True

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
        if rate < 0:
            QMessageBox.warning(self, "Validation", "Default hourly rate must be >= 0.")
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
            if amount < 0:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "Flat fee amount must be >= 0.",
                )
                return False
        else:
            desc = ""
            amount = 0.0

        old_values = (self.invoice.client_name, self.invoice.invoice_date, self.invoice.default_rate, self.invoice.flat_fee_desc, self.invoice.flat_fee_amount)
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
            self._rebuild_service_table()
            self.update_totals()

        if old_values != (self.invoice.client_name, self.invoice.invoice_date, self.invoice.default_rate, self.invoice.flat_fee_desc, self.invoice.flat_fee_amount):
            self.set_dirty(True)
        if float(settings.get("general.default_rate", 250.0)) != rate:
            try:
                settings.set_("general.default_rate", rate)
            except OSError as exc:
                self.status.showMessage(f"Invoice updated; default rate preference could not be saved: {exc}")
        return True

    def go_services(self):
        if not self._apply_meta():
            return
        set_numeric_value(self.s_rate, self.invoice.default_rate, 9_999_999)
        if self.flat_fee.isChecked() and not self.invoice.services:
            self.go_costs()
        else:
            self._show_page(self.page_services, self.s_desc)

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
        self.refresh_invoice_list()
        self._show_page(self.page_open, self.invoice_list)

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

        if not self.confirm_discard_changes():
            return
        self._loading = True
        self.invoice = invoice
        self.current_json_path = path
        expected_pdf = settings.get_export_dir() / f"{path.stem}.pdf"
        self.current_pdf_path = expected_pdf if expected_pdf.exists() else None
        self.edit_mode = True

        self.client.setText(invoice.client_name)
        self.invoice_date.setText(invoice.invoice_date)
        set_numeric_value(self.default_rate, invoice.default_rate, 9_999_999)
        self.rate_behavior.setCurrentIndex(0)

        self.flat_fee.setChecked(invoice.flat_fee_amount is not None)
        self.flat_desc.setText(invoice.flat_fee_desc or "")
        set_numeric_value(self.flat_amount, float(invoice.flat_fee_amount or 0.0), 9_999_999)

        self.clear_service_form(reset_date=True)
        self.clear_cost_form()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals()
        self._loading = False
        self.set_dirty(False)
        self._show_page(self.page_meta, self.client)

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def clear_service_form(self, reset_date: bool = False):
        was_loading = self._loading
        self._loading = True
        self.s_desc.clear()
        if reset_date or not self.s_date.text().strip():
            self.s_date.setText(self.invoice_date.text() or datetime.now().strftime("%m/%d/%Y"))
        self.s_hours.setValue(0.0)
        set_numeric_value(self.s_rate, float(self.default_rate.value()), 9_999_999)
        self._hours_dirty = False
        self._loading = was_loading
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
                    if col == 4:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col >= 2:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    item.setToolTip(value)
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
            self.s_desc.setFocus()
            self.s_desc.selectAll()
            return

        self.invoice.services.append(candidate)
        self._rebuild_service_table()
        self.s_date.setText(format_date_full(date))
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
        set_numeric_value(self.s_hours, last.hours, 10_000)
        set_numeric_value(self.s_rate, last.rate, 9_999_999)
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
                candidate.hours = validate_nonnegative_number(text, "Hours")
            elif col == 3:
                candidate.rate = validate_nonnegative_number(text, "Rate")
            elif col == 4:
                self._rebuild_service_table()
                return
            candidate.validate()
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
        was_loading = self._loading
        self._loading = True
        self.c_desc.clear()
        self.c_qty.setValue(0.0)
        self.c_price.setValue(0.0)
        self._loading = was_loading
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
                    if col == 3:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col >= 1:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    item.setToolTip(value)
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
        set_numeric_value(self.c_qty, last.qty, 1e9)
        set_numeric_value(self.c_price, last.unit_price, 1e9)
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
        candidate = CostItem(cost.desc, cost.qty, cost.unit_price, cost.line_id)
        try:
            if col == 0:
                if not text:
                    raise ValueError("Description cannot be empty")
                candidate.desc = normalize_desc(text)
            elif col == 1:
                value = validate_nonnegative_number(text, "Quantity")
                candidate.qty = value
            elif col == 2:
                value = validate_nonnegative_number(text, "Unit price")
                candidate.unit_price = value
            elif col == 3:
                self._rebuild_cost_table()
                return
            candidate.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            self._rebuild_cost_table()
            return

        cost.desc = candidate.desc
        cost.qty = candidate.qty
        cost.unit_price = candidate.unit_price
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
            f"{hours:.2f} hours    ·    Service fees: ${money(service_total)}"
        )
        self.c_totals.setText(
            f"Costs: ${money(cost_total)}    ·    Invoice total: ${money(grand)}"
        )
        self.s_lines_label.setText(f"Invoice services  ·  {len(self.invoice.services)} entries")
        self.c_lines_label.setText(f"Invoice costs  ·  {len(self.invoice.costs)} entries")
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

    def _preview_html(self) -> str:
        """A readable review of the invoice; PDF generation keeps its existing layout."""
        if self.invoice is None:
            return ""
        inv = self.invoice

        def table(headings, rows):
            header = "".join(f'<th align="{alignment}" bgcolor="#edf1f6">{escape(text)}</th>'
                             for text, alignment in headings)
            body = "".join("<tr>" + "".join(
                f'<td align="{headings[index][1]}">{escape(str(value))}</td>'
                for index, value in enumerate(row)) + "</tr>" for row in rows)
            return f'<table width="98%" cellspacing="0" cellpadding="8"><tr>{header}</tr>{body}</table>'

        service_rows = [(format_date_short(s.date), s.desc, f"{s.hours:.2f}",
                         f"${money(s.rate)}", f"${money(s.amount)}")
                        for s in sorted(inv.services, key=lambda x: x.date)]
        if inv.flat_fee_amount is not None:
            service_rows.append(("", inv.flat_fee_desc or "Flat service fee", "", "", f"${money(inv.flat_fee_amount)}"))
        services = table([("Date", "left"), ("Description", "left"), ("Hours", "right"),
                          ("Rate", "right"), ("Amount", "right")], service_rows) if service_rows else "<p>No service entries.</p>"
        costs = table([("Description", "left"), ("Quantity", "right"), ("Unit price", "right"), ("Amount", "right")],
                      [(c.desc, f"{c.qty:.2f}", f"${money(c.unit_price)}", f"${money(c.total)}")
                       for c in inv.costs]) if inv.costs else "<p>No costs.</p>"
        return (
            '<html><body style="font-family:Segoe UI; color:#202c3e; font-size:14px;">'
            f'<h2>{escape(inv.client_name)}</h2><p>Invoice date: {escape(inv.invoice_date)}</p>'
            f'<h3>Services</h3>{services}<p align="right">Hours billed: {inv.total_hours():.2f}'
            f' &nbsp; · &nbsp; Service fees: ${money(inv.total_services())}</p>'
            f'<h3>Costs</h3>{costs}<p align="right">Total costs: ${money(inv.total_costs())}</p>'
            f'<hr><p align="right" style="font-size:20px;"><b>Grand total: ${money(inv.grand_total())}</b></p>'
            '</body></html>'
        )

    def go_review(self):
        if self.invoice is None or not self._apply_meta():
            return

        if bool(settings.get("invoice.review_dedupe", True)):
            removed = self.invoice.dedupe_services()
            if removed:
                self._rebuild_service_table()
                self.set_dirty(True)
                QMessageBox.information(
                    self,
                    "Duplicates removed",
                    f"Removed {removed} exact duplicate service line(s).",
                )

        self.preview.setHtml(self._preview_html())
        self.review_totals.setText(
            f"Service fees: ${money(self.invoice.total_services())}    ·    "
            f"Costs: ${money(self.invoice.total_costs())}    ·    "
            f"Grand total: ${money(self.invoice.grand_total())}"
        )
        try:
            filename = render_filename(self.invoice)
        except ValueError as exc:
            self.filename_hint.setText(f"Check the filename template in Settings: {exc}")
        else:
            self.filename_hint.setText(f"PDF filename: <b>{escape(filename)}</b>")
        self.update_totals()
        self._update_current_file_label()
        self._show_page(self.page_review, self.save_export_button)

    def _current_paths(self) -> tuple[Path, Path]:
        if self.invoice is None:
            raise ValueError("No invoice loaded")

        if self.edit_mode and self.current_json_path is not None:
            json_path = self.current_json_path
            pdf_path = self.current_pdf_path or (
                settings.get_export_dir() / f"{json_path.stem}.pdf"
            )
            return json_path, pdf_path

        return paired_unique_paths(self.invoice)

    def save_current(self):
        if self.invoice is None or not self._apply_meta():
            return
        try:
            json_path, pdf_path = self._current_paths()
            save_invoice_json(self.invoice, json_path, overwrite=self.edit_mode)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(self._has_pending_entries())
            QMessageBox.information(self, "Invoice saved", f"Editable invoice saved:\n{json_path.name}\n\nTo create the PDF too, choose Save + Export PDF.")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def save_and_export(self):
        if self.invoice is None or not self._apply_meta():
            return
        try:
            json_path, pdf_path = self._current_paths()
            save_invoice_pair(self.invoice, json_path, pdf_path, overwrite=self.edit_mode)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(self._has_pending_entries())

            msg = QMessageBox(self)
            msg.setWindowTitle("Invoice saved")
            msg.setText(f"Your editable invoice and PDF are saved.\n\n{pdf_path.name}")
            msg.setDetailedText(f"Editable invoice:\n{json_path}\n\nPDF:\n{pdf_path}")
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
            save_invoice_pair(self.invoice, json_path, pdf_path, overwrite=False)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(self._has_pending_entries())
            QMessageBox.information(
                self,
                "Saved As New",
                f"Saved a new editable invoice and PDF:\n{pdf_path.name}\n\nYou are now editing this new copy.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save As New failed", str(exc))


class CreatorPage(QWidget):
    def __init__(self, on_back):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = InvoiceWorkspace()
        self.workspace.setWindowFlags(Qt.Widget)
        self.workspace.setParent(self)
        self.workspace.help_button.hide()
        self.workspace.help_shortcut.setEnabled(False)
        layout.addWidget(self.workspace)

    def start_new(self):
        return self.workspace.start_new_invoice()

    def start_edit(self):
        self.workspace.go_open_page()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        apply_theme(QApplication.instance())
        self.setWindowTitle("BetterBilling")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("AppHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(24, 10, 24, 10)
        brand = QLabel('<span style="font-size:22px; font-weight:700;">Better<span style="color:#244e81;">Billing</span></span>')
        brand.setAccessibleName("BetterBilling")
        header_row.addWidget(brand)
        header_row.addSpacing(28)
        self.home_button = button("Home", "quiet")
        self.invoices_button = button("Invoices", "quiet")
        self.settings_button = button("Settings", "quiet")
        for nav_button in (self.home_button, self.invoices_button, self.settings_button):
            nav_button.setFocusPolicy(Qt.NoFocus)
            header_row.addWidget(nav_button)
        header_row.addStretch()
        self.help_button = button("Help  ·  F1")
        self.help_button.setFocusPolicy(Qt.NoFocus)
        header_row.addWidget(self.help_button)
        layout.addWidget(header)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

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
        self.home_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.dashboard))
        self.invoices_button.clicked.connect(self.go_edit)
        self.settings_button.clicked.connect(self.go_settings)
        self.help_button.clicked.connect(self.show_help)
        self.help_shortcut = QShortcut(QKeySequence("F1"), self)
        self.help_shortcut.activated.connect(self.show_help)

    def show_help(self):
        topic = None if self.stack.currentWidget() is self.creator else "files" if self.stack.currentWidget() is self.manage else "first_invoice"
        self.creator.workspace.show_help(topic)

    def go_new(self):
        if self.creator.start_new():
            self.stack.setCurrentWidget(self.creator)
            self.creator.workspace.client.setFocus()

    def go_edit(self):
        self.creator.start_edit()
        self.stack.setCurrentWidget(self.creator)

    def go_manage(self):
        self.manage.refresh()
        self.stack.setCurrentWidget(self.manage)

    def go_settings(self):
        self.settings_page.load()
        self.stack.setCurrentWidget(self.settings_page)

    def closeEvent(self, event):
        if self.creator.workspace.confirm_discard_changes():
            event.accept()
        else:
            event.ignore()


def main():
    settings.ensure_dirs()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
