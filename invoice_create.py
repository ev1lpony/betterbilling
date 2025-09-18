from __future__ import annotations

import sys
import os
import io
import re
from datetime import datetime
from typing import List
from pathlib import Path

# ---- Core / helpers ----
from fpdf import FPDF, XPos, YPos

PAGE_FORMAT      = 'Letter'
FONT_FAMILY      = 'Helvetica'
MAX_FONT_PT      = 14
MIN_FONT_PT      = 10
LEFT_MARGIN_MM   = 15
TOP_MARGIN_MM    = 20
BOTTOM_MARGIN_MM = 5  # safety margin at bottom

# Centralized app settings
import settings

def mm_from_inches(inches: float) -> float:
    return inches * 25.4

def letterhead_margin_in() -> float:
    """Top letterhead margin (inches) from settings, default 2.5in."""
    try:
        return float(settings.get("letterhead.top_margin_in", 2.5))
    except Exception:
        return 2.5

def normalize_desc(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:]

def paginate_table(pdf, rows, col_widths, headers, alignments=None):
    """
    Draw rows + headers with auto-pagination and auto-shrink for overflow.
    Assumes pdf.font_size_pt & pdf.ln_height_mm already set.
    """
    x0        = LEFT_MARGIN_MM
    row_h     = pdf.ln_height_mm
    usable    = pdf.h - mm_from_inches(letterhead_margin_in()) - TOP_MARGIN_MM - BOTTOM_MARGIN_MM
    base_size = pdf.font_size_pt
    min_size  = MIN_FONT_PT

    if alignments is None:
        alignments = ['L'] * len(col_widths)

    def draw_header():
        pdf.set_x(x0)
        pdf.set_font(FONT_FAMILY, 'B', base_size)
        pdf.set_fill_color(200, 220, 255)
        for w, h in zip(col_widths, headers):
            pdf.cell(w, row_h, h, border=1, align='C', fill=True)
        pdf.ln(row_h)
        pdf.set_font(FONT_FAMILY, '', base_size)
        pdf.set_fill_color(245, 245, 245)

    draw_header()
    fill = True
    for row in rows:
        if pdf.get_y() + row_h > usable:
            pdf.add_page()
            pdf.set_y(mm_from_inches(letterhead_margin_in()))
            draw_header()
        pdf.set_x(x0)
        for w, cell, alg in zip(col_widths, row, alignments):
            # measure and shrink if needed
            text_w = pdf.get_string_width(cell)
            if text_w > w - 2:
                scale    = (w - 2) / text_w
                new_size = max(min_size, base_size * scale)
                pdf.set_font(FONT_FAMILY, '', new_size)
            else:
                pdf.set_font(FONT_FAMILY, '', base_size)
            pdf.cell(w, row_h, cell, border=1, align=alg, fill=fill)
        pdf.set_font(FONT_FAMILY, '', base_size)
        pdf.ln(row_h)
        fill = not fill

def parse_input_date(s: str) -> datetime:
    parts = s.strip().split('/')
    if len(parts) == 2:
        m, d = map(int, parts); y = datetime.now().year
    elif len(parts) == 3:
        m, d, y_raw = map(int, parts)
        y = 2000 + y_raw if y_raw < 100 else y_raw
    else:
        raise ValueError("Use M/D or M/D/YY")
    return datetime(y, m, d)

def format_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.strftime('%y')}"

def parse_user_date(s: str) -> datetime:
    s = s.strip()
    if not s:
        raise ValueError("Empty date")
    parts = s.split('/')
    now = datetime.now()
    if len(parts) == 2:
        m, d = map(int, parts)
        y = now.year
    elif len(parts) == 3:
        m, d, y_raw = parts
        m = int(m); d = int(d)
        y_raw = int(y_raw)
        y = 2000 + y_raw if y_raw < 100 else y_raw
    else:
        raise ValueError("Use M/D, M/D/YY, or M/D/YYYY")
    return datetime(y, m, d)

def format_date_full(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y")

# ----- Filename helpers (settings-driven) ------------------------------------

def sanitize_client(name: str) -> str:
    # keep letters, numbers, space, underscore, dash; collapse spaces to _
    s = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    return re.sub(r"\s+", "_", s)

def date_for_filename(ui_mmddyyyy: str) -> str:
    # Convert UI date MM/DD/YYYY to MM-DD-YYYY for filenames
    return ui_mmddyyyy.replace("/", "-")

def render_filename_from_template(inv: "Invoice") -> str:
    """
    Applies settings.pdf.file_naming_template.
    Supported vars: {client}, {date}
    - {client}: sanitized (spaces -> _)
    - {date}: MM-DD-YYYY (from UI invoice_date)
    """
    template = settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf")
    client = sanitize_client(inv.client_name)
    date_str = date_for_filename(inv.invoice_date)
    try:
        return template.format(client=client, date=date_str)
    except Exception:
        return f"{client}_invoice[{date_str}].pdf"

class LineItem:
    def __init__(self, date_obj, desc, hours, rate):
        self.date  = date_obj
        self.desc  = desc
        self.hours = hours
        self.rate  = rate
    @property
    def amount(self):
        return self.hours * self.rate

class CostItem:
    def __init__(self, desc, qty, unit_price):
        self.desc       = desc
        self.qty        = qty
        self.unit_price = unit_price
    @property
    def total(self):
        return self.qty * self.unit_price

class Invoice:
    def __init__(self, client_name, invoice_date, default_rate):
        self.client_name  = client_name
        self.invoice_date = invoice_date
        self.default_rate = default_rate
        self.services: List[LineItem] = []
        self.costs: List[CostItem]    = []

    def add_service(self, dt, desc, hrs):
        self.services.append(LineItem(dt, desc, hrs, self.default_rate))

    def add_cost(self, desc, qty, unit_price):
        self.costs.append(CostItem(desc, qty, unit_price))

    def total_services(self):
        return sum(i.amount for i in self.services)

    def total_costs(self):
        return sum(c.total  for c in self.costs)

    def grand_total(self):
        return self.total_services() + self.total_costs()

    def print_console(self):
        print(f"\n===== Invoice for {self.client_name} =====")
        print(f"Date: {self.invoice_date}    Rate: {self.default_rate:.2f}\n")
        if self.services:
            print("SERVICES:")
            print(f"{'Date':<10} {'Desc':<30} {'Hrs':>5} {'Rate':>8} {'Amt':>10}")
            print("-"*65)
            for i in sorted(self.services, key=lambda x: x.date):
                print(f"{format_date(i.date):<10} {i.desc:<30}"
                      f" {i.hours:>5.2f} {i.rate:>8.2f} {i.amount:>10.2f}")
            print("-"*65)
            print(f"{'Total Service Fees':>55} {self.total_services():>10.2f}\n")
        else:
            print("No services.\n")
        if self.costs:
            print("COSTS:")
            print(f"{'Desc':<30} {'Qty':>5} {'Unit':>8} {'Total':>10}")
            print("-"*55)
            for c in self.costs:
                print(f"{c.desc:<30} {c.qty:>5.2f}"
                      f" {c.unit_price:>8.2f} {c.total:>10.2f}")
            print("-"*55)
            print(f"{'Total Costs':>45} {self.total_costs():>10.2f}\n")
        else:
            print("No costs.\n")
        print(f"GRAND TOTAL: {self.grand_total():.2f}\n")

    def generate_pdf(self, filename=None):
        # choose dynamic font
        svc_count  = len(self.services) + 1
        cost_count = len(self.costs) + 1
        total_rows = svc_count + cost_count + 6
        chosen_pt  = None
        for pt in range(MAX_FONT_PT, MIN_FONT_PT-1, -1):
            if total_rows * (pt*0.35) < (
                FPDF(format=PAGE_FORMAT).h
                - mm_from_inches(letterhead_margin_in())
                - TOP_MARGIN_MM
            ):
                chosen_pt = pt
                break
        chosen_pt = chosen_pt or MIN_FONT_PT

        pdf = FPDF(format=PAGE_FORMAT)
        pdf.set_auto_page_break(False)
        pdf.add_page()
        pdf.set_font(FONT_FAMILY, '', chosen_pt)
        pdf.font_size_pt = chosen_pt
        pdf.ln_height_mm = chosen_pt * 0.35

        # letterhead margin + heading
        pdf.set_y(mm_from_inches(letterhead_margin_in()))
        pdf.set_font(FONT_FAMILY, 'B', chosen_pt+4)
        pdf.cell(0, pdf.ln_height_mm*2, "Invoice", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(pdf.ln_height_mm/2)
        pdf.set_font(FONT_FAMILY, '', chosen_pt)
        pdf.cell(0, pdf.ln_height_mm, f"Invoice for: {self.client_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, pdf.ln_height_mm, f"Date:        {self.invoice_date}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(pdf.ln_height_mm)

        # SERVICES table
        svc_rows = [
            [ format_date(i.date), i.desc, f"{i.hours:.2f}", f"{i.rate:,.2f}", f"{i.amount:,.2f}" ]
            for i in sorted(self.services, key=lambda x: x.date)
        ]
        svc_col_w = [25, 80, 25, 30, 30]
        svc_align = ['L', 'L', 'R', 'R', 'R']
        paginate_table(pdf, svc_rows, svc_col_w, headers=["Date","Service","Hrs","Rate","Amt"], alignments=svc_align)
        pdf.ln(pdf.ln_height_mm/2)

        # TOTAL SERVICE FEES row
        row_h   = pdf.ln_height_mm
        w_label = sum(svc_col_w[:-1])
        label   = "TOTAL SERVICE FEES"
        text_w  = pdf.get_string_width(label)
        if text_w > w_label-2:
            new_pt = max(MIN_FONT_PT, chosen_pt*((w_label-2)/text_w))
            pdf.set_font(FONT_FAMILY, 'B', new_pt)
        else:
            pdf.set_font(FONT_FAMILY, 'B', chosen_pt)
        pdf.set_x(LEFT_MARGIN_MM)
        pdf.cell(w_label, row_h, label,     border=1, align='R')
        pdf.set_font(FONT_FAMILY, 'B', chosen_pt)
        pdf.cell(svc_col_w[-1], row_h, f"{self.total_services():,.2f}", border=1, align='R')
        pdf.ln(row_h*1.5)

        # COSTS table
        cost_rows = [
            [ c.desc, f"{c.qty:,.2f}", f"{c.unit_price:,.2f}", f"{c.total:,.2f}" ]
            for c in self.costs
        ]
        cost_col_w = [80, 30, 30, 30]
        cost_align = ['L', 'R', 'R', 'R']
        paginate_table(pdf, cost_rows, cost_col_w, headers=["Description","Qty","Unit","Total"], alignments=cost_align)
        pdf.ln(pdf.ln_height_mm/2)

        # TOTAL COSTS row
        w_label2 = sum(cost_col_w[:-1])
        label2   = "TOTAL COSTS"
        text_w2  = pdf.get_string_width(label2)
        if text_w2 > w_label2-2:
            new_pt2 = max(MIN_FONT_PT, chosen_pt*((w_label2-2)/text_w2))
            pdf.set_font(FONT_FAMILY, 'B', new_pt2)
        else:
            pdf.set_font(FONT_FAMILY, 'B', chosen_pt)
        pdf.set_x(LEFT_MARGIN_MM)
        pdf.cell(w_label2, row_h, label2,           border=1, align='R')
        pdf.set_font(FONT_FAMILY, 'B', chosen_pt)
        pdf.cell(cost_col_w[-1], row_h, f"{self.total_costs():,.2f}", border=1, align='R')
        pdf.ln(row_h*1.5)

        # Boxed Grand Total
        pdf.set_font(FONT_FAMILY, 'B', chosen_pt+2)
        gt = f"GRAND TOTAL: {self.grand_total():,.2f}"
        w_gt = pdf.get_string_width(gt) + 6
        pdf.set_x(pdf.w - LEFT_MARGIN_MM - w_gt)
        pdf.set_draw_color(0,0,0)
        pdf.set_line_width(0.5)
        pdf.cell(w_gt, row_h*1.2, gt, border=1, align='C')

        # save
        safe_date = self.invoice_date.replace('/','-')
        out = filename or f"{self.client_name.replace(' ','_')}_invoice[{safe_date}].pdf"
        pdf.output(out)
        print(f"PDF saved as: {out}")

# ---- UI ----
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QTextEdit, QGroupBox, QFrame, QStatusBar, QFileDialog
)
from PySide6.QtGui import QShortcut, QKeySequence, QDesktopServices

def default_pdf_filename(inv: Invoice) -> str:
    return render_filename_from_template(inv)

class InvoiceWizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Builder – UI (parity with CLI)")
        self.setMinimumWidth(820)

        self.invoice: Invoice | None = None
        self._suppress_service_table = False
        self._suppress_cost_table = False
        self._hours_dirty = False  # require explicit entry of hours (0 allowed if typed)
        self.require_explicit_zero = True  # updated in load_settings()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # --- Step 1: Meta ---
        self.page_meta = QWidget()
        self.stack.addWidget(self.page_meta)
        v1 = QVBoxLayout(self.page_meta)
        title1 = QLabel("▶ Invoice Meta")
        title1.setStyleSheet("font-size:18px; font-weight:600;")
        v1.addWidget(title1)

        form1 = QFormLayout()
        self.client_name_in = QLineEdit()
        self.date_in = QLineEdit()
        self.date_in.setPlaceholderText("MM/DD/YYYY")
        self.date_in.setText(datetime.now().strftime("%m/%d/%Y"))
        self.rate_in = QDoubleSpinBox()
        self.rate_in.setDecimals(2)
        self.rate_in.setMinimum(0.01)
               # max big enough
        self.rate_in.setMaximum(9999999.0)
        self.rate_in.setSingleStep(25.0)
        # initial; will be overridden by settings
        self.rate_in.setValue(250.0)

        form1.addRow("Client's Name:", self.client_name_in)
        form1.addRow("Invoice Date:", self.date_in)
        form1.addRow("Default hourly rate:", self.rate_in)
        v1.addLayout(form1)

        bar1 = QHBoxLayout()
        bar1.addStretch(1)
        self.meta_next = QPushButton("Next →")
        bar1.addWidget(self.meta_next)
        v1.addLayout(bar1)

        # Enter should advance if valid
        self.client_name_in.returnPressed.connect(self.go_services)
        self.date_in.returnPressed.connect(self.go_services)
        self.rate_in.lineEdit().returnPressed.connect(self.go_services)

        self.meta_next.clicked.connect(self.go_services)

        # Load settings (rate, explicit-zero rule)
        self.load_settings()

        # --- Step 2: Services ---
        self.page_services = QWidget()
        self.stack.addWidget(self.page_services)
        v2 = QVBoxLayout(self.page_services)
        title2 = QLabel("▶ Enter SERVICES (click Done when finished; Remove pops last)")
        title2.setStyleSheet("font-size:18px; font-weight:600;")
        v2.addWidget(title2)

        entry_box = QGroupBox("Add service")
        entry_form = QFormLayout(entry_box)
        self.s_desc = QLineEdit()
        self.s_date = QLineEdit()
        self.s_date.setPlaceholderText("MM/DD/YYYY")
        self.s_date.setText(datetime.now().strftime("%m/%d/%Y"))
        self.s_hours = QDoubleSpinBox()
        self.s_hours.setDecimals(2)
        self.s_hours.setMinimum(0.0)  # explicit 0 required if setting says so
        self.s_hours.setMaximum(10000.0)
        self.s_hours.setSingleStep(0.25)
        # track explicit typing of hours
        self.s_hours.lineEdit().textEdited.connect(self._mark_hours_dirty)

        entry_form.addRow("Service desc:", self.s_desc)
        entry_form.addRow("Date (M/D/YY or YYYY):", self.s_date)
        entry_form.addRow("Hours (type 0 if no charge):", self.s_hours)

        btnrow = QHBoxLayout()
        self.s_add = QPushButton("Add Service (Enter)")
        self.s_cancel = QPushButton("Clear")
        btnrow.addWidget(self.s_add)
        btnrow.addWidget(self.s_cancel)
        entry_form.addRow(btnrow)

        v2.addWidget(entry_box)

        self.s_table = QTableWidget(0, 3)
        self.s_table.setHorizontalHeaderLabels(["Date", "Description", "Hours"])
        self.s_table.horizontalHeader().setStretchLastSection(True)
        v2.addWidget(self.s_table)

        line = QFrame(); line.setFrameShape(QFrame.HLine); v2.addWidget(line)
        actions = QHBoxLayout()
        self.s_back = QPushButton("← Back")
        self.s_remove_last = QPushButton("Remove last service")
        self.s_done = QPushButton("Done →")
        actions.addWidget(self.s_back)
        actions.addStretch(1)
        actions.addWidget(self.s_remove_last)
        actions.addWidget(self.s_done)
        v2.addLayout(actions)

        self.s_totals_lbl = QLabel("")
        self.s_totals_lbl.setAlignment(Qt.AlignRight)
        v2.addWidget(self.s_totals_lbl)

        # wiring
        self.s_add.clicked.connect(self.add_service)
        self.s_cancel.clicked.connect(self.clear_service_form)
        self.s_back.clicked.connect(self.confirm_reset_to_meta)
        self.s_remove_last.clicked.connect(self.remove_last_service)
        self.s_done.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        self.s_desc.returnPressed.connect(self.add_service)
        self.s_hours.lineEdit().returnPressed.connect(self.add_service)
        self.s_date.returnPressed.connect(self.add_service)

        # Table edit -> save back to data
        self.s_table.itemChanged.connect(self.on_service_item_changed)

        # Tab order for rapid service entry
        self.setTabOrder(self.s_desc, self.s_date)
        self.setTabOrder(self.s_date, self.s_hours)
        self.setTabOrder(self.s_hours, self.s_add)

        # Shortcuts
        self.short_dup_service = QShortcut(QKeySequence("Ctrl+D"), self.page_services)
        self.short_dup_service.activated.connect(self.prefill_last_service)

        # --- Step 3: Costs ---
        self.page_costs = QWidget()
        self.stack.addWidget(self.page_costs)
        v3 = QVBoxLayout(self.page_costs)
        title3 = QLabel("▶ Enter COST ITEMS (click Done when finished)")
        title3.setStyleSheet("font-size:18px; font-weight:600;")
        v3.addWidget(title3)

        c_box = QGroupBox("Add cost")
        c_form = QFormLayout(c_box)
        self.c_desc = QLineEdit()
        self.c_qty = QDoubleSpinBox(); self.c_qty.setDecimals(2); self.c_qty.setMinimum(0.0); self.c_qty.setMaximum(1e9); self.c_qty.setSingleStep(1.0)
        self.c_price = QDoubleSpinBox(); self.c_price.setDecimals(2); self.c_price.setMinimum(0.0); self.c_price.setMaximum(1e9); self.c_price.setSingleStep(1.0)
        c_form.addRow("Cost desc:", self.c_desc)
        c_form.addRow("Quantity:", self.c_qty)
        c_form.addRow("Unit price:", self.c_price)
        c_btnrow = QHBoxLayout()
        self.c_add = QPushButton("Add Cost (Enter)")
        self.c_clear = QPushButton("Clear")
        c_btnrow.addWidget(self.c_add)
        c_btnrow.addWidget(self.c_clear)
        c_form.addRow(c_btnrow)
        v3.addWidget(c_box)

        self.c_table = QTableWidget(0, 3)
        self.c_table.setHorizontalHeaderLabels(["Description", "Qty", "Unit Price"])
        self.c_table.horizontalHeader().setStretchLastSection(True)
        v3.addWidget(self.c_table)

        line2 = QFrame(); line2.setFrameShape(QFrame.HLine); v3.addWidget(line2)
        actions3 = QHBoxLayout()
        self.c_back = QPushButton("← Back")
        self.c_done = QPushButton("Done →")
        actions3.addWidget(self.c_back)
        actions3.addStretch(1)
        actions3.addWidget(self.c_done)
        v3.addLayout(actions3)

        self.c_totals_lbl = QLabel("")
        self.c_totals_lbl.setAlignment(Qt.AlignRight)
        v3.addWidget(self.c_totals_lbl)

        self.c_add.clicked.connect(self.add_cost)
        self.c_clear.clicked.connect(self.clear_cost_form)
        self.c_back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_services))
        self.c_done.clicked.connect(self.go_review)
        self.c_desc.returnPressed.connect(self.add_cost)
        self.c_qty.lineEdit().returnPressed.connect(self.add_cost)
        self.c_price.lineEdit().returnPressed.connect(self.add_cost)

        # Table edit -> save back to data
        self.c_table.itemChanged.connect(self.on_cost_item_changed)

        # Tab order for rapid cost entry
        self.setTabOrder(self.c_desc, self.c_qty)
        self.setTabOrder(self.c_qty, self.c_price)
        self.setTabOrder(self.c_price, self.c_add)

        # Shortcut: duplicate last cost
        self.short_dup_cost = QShortcut(QKeySequence("Ctrl+D"), self.page_costs)
        self.short_dup_cost.activated.connect(self.prefill_last_cost)

        # --- Step 4: Review & Export ---
        self.page_review = QWidget()
        self.stack.addWidget(self.page_review)
        v4 = QVBoxLayout(self.page_review)
        title4 = QLabel("▶ Review & Export")
        title4.setStyleSheet("font-size:18px; font-weight:600;")
        v4.addWidget(title4)

        self.console_preview = QTextEdit(); self.console_preview.setReadOnly(True)
        self.console_preview.setStyleSheet("font-family: Consolas, monospace; font-size:12px;")
        v4.addWidget(self.console_preview)

        self.filename_hint = QLabel("")
        self.filename_hint.setAlignment(Qt.AlignRight)
        v4.addWidget(self.filename_hint)

        line3 = QFrame(); line3.setFrameShape(QFrame.HLine); v4.addWidget(line3)
        actions4 = QHBoxLayout()
        self.r_menu = QPushButton("Return to Menu")
        self.r_back = QPushButton("← Back")
        self.r_export = QPushButton("Generate PDF")
        self.r_new = QPushButton("New Invoice")
        actions4.addWidget(self.r_menu)
        actions4.addStretch(1)
        actions4.addWidget(self.r_back)
        actions4.addWidget(self.r_export)
        actions4.addWidget(self.r_new)
        v4.addLayout(actions4)

        self.r_menu.clicked.connect(self.start_new_invoice)
        self.r_back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        self.r_export.clicked.connect(self.export_pdf)
        self.r_new.clicked.connect(self.start_new_invoice)

        # Start at meta
        self.stack.setCurrentWidget(self.page_meta)

    # --- helpers/signals ---
    def _mark_hours_dirty(self, *_):
        self._hours_dirty = True

    # ---- Meta navigation ----
    def go_services(self):
        name = self.client_name_in.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Client's Name cannot be empty.")
            return
        rate = self.rate_in.value()
        if rate <= 0:
            QMessageBox.warning(self, "Validation", "Default hourly rate must be > 0.")
            return
        try:
            dt = parse_user_date(self.date_in.text())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Use M/D, M/D/YY, or M/D/YYYY for the date.")
            return
        inv_date = format_date_full(dt)
        self.date_in.setText(inv_date)
        self.invoice = Invoice(name, inv_date, rate)

        # persist default rate through centralized settings
        self.persist_rate_now()

        self.update_totals_labels()
        self.stack.setCurrentWidget(self.page_services)

    def go_review(self):
        if self.invoice is None:
            return
        buf = io.StringIO()
        _stdout = sys.stdout
        try:
            sys.stdout = buf
            self.invoice.print_console()
        finally:
            sys.stdout = _stdout
        self.console_preview.setPlainText(buf.getvalue())
        hint = default_pdf_filename(self.invoice)
        self.filename_hint.setText(f"Default file name: <b>{hint}</b>")
        self.stack.setCurrentWidget(self.page_review)

    # ---- New invoice / return to menu ----
    def start_new_invoice(self):
        # clear invoice data, reset meta fields for a new one, go to meta
        self.invoice = None
        self._suppress_service_table = True
        self._suppress_cost_table = True
        try:
            self.s_table.setRowCount(0)
            self.c_table.setRowCount(0)
        finally:
            self._suppress_service_table = False
            self._suppress_cost_table = False
        self.update_totals_labels()

        # reset meta inputs for quick start
        self.client_name_in.clear()
        self.date_in.setText(datetime.now().strftime("%m/%d/%Y"))
        # keep rate_in as-is (it's persisted), user can change if needed

        self.stack.setCurrentWidget(self.page_meta)
        self.client_name_in.setFocus()

    # ---- Services actions ----
    def clear_service_form(self):
        self.s_desc.clear()
        self.s_date.setText(datetime.now().strftime("%m/%d/%Y"))
        self.s_hours.setValue(0.0)
        self._hours_dirty = False
        self.s_desc.setFocus()
        self.s_desc.selectAll()

    def add_service(self):
        if self.invoice is None:
            return
        raw_desc = self.s_desc.text().strip()
        if not raw_desc:
            QMessageBox.warning(self, "Validation", "Service description cannot be empty.")
            return
        try:
            d_dt = parse_user_date(self.s_date.text())
            self.s_date.setText(format_date_full(d_dt))
        except ValueError:
            QMessageBox.warning(self, "Validation", "Use M/D, M/D/YY, or M/D/YYYY for the service date.")
            return

        # require explicit entry for hours; typing '0' is allowed (if setting requires)
        if self.require_explicit_zero and self.s_hours.value() == 0.0 and not self._hours_dirty:
            QMessageBox.warning(self, "Validation", "Hours required. If this is a no-charge entry, type 0 explicitly.")
            return

        hrs = float(self.s_hours.value())
        if hrs < 0:
            QMessageBox.warning(self, "Validation", "Hours must be ≥ 0.")
            return

        clean = normalize_desc(raw_desc)
        self.invoice.add_service(d_dt, clean, hrs)
        row = self.s_table.rowCount()
        self._suppress_service_table = True
        try:
            self.s_table.insertRow(row)
            self.s_table.setItem(row, 0, QTableWidgetItem(format_date(d_dt)))
            self.s_table.setItem(row, 1, QTableWidgetItem(clean))
            self.s_table.setItem(row, 2, QTableWidgetItem(f"{hrs:.2f}"))
        finally:
            self._suppress_service_table = False

        self.clear_service_form()
        self.update_totals_labels()

    def remove_last_service(self):
        if self.invoice is None:
            return
        if not self.invoice.services:
            QMessageBox.information(self, "Info", "Nothing to remove.")
            return
        self.invoice.services.pop()
        last = self.s_table.rowCount() - 1
        if last >= 0:
            self._suppress_service_table = True
            try:
                self.s_table.removeRow(last)
            finally:
                self._suppress_service_table = False
        self.update_totals_labels()

    def prefill_last_service(self):
        if self.invoice and self.invoice.services:
            last = self.invoice.services[-1]
            self.s_desc.setText(last.desc)
            self.s_date.setText(format_date_full(last.date))
            self.s_hours.setValue(float(last.hours))
            self._hours_dirty = True
            self.s_desc.setFocus(); self.s_desc.selectAll()

    def on_service_item_changed(self, item):
        if self._suppress_service_table or self.invoice is None:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.invoice.services):
            return
        svc = self.invoice.services[row]
        text = item.text().strip()
        if col == 0:  # Date
            try:
                d_dt = parse_user_date(text)
            except ValueError:
                QMessageBox.warning(self, "Validation", "Bad date. Use M/D, M/D/YY, or M/D/YYYY.")
                self._suppress_service_table = True
                try:
                    item.setText(format_date(svc.date))
                finally:
                    self._suppress_service_table = False
                return
            svc.date = d_dt
            self._suppress_service_table = True
            try:
                item.setText(format_date(d_dt))
            finally:
                self._suppress_service_table = False
        elif col == 1:  # Description
            new_desc = normalize_desc(text)
            svc.desc = new_desc
            self._suppress_service_table = True
            try:
                item.setText(new_desc)
            finally:
                self._suppress_service_table = False
        elif col == 2:  # Hours
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Hours must be a number ≥ 0.")
                self._suppress_service_table = True
                try:
                    item.setText(f"{svc.hours:.2f}")
                finally:
                    self._suppress_service_table = False
                return
            svc.hours = val
            self._suppress_service_table = True
            try:
                item.setText(f"{val:.2f}")
            finally:
                self._suppress_service_table = False
        self.update_totals_labels()

    # ---- Costs actions ----
    def clear_cost_form(self):
        self.c_desc.clear()
        self.c_qty.setValue(0.0)
        self.c_price.setValue(0.0)
        self.c_desc.setFocus()
        self.c_desc.selectAll()

    def add_cost(self):
        if self.invoice is None:
            return
        raw_desc = self.c_desc.text().strip()
        if not raw_desc:
            QMessageBox.warning(self, "Validation", "Cost description cannot be empty.")
            return
        qty = self.c_qty.value()
        if qty < 0:
            QMessageBox.warning(self, "Validation", "Quantity must be ≥ 0.")
            return
        price = self.c_price.value()
        if price < 0:
            QMessageBox.warning(self, "Validation", "Unit price must be ≥ 0.")
            return
        clean = normalize_desc(raw_desc)
        self.invoice.add_cost(clean, float(qty), float(price))
        row = self.c_table.rowCount()
        self._suppress_cost_table = True
        try:
            self.c_table.insertRow(row)
            self.c_table.setItem(row, 0, QTableWidgetItem(clean))
            self.c_table.setItem(row, 1, QTableWidgetItem(f"{qty:.2f}"))
            self.c_table.setItem(row, 2, QTableWidgetItem(f"{price:.2f}"))
        finally:
            self._suppress_cost_table = False
        self.clear_cost_form()
        self.update_totals_labels()

    def prefill_last_cost(self):
        if self.invoice and self.invoice.costs:
            last = self.invoice.costs[-1]
            self.c_desc.setText(last.desc)
            self.c_qty.setValue(float(last.qty))
            self.c_price.setValue(float(last.unit_price))
            self.c_desc.setFocus(); self.c_desc.selectAll()

    def on_cost_item_changed(self, item):
        if self._suppress_cost_table or self.invoice is None:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.invoice.costs):
            return
        cost = self.invoice.costs[row]
        text = item.text().strip()
        if col == 0:  # desc
            new_desc = normalize_desc(text)
            cost.desc = new_desc
            self._suppress_cost_table = True
            try:
                item.setText(new_desc)
            finally:
                self._suppress_cost_table = False
        elif col == 1:  # qty
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Quantity must be a number ≥ 0.")
                self._suppress_cost_table = True
                try:
                    item.setText(f"{cost.qty:.2f}")
                finally:
                    self._suppress_cost_table = False
                return
            cost.qty = val
            self._suppress_cost_table = True
            try:
                item.setText(f"{val:.2f}")
            finally:
                self._suppress_cost_table = False
        elif col == 2:  # unit price
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Unit price must be a number ≥ 0.")
                self._suppress_cost_table = True
                try:
                    item.setText(f"{cost.unit_price:.2f}")
                finally:
                    self._suppress_cost_table = False
                return
            cost.unit_price = val
            self._suppress_cost_table = True
            try:
                item.setText(f"{val:.2f}")
            finally:
                self._suppress_cost_table = False
        self.update_totals_labels()

    # ---- Export ----
    def export_pdf(self):
        if self.invoice is None:
            return

        # Pull default export dir from settings (ensures existence)
        try:
            export_dir = settings.get_export_dir(create=True)
        except Exception:
            export_dir = Path.home()

        filename = default_pdf_filename(self.invoice)
        outfile = Path(export_dir) / filename

        # If path doesn't exist (or user wants a different folder), prompt and persist
        if not outfile.parent.exists():
            chosen = QFileDialog.getExistingDirectory(self, "Choose export folder", os.path.expanduser("~"))
            if not chosen:
                return
            settings.set_("general.default_export_dir", chosen)
            outfile = Path(chosen) / filename

        try:
            self.invoice.generate_pdf(filename=str(outfile))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate PDF:\n{e}")
            return

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("PDF saved")
        msg.setText(f"Saved to:\n{outfile}")
        btn_open = msg.addButton("Open PDF", QMessageBox.AcceptRole)
        btn_folder = msg.addButton("Open Folder", QMessageBox.ActionRole)
        btn_new = msg.addButton("New Invoice", QMessageBox.ActionRole)
        btn_menu = msg.addButton("Return to Menu", QMessageBox.ActionRole)
        btn_close = msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_open:
            try:
                if sys.platform.startswith('win'):
                    os.startfile(str(outfile))  # type: ignore[attr-defined]
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(outfile)))
            except Exception:
                pass
        elif clicked == btn_folder:
            try:
                if sys.platform.startswith('win'):
                    os.system(f'explorer /select,"{outfile}"')
                else:
                    folder = str(outfile.parent)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            except Exception:
                pass
        elif clicked in (btn_new, btn_menu):
            self.start_new_invoice()

    # ---- Reset to meta (legacy back) ----
    def confirm_reset_to_meta(self):
        # Keep the discard dialog (you okayed this)
        if self.invoice and (self.invoice.services or self.invoice.costs):
            res = QMessageBox.question(
                self,
                "Discard invoice?",
                "Going back to the start will discard the current invoice data. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return
        self.invoice = None
        self._suppress_service_table = True
        self._suppress_cost_table = True
        try:
            self.s_table.setRowCount(0)
            self.c_table.setRowCount(0)
        finally:
            self._suppress_service_table = False
            self._suppress_cost_table = False
        self.update_totals_labels()
        self.stack.setCurrentWidget(self.page_meta)

    # ---- Totals / settings ----
    def update_totals_labels(self):
        if self.invoice is None:
            if hasattr(self, 'status'):
                self.status.showMessage("")
            return
        svc_total = self.invoice.total_services()
        cost_total = self.invoice.total_costs()
        grand = self.invoice.grand_total()
        hours_sum = sum((i.hours for i in self.invoice.services), 0.0)
        self.s_totals_lbl.setText(f"Service fees total: {svc_total:,.2f}")
        self.c_totals_lbl.setText(f"Costs total: {cost_total:,.2f}    |    GRAND TOTAL: <b>{grand:,.2f}</b>")
        if hasattr(self, 'status'):
            self.status.showMessage(f"Services: ${svc_total:,.2f} | Hours: {hours_sum:.2f} | Costs: ${cost_total:,.2f} | Grand: ${grand:,.2f}")

    def load_settings(self):
        # default rate
        try:
            rate = float(settings.get("general.default_rate", 250.0))
            self.rate_in.setValue(rate if rate > 0 else 250.0)
        except Exception:
            self.rate_in.setValue(250.0)
        # require explicit zero hours (default True)
        self.require_explicit_zero = bool(settings.get("invoice.require_explicit_zero_hours", True))

    def persist_rate_now(self):
        try:
            settings.set_("general.default_rate", float(self.rate_in.value()))
        except Exception:
            pass

def main():
    app = QApplication(sys.argv)
    w = InvoiceWizard()
    w.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
