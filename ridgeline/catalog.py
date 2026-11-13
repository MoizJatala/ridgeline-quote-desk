"""Load the reference CSVs as strings. Prices are dropped at load time."""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# Columns kept from products.csv. list_price is deliberately not in this list.
PRODUCT_COLUMNS = ("part_number", "description", "category", "unit", "status", "replaced_by")


def _read(path: Path, keep: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = []
        for row in csv.DictReader(f):
            cols = keep or tuple(row.keys())
            rows.append({c: (row.get(c) or "").strip() for c in cols})
        return rows


def normalize_part_number(value: str) -> str:
    return "".join(value.split()).upper()


@dataclass
class Catalog:
    products: dict[str, dict[str, str]]
    xref: dict[str, list[dict[str, str]]]  # normalized competitor PN -> rows
    customers: list[dict[str, str]]
    descriptions: list[tuple[str, str]] = field(default_factory=list)  # (part_number, description)


def load_catalog() -> Catalog:
    products = {}
    for row in _read(config.PRODUCTS_CSV, PRODUCT_COLUMNS):
        products[normalize_part_number(row["part_number"])] = row

    xref: dict[str, list[dict[str, str]]] = {}
    for row in _read(config.CROSS_REFERENCE_CSV):
        xref.setdefault(normalize_part_number(row["competitor_part_number"]), []).append(row)

    customers = _read(config.CUSTOMERS_CSV)
    descriptions = [(p["part_number"], p["description"]) for p in products.values()]
    return Catalog(products=products, xref=xref, customers=customers, descriptions=descriptions)
