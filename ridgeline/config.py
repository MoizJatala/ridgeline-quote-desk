"""All tunable constants for the pipeline live here."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RFQ_DIR = ROOT / "rfqs"
OUTPUT_DIR = ROOT / "outputs"
PRODUCTS_CSV = ROOT / "products.csv"
CROSS_REFERENCE_CSV = ROOT / "cross_reference.csv"
CUSTOMERS_CSV = ROOT / "customers.csv"

# A line needs review when its confidence is below this value.
REVIEW_THRESHOLD = 0.8

# --- LLM ------------------------------------------------------------------
MAX_TOKENS = 16000
TEMPERATURE = 0  # sent only if the model accepts it
EXTRACTION_ATTEMPTS = 2  # first try + one retry

# --- Matching ---------------------------------------------------------------
RIDGELINE_CONFIDENCE = 1.0

XREF_BASE_CONFIDENCE = 0.95
# Deductions keyed by the exact text of cross_reference.csv `notes`.
XREF_NOTE_PENALTIES = {
    "close sub": 0.20,
    "pkg qty differs": 0.10,
    "check thickness": 0.15,
}
XREF_OTHER_NOTE_PENALTY = 0.15  # any note not listed above
XREF_BLANK_VERIFIED_PENALTY = 0.10
XREF_STALE_PENALTY = 0.05
# Fixed cutoff (not "N days ago") so results don't drift from day to day.
XREF_STALE_BEFORE = "2025-01-01"

# Description fallback
DESC_MIN_SCORE = 0.45  # below this, no match
DESC_CONFIDENCE_CAP = 0.90  # a description match never looks as sure as a part number
# Confidence is lowered by however much the runner-up is closer than this to the best score.
DESC_MARGIN_TARGET = 0.25

# --- Output -----------------------------------------------------------------
CATALOG_UNITS = {"EA", "BX", "PK", "CS", "RL", "PR", "FT"}
PACK_UNITS = {"BX", "PK", "CS"}  # quantity is ambiguous if the customer gave no unit

UNIT_SYNONYMS = {
    "ea": "EA", "each": "EA", "pc": "EA", "pcs": "EA", "piece": "EA", "pieces": "EA",
    "bx": "BX", "box": "BX", "boxes": "BX",
    "pk": "PK", "pack": "PK", "packs": "PK", "pkg": "PK", "package": "PK", "packages": "PK",
    "cs": "CS", "case": "CS", "cases": "CS",
    "rl": "RL", "roll": "RL", "rolls": "RL",
    "pr": "PR", "pair": "PR", "pairs": "PR",
    "ft": "FT", "foot": "FT", "feet": "FT",
}

# `llm` is an allowed value but never emitted: the LLM never picks part numbers.
MATCH_METHODS = {"ridgeline_part_number", "cross_reference", "description", "llm"}
ALLOWED_FLAGS = {"needs_human_review", "discontinued_replaced", "not_carried", "stub"}
