"""Console summary printed after each RFQ."""

from .output import OutputDoc

COLUMNS = (("line", 4), ("as_written", 44), ("part", 10), ("method", 21), ("confidence", 10), ("needs_review", 12))


def _cell(value, width: int) -> str:
    text = "-" if value is None else str(value).replace("\t", " ").replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


def print_summary(doc: OutputDoc, elapsed: float, input_tokens: int, output_tokens: int) -> None:
    print(f"\n=== {doc.rfq_id}  customer: {doc.customer_id or '-'} {doc.customer_name or ''}".rstrip())
    print("  ".join(name.ljust(w) for name, w in COLUMNS))
    print("  ".join("-" * w for _, w in COLUMNS))
    for ln in doc.lines:
        conf = None if ln.confidence is None else f"{ln.confidence:.2f}"
        values = (ln.line, ln.as_written, ln.ridgeline_part_number, ln.match_method, conf, ln.needs_review)
        print("  ".join(_cell(v, w).ljust(w) for v, (_, w) in zip(values, COLUMNS)))
    print(f"elapsed: {elapsed:.1f}s  tokens: {input_tokens} in / {output_tokens} out")
