from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


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
        return {
            "line_id": self.line_id,
            "date": self.date.strftime("%Y-%m-%d"),
            "desc": self.desc,
            "hours": self.hours,
            "rate": self.rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineItem":
        raw_date = str(data.get("date", "")).strip()
        try:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
        except Exception:
            try:
                dt = parse_user_date(raw_date)
            except Exception:
                dt = datetime.now()

        return cls(
            date=dt,
            desc=normalize_desc(str(data.get("desc", ""))),
            hours=float(data.get("hours", 0.0)),
            rate=float(data.get("rate", 0.0)),
            line_id=str(data.get("line_id") or uuid4().hex),
        )


@dataclass
class CostItem:
    desc: str
    qty: float
    unit_price: float
    line_id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def total(self) -> float:
        return self.qty * self.unit_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "desc": self.desc,
            "qty": self.qty,
            "unit_price": self.unit_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostItem":
        return cls(
            desc=normalize_desc(str(data.get("desc", ""))),
            qty=float(data.get("qty", 0.0)),
            unit_price=float(data.get("unit_price", 0.0)),
            line_id=str(data.get("line_id") or uuid4().hex),
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
            hours=float(hours),
            rate=float(self.default_rate if rate is None else rate),
        )
        self.services.append(item)
        return item

    def add_cost(self, desc: str, qty: float, unit_price: float) -> CostItem:
        item = CostItem(
            desc=normalize_desc(desc),
            qty=float(qty),
            unit_price=float(unit_price),
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
        return {
            "schema_version": 2,
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
        inv = cls(
            client_name=str(data.get("client_name", "")).strip(),
            invoice_date=str(
                data.get("invoice_date", datetime.now().strftime("%m/%d/%Y"))
            ).strip(),
            default_rate=float(data.get("default_rate", 250.0)),
            flat_fee_desc=(
                normalize_desc(str(data.get("flat_fee_desc")))
                if data.get("flat_fee_desc") not in (None, "")
                else None
            ),
            flat_fee_amount=(
                float(data["flat_fee_amount"])
                if data.get("flat_fee_amount") not in (None, "")
                else None
            ),
        )

        for raw in data.get("services", []):
            if isinstance(raw, dict):
                inv.services.append(LineItem.from_dict(raw))

        for raw in data.get("costs", []):
            if isinstance(raw, dict):
                inv.costs.append(CostItem.from_dict(raw))

        return inv
