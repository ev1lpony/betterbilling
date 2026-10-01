from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = 2


def validate_nonnegative_number(value: Any, field_name: str) -> float:
    """Accept legacy numeric strings, but never NaN, infinity, or negatives."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite number >= 0")
    return number


def _description(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    return normalize_desc(value)


def _stored_date(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a date")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        try:
            return parse_user_date(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{field_name} is invalid: use M/D, M/D/YY, M/D/YYYY, or YYYY-MM-DD") from exc


def _line_id(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else uuid4().hex


def normalize_desc(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return value[0].upper() + value[1:]


def parse_user_date(value: str) -> datetime:
    value = value.strip()
    if not value:
        raise ValueError("Empty date")

    parts = value.split("/")
    if any(not part.strip().isdecimal() for part in parts):
        raise ValueError("Use M/D, M/D/YY, or M/D/YYYY")
    now = datetime.now()

    if len(parts) == 2:
        month, day = map(int, parts)
        year = now.year
    elif len(parts) == 3:
        month, day, raw_year = map(int, parts)
        year = 2000 + raw_year if raw_year < 100 else raw_year
    else:
        raise ValueError("Use M/D, M/D/YY, or M/D/YYYY")

    return datetime(year, month, day)


def format_date_short(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.strftime('%y')}"


def format_date_full(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y")


@dataclass
class LineItem:
    date: datetime
    desc: str
    hours: float
    rate: float
    line_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.hours = validate_nonnegative_number(self.hours, "Hours")
        self.rate = validate_nonnegative_number(self.rate, "Rate")
        self.desc = _description(self.desc, "Service description")
        self.line_id = _line_id(self.line_id)
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.date, datetime):
            raise ValueError("Service date must be a datetime")
        _description(self.desc, "Service description")
        hours = validate_nonnegative_number(self.hours, "Hours")
        rate = validate_nonnegative_number(self.rate, "Rate")
        validate_nonnegative_number(hours * rate, "Service amount")

    @property
    def amount(self) -> float:
        return self.hours * self.rate

    def duplicate_key(self) -> tuple[str, str, float, float]:
        return (
            self.date.strftime("%Y-%m-%d"),
            normalize_desc(self.desc).lower(),
            round(float(self.hours), 4),
            round(float(self.rate), 4),
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "line_id": self.line_id,
            "date": self.date.strftime("%Y-%m-%d"),
            "desc": self.desc,
            "hours": self.hours,
            "rate": self.rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineItem":
        if not isinstance(data, dict):
            raise ValueError("Service line must be an object")
        dt = _stored_date(data.get("date", ""), "Service date")

        return cls(
            date=dt,
            desc=_description(data.get("desc", ""), "Service description"),
            hours=validate_nonnegative_number(data.get("hours", 0.0), "Hours"),
            rate=validate_nonnegative_number(data.get("rate", 0.0), "Rate"),
            line_id=_line_id(data.get("line_id")),
        )


@dataclass
class CostItem:
    desc: str
    qty: float
    unit_price: float
    line_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.qty = validate_nonnegative_number(self.qty, "Quantity")
        self.unit_price = validate_nonnegative_number(self.unit_price, "Unit price")
        self.desc = _description(self.desc, "Cost description")
        self.line_id = _line_id(self.line_id)
        self.validate()

    def validate(self) -> None:
        _description(self.desc, "Cost description")
        qty = validate_nonnegative_number(self.qty, "Quantity")
        unit_price = validate_nonnegative_number(self.unit_price, "Unit price")
        validate_nonnegative_number(qty * unit_price, "Cost total")

    @property
    def total(self) -> float:
        return self.qty * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "line_id": self.line_id,
            "desc": self.desc,
            "qty": self.qty,
            "unit_price": self.unit_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostItem":
        if not isinstance(data, dict):
            raise ValueError("Cost line must be an object")
        return cls(
            desc=_description(data.get("desc", ""), "Cost description"),
            qty=validate_nonnegative_number(data.get("qty", 0.0), "Quantity"),
            unit_price=validate_nonnegative_number(data.get("unit_price", 0.0), "Unit price"),
            line_id=_line_id(data.get("line_id")),
        )


@dataclass
class Invoice:
    client_name: str
    invoice_date: str
    default_rate: float
    services: list[LineItem] = field(default_factory=list)
    costs: list[CostItem] = field(default_factory=list)
    flat_fee_desc: str | None = None
    flat_fee_amount: float | None = None

    def __post_init__(self) -> None:
        self.default_rate = validate_nonnegative_number(self.default_rate, "Default rate")
        if self.flat_fee_amount is not None:
            self.flat_fee_amount = validate_nonnegative_number(self.flat_fee_amount, "Flat fee amount")

    def validate(self) -> None:
        """Recheck mutable values at the persistence boundary."""
        if not isinstance(self.client_name, str):
            raise ValueError("Client name must be text")
        _stored_date(self.invoice_date, "Invoice date")
        validate_nonnegative_number(self.default_rate, "Default rate")
        if self.flat_fee_amount is not None:
            validate_nonnegative_number(self.flat_fee_amount, "Flat fee amount")
        if self.flat_fee_desc is not None:
            _description(self.flat_fee_desc, "Flat fee description")
        ids: set[str] = set()
        for items, item_type, name in (
            (self.services, LineItem, "Services"),
            (self.costs, CostItem, "Costs"),
        ):
            if not isinstance(items, list):
                raise ValueError(f"{name} must be a list")
            for item in items:
                if not isinstance(item, item_type):
                    raise ValueError(f"{name} contains an invalid line")
                item.validate()
                if not isinstance(item.line_id, str) or not item.line_id.strip() or item.line_id in ids:
                    raise ValueError("Every service and cost must have a unique line ID")
                ids.add(item.line_id)
        for field_name, amount in (
            ("Total hours", self.total_hours()),
            ("Total service fees", self.total_services()),
            ("Total costs", self.total_costs()),
            ("Grand total", self.grand_total()),
        ):
            validate_nonnegative_number(amount, field_name)

    def add_service(
        self,
        date: datetime,
        desc: str,
        hours: float,
        rate: float | None = None,
    ) -> LineItem:
        item = LineItem(
            date=date,
            desc=normalize_desc(desc),
            hours=validate_nonnegative_number(hours, "Hours"),
            rate=validate_nonnegative_number(self.default_rate if rate is None else rate, "Rate"),
        )
        self.services.append(item)
        return item

    def add_cost(self, desc: str, qty: float, unit_price: float) -> CostItem:
        item = CostItem(
            desc=normalize_desc(desc),
            qty=validate_nonnegative_number(qty, "Quantity"),
            unit_price=validate_nonnegative_number(unit_price, "Unit price"),
        )
        self.costs.append(item)
        return item

    def total_hours(self) -> float:
        return sum(item.hours for item in self.services)

    def total_services(self) -> float:
        return sum(item.amount for item in self.services) + float(self.flat_fee_amount or 0.0)

    def total_costs(self) -> float:
        return sum(item.total for item in self.costs)

    def grand_total(self) -> float:
        return self.total_services() + self.total_costs()

    def find_service(self, line_id: str) -> LineItem | None:
        return next((x for x in self.services if x.line_id == line_id), None)

    def find_cost(self, line_id: str) -> CostItem | None:
        return next((x for x in self.costs if x.line_id == line_id), None)

    def has_duplicate_service(
        self,
        candidate: LineItem,
        exclude_line_id: str | None = None,
    ) -> bool:
        key = candidate.duplicate_key()
        return any(
            item.line_id != exclude_line_id and item.duplicate_key() == key
            for item in self.services
        )

    def dedupe_services(self) -> int:
        seen: set[tuple[str, str, float, float]] = set()
        unique: list[LineItem] = []
        removed = 0
        for item in self.services:
            key = item.duplicate_key()
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            unique.append(item)
        self.services = unique
        return removed

    def apply_default_rate_to_all_services(self) -> None:
        for item in self.services:
            item.rate = self.default_rate

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": SCHEMA_VERSION,
            "client_name": self.client_name,
            "invoice_date": self.invoice_date,
            "default_rate": self.default_rate,
            "flat_fee_desc": self.flat_fee_desc,
            "flat_fee_amount": self.flat_fee_amount,
            "services": [item.to_dict() for item in self.services],
            "costs": [item.to_dict() for item in self.costs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Invoice":
        if not isinstance(data, dict):
            raise ValueError("Invoice JSON root must be an object")
        version = data.get("schema_version", 1)
        if type(version) is not int or version not in (1, SCHEMA_VERSION):
            raise ValueError(f"Unsupported invoice schema version: {version!r}")
        client_name = data.get("client_name", "")
        if not isinstance(client_name, str):
            raise ValueError("Client name must be text")
        invoice_date = _stored_date(
            data.get("invoice_date", datetime.now().strftime("%m/%d/%Y")), "Invoice date"
        )
        inv = cls(
            client_name=client_name.strip(),
            invoice_date=format_date_full(invoice_date),
            default_rate=validate_nonnegative_number(data.get("default_rate", 250.0), "Default rate"),
            flat_fee_desc=(
                _description(data.get("flat_fee_desc"), "Flat fee description")
                if data.get("flat_fee_desc") not in (None, "")
                else None
            ),
            flat_fee_amount=(
                validate_nonnegative_number(data["flat_fee_amount"], "Flat fee amount")
                if data.get("flat_fee_amount") not in (None, "")
                else None
            ),
        )

        # Keep valid IDs, including IDs appearing later in the file. Repeated
        # or missing IDs get new identities without discarding invoice lines.
        reserved_ids: set[str] = set()
        for name in ("services", "costs"):
            records = data.get(name, [])
            if not isinstance(records, list):
                raise ValueError(f"{name} must be a list")
            for index, raw in enumerate(records):
                if not isinstance(raw, dict):
                    raise ValueError(f"{name}[{index}] must be an object")
                value = raw.get("line_id")
                if isinstance(value, str) and value.strip():
                    reserved_ids.add(value.strip())

        seen_ids: set[str] = set()
        for name, item_type in (("services", LineItem), ("costs", CostItem)):
            for index, raw in enumerate(data.get(name, [])):
                try:
                    legacy_line = raw
                    if name == "services" and "rate" not in raw:
                        legacy_line = {**raw, "rate": inv.default_rate}
                    item = item_type.from_dict(legacy_line)
                except ValueError as exc:
                    raise ValueError(f"{name}[{index}]: {exc}") from exc
                raw_id = raw.get("line_id")
                has_original_id = isinstance(raw_id, str) and bool(raw_id.strip())
                if not has_original_id or item.line_id in seen_ids:
                    while item.line_id in reserved_ids or item.line_id in seen_ids:
                        item.line_id = uuid4().hex
                seen_ids.add(item.line_id)
                getattr(inv, name).append(item)

        inv.validate()
        return inv
