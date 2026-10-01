from copy import deepcopy
from datetime import datetime

import pytest

from models import CostItem, Invoice, LineItem, normalize_desc, parse_user_date


def invoice_payload():
    return {
        "client_name": "Synthetic Client",
        "invoice_date": "04/30/2025",
        "default_rate": 250,
        "services": [{"date": "2025-04-01", "desc": "review IRS file", "hours": 1.5, "rate": 200}],
        "costs": [{"desc": "Certified mail", "qty": 2, "unit_price": 9.85}],
    }


def test_description_preserves_acronyms():
    assert normalize_desc("  review IRS correspondence and prepare response  ") == "Review IRS correspondence and prepare response"


@pytest.mark.parametrize("value", ["", "2/29/2025", "13/1/25", "4/31/25", "1/1/-1", "1/1/25/2", "not a date"])
def test_reject_invalid_user_dates(value):
    with pytest.raises(ValueError):
        parse_user_date(value)


def test_legacy_load_and_schema_roundtrip_preserve_lines_and_ids():
    payload = invoice_payload()
    inv = Invoice.from_dict(payload)
    assert inv.services[0].desc == "Review IRS file"
    assert inv.grand_total() == pytest.approx(319.70)
    encoded = inv.to_dict()
    assert encoded["schema_version"] == 2
    restored = Invoice.from_dict(encoded)
    assert restored.to_dict() == encoded
    assert payload == invoice_payload()


def test_legacy_numeric_strings_and_user_dates():
    payload = invoice_payload()
    payload["services"][0].update(date="4/1/25", hours="0", rate="0")
    payload["costs"][0].update(qty="2", unit_price="9.85")
    payload["default_rate"] = "250"
    inv = Invoice.from_dict(payload)
    assert inv.services[0].date == datetime(2025, 4, 1)
    assert inv.services[0].amount == 0
    assert inv.default_rate == 250
    assert inv.total_costs() == pytest.approx(19.70)


def test_legacy_missing_rate_inherits_invoice_default_but_zero_is_preserved():
    payload = invoice_payload()
    payload["services"][0].pop("rate")
    payload["services"].append({"date": "2025-04-02", "desc": "No charge", "hours": 1, "rate": 0})
    inv = Invoice.from_dict(payload)
    assert inv.services[0].rate == 250
    assert inv.services[1].rate == 0


@pytest.mark.parametrize("version", [0, 3, 999, "2", None, True])
def test_reject_unknown_or_malformed_schema(version):
    with pytest.raises(ValueError, match="schema version"):
        Invoice.from_dict({**invoice_payload(), "schema_version": version})


@pytest.mark.parametrize("field", ["services", "costs"])
@pytest.mark.parametrize("value", [None, {}, "lines", [None], [123]])
def test_reject_malformed_lines_instead_of_discarding_them(field, value):
    with pytest.raises(ValueError, match=field):
        Invoice.from_dict({**invoice_payload(), field: value})


@pytest.mark.parametrize("date", [None, "", "bad date", "2025-02-29"])
def test_invalid_service_date_is_not_replaced_with_today(date):
    payload = invoice_payload()
    payload["services"][0]["date"] = date
    with pytest.raises(ValueError, match=r"services\[0\].*date"):
        Invoice.from_dict(payload)


def test_invalid_invoice_date_is_rejected():
    with pytest.raises(ValueError, match="Invoice date"):
        Invoice.from_dict({**invoice_payload(), "invoice_date": "bad date"})


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", -1, None, True, "not a number"])
@pytest.mark.parametrize("field", ["hours", "rate"])
def test_invalid_service_numbers_are_rejected(field, bad):
    payload = invoice_payload()
    payload["services"][0][field] = bad
    with pytest.raises(ValueError, match=r"services\[0\]"):
        Invoice.from_dict(payload)


@pytest.mark.parametrize("field", ["qty", "unit_price"])
def test_invalid_cost_numbers_are_rejected(field):
    payload = invoice_payload()
    payload["costs"][0][field] = float("inf")
    with pytest.raises(ValueError, match=r"costs\[0\]"):
        Invoice.from_dict(payload)


def test_import_repairs_repeated_and_missing_ids_without_removing_lines():
    payload = invoice_payload()
    first = payload["services"][0]
    first["line_id"] = "preserved"
    payload["services"].extend([
        {**first, "desc": "Second", "line_id": "preserved"},
        {**first, "desc": "Third", "line_id": ""},
    ])
    payload["costs"][0]["line_id"] = "preserved"
    inv = Invoice.from_dict(payload)
    ids = [item.line_id for item in inv.services + inv.costs]
    assert len(ids) == len(set(ids)) == 4
    assert inv.services[0].line_id == "preserved"
    assert inv.find_service(inv.services[1].line_id) is inv.services[1]
    assert Invoice.from_dict(inv.to_dict()).to_dict() == inv.to_dict()


def test_mixed_fees_zero_hours_rates_and_bulk_rate_application():
    inv = Invoice("Synthetic Client", "04/30/2025", 250, flat_fee_desc="Attorney Fees", flat_fee_amount=1500)
    first = inv.add_service(datetime(2025, 4, 1), "Hourly service", 2, 200)
    second = inv.add_service(datetime(2025, 4, 2), "No charge", 3, 0)
    inv.add_service(datetime(2025, 4, 3), "Zero hours", 0)
    inv.add_cost("Copies", 10, 0.25)
    ids = [item.line_id for item in inv.services]
    assert inv.total_hours() == 5
    assert inv.grand_total() == 1902.50
    inv.default_rate = 300
    inv.apply_default_rate_to_all_services()
    assert first.rate == second.rate == 300
    assert [item.line_id for item in inv.services] == ids
    assert inv.grand_total() == 3002.50


def test_duplicate_check_exclusion_and_dedupe_keep_first_identity():
    inv = Invoice("Synthetic Client", "04/30/2025", 250)
    first = inv.add_service(datetime(2025, 4, 1), "Review IRS file", 1)
    candidate = LineItem(first.date, " review IRS FILE ", 1, 250)
    assert inv.has_duplicate_service(candidate)
    assert not inv.has_duplicate_service(candidate, exclude_line_id=first.line_id)
    inv.services.append(candidate)
    assert inv.dedupe_services() == 1
    assert inv.services == [first]


def test_serialization_rechecks_mutated_values():
    inv = Invoice.from_dict(invoice_payload())
    inv.services[0].rate = float("nan")
    with pytest.raises(ValueError, match="Rate"):
        inv.to_dict()


def test_overflowing_amounts_are_rejected():
    with pytest.raises(ValueError, match="Service amount"):
        LineItem(datetime(2025, 4, 1), "Synthetic work", 1e308, 1e308)
    with pytest.raises(ValueError, match="Cost total"):
        CostItem("Synthetic cost", 1e308, 1e308)


def test_repeated_ids_in_mutated_invoice_cannot_be_saved():
    inv = Invoice.from_dict(invoice_payload())
    other = deepcopy(inv.services[0])
    other.desc = "Other work"
    inv.services.append(other)
    with pytest.raises(ValueError, match="unique line ID"):
        inv.to_dict()
