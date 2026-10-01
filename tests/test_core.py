from datetime import datetime
from pathlib import Path
import tempfile

from models import Invoice, LineItem, parse_user_date
from pdf_gen import generate_pdf


def test_dates():
    current_year = datetime.now().year
    assert parse_user_date("4/30").year == current_year
    assert parse_user_date("4/30/25").year == 2025
    assert parse_user_date("4/30/2025").year == 2025


def test_totals_and_dedupe():
    inv = Invoice("Test Client", "04/30/2025", 250.0)
    inv.add_service(datetime(2025, 4, 1), "Phone call", 1.0)
    inv.add_service(datetime(2025, 4, 1), "Phone call", 1.0)
    inv.add_cost("Copies", 10, 0.25)

    assert inv.total_hours() == 2.0
    assert inv.total_services() == 500.0
    assert inv.total_costs() == 2.5
    assert inv.grand_total() == 502.5

    removed = inv.dedupe_services()
    assert removed == 1
    assert inv.total_hours() == 1.0
    assert inv.total_services() == 250.0


def test_pdf():
    inv = Invoice("Test Client", "04/30/2025", 250.0)
    inv.add_service(
        datetime(2025, 4, 1),
        "Review file and prepare correspondence",
        1.5,
    )
    inv.add_cost("Certified mail", 1, 9.85)

    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / "test.pdf"
        generate_pdf(inv, out)
        assert out.exists()
        assert out.stat().st_size > 0


if __name__ == "__main__":
    test_dates()
    test_totals_and_dedupe()
    test_pdf()
    print("Core tests passed.")
