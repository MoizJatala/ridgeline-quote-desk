"""Stage 4: assemble the output document for one RFQ."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from . import config
from .catalog import Catalog, normalize_part_number
from .extract import Extraction
from .match import Matcher

Flag = Literal["needs_human_review", "discontinued_replaced", "not_carried", "stub"]
Method = Literal["ridgeline_part_number", "cross_reference", "description", "llm"]
Unit = Literal["EA", "BX", "PK", "CS", "RL", "PR", "FT"]


class OutputLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line: int
    as_written: str
    quantity: int | float | None
    unit: Unit | None
    ridgeline_part_number: str | None
    match_method: Method | None
    confidence: float | None
    needs_review: bool
    flags: list[Flag]
    note: str


class OutputDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfq_id: str
    customer_id: str | None
    customer_name: str | None
    lines: list[OutputLine]
    non_item_rows: list[str]


def needs_review(confidence: float | None, part: str | None, quantity, flags: list[str]) -> bool:
    return (
        confidence is None
        or confidence < config.REVIEW_THRESHOLD
        or part is None
        or quantity is None
        or bool(flags)
    )


def make_line(n: int, as_written: str, quantity=None, unit=None, part=None, method=None,
              confidence=None, flags=None, note: str = "") -> OutputLine:
    flags = list(dict.fromkeys(flags or []))  # dedupe, keep order
    return OutputLine(
        line=n, as_written=as_written, quantity=quantity, unit=unit,
        ridgeline_part_number=part, match_method=method, confidence=confidence,
        needs_review=needs_review(confidence, part, quantity, flags), flags=flags, note=note,
    )


def stub_doc(rfq_id: str) -> OutputDoc:
    line = make_line(1, "entire RFQ", flags=["stub"], note="photo source: needs OCR or a vision model")
    return OutputDoc(rfq_id=rfq_id, customer_id=None, customer_name=None, lines=[line], non_item_rows=[])


def failure_doc(rfq_id: str, error: str) -> OutputDoc:
    line = make_line(1, "entire RFQ", flags=["needs_human_review"], note=error)
    return OutputDoc(rfq_id=rfq_id, customer_id=None, customer_name=None, lines=[line], non_item_rows=[])


def _customer_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    key = unit.strip().strip(".").lower()
    if key.upper() in config.CATALOG_UNITS:
        return key.upper()
    return config.UNIT_SYNONYMS.get(key)


def _clean_quantity(q: float | None):
    if q is None:
        return None
    return int(q) if float(q).is_integer() else q


def _squash_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def build_doc(rfq_id: str, source_text: str, extraction: Extraction, catalog: Catalog,
              matcher: Matcher, customer: dict[str, str] | None) -> OutputDoc:
    source = _squash_ws(source_text)
    lines = []
    for n, ex in enumerate(extraction.lines, start=1):
        m = matcher.match(ex.as_written, ex.part_number_as_written, ex.description, ex.unresolved_reason)
        flags, notes = list(m.flags), list(m.notes)

        if _squash_ws(ex.as_written) not in source:
            flags.append("needs_human_review")
            notes.append("as_written was not found verbatim in the document")

        quantity = _clean_quantity(ex.quantity)
        if quantity is None:
            notes.append("quantity missing or vague")

        product = catalog.products.get(normalize_part_number(m.part_number)) if m.part_number else None
        unit = _customer_unit(ex.unit)
        if unit is None:
            if ex.unit:
                notes.append(f"customer unit '{ex.unit}' is not a catalog unit")
            if product:
                unit = product["unit"]
                # A customer quoting our own part number is ordering in that part's unit,
                # so the pieces-vs-packs check only applies to cross-reference and description matches.
                if (ex.unit is None and quantity is not None and unit in config.PACK_UNITS
                        and m.method in ("cross_reference", "description")):
                    flags.append("needs_human_review")
                    notes.append(f"no unit given and product is sold by {unit}; quantity may be pieces")
        elif product and unit != product["unit"]:
            notes.append(f"customer unit {unit} differs from catalog unit {product['unit']}")

        if ex.description and m.method in ("description", None):
            notes.append(f"description read as: {ex.description}")

        lines.append(make_line(
            n, ex.as_written, quantity, unit, m.part_number, m.method, m.confidence, flags, "; ".join(notes),
        ))

    return OutputDoc(
        rfq_id=rfq_id,
        customer_id=customer["customer_id"] if customer else None,
        customer_name=customer["name"] if customer else extraction.customer_name,
        lines=lines,
        non_item_rows=extraction.non_item_rows,
    )
