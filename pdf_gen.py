from __future__ import annotations

from math import floor
from pathlib import Path
from typing import Callable

from fpdf import FPDF, XPos, YPos
from fpdf.enums import MethodReturnValue

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
    # Measure with the same engine and cell margins used to draw the text.
    # Counting lines ourselves misses explicit newlines and can make fpdf wrap
    # a supposedly single-line value again, outside its row's border.
    lines = pdf.multi_cell(
        max_width,
        pdf.ln_height_mm,
        text,
        dry_run=True,
        output=MethodReturnValue.LINES,
    ) or [""]
    # fpdf returns core-font lines in its internal Latin-1 representation.
    # Convert them back before drawing, which performs normalization again.
    return [line.encode("latin-1").decode(pdf.core_fonts_encoding) for line in lines]


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


def paginate_services(
    pdf: FPDF,
    rows: list[list[str]],
    widths: list[float],
    headers: list[str],
) -> None:
    paginate_wrapped_table(pdf, rows, widths, headers, ["L", "L", "R", "R", "R"], 1)


def paginate_flat_fee(
    pdf: FPDF,
    description: str,
    amount: float,
    service_widths: list[float],
) -> None:
    left_width = sum(service_widths[:-1])
    amount_width = service_widths[-1]
    paginate_wrapped_table(
        pdf,
        [[description, money(amount)]],
        [left_width, amount_width],
        ["Service", "Amt"],
        ["L", "R"],
        0,
    )


def paginate_simple_table(
    pdf: FPDF,
    rows: list[list[str]],
    widths: list[float],
    headers: list[str],
    alignments: list[str],
) -> None:
    paginate_wrapped_table(pdf, rows, widths, headers, alignments, 0)


def fit_cell_text(
    pdf: FPDF, text: str, width: float, base_size: float, style: str = ""
) -> float:
    pdf.set_font(FONT_FAMILY, style, base_size)
    text_width = pdf.get_string_width(text)
    usable_width = width - 2 * pdf.c_margin
    size = max(MIN_FONT_PT, min(base_size, base_size * usable_width / max(text_width, 1e-6)))
    pdf.set_font(FONT_FAMILY, style, size)
    return size


def paginate_wrapped_table(
    pdf: FPDF,
    rows: list[list[str]],
    widths: list[float],
    headers: list[str],
    alignments: list[str],
    description_column: int,
) -> None:
    row_height = pdf.ln_height_mm
    base_size = pdf.font_size_pt
    minimum = row_height + 2 * ROW_PAD_MM
    usable_bottom = pdf.h - BOTTOM_MARGIN_MM

    def redraw() -> None:
        pdf.set_font(FONT_FAMILY, "", base_size)
        draw_header(pdf, widths, headers, row_height)

    # Do not strand a header at the bottom of a page without its first row.
    ensure_room(pdf, row_height + minimum)
    redraw()
    fill = True

    for row in rows:
        columns: list[tuple[list[str], float]] = []
        for index, (width, value) in enumerate(zip(widths, row)):
            if index == description_column:
                pdf.set_font(FONT_FAMILY, "", base_size)
                lines = wrap_text_lines(pdf, value, width - 2 * DESC_INNER_PAD_X)
                size = base_size
            else:
                size = fit_cell_text(pdf, value, width, base_size)
                lines = wrap_text_lines(pdf, value, width)
            columns.append((lines, size))

        line_count = max(len(lines) for lines, _ in columns)
        start = 0
        while start < line_count:
            ensure_room(pdf, minimum, redraw)
            y0 = pdf.get_y()
            available = usable_bottom - y0
            max_lines = max(1, floor((available - 2 * ROW_PAD_MM) / row_height))
            end = min(line_count, start + max_lines)
            height = 2 * ROW_PAD_MM + row_height * (end - start)

            x = LEFT_MARGIN_MM
            for width in widths:
                draw_box(pdf, x, y0, width, height, fill)
                x += width

            x = LEFT_MARGIN_MM
            for index, (width, alignment, (all_lines, size)) in enumerate(
                zip(widths, alignments, columns)
            ):
                # Keep the date and ordinary amounts visible on continuation
                # pages, as in the recovered service-table layout.
                lines = all_lines[start:end]
                if index != description_column and len(all_lines) == 1:
                    lines = all_lines
                pdf.set_font(FONT_FAMILY, "", size)
                if index == description_column:
                    pdf.set_xy(x + DESC_INNER_PAD_X, y0 + ROW_PAD_MM)
                    if lines:
                        pdf.multi_cell(
                            width - 2 * DESC_INNER_PAD_X,
                            row_height,
                            "\n".join(lines),
                            border=0,
                            align=alignment,
                        )
                else:
                    baseline = y0 + (height - row_height * len(lines)) / 2
                    for offset, line in enumerate(lines):
                        pdf.set_xy(x, baseline + offset * row_height)
                        pdf.cell(width, row_height, line, align=alignment)
                x += width

            pdf.set_y(y0 + height)
            start = end
        pdf.set_font(FONT_FAMILY, "", base_size)
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
    value_size = fit_cell_text(pdf, value, value_width, font_size, "B")
    value_lines = wrap_text_lines(pdf, value, value_width)
    height = row_height * len(value_lines)
    ensure_room(pdf, height)
    y0 = pdf.get_y()
    pdf.set_x(LEFT_MARGIN_MM)
    pdf.set_font(FONT_FAMILY, "B", font_size)
    pdf.cell(
        label_width,
        height,
        label,
        border=1,
        align="R",
        new_x=XPos.RIGHT,
        new_y=YPos.TOP,
    )
    draw_box(pdf, LEFT_MARGIN_MM + label_width, y0, value_width, height, False)
    pdf.set_font(FONT_FAMILY, "B", value_size)
    for offset, line in enumerate(value_lines):
        pdf.set_xy(LEFT_MARGIN_MM + label_width, y0 + offset * row_height)
        pdf.cell(value_width, row_height, line, align="R")
    pdf.set_xy(LEFT_MARGIN_MM, y0 + height)
    pdf.set_font(FONT_FAMILY, "B", font_size)


def validate_pdf_text(inv: Invoice) -> None:
    fields = [
        ("client name", inv.client_name),
        ("invoice date", inv.invoice_date),
        ("flat fee description", inv.flat_fee_desc or ""),
        *(("service description", item.desc) for item in inv.services),
        *(("cost description", item.desc) for item in inv.costs),
    ]
    for label, text in fields:
        try:
            text.encode("cp1252")
        except UnicodeEncodeError as exc:
            character = text[exc.start]
            raise ValueError(
                f"The {label} contains {character!r}, which Helvetica cannot display. "
                "Replace that character before exporting the PDF."
            ) from exc


def estimate_invoice_height(inv: Invoice, size: int) -> float:
    """Measure wrapped rows so a smaller readable font can keep totals together."""
    pdf = FPDF(format=PAGE_FORMAT)
    pdf.core_fonts_encoding = "cp1252"
    pdf.set_margins(LEFT_MARGIN_MM, TOP_MARGIN_MM, LEFT_MARGIN_MM)
    pdf.add_page()
    pdf.set_font(FONT_FAMILY, "", size)
    pdf.ln_height_mm = row_height = size * 0.35
    height = row_height * (
        4.5 + len(wrap_text_lines(pdf, f"Invoice for: {inv.client_name}", pdf.epw))
    )

    def table_height(rows: list[list[str]], widths: list[float], desc_column: int) -> float:
        result = row_height
        for row in rows:
            count = 1
            for index, (value, width) in enumerate(zip(row, widths)):
                if index == desc_column:
                    pdf.set_font(FONT_FAMILY, "", size)
                    lines = wrap_text_lines(pdf, value, width - 2 * DESC_INNER_PAD_X)
                else:
                    fit_cell_text(pdf, value, width, size)
                    lines = wrap_text_lines(pdf, value, width)
                count = max(count, len(lines))
            result += 2 * ROW_PAD_MM + count * row_height
        return result

    def value_height(value: str) -> float:
        fit_cell_text(pdf, value, 30, size, "B")
        return row_height * len(wrap_text_lines(pdf, value, 30))

    service_rows = [
        [format_date_short(item.date), item.desc, f"{item.hours:.2f}", money(item.rate), money(item.amount)]
        for item in inv.services
    ]
    if inv.flat_fee_amount is not None and not inv.services:
        height += table_height(
            [[inv.flat_fee_desc or "Attorney Fees", money(inv.flat_fee_amount)]], [160, 30], 0
        )
    else:
        if inv.flat_fee_amount is not None:
            service_rows.append(["", inv.flat_fee_desc or "Flat service fee", "", "", money(inv.flat_fee_amount)])
        height += table_height(service_rows, [25, 80, 25, 30, 30], 1)
    if bool(settings.get("pdf.show_total_hours", True)):
        height += value_height(f"{inv.total_hours():.2f}")
    height += value_height(money(inv.total_services())) + row_height * 0.5
    if inv.costs:
        height += table_height(
            [[item.desc, f"{item.qty:.2f}", money(item.unit_price), money(item.total)] for item in inv.costs],
            [80, 30, 30, 30],
            0,
        )
        height += value_height(money(inv.total_costs())) + row_height * 0.5
    return height + row_height * 1.2


def draw_paged_text(pdf: FPDF, text: str, width: float) -> None:
    """Keep unusually long client names inside the printable area too."""
    lines = wrap_text_lines(pdf, text, width)
    start = 0
    while start < len(lines):
        ensure_room(pdf, pdf.ln_height_mm)
        y0 = pdf.get_y()
        capacity = max(1, floor((pdf.h - BOTTOM_MARGIN_MM - y0) / pdf.ln_height_mm))
        end = min(len(lines), start + capacity)
        pdf.set_x(LEFT_MARGIN_MM)
        pdf.multi_cell(width, pdf.ln_height_mm, "\n".join(lines[start:end]))
        pdf.set_y(y0 + (end - start) * pdf.ln_height_mm)
        start = end


def generate_pdf(inv: Invoice, filename: str | Path) -> Path:
    # Validate before creating directories or replacing an existing export.
    # Windows typography (curly quotes, en/em dashes, euro signs) is supported
    # by core Helvetica using its Windows-1252 character mapping.
    inv.validate()
    validate_pdf_text(inv)
    target = Path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    available_height = FPDF(format=PAGE_FORMAT).h - BOTTOM_MARGIN_MM - mm_from_inches(letterhead_margin_in())
    chosen = MIN_FONT_PT
    for size in range(MAX_FONT_PT, MIN_FONT_PT - 1, -1):
        if estimate_invoice_height(inv, size) <= available_height:
            chosen = size
            break

    pdf = FPDF(format=PAGE_FORMAT)
    pdf.core_fonts_encoding = "cp1252"
    pdf.set_margins(LEFT_MARGIN_MM, TOP_MARGIN_MM, LEFT_MARGIN_MM)
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
    draw_paged_text(pdf, f"Invoice for: {inv.client_name}", pdf.epw)
    ensure_room(pdf, pdf.ln_height_mm)
    pdf.set_x(LEFT_MARGIN_MM)
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

    grand = f"GRAND TOTAL: {money(inv.grand_total())}"
    pdf.set_font(FONT_FAMILY, "B", chosen + 2)
    available_width = pdf.w - 2 * LEFT_MARGIN_MM
    text_width = pdf.get_string_width(grand)
    if text_width + 6 > available_width:
        size = max(MIN_FONT_PT, (chosen + 2) * (available_width - 6) / text_width)
        pdf.set_font(FONT_FAMILY, "B", size)
    grand_width = pdf.get_string_width(grand) + 6
    grand_width = min(grand_width, available_width)
    grand_lines = wrap_text_lines(pdf, grand, grand_width)
    grand_height = row_height * 1.2 * len(grand_lines)
    ensure_room(pdf, grand_height)
    x, y = pdf.w - LEFT_MARGIN_MM - grand_width, pdf.get_y()
    pdf.set_line_width(0.5)
    draw_box(pdf, x, y, grand_width, grand_height, False)
    for offset, line in enumerate(grand_lines):
        pdf.set_xy(x, y + offset * row_height * 1.2)
        pdf.cell(grand_width, row_height * 1.2, line, align="C")
    pdf.set_xy(LEFT_MARGIN_MM, y + grand_height)

    pdf.output(str(target))
    return target
