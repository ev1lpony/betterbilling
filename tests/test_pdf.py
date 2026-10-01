"""PDF regression coverage uses synthetic invoices and real page content."""

from datetime import datetime
from pathlib import Path
import re

from fpdf import FPDF
from pypdf import PdfReader
from pypdf.generic import ContentStream
import pytest

from models import Invoice
import pdf_gen
import settings


MM_TO_PT = 72 / 25.4


def export(inv: Invoice, tmp_path: Path) -> PdfReader:
    target = tmp_path / "invoice.pdf"
    assert pdf_gen.generate_pdf(inv, target) == target
    return PdfReader(target)


def page_texts(reader: PdfReader) -> list[str]:
    return [page.extract_text() for page in reader.pages]


def assert_page_bounds(reader: PdfReader) -> None:
    """Check actual PDF rectangle and text positions, including blank borders."""
    for page in reader.pages:
        assert float(page.mediabox.width) == pytest.approx(612, abs=0.01)
        assert float(page.mediabox.height) == pytest.approx(792, abs=0.01)
        stream = ContentStream(page.get_contents(), reader)
        text_x = text_y = 0.0
        for operands, operator in stream.operations:
            if operator == b"re":
                x, y, width, height = map(float, operands)
                assert min(x, x + width) >= -0.02
                assert max(x, x + width) <= 612.02
                assert min(y, y + height) >= pdf_gen.BOTTOM_MARGIN_MM * MM_TO_PT - 0.02
                assert max(y, y + height) <= 792.02
            elif operator == b"BT":
                text_x = text_y = 0.0
            elif operator == b"Td":
                text_x += float(operands[0])
                text_y += float(operands[1])
            elif operator == b"Tm":
                text_x, text_y = map(float, operands[-2:])
            elif operator in (b"Tj", b"TJ"):
                assert 0 <= text_x < 612
                assert pdf_gen.BOTTOM_MARGIN_MM * MM_TO_PT <= text_y < 792


def assert_tokens_once(reader: PdfReader, tokens: list[str], header: str) -> None:
    pages = page_texts(reader)
    words = " ".join(pages).split()
    for token in tokens:
        assert words.count(token) == 1
    for text in pages:
        if any(token in text for token in tokens):
            assert header in text


def invoice() -> Invoice:
    return Invoice("Synthetic Test Client", "04/30/2025", 250.0)


def test_mixed_fees_totals_and_historical_page_design(tmp_path):
    inv = invoice()
    inv.add_service(datetime(2025, 4, 1), "Review IRS correspondence", 1.5)
    inv.flat_fee_desc = "Attorney Fees"
    inv.flat_fee_amount = 1500
    inv.add_cost("Certified mail", 1, 9.85)
    reader = export(inv, tmp_path)
    assert len(reader.pages) == 1
    text = page_texts(reader)[0]
    assert "Review IRS correspondence" in text
    assert "Attorney Fees" in text
    assert "TOTAL HOURS BILLED 1.50" in text
    assert "TOTAL SERVICE FEES 1,875.00" in text
    assert "TOTAL COSTS 9.85" in text
    assert "GRAND TOTAL: 1,884.85" in text
    fonts = reader.pages[0]["/Resources"]["/Font"]
    assert {font.get_object()["/BaseFont"] for font in fonts.values()} == {
        "/Helvetica", "/Helvetica-Bold"
    }
    stream = ContentStream(reader.pages[0].get_contents(), reader)
    rectangles = [tuple(map(float, args)) for args, op in stream.operations if op == b"re"]
    first_header = rectangles[:5]
    assert [rectangle[2] / MM_TO_PT for rectangle in first_header] == pytest.approx(
        [25, 80, 25, 30, 30], abs=0.01
    )
    assert first_header[0][0] / MM_TO_PT == pytest.approx(15, abs=0.01)
    assert max(rect[1] + rect[3] for rect in first_header) < 792 - 2.5 * 72
    assert_page_bounds(reader)


@pytest.mark.parametrize("row_count", [25, 26, 83])
def test_cost_header_stays_with_first_cost_and_inside_page(tmp_path, row_count):
    inv = invoice()
    for number in range(row_count):
        inv.add_service(datetime(2025, 4, 1), f"Service entry {number}", 1)
    inv.add_cost("Postage", 1, 2.5)
    reader = export(inv, tmp_path)
    cost_pages = [text for text in page_texts(reader) if "Description Qty Unit Total" in text]
    assert len(cost_pages) == 1
    assert "Postage" in cost_pages[0]
    assert_page_bounds(reader)


@pytest.mark.parametrize("kind", ["hourly", "flat", "cost"])
def test_description_taller_than_page_preserves_text_headers_and_borders(tmp_path, kind):
    tokens = [f"WORD{number:04d}" for number in range(900)]
    description = " ".join(tokens)
    inv = invoice()
    if kind == "hourly":
        inv.add_service(datetime(2025, 4, 1), description, 1)
        header = "Date Service Hrs Rate Amt"
    elif kind == "flat":
        inv.flat_fee_desc = description
        inv.flat_fee_amount = 1500
        header = "Service Amt"
    else:
        inv.add_cost(description, 1, 10)
        header = "Description Qty Unit Total"
    reader = export(inv, tmp_path)
    assert len(reader.pages) > 1
    assert_tokens_once(reader, tokens, header)
    assert_page_bounds(reader)
    assert "GRAND TOTAL:" in page_texts(reader)[-1]


@pytest.mark.parametrize("kind", ["service", "cost"])
def test_many_rows_repeat_headers_and_keep_every_entry(tmp_path, kind):
    inv = invoice()
    tokens = [f"Entry{number:04d}" for number in range(160)]
    for token in tokens:
        if kind == "service":
            inv.add_service(datetime(2025, 4, 1), token, 0.5)
        else:
            inv.add_cost(token, 1, 0.25)
    reader = export(inv, tmp_path)
    assert len(reader.pages) >= 3
    assert_tokens_once(
        reader, tokens,
        "Date Service Hrs Rate Amt" if kind == "service" else "Description Qty Unit Total",
    )
    assert_page_bounds(reader)


def test_wrapping_uses_real_internal_margins_and_explicit_newlines(tmp_path):
    pdf = FPDF(format="Letter")
    pdf.add_page()
    pdf.set_font("Helvetica", "", 14)
    pdf.ln_height_mm = 14 * 0.35
    text = "i" * 70 + "\nSECOND LINE\nTHIRD LINE"
    lines = pdf_gen.wrap_text_lines(pdf, text, 78)
    assert len(lines) == 4
    assert "".join(lines[:2]) == "i" * 70
    assert lines[-2:] == ["SECOND LINE", "THIRD LINE"]
    assert all(pdf.get_string_width(line) <= 78 - 2 * pdf.c_margin for line in lines)
    inv = invoice()
    inv.add_service(datetime(2025, 4, 1), text, 0)
    reader = export(inv, tmp_path)
    assert "SECOND LINE\nTHIRD LINE" in "\n".join(page_texts(reader))
    assert "GRAND TOTAL: 0.00" in page_texts(reader)[-1]
    assert_page_bounds(reader)


def test_windows_typography_exports_with_helvetica(tmp_path):
    inv = invoice()
    inv.client_name = "O\u2019Brien \u2013 Synthetic"
    inv.add_service(datetime(2025, 4, 1), "Review client\u2019s IRS notice \u2014 \u20ac reference", 1)
    reader = export(inv, tmp_path)
    text = "\n".join(page_texts(reader))
    assert "O\u2019Brien \u2013 Synthetic" in text
    assert "client\u2019s" in text
    assert "\u2014" in text
    assert "\u20ac" in text


def test_unsupported_unicode_is_reported_before_export_is_touched(tmp_path):
    inv = invoice()
    inv.add_cost("Unsupported \u6f22 character", 1, 1)
    existing = tmp_path / "invoice.pdf"
    existing.write_bytes(b"existing business record")
    with pytest.raises(ValueError, match="cost description.*Helvetica"):
        pdf_gen.generate_pdf(inv, existing)
    assert existing.read_bytes() == b"existing business record"
    new_path = tmp_path / "not-created" / "invoice.pdf"
    with pytest.raises(ValueError, match="Helvetica"):
        pdf_gen.generate_pdf(inv, new_path)
    assert not new_path.parent.exists()


def test_large_numeric_cells_stay_inside_columns(tmp_path, monkeypatch):
    checked = []

    class RecordingPDF(FPDF):
        def cell(self, w=None, h=None, text="", *args, **kwargs):
            if text and w and re.fullmatch(r"[\d,.]+", text):
                checked.append(text)
                assert self.get_string_width(text) <= w - 2 * self.c_margin + 0.01
                assert self.font_size_pt >= pdf_gen.MIN_FONT_PT
            return super().cell(w, h, text, *args, **kwargs)

    monkeypatch.setattr(pdf_gen, "FPDF", RecordingPDF)
    inv = invoice()
    inv.add_service(datetime(2025, 4, 1), "Large synthetic amount", 1_000_000_000, 9_999_999)
    inv.add_cost("Large synthetic cost", 1_000_000_000, 9_999_999)
    reader = export(inv, tmp_path)
    assert checked
    assert_page_bounds(reader)
    text = re.sub(r"\s+", "", "\n".join(page_texts(reader)))
    assert "GRANDTOTAL:19,999,998,000,000,000.00" in text


def test_empty_cost_list_and_pdf_display_settings(tmp_path):
    inv = invoice()
    inv.add_service(datetime(2025, 4, 1), "No-charge entry", 1, 0)
    inv.flat_fee_amount = 1500
    settings._cache["pdf"]["show_total_hours"] = False
    settings._cache["pdf"]["thousand_separators"] = False
    reader = export(inv, tmp_path)
    text = "\n".join(page_texts(reader))
    assert "TOTAL HOURS BILLED" not in text
    assert "TOTAL COSTS" not in text
    assert "GRAND TOTAL: 1500.00" in text
    assert_page_bounds(reader)


def test_wrapped_typical_invoice_fits_with_readable_font_and_totals(tmp_path):
    inv = invoice()
    for number in range(14):
        inv.add_service(
            datetime(2025, 4, 1),
            f"Review IRS correspondence and prepare draft response {number}",
            0.5,
        )
    inv.flat_fee_desc = "Additional flat service fee"
    inv.flat_fee_amount = 1500
    inv.add_cost("Certified mail", 1, 9.85)
    inv.add_cost("Copies", 35, 0.25)
    inv.add_cost("Court filing fee", 1, 450)
    reader = export(inv, tmp_path)
    assert len(reader.pages) == 1
    assert "GRAND TOTAL: 3,718.60" in page_texts(reader)[0]
    stream = ContentStream(reader.pages[0].get_contents(), reader)
    sizes = [float(args[1]) for args, op in stream.operations if op == b"Tf"]
    assert min(sizes) >= pdf_gen.MIN_FONT_PT
    assert_page_bounds(reader)


def test_very_long_client_header_paginates_without_losing_text(tmp_path):
    inv = invoice()
    tokens = [f"CLIENT{number:04d}" for number in range(1500)]
    inv.client_name = " ".join(tokens)
    inv.add_service(datetime(2025, 4, 1), "Service after client header", 1)
    reader = export(inv, tmp_path)
    assert len(reader.pages) > 1
    words = " ".join(page_texts(reader)).split()
    assert all(words.count(token) == 1 for token in tokens)
    assert "Service after client header" in page_texts(reader)[-1]
    assert "GRAND TOTAL: 250.00" in page_texts(reader)[-1]
    assert_page_bounds(reader)


def test_mutated_invalid_model_cannot_replace_pdf(tmp_path):
    inv = invoice()
    item = inv.add_service(datetime(2025, 4, 1), "Synthetic service", 1)
    item.rate = float("nan")
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"existing PDF")
    with pytest.raises(ValueError, match="finite"):
        pdf_gen.generate_pdf(inv, path)
    assert path.read_bytes() == b"existing PDF"


def test_very_large_finite_total_stays_inside_page(tmp_path):
    inv = invoice()
    inv.add_cost("Synthetic extreme value", 1, 1e100)
    reader = export(inv, tmp_path)
    assert_page_bounds(reader)
    text = re.sub(r"\s+", "", "\n".join(page_texts(reader)))
    assert f"GRANDTOTAL:{pdf_gen.money(inv.grand_total())}" in text
