"""RFQ -> draft quote pipeline. Usage: python run_pipeline.py

Reads every file in rfqs/ and writes outputs/<file name without extension>.json.
"""

import sys
import time

from dotenv import load_dotenv

from ridgeline import config
from ridgeline.catalog import load_catalog
from ridgeline.customers import match_customer
from ridgeline.extract import Extractor
from ridgeline.loaders import UnsupportedFile, is_image, list_rfqs, load_text
from ridgeline.match import Matcher
from ridgeline.output import OutputDoc, build_doc, failure_doc, stub_doc
from ridgeline.report import print_summary


def write(doc: OutputDoc) -> None:
    path = config.OUTPUT_DIR / f"{doc.rfq_id}.json"
    path.write_text(doc.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(config.ROOT / ".env")
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    catalog = load_catalog()
    matcher = Matcher(catalog)
    rfqs = list_rfqs(config.RFQ_DIR)

    extractor = None
    if any(not is_image(p) for p in rfqs):
        try:
            extractor = Extractor()
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    total_in = total_out = 0
    for path in rfqs:
        start = time.perf_counter()
        rfq_id = path.stem
        in_tok = out_tok = 0

        if is_image(path):
            doc = stub_doc(rfq_id)
        else:
            try:
                text = load_text(path)
            except UnsupportedFile as e:
                doc = failure_doc(rfq_id, str(e))
            except Exception as e:  # unreadable file: route to a person, keep going
                doc = failure_doc(rfq_id, f"could not read file: {type(e).__name__}: {e}")
            else:
                result = extractor.extract(text)
                in_tok, out_tok = result.input_tokens, result.output_tokens
                if result.extraction is None:
                    doc = failure_doc(rfq_id, f"extraction failed after {result.attempts} attempts: {result.error}")
                else:
                    ex = result.extraction
                    customer = match_customer(catalog.customers, ex.sender_email, ex.customer_name)
                    doc = build_doc(rfq_id, text, ex, catalog, matcher, customer)

        write(doc)
        total_in += in_tok
        total_out += out_tok
        print_summary(doc, time.perf_counter() - start, in_tok, out_tok)

    print(f"\nDone: {len(rfqs)} RFQs -> {config.OUTPUT_DIR.name}/  total tokens: {total_in} in / {total_out} out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
