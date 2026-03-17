from __future__ import annotations

import io
import json
import os
import re
import sys
from datetime import datetime
from math import floor
from pathlib import Path
from typing import Any, List, Tuple, Set

from fpdf import FPDF, XPos, YPos
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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

PAGE_FORMAT = "Letter"
FONT_FAMILY = "Helvetica"
MAX_FONT_PT = 14
MIN_FONT_PT = 10
LEFT_MARGIN_MM = 15
TOP_MARGIN_MM = 20
BOTTOM_MARGIN_MM = 5
ROW_PAD_MM = 0.8
DESC_INNER_PAD_X = 1.0


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def mm_from_inches(inches: float) -> float:
    return inches * 25.4


def letterhead_margin_in() -> float:
    try:
        return float(settings.get("letterhead.top_margin_in", 2.5))
    except Exception:
        return 2.5


def page_top_y(pdf: FPDF) -> float:
    return mm_from_inches(letterhead_margin_in()) if pdf.page_no() == 1 else TOP_MARGIN_MM


def normalize_desc(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


def _avg_char_mm(pdf: FPDF) -> float:
    sample = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
    w = pdf.get_string_width(sample)
    return max(0.1, w / len(sample))


def wrap_text_lines(pdf: FPDF, text: str, max_w_mm: float) -> List[str]:
    if not text:
        return [""]

    tokens = re.split(r"(\s+|[-,/;:])", text)
    tokens = [t for t in tokens if t is not None]

    lines: List[str] = []
    cur = ""

    def too_wide(s: str) -> bool:
        return pdf.get_string_width(s) > max_w_mm - 0.5

    for tok in tokens:
        if tok == "":
            continue

        candidate = (cur + tok) if cur else tok

        if not too_wide(candidate):
            cur = candidate
            continue

        if pdf.get_string_width(tok) > max_w_mm - 0.5:
            if cur:
                lines.append(cur.rstrip())
                cur = ""

            buf: List[str] = []
            for ch in tok:
                buf.append(ch)
                if pdf.get_string_width("".join(buf)) > max_w_mm - 0.5:
                    last = buf.pop()
                    if buf:
                        lines.append("".join(buf))
                    buf = [last]
            cur = "".join(buf)
            continue

        if cur:
            lines.append(cur.rstrip())
        cur = tok.lstrip()

    if cur:
        lines.append(cur.rstrip())

    return lines or [""]


def _draw_header(pdf: FPDF, col_widths: List[float], headers: List[str], row_h: float) -> None:
    pdf.set_x(LEFT_MARGIN_MM)
    pdf.set_font(FONT_FAMILY, "B", pdf.font_size_pt)
    pdf.set_fill_color(200, 220, 255)
    for w, h in zip(col_widths, headers):
        pdf.cell(w, row_h, h, border=1, align="C", fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(row_h)
    pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
    pdf.set_fill_color(245, 245, 245)


def _ensure_room_or_new_page(pdf: FPDF, needed_h: float, redraw_header_cb) -> None:
    usable_bottom = pdf.h - BOTTOM_MARGIN_MM
    if pdf.get_y() + needed_h > usable_bottom:
        pdf.add_page()
        pdf.set_y(page_top_y(pdf))
        redraw_header_cb()


def _draw_cell_box(pdf: FPDF, x: float, y: float, w: float, h: float, fill: bool) -> None:
    pdf.set_xy(x, y)
    pdf.cell(w, h, "", border=1, fill=fill)


def _text_at(pdf: FPDF, x: float, y: float, w: float, h: float, text: str, align: str, v_center: bool) -> None:
    baseline_y = y + (h - pdf.ln_height_mm) / 2.0 if v_center else y + ROW_PAD_MM
    pdf.set_xy(x, baseline_y)
    pdf.cell(w, pdf.ln_height_mm, text, border=0, align=align, new_x=XPos.RIGHT, new_y=YPos.TOP)


def money_str(value: float) -> str:
    use_commas = bool(settings.get("pdf.thousand_separators", True))
    return f"{value:,.2f}" if use_commas else f"{value:.2f}"


def sanitize_client(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _\-]", "", name).strip()
    return re.sub(r"\s+", "_", s)


def date_for_filename(ui_mmddyyyy: str) -> str:
    return ui_mmddyyyy.replace("/", "-")


def render_filename_from_template(inv: "Invoice") -> str:
    template = settings.get("pdf.file_naming_template", "{client}_invoice[{date}].pdf")
    client = sanitize_client(inv.client_name)
    date_str = date_for_filename(inv.invoice_date)
    try:
        return template.format(client=client, date=date_str)
    except Exception:
        return f"{client}_invoice[{date_str}].pdf"


def uniquify_path(p: Path) -> Path:
    parent, stem, suffix = p.parent, p.stem, p.suffix or ".pdf"
    candidate = parent / f"{stem}{suffix}"
    n = 1
    while candidate.exists():
        candidate = parent / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def json_path_for_pdf_path(pdf_path: Path) -> Path:
    json_dir = settings.get_json_dir(create=True)
    return Path(json_dir) / f"{pdf_path.stem}.json"


def pdf_path_for_invoice(inv: "Invoice") -> Path:
    return Path(settings.get_export_dir(create=True)) / render_filename_from_template(inv)


def json_path_for_invoice(inv: "Invoice") -> Path:
    return Path(settings.get_json_dir(create=True)) / (Path(render_filename_from_template(inv)).stem + ".json")


def parse_input_date(s: str) -> datetime:
    parts = s.strip().split("/")
    if len(parts) == 2:
        m, d = map(int, parts)
        y = datetime.now().year
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

    parts = s.split("/")
    now = datetime.now()

    if len(parts) == 2:
        m, d = map(int, parts)
        y = now.year
    elif len(parts) == 3:
        m, d, y_raw = parts
        m = int(m)
        d = int(d)
        y_raw = int(y_raw)
        y = 2000 + y_raw if y_raw < 100 else y_raw
    else:
        raise ValueError("Use M/D, M/D/YY, or M/D/YYYY")

    return datetime(y, m, d)


def format_date_full(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y")


def open_local_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except Exception:
        pass


def list_invoice_json_files() -> List[Path]:
    json_dir = settings.get_json_dir(create=True)
    files = sorted(json_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# -----------------------------------------------------------------------------
# PDF rendering
# -----------------------------------------------------------------------------

def paginate_services_wrapped(
    pdf: FPDF,
    rows: List[List[str]],
    col_widths: List[float],
    headers: List[str],
) -> None:
    row_h = pdf.ln_height_mm
    usable_bottom = pdf.h - BOTTOM_MARGIN_MM

    def redraw_header():
        _draw_header(pdf, col_widths, headers, row_h)

    redraw_header()
    fill = True

    for row in rows:
        date_txt, desc_txt, hrs_txt, rate_txt, amt_txt = row
        desc_w = col_widths[1]

        pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
        desc_lines = wrap_text_lines(pdf, desc_txt, desc_w - 2 * DESC_INNER_PAD_X)

        start_idx = 0
        while start_idx < len(desc_lines):
            y0 = pdf.get_y()
            available_h = usable_bottom - y0
            min_row_h = row_h + 2 * ROW_PAD_MM

            if available_h < min_row_h:
                pdf.add_page()
                pdf.set_y(page_top_y(pdf))
                redraw_header()
                y0 = pdf.get_y()
                available_h = usable_bottom - y0

            max_lines_here = max(1, floor((available_h - 2 * ROW_PAD_MM) / row_h))
            end_idx = min(len(desc_lines), start_idx + max_lines_here)
            this_lines = desc_lines[start_idx:end_idx]
            this_row_h = ROW_PAD_MM + (row_h * max(1, len(this_lines))) + ROW_PAD_MM

            x = LEFT_MARGIN_MM
            _draw_cell_box(pdf, x, y0, col_widths[0], this_row_h, fill)
            x += col_widths[0]
            _draw_cell_box(pdf, x, y0, col_widths[1], this_row_h, fill)
            x += col_widths[1]
            _draw_cell_box(pdf, x, y0, col_widths[2], this_row_h, fill)
            x += col_widths[2]
            _draw_cell_box(pdf, x, y0, col_widths[3], this_row_h, fill)
            x += col_widths[3]
            _draw_cell_box(pdf, x, y0, col_widths[4], this_row_h, fill)

            x = LEFT_MARGIN_MM
            _text_at(pdf, x, y0, col_widths[0], this_row_h, date_txt, "L", v_center=True)
            x += col_widths[0]

            text_x = x + DESC_INNER_PAD_X
            text_y = y0 + ROW_PAD_MM
            pdf.set_xy(text_x, text_y)
            pdf.multi_cell(
                col_widths[1] - 2 * DESC_INNER_PAD_X,
                row_h,
                "\n".join(this_lines),
                border=0,
                align="L",
                fill=False,
            )
            x += col_widths[1]

            _text_at(pdf, x, y0, col_widths[2], this_row_h, hrs_txt, "R", v_center=True)
            x += col_widths[2]
            _text_at(pdf, x, y0, col_widths[3], this_row_h, rate_txt, "R", v_center=True)
            x += col_widths[3]
            _text_at(pdf, x, y0, col_widths[4], this_row_h, amt_txt, "R", v_center=True)

            pdf.set_y(y0 + this_row_h)
            start_idx = end_idx

        fill = not fill


def paginate_flat_fee_service(
    pdf: FPDF,
    desc_txt: str,
    amount: float,
    svc_col_w: List[float],
) -> None:
    row_h = pdf.ln_height_mm
    usable_bottom = pdf.h - BOTTOM_MARGIN_MM

    left_w = sum(svc_col_w[:-1])
    amt_w = svc_col_w[-1]

    def redraw_header():
        pdf.set_x(LEFT_MARGIN_MM)
        pdf.set_font(FONT_FAMILY, "B", pdf.font_size_pt)
        pdf.set_fill_color(200, 220, 255)
        pdf.cell(left_w, row_h, "Service", border=1, align="C", fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(amt_w, row_h, "Amt", border=1, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.TOP)
        pdf.ln(row_h)
        pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
        pdf.set_fill_color(245, 245, 245)

    redraw_header()

    pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
    desc_lines = wrap_text_lines(pdf, desc_txt, left_w - 2 * DESC_INNER_PAD_X)

    y0 = pdf.get_y()
    available_h = usable_bottom - y0
    min_row_h = row_h + 2 * ROW_PAD_MM
    if available_h < min_row_h:
        pdf.add_page()
        pdf.set_y(page_top_y(pdf))
        redraw_header()
        y0 = pdf.get_y()

    this_row_h = ROW_PAD_MM + (row_h * max(1, len(desc_lines))) + ROW_PAD_MM

    x = LEFT_MARGIN_MM
    _draw_cell_box(pdf, x, y0, left_w, this_row_h, True)
    x += left_w
    _draw_cell_box(pdf, x, y0, amt_w, this_row_h, True)

    text_x = LEFT_MARGIN_MM + DESC_INNER_PAD_X
    text_y = y0 + ROW_PAD_MM
    pdf.set_xy(text_x, text_y)
    pdf.multi_cell(
        left_w - 2 * DESC_INNER_PAD_X,
        row_h,
        "\n".join(desc_lines),
        border=0,
        align="L",
        fill=False,
    )

    _text_at(pdf, LEFT_MARGIN_MM + left_w, y0, amt_w, this_row_h, money_str(amount), "R", v_center=True)
    pdf.set_y(y0 + this_row_h)


def paginate_table(pdf: FPDF, rows, col_widths, headers, alignments=None) -> None:
    row_h = pdf.ln_height_mm
    base_size = pdf.font_size_pt
    min_size = MIN_FONT_PT

    if alignments is None:
        alignments = ["L"] * len(col_widths)

    def redraw_header():
        _draw_header(pdf, col_widths, headers, row_h)

    redraw_header()
    fill = True
    for row in rows:
        _ensure_room_or_new_page(pdf, row_h, redraw_header)

        pdf.set_x(LEFT_MARGIN_MM)
        for w, cell, alg in zip(col_widths, row, alignments):
            text_w = pdf.get_string_width(cell)
            if text_w > w - 2:
                scale = (w - 2) / max(1e-6, text_w)
                new_size = max(min_size, base_size * scale)
                pdf.set_font(FONT_FAMILY, "", new_size)
            else:
                pdf.set_font(FONT_FAMILY, "", base_size)

            pdf.cell(w, row_h, cell, border=1, align=alg, fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_font(FONT_FAMILY, "", base_size)
        pdf.ln(row_h)
        fill = not fill


# -----------------------------------------------------------------------------
# Domain
# -----------------------------------------------------------------------------

class LineItem:
    def __init__(self, date_obj: datetime, desc: str, hours: float, rate: float):
        self.date = date_obj
        self.desc = desc
        self.hours = hours
        self.rate = rate

    @property
    def amount(self) -> float:
        return self.hours * self.rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "desc": self.desc,
            "hours": self.hours,
            "rate": self.rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineItem":
        date_raw = str(data.get("date", "")).strip()
        try:
            date_obj = datetime.strptime(date_raw, "%Y-%m-%d")
        except Exception:
            date_obj = datetime.now()

        desc = normalize_desc(str(data.get("desc", "")))
        hours = float(data.get("hours", 0.0))
        rate = float(data.get("rate", 0.0))
        return cls(date_obj, desc, hours, rate)


class CostItem:
    def __init__(self, desc: str, qty: float, unit_price: float):
        self.desc = desc
        self.qty = qty
        self.unit_price = unit_price

    @property
    def total(self) -> float:
        return self.qty * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "desc": self.desc,
            "qty": self.qty,
            "unit_price": self.unit_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostItem":
        desc = normalize_desc(str(data.get("desc", "")))
        qty = float(data.get("qty", 0.0))
        unit_price = float(data.get("unit_price", 0.0))
        return cls(desc, qty, unit_price)


class Invoice:
    def __init__(self, client_name: str, invoice_date: str, default_rate: float):
        self.client_name = client_name
        self.invoice_date = invoice_date
        self.default_rate = default_rate
        self.services: List[LineItem] = []
        self.costs: List[CostItem] = []
        self.flat_fee_desc: str | None = None
        self.flat_fee_amount: float | None = None

    def add_service(self, dt: datetime, desc: str, hrs: float, rate: float | None = None) -> None:
        self.services.append(LineItem(dt, desc, hrs, self.default_rate if rate is None else rate))

    def add_cost(self, desc: str, qty: float, unit_price: float) -> None:
        self.costs.append(CostItem(desc, qty, unit_price))

    def total_services(self) -> float:
        base = sum(i.amount for i in self.services)
        return base + (self.flat_fee_amount or 0.0)

    def total_costs(self) -> float:
        return sum(c.total for c in self.costs)

    def grand_total(self) -> float:
        return self.total_services() + self.total_costs()

    def apply_default_rate_to_all_services(self) -> None:
        for svc in self.services:
            svc.rate = self.default_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_name": self.client_name,
            "invoice_date": self.invoice_date,
            "default_rate": self.default_rate,
            "flat_fee_desc": self.flat_fee_desc,
            "flat_fee_amount": self.flat_fee_amount,
            "services": [svc.to_dict() for svc in self.services],
            "costs": [cost.to_dict() for cost in self.costs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Invoice":
        client_name = str(data.get("client_name", "")).strip()
        invoice_date = str(data.get("invoice_date", datetime.now().strftime("%m/%d/%Y"))).strip()
        default_rate = float(data.get("default_rate", 250.0))

        inv = cls(client_name, invoice_date, default_rate)
        inv.flat_fee_desc = data.get("flat_fee_desc")
        flat_fee_amount = data.get("flat_fee_amount")
        inv.flat_fee_amount = float(flat_fee_amount) if flat_fee_amount not in (None, "") else None

        for item in data.get("services", []):
            if isinstance(item, dict):
                inv.services.append(LineItem.from_dict(item))

        for item in data.get("costs", []):
            if isinstance(item, dict):
                inv.costs.append(CostItem.from_dict(item))

        return inv

    def print_console(self) -> None:
        print(f"\n===== Invoice for {self.client_name} =====")
        print(f"Date: {self.invoice_date}    Rate: {self.default_rate:.2f}\n")
        print("SERVICES:")
        if not self.services and self.flat_fee_amount is None:
            print("No services.\n")
        else:
            print(f"{'Date':<10} {'Desc':<30} {'Hrs':>5} {'Rate':>8} {'Amt':>10}")
            print("-" * 65)
            for i in sorted(self.services, key=lambda x: x.date):
                print(
                    f"{format_date(i.date):<10} {i.desc:<30}"
                    f" {i.hours:>5.2f} {i.rate:>8.2f} {i.amount:>10.2f}"
                )
            if self.flat_fee_amount is not None:
                desc = self.flat_fee_desc or "Flat service fee"
                print(f"{'':<10} {desc:<30} {'':>5} {'':>8} {self.flat_fee_amount:>10.2f}")
            print("-" * 65)
            print(f"{'Total Service Fees':>55} {self.total_services():>10.2f}\n")

        if self.costs:
            print("COSTS:")
            print(f"{'Desc':<30} {'Qty':>5} {'Unit':>8} {'Total':>10}")
            print("-" * 55)
            for c in self.costs:
                print(f"{c.desc:<30} {c.qty:>5.2f} {c.unit_price:>8.2f} {c.total:>10.2f}")
            print("-" * 55)
            print(f"{'Total Costs':>45} {self.total_costs():>10.2f}\n")
        else:
            print("No costs.\n")

        print(f"GRAND TOTAL: {self.grand_total():.2f}\n")

    def generate_pdf(self, filename: str | None = None) -> None:
        svc_count = max(1, len(self.services) + (1 if self.flat_fee_amount is not None else 0)) + 1
        cost_count = len(self.costs) + 1
        total_rows = svc_count + cost_count + 6

        chosen_pt = None
        for pt in range(MAX_FONT_PT, MIN_FONT_PT - 1, -1):
            if total_rows * (pt * 0.35) < (FPDF(format=PAGE_FORMAT).h - mm_from_inches(letterhead_margin_in()) - TOP_MARGIN_MM):
                chosen_pt = pt
                break
        chosen_pt = chosen_pt or MIN_FONT_PT

        pdf = FPDF(format=PAGE_FORMAT)
        pdf.set_auto_page_break(False)
        pdf.add_page()
        pdf.set_font(FONT_FAMILY, "", chosen_pt)
        pdf.font_size_pt = chosen_pt
        pdf.ln_height_mm = chosen_pt * 0.35

        pdf.set_y(page_top_y(pdf))
        pdf.set_font(FONT_FAMILY, "B", chosen_pt + 4)
        pdf.cell(0, pdf.ln_height_mm * 2, "Invoice", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(pdf.ln_height_mm / 2)

        pdf.set_font(FONT_FAMILY, "", chosen_pt)
        pdf.cell(0, pdf.ln_height_mm, f"Invoice for: {self.client_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, pdf.ln_height_mm, f"Date:        {self.invoice_date}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(pdf.ln_height_mm)

        svc_col_w = [25, 80, 25, 30, 30]

        if self.flat_fee_amount is not None and not self.services:
            desc = self.flat_fee_desc or "Attorney Fees"
            paginate_flat_fee_service(pdf, desc_txt=desc, amount=self.flat_fee_amount, svc_col_w=svc_col_w)
        else:
            svc_rows: List[List[str]] = []
            for i in sorted(self.services, key=lambda x: x.date):
                svc_rows.append([
                    format_date(i.date),
                    i.desc,
                    f"{i.hours:.2f}",
                    money_str(i.rate),
                    money_str(i.amount),
                ])

            if self.flat_fee_amount is not None:
                desc = self.flat_fee_desc or "Flat service fee"
                svc_rows.append(["", desc, "", "", money_str(self.flat_fee_amount)])

            paginate_services_wrapped(pdf, svc_rows, svc_col_w, headers=["Date", "Service", "Hrs", "Rate", "Amt"])

        pdf.ln(pdf.ln_height_mm / 2)

        row_h = pdf.ln_height_mm
        w_label = sum(svc_col_w[:-1])
        label = "TOTAL SERVICE FEES"
        text_w = pdf.get_string_width(label)
        if text_w > w_label - 2:
            new_pt = max(MIN_FONT_PT, chosen_pt * ((w_label - 2) / max(1e-6, text_w)))
            pdf.set_font(FONT_FAMILY, "B", new_pt)
        else:
            pdf.set_font(FONT_FAMILY, "B", chosen_pt)

        pdf.set_x(LEFT_MARGIN_MM)
        pdf.cell(w_label, row_h, label, border=1, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font(FONT_FAMILY, "B", chosen_pt)
        pdf.cell(svc_col_w[-1], row_h, money_str(self.total_services()), border=1, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(row_h * 0.5)

        cost_rows = [[c.desc, money_str(c.qty), money_str(c.unit_price), money_str(c.total)] for c in self.costs]
        cost_col_w = [80, 30, 30, 30]
        cost_align = ["L", "R", "R", "R"]

        paginate_table(pdf, cost_rows, cost_col_w, headers=["Description", "Qty", "Unit", "Total"], alignments=cost_align)

        pdf.ln(pdf.ln_height_mm / 2)

        w_label2 = sum(cost_col_w[:-1])
        label2 = "TOTAL COSTS"
        text_w2 = pdf.get_string_width(label2)
        if text_w2 > w_label2 - 2:
            new_pt2 = max(MIN_FONT_PT, chosen_pt * ((w_label2 - 2) / max(1e-6, text_w2)))
            pdf.set_font(FONT_FAMILY, "B", new_pt2)
        else:
            pdf.set_font(FONT_FAMILY, "B", chosen_pt)

        pdf.set_x(LEFT_MARGIN_MM)
        pdf.cell(w_label2, row_h, label2, border=1, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font(FONT_FAMILY, "B", chosen_pt)
        pdf.cell(cost_col_w[-1], row_h, money_str(self.total_costs()), border=1, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(row_h * 0.5)

        pdf.set_font(FONT_FAMILY, "B", chosen_pt + 2)
        gt = f"GRAND TOTAL: {money_str(self.grand_total())}"
        w_gt = pdf.get_string_width(gt) + 6
        pdf.set_x(pdf.w - LEFT_MARGIN_MM - w_gt)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.cell(w_gt, row_h * 1.2, gt, border=1, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        safe_date = self.invoice_date.replace("/", "-")
        out = filename or f"{self.client_name.replace(' ', '_')}_invoice[{safe_date}].pdf"
        pdf.output(out)


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

def default_pdf_filename(inv: Invoice) -> str:
    return render_filename_from_template(inv)


def _svc_key(date_obj: datetime, desc: str, hours: float, rate: float) -> Tuple[str, str, float, float]:
    return (
        date_obj.strftime("%Y-%m-%d"),
        normalize_desc(desc).strip().lower(),
        round(float(hours), 4),
        round(float(rate), 4),
    )


class InvoiceWizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Builder – UI")
        self.setMinimumWidth(980)

        self.invoice: Invoice | None = None
        self.current_json_path: Path | None = None
        self.current_pdf_path: Path | None = None
        self.edit_mode = False
        self.dirty = False

        self._suppress_service_table = False
        self._suppress_cost_table = False
        self._hours_dirty = False
        self.require_explicit_zero = True

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # ---------------------------------------------------------------------
        # Page: Choose existing invoice
        # ---------------------------------------------------------------------
        self.page_open = QWidget()
        self.stack.addWidget(self.page_open)
        open_layout = QVBoxLayout(self.page_open)

        open_title = QLabel("▶ Edit Existing Invoice")
        open_title.setStyleSheet("font-size:18px; font-weight:600;")
        open_layout.addWidget(open_title)

        self.open_hint = QLabel("Saved invoice JSON files from the portable data/json folder.")
        self.open_hint.setWordWrap(True)
        open_layout.addWidget(self.open_hint)

        self.invoice_list = QListWidget()
        open_layout.addWidget(self.invoice_list)

        open_btn_row = QHBoxLayout()
        self.btn_refresh_invoice_list = QPushButton("Refresh")
        self.btn_open_json_folder = QPushButton("Open JSON Folder")
        self.btn_open_selected_invoice = QPushButton("Open Selected")
        self.btn_new_from_open_page = QPushButton("New Invoice Instead")
        open_btn_row.addWidget(self.btn_refresh_invoice_list)
        open_btn_row.addWidget(self.btn_open_json_folder)
        open_btn_row.addStretch(1)
        open_btn_row.addWidget(self.btn_new_from_open_page)
        open_btn_row.addWidget(self.btn_open_selected_invoice)
        open_layout.addLayout(open_btn_row)

        self.btn_refresh_invoice_list.clicked.connect(self.refresh_invoice_list)
        self.btn_open_json_folder.clicked.connect(lambda: open_local_path(settings.get_json_dir(create=True)))
        self.btn_open_selected_invoice.clicked.connect(self.open_selected_invoice_from_list)
        self.btn_new_from_open_page.clicked.connect(self.start_new_invoice)
        self.invoice_list.itemDoubleClicked.connect(lambda _: self.open_selected_invoice_from_list())

        # ---------------------------------------------------------------------
        # Page: Meta
        # ---------------------------------------------------------------------
        self.page_meta = QWidget()
        self.stack.addWidget(self.page_meta)
        v1 = QVBoxLayout(self.page_meta)

        title1 = QLabel("▶ Invoice Meta")
        title1.setStyleSheet("font-size:18px; font-weight:600;")
        v1.addWidget(title1)

        self.mode_label = QLabel("Mode: New Invoice")
        self.mode_label.setStyleSheet("color:#666;")
        v1.addWidget(self.mode_label)

        form1 = QFormLayout()
        self.client_name_in = QLineEdit()

        self.date_in = QLineEdit()
        self.date_in.setPlaceholderText("MM/DD/YYYY")
        self.date_in.setText(datetime.now().strftime("%m/%d/%Y"))

        self.rate_in = QDoubleSpinBox()
        self.rate_in.setDecimals(2)
        self.rate_in.setMinimum(0.01)
        self.rate_in.setMaximum(9999999.0)
        self.rate_in.setSingleStep(25.0)
        self.rate_in.setValue(250.0)

        self.apply_rate_mode = QComboBox()
        self.apply_rate_mode.addItems([
            "Do not change existing service rates",
            "Apply default hourly rate to all service lines",
        ])

        self.flat_fee_chk = QCheckBox("Flat service fee (no hourly breakdown)")
        self.flat_desc_in = QLineEdit()
        self.flat_desc_in.setPlaceholderText("e.g. Attorney Fees")
        self.flat_amount_in = QDoubleSpinBox()
        self.flat_amount_in.setDecimals(2)
        self.flat_amount_in.setMinimum(0.00)
        self.flat_amount_in.setMaximum(9999999.0)
        self.flat_amount_in.setSingleStep(50.0)

        self.flat_desc_in.setEnabled(False)
        self.flat_amount_in.setEnabled(False)
        self.flat_fee_chk.toggled.connect(self._on_flat_fee_toggled)

        form1.addRow("Client's Name:", self.client_name_in)
        form1.addRow("Invoice Date:", self.date_in)
        form1.addRow("Default hourly rate:", self.rate_in)
        form1.addRow("Rate change behavior:", self.apply_rate_mode)
        form1.addRow(self.flat_fee_chk)
        form1.addRow("Flat fee description:", self.flat_desc_in)
        form1.addRow("Flat fee amount:", self.flat_amount_in)
        v1.addLayout(form1)

        bar1 = QHBoxLayout()
        self.meta_back_to_open = QPushButton("← Open Existing")
        self.meta_back_to_open.clicked.connect(self.go_to_open_page)
        bar1.addWidget(self.meta_back_to_open)
        bar1.addStretch(1)
        self.meta_next = QPushButton("Next →")
        bar1.addWidget(self.meta_next)
        v1.addLayout(bar1)

        self.client_name_in.returnPressed.connect(self.go_services)
        self.date_in.returnPressed.connect(self.go_services)
        self.rate_in.lineEdit().returnPressed.connect(self.go_services)
        self.meta_next.clicked.connect(self.go_services)

        self.load_settings()

        # ---------------------------------------------------------------------
        # Page: Services
        # ---------------------------------------------------------------------
        self.page_services = QWidget()
        self.stack.addWidget(self.page_services)
        v2 = QVBoxLayout(self.page_services)

        title2 = QLabel("▶ Services")
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
        self.s_hours.setMinimum(0.0)
        self.s_hours.setMaximum(10000.0)
        self.s_hours.setSingleStep(0.25)
        self.s_hours.lineEdit().textEdited.connect(self._mark_hours_dirty)

        self.s_rate = QDoubleSpinBox()
        self.s_rate.setDecimals(2)
        self.s_rate.setMinimum(0.0)
        self.s_rate.setMaximum(9999999.0)
        self.s_rate.setSingleStep(25.0)

        entry_form.addRow("Service desc:", self.s_desc)
        entry_form.addRow("Date (M/D/YY or YYYY):", self.s_date)
        entry_form.addRow("Hours (type 0 if no charge):", self.s_hours)
        entry_form.addRow("Rate:", self.s_rate)

        btnrow = QHBoxLayout()
        self.s_add = QPushButton("Add Service (Enter)")
        self.s_cancel = QPushButton("Clear")
        btnrow.addWidget(self.s_add)
        btnrow.addWidget(self.s_cancel)
        entry_form.addRow(btnrow)

        v2.addWidget(entry_box)

        self.s_table = QTableWidget(0, 5)
        self.s_table.setHorizontalHeaderLabels(["Date", "Description", "Hours", "Rate", "Amount"])
        self.s_table.horizontalHeader().setStretchLastSection(True)
        v2.addWidget(self.s_table)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        v2.addWidget(line)

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

        self.s_add.clicked.connect(self.add_service)
        self.s_cancel.clicked.connect(self.clear_service_form)
        self.s_back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_meta))
        self.s_remove_last.clicked.connect(self.remove_last_service)
        self.s_done.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        self.s_desc.returnPressed.connect(self.add_service)
        self.s_hours.lineEdit().returnPressed.connect(self.add_service)
        self.s_date.returnPressed.connect(self.add_service)
        self.s_rate.lineEdit().returnPressed.connect(self.add_service)
        self.s_table.itemChanged.connect(self.on_service_item_changed)

        self.short_dup_service = QShortcut(QKeySequence("Ctrl+D"), self.page_services)
        self.short_dup_service.activated.connect(self.prefill_last_service)

        # ---------------------------------------------------------------------
        # Page: Costs
        # ---------------------------------------------------------------------
        self.page_costs = QWidget()
        self.stack.addWidget(self.page_costs)
        v3 = QVBoxLayout(self.page_costs)

        title3 = QLabel("▶ Costs")
        title3.setStyleSheet("font-size:18px; font-weight:600;")
        v3.addWidget(title3)

        c_box = QGroupBox("Add cost")
        c_form = QFormLayout(c_box)

        self.c_desc = QLineEdit()
        self.c_qty = QDoubleSpinBox()
        self.c_qty.setDecimals(2)
        self.c_qty.setMinimum(0.0)
        self.c_qty.setMaximum(1e9)
        self.c_qty.setSingleStep(1.0)

        self.c_price = QDoubleSpinBox()
        self.c_price.setDecimals(2)
        self.c_price.setMinimum(0.0)
        self.c_price.setMaximum(1e9)
        self.c_price.setSingleStep(1.0)

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

        self.c_table = QTableWidget(0, 4)
        self.c_table.setHorizontalHeaderLabels(["Description", "Qty", "Unit Price", "Amount"])
        self.c_table.horizontalHeader().setStretchLastSection(True)
        v3.addWidget(self.c_table)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        v3.addWidget(line2)

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
        self.c_table.itemChanged.connect(self.on_cost_item_changed)

        self.short_dup_cost = QShortcut(QKeySequence("Ctrl+D"), self.page_costs)
        self.short_dup_cost.activated.connect(self.prefill_last_cost)

        # ---------------------------------------------------------------------
        # Page: Review
        # ---------------------------------------------------------------------
        self.page_review = QWidget()
        self.stack.addWidget(self.page_review)
        v4 = QVBoxLayout(self.page_review)

        title4 = QLabel("▶ Review & Save")
        title4.setStyleSheet("font-size:18px; font-weight:600;")
        v4.addWidget(title4)

        self.current_file_hint = QLabel("")
        self.current_file_hint.setWordWrap(True)
        self.current_file_hint.setStyleSheet("color:#666;")
        v4.addWidget(self.current_file_hint)

        self.console_preview = QTextEdit()
        self.console_preview.setReadOnly(True)
        self.console_preview.setStyleSheet("font-family: Consolas, monospace; font-size:12px;")
        v4.addWidget(self.console_preview)

        self.filename_hint = QLabel("")
        self.filename_hint.setAlignment(Qt.AlignRight)
        v4.addWidget(self.filename_hint)

        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        v4.addWidget(line3)

        actions4 = QHBoxLayout()
        self.r_open_existing = QPushButton("Open Existing")
        self.r_back = QPushButton("← Back")
        self.r_save = QPushButton("Save")
        self.r_save_export = QPushButton("Save + Export PDF")
        self.r_save_as_new = QPushButton("Save As New")
        self.r_new = QPushButton("New Invoice")

        actions4.addWidget(self.r_open_existing)
        actions4.addStretch(1)
        actions4.addWidget(self.r_back)
        actions4.addWidget(self.r_save)
        actions4.addWidget(self.r_save_export)
        actions4.addWidget(self.r_save_as_new)
        actions4.addWidget(self.r_new)
        v4.addLayout(actions4)

        self.r_open_existing.clicked.connect(self.go_to_open_page)
        self.r_back.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_costs))
        self.r_save.clicked.connect(self.save_current_invoice)
        self.r_save_export.clicked.connect(self.save_and_export_current_invoice)
        self.r_save_as_new.clicked.connect(self.save_as_new_invoice)
        self.r_new.clicked.connect(self.start_new_invoice)

        self.refresh_invoice_list()
        self.stack.setCurrentWidget(self.page_meta)

    # -------------------------------------------------------------------------
    # General UI state
    # -------------------------------------------------------------------------

    def set_dirty(self, value: bool = True) -> None:
        self.dirty = value
        suffix = " *" if self.dirty else ""
        mode = "Editing Existing Invoice" if self.edit_mode else "New Invoice"
        self.mode_label.setText(f"Mode: {mode}{suffix}")
        self._update_current_file_hint()

    def _update_current_file_hint(self) -> None:
        if self.current_json_path:
            txt = f"JSON: {self.current_json_path}"
            if self.current_pdf_path:
                txt += f"\nPDF: {self.current_pdf_path}"
            self.current_file_hint.setText(txt)
        else:
            self.current_file_hint.setText("This invoice has not been saved yet.")

    def _mark_hours_dirty(self, *_):
        self._hours_dirty = True

    def _on_flat_fee_toggled(self, checked: bool):
        self.flat_desc_in.setEnabled(checked)
        self.flat_amount_in.setEnabled(checked)
        self.set_dirty(True)

    def load_settings(self):
        try:
            rate = float(settings.get("general.default_rate", 250.0))
            self.rate_in.setValue(rate if rate > 0 else 250.0)
        except Exception:
            self.rate_in.setValue(250.0)

        self.require_explicit_zero = bool(settings.get("invoice.require_explicit_zero_hours", True))

    def persist_rate_now(self):
        try:
            settings.set_("general.default_rate", float(self.rate_in.value()))
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Existing invoice selection
    # -------------------------------------------------------------------------

    def refresh_invoice_list(self):
        self.invoice_list.clear()
        for path in list_invoice_json_files():
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            self.invoice_list.addItem(item)

    def go_to_open_page(self):
        if self.dirty and self.invoice is not None:
            res = QMessageBox.question(
                self,
                "Unsaved changes",
                "You have unsaved changes. Leave this invoice and open another one anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return
        self.refresh_invoice_list()
        self.stack.setCurrentWidget(self.page_open)

    def open_selected_invoice_from_list(self):
        item = self.invoice_list.currentItem()
        if item is None:
            QMessageBox.information(self, "No selection", "Select an invoice JSON file first.")
            return

        path_raw = item.data(Qt.UserRole)
        if not path_raw:
            QMessageBox.warning(self, "Error", "Selected item does not contain a valid path.")
            return

        try:
            self.load_invoice_from_json(Path(path_raw))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load invoice:\n{e}")

    # -------------------------------------------------------------------------
    # Invoice loading / saving
    # -------------------------------------------------------------------------

    def load_invoice_from_json(self, json_path: Path):
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Invoice JSON root must be an object.")

        inv = Invoice.from_dict(data)
        self.invoice = inv
        self.current_json_path = json_path

        expected_pdf = Path(settings.get_export_dir(create=True)) / (json_path.stem + ".pdf")
        self.current_pdf_path = expected_pdf if expected_pdf.exists() else None

        self.edit_mode = True
        self._load_invoice_into_ui()
        self.set_dirty(False)
        self.stack.setCurrentWidget(self.page_meta)

    def _load_invoice_into_ui(self):
        if self.invoice is None:
            return

        self.client_name_in.setText(self.invoice.client_name)
        self.date_in.setText(self.invoice.invoice_date)
        self.rate_in.setValue(float(self.invoice.default_rate))

        has_flat_fee = self.invoice.flat_fee_amount is not None
        self.flat_fee_chk.setChecked(has_flat_fee)
        self.flat_desc_in.setText(self.invoice.flat_fee_desc or "")
        self.flat_amount_in.setValue(float(self.invoice.flat_fee_amount or 0.0))
        self.apply_rate_mode.setCurrentIndex(0)

        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals_labels()

    def _invoice_paths_for_current_save(self) -> tuple[Path, Path]:
        if self.invoice is None:
            raise ValueError("No invoice loaded.")

        if self.edit_mode and self.current_json_path is not None:
            json_path = self.current_json_path
            pdf_path = self.current_pdf_path or (Path(settings.get_export_dir(create=True)) / f"{json_path.stem}.pdf")
            return json_path, pdf_path

        pdf_path = pdf_path_for_invoice(self.invoice)
        json_path = json_path_for_invoice(self.invoice)
        return json_path, pdf_path

    def _write_invoice_json(self, json_path: Path) -> None:
        if self.invoice is None:
            return
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(self.invoice.to_dict(), f, indent=2, ensure_ascii=False)

    def _apply_meta_to_invoice(self) -> bool:
        if self.invoice is None:
            return False

        name = self.client_name_in.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Client's Name cannot be empty.")
            return False

        try:
            dt = parse_user_date(self.date_in.text())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Use M/D, M/D/YY, or M/D/YYYY for the date.")
            return False

        new_default_rate = float(self.rate_in.value())
        if new_default_rate <= 0:
            QMessageBox.warning(self, "Validation", "Default hourly rate must be > 0.")
            return False

        flat_checked = self.flat_fee_chk.isChecked()
        flat_desc_raw = self.flat_desc_in.text().strip()
        flat_amount = float(self.flat_amount_in.value())

        if flat_checked:
            if not flat_desc_raw:
                QMessageBox.warning(self, "Validation", "Flat fee description cannot be empty.")
                return False
            if flat_amount <= 0:
                QMessageBox.warning(self, "Validation", "Flat fee amount must be > 0.")
                return False

        old_rate = self.invoice.default_rate
        self.invoice.client_name = name
        self.invoice.invoice_date = format_date_full(dt)
        self.invoice.default_rate = new_default_rate

        if flat_checked:
            self.invoice.flat_fee_desc = normalize_desc(flat_desc_raw)
            self.invoice.flat_fee_amount = flat_amount
        else:
            self.invoice.flat_fee_desc = None
            self.invoice.flat_fee_amount = None

        if old_rate != new_default_rate and self.apply_rate_mode.currentIndex() == 1:
            self.invoice.apply_default_rate_to_all_services()

        return True

    def save_current_invoice(self):
        if self.invoice is None:
            QMessageBox.information(self, "No invoice", "There is no invoice loaded to save.")
            return

        if not self._apply_meta_to_invoice():
            return

        self.persist_rate_now()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals_labels()

        try:
            json_path, pdf_path = self._invoice_paths_for_current_save()
            self._write_invoice_json(json_path)
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)
            QMessageBox.information(self, "Saved", f"Invoice JSON saved to:\n{json_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save invoice JSON:\n{e}")

    def save_and_export_current_invoice(self):
        if self.invoice is None:
            QMessageBox.information(self, "No invoice", "There is no invoice loaded to save.")
            return

        if not self._apply_meta_to_invoice():
            return

        self.persist_rate_now()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals_labels()

        try:
            json_path, pdf_path = self._invoice_paths_for_current_save()
            self._write_invoice_json(json_path)
            self.invoice.generate_pdf(filename=str(pdf_path))
            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Invoice saved")
            msg.setText(f"JSON saved to:\n{json_path}\n\nPDF exported to:\n{pdf_path}")
            btn_open_pdf = msg.addButton("Open PDF", QMessageBox.AcceptRole)
            btn_open_pdf_folder = msg.addButton("Open PDFs Folder", QMessageBox.ActionRole)
            btn_open_json_folder = msg.addButton("Open JSON Folder", QMessageBox.ActionRole)
            msg.addButton("Close", QMessageBox.RejectRole)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_open_pdf:
                open_local_path(pdf_path)
            elif clicked == btn_open_pdf_folder:
                open_local_path(pdf_path.parent)
            elif clicked == btn_open_json_folder:
                open_local_path(json_path.parent)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save/export invoice:\n{e}")

    def save_as_new_invoice(self):
        if self.invoice is None:
            QMessageBox.information(self, "No invoice", "There is no invoice loaded to save.")
            return

        if not self._apply_meta_to_invoice():
            return

        self.persist_rate_now()
        self._rebuild_service_table()
        self._rebuild_cost_table()
        self.update_totals_labels()

        try:
            base_json = json_path_for_invoice(self.invoice)
            base_pdf = pdf_path_for_invoice(self.invoice)
            json_path = uniquify_path(base_json)
            pdf_path = uniquify_path(base_pdf)

            self._write_invoice_json(json_path)
            self.invoice.generate_pdf(filename=str(pdf_path))

            self.current_json_path = json_path
            self.current_pdf_path = pdf_path
            self.edit_mode = True
            self.set_dirty(False)

            QMessageBox.information(
                self,
                "Saved As New",
                f"New invoice created.\n\nJSON:\n{json_path}\n\nPDF:\n{pdf_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save invoice as new:\n{e}")

    # -------------------------------------------------------------------------
    # New / reset / navigation
    # -------------------------------------------------------------------------

    def start_new_invoice(self):
        self.invoice = Invoice("", datetime.now().strftime("%m/%d/%Y"), float(settings.get("general.default_rate", 250.0)))
        self.current_json_path = None
        self.current_pdf_path = None
        self.edit_mode = False

        self.client_name_in.clear()
        self.date_in.setText(datetime.now().strftime("%m/%d/%Y"))
        self.rate_in.setValue(float(settings.get("general.default_rate", 250.0)))
        self.apply_rate_mode.setCurrentIndex(0)

        self.flat_fee_chk.setChecked(False)
        self.flat_desc_in.clear()
        self.flat_amount_in.setValue(0.00)

        self._suppress_service_table = True
        self._suppress_cost_table = True
        try:
            self.s_table.setRowCount(0)
            self.c_table.setRowCount(0)
        finally:
            self._suppress_service_table = False
            self._suppress_cost_table = False

        self.clear_service_form()
        self.clear_cost_form()
        self.update_totals_labels()
        self.set_dirty(False)
        self.stack.setCurrentWidget(self.page_meta)
        self.client_name_in.setFocus()

    def go_services(self):
        if self.invoice is None:
            self.invoice = Invoice("", datetime.now().strftime("%m/%d/%Y"), float(settings.get("general.default_rate", 250.0)))

        if not self._apply_meta_to_invoice():
            return

        self.persist_rate_now()
        self.s_rate.setValue(float(self.invoice.default_rate))
        self.update_totals_labels()

        if self.flat_fee_chk.isChecked():
            self.stack.setCurrentWidget(self.page_costs)
        else:
            self.stack.setCurrentWidget(self.page_services)

        self.set_dirty(True)

    def confirm_reset_to_meta(self):
        has_content = (
            self.invoice is not None
            and (
                self.invoice.services
                or self.invoice.costs
                or self.invoice.flat_fee_amount is not None
                or bool(self.client_name_in.text().strip())
            )
        )
        if has_content and self.dirty:
            res = QMessageBox.question(
                self,
                "Discard changes?",
                "Going back to the start will discard unsaved changes. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return

        self.start_new_invoice()

    # -------------------------------------------------------------------------
    # Service UI
    # -------------------------------------------------------------------------

    def clear_service_form(self):
        self.s_desc.clear()
        self.s_date.setText(datetime.now().strftime("%m/%d/%Y"))
        self.s_hours.setValue(0.0)
        self.s_rate.setValue(float(self.rate_in.value()))
        self._hours_dirty = False
        self.s_desc.setFocus()
        self.s_desc.selectAll()

    def _rebuild_service_table(self):
        if self.invoice is None:
            return

        self._suppress_service_table = True
        try:
            self.s_table.setRowCount(0)
            for svc in sorted(self.invoice.services, key=lambda x: x.date):
                row = self.s_table.rowCount()
                self.s_table.insertRow(row)
                self.s_table.setItem(row, 0, QTableWidgetItem(format_date(svc.date)))
                self.s_table.setItem(row, 1, QTableWidgetItem(svc.desc))
                self.s_table.setItem(row, 2, QTableWidgetItem(f"{svc.hours:.2f}"))
                self.s_table.setItem(row, 3, QTableWidgetItem(f"{svc.rate:.2f}"))
                self.s_table.setItem(row, 4, QTableWidgetItem(money_str(svc.amount)))
        finally:
            self._suppress_service_table = False

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

        if self.require_explicit_zero and self.s_hours.value() == 0.0 and not self._hours_dirty:
            QMessageBox.warning(self, "Validation", "Hours required. If this is a no-charge entry, type 0 explicitly.")
            return

        hrs = float(self.s_hours.value())
        rate = float(self.s_rate.value())

        if hrs < 0:
            QMessageBox.warning(self, "Validation", "Hours must be ≥ 0.")
            return
        if rate < 0:
            QMessageBox.warning(self, "Validation", "Rate must be ≥ 0.")
            return

        clean = normalize_desc(raw_desc)

        new_key = _svc_key(d_dt, clean, hrs, rate)
        if any(_svc_key(it.date, it.desc, it.hours, it.rate) == new_key for it in self.invoice.services):
            QMessageBox.warning(self, "Duplicate service", "That exact service line already exists on this invoice.")
            self.clear_service_form()
            return

        self.invoice.add_service(d_dt, clean, hrs, rate=rate)
        self._rebuild_service_table()
        self.clear_service_form()
        self.update_totals_labels()
        self.set_dirty(True)

    def remove_last_service(self):
        if self.invoice is None:
            return

        if not self.invoice.services:
            QMessageBox.information(self, "Info", "Nothing to remove.")
            return

        self.invoice.services.pop()
        self._rebuild_service_table()
        self.update_totals_labels()
        self.set_dirty(True)

    def prefill_last_service(self):
        if self.invoice and self.invoice.services:
            last = self.invoice.services[-1]
            self.s_desc.setText(last.desc)
            self.s_date.setText(format_date_full(last.date))
            self.s_hours.setValue(float(last.hours))
            self.s_rate.setValue(float(last.rate))
            self._hours_dirty = True
            self.s_desc.setFocus()
            self.s_desc.selectAll()

    def on_service_item_changed(self, item):
        if self._suppress_service_table or self.invoice is None:
            return

        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.invoice.services):
            return

        if col == 4:
            return

        svc = self.invoice.services[row]
        text = item.text().strip()

        if col == 0:
            try:
                d_dt = parse_user_date(text)
            except ValueError:
                QMessageBox.warning(self, "Validation", "Bad date. Use M/D, M/D/YY, or M/D/YYYY.")
                self._rebuild_service_table()
                return
            svc.date = d_dt

        elif col == 1:
            if not text:
                QMessageBox.warning(self, "Validation", "Description cannot be empty.")
                self._rebuild_service_table()
                return
            svc.desc = normalize_desc(text)

        elif col == 2:
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Hours must be a number ≥ 0.")
                self._rebuild_service_table()
                return
            svc.hours = val

        elif col == 3:
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Rate must be a number ≥ 0.")
                self._rebuild_service_table()
                return
            svc.rate = val

        seen: Set[Tuple[str, str, float, float]] = set()
        for line in self.invoice.services:
            key = _svc_key(line.date, line.desc, line.hours, line.rate)
            if key in seen:
                QMessageBox.warning(self, "Duplicate service", "This edit created a duplicate service line.")
                self._rebuild_service_table()
                return
            seen.add(key)

        self._rebuild_service_table()
        self.update_totals_labels()
        self.set_dirty(True)

    # -------------------------------------------------------------------------
    # Cost UI
    # -------------------------------------------------------------------------

    def clear_cost_form(self):
        self.c_desc.clear()
        self.c_qty.setValue(0.0)
        self.c_price.setValue(0.0)
        self.c_desc.setFocus()
        self.c_desc.selectAll()

    def _rebuild_cost_table(self):
        if self.invoice is None:
            return

        self._suppress_cost_table = True
        try:
            self.c_table.setRowCount(0)
            for cost in self.invoice.costs:
                row = self.c_table.rowCount()
                self.c_table.insertRow(row)
                self.c_table.setItem(row, 0, QTableWidgetItem(cost.desc))
                self.c_table.setItem(row, 1, QTableWidgetItem(f"{cost.qty:.2f}"))
                self.c_table.setItem(row, 2, QTableWidgetItem(f"{cost.unit_price:.2f}"))
                self.c_table.setItem(row, 3, QTableWidgetItem(money_str(cost.total)))
        finally:
            self._suppress_cost_table = False

    def add_cost(self):
        if self.invoice is None:
            return

        raw_desc = self.c_desc.text().strip()
        if not raw_desc:
            QMessageBox.warning(self, "Validation", "Cost description cannot be empty.")
            return

        qty = float(self.c_qty.value())
        price = float(self.c_price.value())

        if qty < 0:
            QMessageBox.warning(self, "Validation", "Quantity must be ≥ 0.")
            return
        if price < 0:
            QMessageBox.warning(self, "Validation", "Unit price must be ≥ 0.")
            return

        clean = normalize_desc(raw_desc)
        self.invoice.add_cost(clean, qty, price)
        self._rebuild_cost_table()
        self.clear_cost_form()
        self.update_totals_labels()
        self.set_dirty(True)

    def prefill_last_cost(self):
        if self.invoice and self.invoice.costs:
            last = self.invoice.costs[-1]
            self.c_desc.setText(last.desc)
            self.c_qty.setValue(float(last.qty))
            self.c_price.setValue(float(last.unit_price))
            self.c_desc.setFocus()
            self.c_desc.selectAll()

    def on_cost_item_changed(self, item):
        if self._suppress_cost_table or self.invoice is None:
            return

        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.invoice.costs):
            return

        if col == 3:
            return

        cost = self.invoice.costs[row]
        text = item.text().strip()

        if col == 0:
            if not text:
                QMessageBox.warning(self, "Validation", "Description cannot be empty.")
                self._rebuild_cost_table()
                return
            cost.desc = normalize_desc(text)

        elif col == 1:
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Quantity must be a number ≥ 0.")
                self._rebuild_cost_table()
                return
            cost.qty = val

        elif col == 2:
            try:
                val = float(text)
                if val < 0:
                    raise ValueError
            except Exception:
                QMessageBox.warning(self, "Validation", "Unit price must be a number ≥ 0.")
                self._rebuild_cost_table()
                return
            cost.unit_price = val

        self._rebuild_cost_table()
        self.update_totals_labels()
        self.set_dirty(True)

    # -------------------------------------------------------------------------
    # Review
    # -------------------------------------------------------------------------

    def go_review(self):
        if self.invoice is None:
            return

        if not self._apply_meta_to_invoice():
            return

        buf = io.StringIO()
        _stdout = sys.stdout
        try:
            sys.stdout = buf
            self.invoice.print_console()
        finally:
            sys.stdout = _stdout

        self.console_preview.setPlainText(buf.getvalue())
        self.filename_hint.setText(f"Default file name: <b>{default_pdf_filename(self.invoice)}</b>")
        self._update_current_file_hint()
        self.stack.setCurrentWidget(self.page_review)
        self.set_dirty(True)

    # -------------------------------------------------------------------------
    # Totals / status
    # -------------------------------------------------------------------------

    def update_totals_labels(self):
        if self.invoice is None:
            self.s_totals_lbl.setText("")
            self.c_totals_lbl.setText("")
            if hasattr(self, "status"):
                self.status.showMessage("")
            return

        svc_total = self.invoice.total_services()
        cost_total = self.invoice.total_costs()
        grand = self.invoice.grand_total()
        hours_sum = sum((i.hours for i in self.invoice.services), 0.0)

        self.s_totals_lbl.setText(f"Service fees total: {money_str(svc_total)}")
        self.c_totals_lbl.setText(f"Costs total: {money_str(cost_total)}    |    GRAND TOTAL: <b>{money_str(grand)}</b>")

        if hasattr(self, "status"):
            self.status.showMessage(
                f"Services: ${money_str(svc_total)} | Hours: {hours_sum:.2f} | Costs: ${money_str(cost_total)} | Grand: ${money_str(grand)}"
            )

    # -------------------------------------------------------------------------
    # Main entry
    # -------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    w = InvoiceWizard()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()