from __future__ import annotations

import re
from math import floor
from pathlib import Path
from typing import Callable

from fpdf import FPDF, XPos, YPos

import settings
from models import Invoice, format_date_short

PAGE_FORMAT = "Letter"
FONT_FAMILY = "Helvetica"
MAX_FONT_PT = 14
MIN_FONT_PT = 10
LEFT_MARGIN_MM = 15
TOP_MARGIN_MM = 20
BOTTOM_MARGIN_MM = 5
ROW_PAD_MM = 0.8
DESC_INNER_PAD_X = 1.0


def mm_from_inches(value: float) -> float:
    return value * 25.4


def letterhead_margin_in() -> float:
    try:
        return float(settings.get("letterhead.top_margin_in", 2.5))
    except Exception:
        return 2.5


def page_top_y(pdf: FPDF) -> float:
    return (
        mm_from_inches(letterhead_margin_in())
        if pdf.page_no() == 1
        else TOP_MARGIN_MM
    )


def money(value: float) -> str:
    commas = bool(settings.get("pdf.thousand_separators", True))
    return f"{value:,.2f}" if commas else f"{value:.2f}"


def wrap_text_lines(pdf: FPDF, text: str, max_width: float) -> list[str]:
    if not text:
        return [""]

    tokens = [
        token
        for token in re.split(r"(\s+|[-,/;:])", text)
        if token is not None and token != ""
    ]
    lines: list[str] = []
    current = ""

    for token in tokens:
        candidate = current + token if current else token
        if pdf.get_string_width(candidate) <= max_width - 0.5:
            current = candidate
            continue

        if current:
            lines.append(current.rstrip())
            current = ""

        if pdf.get_string_width(token) <= max_width - 0.5:
            current = token.lstrip()
            continue

        buffer = ""
        for char in token:
            candidate = buffer + char
            if pdf.get_string_width(candidate) > max_width - 0.5 and buffer:
                lines.append(buffer)
                buffer = char
            else:
                buffer = candidate
        current = buffer

    if current:
        lines.append(current.rstrip())

    return lines or [""]


def draw_header(
    pdf: FPDF,
    widths: list[float],
    headers: list[str],
    row_height: float,
) -> None:
    pdf.set_x(LEFT_MARGIN_MM)
    pdf.set_font(FONT_FAMILY, "B", pdf.font_size_pt)
    pdf.set_fill_color(200, 220, 255)
    for width, header in zip(widths, headers):
        pdf.cell(
            width,
            row_height,
            header,
            border=1,
            align="C",
            fill=True,
            new_x=XPos.RIGHT,
            new_y=YPos.TOP,
        )
    pdf.ln(row_height)
    pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
    pdf.set_fill_color(245, 245, 245)


def ensure_room(
    pdf: FPDF,
    needed_height: float,
    redraw: Callable[[], None] | None = None,
) -> None:
    if pdf.get_y() + needed_height <= pdf.h - BOTTOM_MARGIN_MM:
        return
    pdf.add_page()
    pdf.set_y(page_top_y(pdf))
    if redraw:
        redraw()


def draw_box(pdf: FPDF, x: float, y: float, width: float, height: float, fill: bool) -> None:
    pdf.set_xy(x, y)
    pdf.cell(width, height, "", border=1, fill=fill)


def draw_centered_text(
    pdf: FPDF,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    align: str,
) -> None:
    baseline = y + (height - pdf.ln_height_mm) / 2.0
    pdf.set_xy(x, baseline)
    pdf.cell(
        width,
        pdf.ln_height_mm,
        text,
        border=0,
        align=align,
        new_x=XPos.RIGHT,
        new_y=YPos.TOP,
    )


def paginate_services(
    pdf: FPDF,
    rows: list[list[str]],
    widths: list[float],
    headers: list[str],
) -> None:
    row_height = pdf.ln_height_mm
    usable_bottom = pdf.h - BOTTOM_MARGIN_MM

    def redraw() -> None:
        draw_header(pdf, widths, headers, row_height)

    redraw()
    fill = True

    for row in rows:
        date_text, desc_text, hrs_text, rate_text, amt_text = row
        pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
        desc_lines = wrap_text_lines(
            pdf,
            desc_text,
            widths[1] - (2 * DESC_INNER_PAD_X),
        )

        start = 0
        while start < len(desc_lines):
            y0 = pdf.get_y()
            available = usable_bottom - y0
            minimum = row_height + 2 * ROW_PAD_MM

            if available < minimum:
                pdf.add_page()
                pdf.set_y(page_top_y(pdf))
                redraw()
                y0 = pdf.get_y()
                available = usable_bottom - y0

            max_lines = max(
                1,
                floor((available - 2 * ROW_PAD_MM) / row_height),
            )
            end = min(len(desc_lines), start + max_lines)
            lines = desc_lines[start:end]
            height = ROW_PAD_MM + row_height * max(1, len(lines)) + ROW_PAD_MM

            x = LEFT_MARGIN_MM
            for width in widths:
                draw_box(pdf, x, y0, width, height, fill)
                x += width

            x = LEFT_MARGIN_MM
            draw_centered_text(pdf, x, y0, widths[0], height, date_text, "L")
            x += widths[0]

            pdf.set_xy(x + DESC_INNER_PAD_X, y0 + ROW_PAD_MM)
            pdf.multi_cell(
                widths[1] - 2 * DESC_INNER_PAD_X,
                row_height,
                "\n".join(lines),
                border=0,
                align="L",
                fill=False,
            )
            x += widths[1]

            draw_centered_text(pdf, x, y0, widths[2], height, hrs_text, "R")
            x += widths[2]
            draw_centered_text(pdf, x, y0, widths[3], height, rate_text, "R")
            x += widths[3]
            draw_centered_text(pdf, x, y0, widths[4], height, amt_text, "R")

            pdf.set_y(y0 + height)
            start = end

        fill = not fill


def paginate_flat_fee(
    pdf: FPDF,
    description: str,
    amount: float,
    service_widths: list[float],
) -> None:
    row_height = pdf.ln_height_mm
    left_width = sum(service_widths[:-1])
    amount_width = service_widths[-1]

    def redraw() -> None:
        pdf.set_x(LEFT_MARGIN_MM)
        pdf.set_font(FONT_FAMILY, "B", pdf.font_size_pt)
        pdf.set_fill_color(200, 220, 255)
        pdf.cell(
            left_width,
            row_height,
            "Service",
            border=1,
            align="C",
            fill=True,
            new_x=XPos.RIGHT,
            new_y=YPos.TOP,
        )
        pdf.cell(
            amount_width,
            row_height,
            "Amt",
            border=1,
            align="C",
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.TOP,
        )
        pdf.ln(row_height)
        pdf.set_font(FONT_FAMILY, "", pdf.font_size_pt)
        pdf.set_fill_color(245, 245, 245)

    redraw()
    lines = wrap_text_lines(
        pdf,
        description,
        left_width - 2 * DESC_INNER_PAD_X,
    )
    height = ROW_PAD_MM + row_height * max(1, len(lines)) + ROW_PAD_MM
    ensure_room(pdf, height, redraw)

    y0 = pdf.get_y()
    draw_box(pdf, LEFT_MARGIN_MM, y0, left_width, height, True)
    draw_box(
        pdf,
        LEFT_MARGIN_MM + left_width,
        y0,
        amount_width,
        height,
        True,
    )

    pdf.set_xy(LEFT_MARGIN_MM + DESC_INNER_PAD_X, y0 + ROW_PAD_MM)
    pdf.multi_cell(
        left_width - 2 * DESC_INNER_PAD_X,
        row_height,
        "\n".join(lines),
        border=0,
        align="L",
    )
    draw_centered_text(
        pdf,
        LEFT_MARGIN_MM + left_width,
        y0,
        amount_width,
        height,
        money(amount),
        "R",
    )
    pdf.set_y(y0 + height)


def paginate_simple_table(
    pdf: FPDF,
    rows: list[list[str]],
    widths: list[float],
    headers: list[str],
    alignments: list[str],
) -> None:
    row_height = pdf.ln_height_mm
    base_size = pdf.font_size_pt

    def redraw() -> None:
        draw_header(pdf, widths, headers, row_height)

    redraw()
    fill = True

    for row in rows:
        ensure_room(pdf, row_height, redraw)
        pdf.set_x(LEFT_MARGIN_MM)

        for width, value, alignment in zip(widths, row, alignments):
            text_width = pdf.get_string_width(value)
            if text_width > width - 2:
                size = max(
                    MIN_FONT_PT,
                    base_size * ((width - 2) / max(text_width, 1e-6)),
                )
                pdf.set_font(FONT_FAMILY, "", size)
            else:
                pdf.set_font(FONT_FAMILY, "", base_size)

            pdf.cell(
                width,
                row_height,
                value,
                border=1,
                align=alignment,
                fill=fill,
                new_x=XPos.RIGHT,
                new_y=YPos.TOP,
            )

        pdf.set_font(FONT_FAMILY, "", base_size)
        pdf.ln(row_height)
        fill = not fill


def total_row(
    pdf: FPDF,
    label_width: float,
    value_width: float,
    label: str,
    value: str,
    row_height: float,
    font_size: float,
) -> None:
    ensure_room(pdf, row_height)
    pdf.set_x(LEFT_MARGIN_MM)
    pdf.set_font(FONT_FAMILY, "B", font_size)
    pdf.cell(
        label_width,
        row_height,
        label,
        border=1,
        align="R",
        new_x=XPos.RIGHT,
        new_y=YPos.TOP,
    )
    pdf.cell(
        value_width,
        row_height,
        value,
        border=1,
        align="R",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def generate_pdf(inv: Invoice, filename: str | Path) -> Path:
    target = Path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    service_rows_count = max(
        1,
        len(inv.services) + (1 if inv.flat_fee_amount is not None else 0),
    )
    total_rows = service_rows_count + len(inv.costs) + 8

    chosen = None
    for size in range(MAX_FONT_PT, MIN_FONT_PT - 1, -1):
        if total_rows * (size * 0.35) < (
            FPDF(format=PAGE_FORMAT).h
            - mm_from_inches(letterhead_margin_in())
            - TOP_MARGIN_MM
        ):
            chosen = size
            break
    chosen = chosen or MIN_FONT_PT

    pdf = FPDF(format=PAGE_FORMAT)
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font(FONT_FAMILY, "", chosen)
    pdf.font_size_pt = chosen
    pdf.ln_height_mm = chosen * 0.35

    pdf.set_y(page_top_y(pdf))
    pdf.set_font(FONT_FAMILY, "B", chosen + 4)
    pdf.cell(
        0,
        pdf.ln_height_mm * 2,
        "Invoice",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(pdf.ln_height_mm / 2)
    pdf.set_font(FONT_FAMILY, "", chosen)
    pdf.cell(
        0,
        pdf.ln_height_mm,
        f"Invoice for: {inv.client_name}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        pdf.ln_height_mm,
        f"Date:        {inv.invoice_date}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(pdf.ln_height_mm)

    service_widths = [25, 80, 25, 30, 30]

    if inv.flat_fee_amount is not None and not inv.services:
        paginate_flat_fee(
            pdf,
            inv.flat_fee_desc or "Attorney Fees",
            inv.flat_fee_amount,
            service_widths,
        )
    else:
        rows = [
            [
                format_date_short(item.date),
                item.desc,
                f"{item.hours:.2f}",
                money(item.rate),
                money(item.amount),
            ]
            for item in sorted(inv.services, key=lambda x: x.date)
        ]
        if inv.flat_fee_amount is not None:
            rows.append(
                [
                    "",
                    inv.flat_fee_desc or "Flat service fee",
                    "",
                    "",
                    money(inv.flat_fee_amount),
                ]
            )
        paginate_services(
            pdf,
            rows,
            service_widths,
            ["Date", "Service", "Hrs", "Rate", "Amt"],
        )

    row_height = pdf.ln_height_mm
    label_width = sum(service_widths[:-1])
    amount_width = service_widths[-1]

    if bool(settings.get("pdf.show_total_hours", True)):
        total_row(
            pdf,
            label_width,
            amount_width,
            "TOTAL HOURS BILLED",
            f"{inv.total_hours():.2f}",
            row_height,
            chosen,
        )

    total_row(
        pdf,
        label_width,
        amount_width,
        "TOTAL SERVICE FEES",
        money(inv.total_services()),
        row_height,
        chosen,
    )
    pdf.ln(row_height * 0.5)

    if inv.costs:
        cost_widths = [80, 30, 30, 30]
        cost_rows = [
            [
                item.desc,
                f"{item.qty:.2f}",
                money(item.unit_price),
                money(item.total),
            ]
            for item in inv.costs
        ]
        paginate_simple_table(
            pdf,
            cost_rows,
            cost_widths,
            ["Description", "Qty", "Unit", "Total"],
            ["L", "R", "R", "R"],
        )
        total_row(
            pdf,
            sum(cost_widths[:-1]),
            cost_widths[-1],
            "TOTAL COSTS",
            money(inv.total_costs()),
            row_height,
            chosen,
        )
        pdf.ln(row_height * 0.5)

    ensure_room(pdf, row_height * 1.2)
    pdf.set_font(FONT_FAMILY, "B", chosen + 2)
    grand = f"GRAND TOTAL: {money(inv.grand_total())}"
    grand_width = pdf.get_string_width(grand) + 6
    pdf.set_x(pdf.w - LEFT_MARGIN_MM - grand_width)
    pdf.set_line_width(0.5)
    pdf.cell(
        grand_width,
        row_height * 1.2,
        grand,
        border=1,
        align="C",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.output(str(target))
    return target
