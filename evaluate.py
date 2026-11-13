"""Score outputs/ against answer_key/. Usage: python evaluate.py

This is the only code in the repository that reads answer_key/. The pipeline never imports it.
Writes evaluation/results.json.
"""

import json
import re
import sys
from pathlib import Path

from ridgeline.config import REVIEW_THRESHOLD, ROOT

KEY_DIR = ROOT / "answer_key"
OUT_DIR = ROOT / "outputs"
RESULTS = ROOT / "evaluation" / "results.json"
PART_FIELDS = ("ridgeline_part_number", "expected_part_number")
SWEEP = [round(0.5 + 0.05 * i, 2) for i in range(10)]  # 0.50 .. 0.95


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def number(r: float | None) -> float:
    return 0.0 if r is None else r


def squash(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def key_part(line: dict):
    for f in PART_FIELDS:
        if f in line:
            return line[f]
    return None


def same_qty(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return squash(a) == squash(b)


def same_unit(a, b) -> bool:
    return squash(a) == squash(b)


def loose_text(a, b) -> bool:
    a, b = squash(a), squash(b)
    return bool(a and b) and (a in b or b in a)


def needs_review_at(line: dict, t: float) -> bool:
    c = line.get("confidence")
    return (c is None or c < t or line.get("ridgeline_part_number") is None
            or line.get("quantity") is None or bool(line.get("flags")))


def load_lines(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(lines, list):
        raise ValueError(f"{path.name}: no 'lines' list (top-level keys: {sorted(data) if isinstance(data, dict) else type(data).__name__})")
    return [dict(ln, line=ln.get("line", i)) for i, ln in enumerate(lines, start=1)]


class Tally:
    def __init__(self) -> None:
        self.c = {k: 0 for k in (
            "key_lines", "extra_lines", "extraction_ok", "as_written_loose_ok",
            "returned_part", "part_correct", "key_expects_part",
            "key_expects_null", "abstained_ok",
            "flags_total", "flags_ok", "method_total", "method_ok",
        )}

    def add(self, other: "Tally") -> None:
        for k, v in other.c.items():
            self.c[k] += v

    def metrics(self) -> dict:
        c = self.c
        return {
            "extraction_accuracy": ratio(c["extraction_ok"], c["key_lines"] + c["extra_lines"]),
            "as_written_loose_match": ratio(c["as_written_loose_ok"], c["key_lines"]),
            "match_precision": ratio(c["part_correct"], c["returned_part"]),
            "match_recall": ratio(c["part_correct"], c["key_expects_part"]),
            "abstention_accuracy": ratio(c["abstained_ok"], c["key_expects_null"]),
            "flag_accuracy": ratio(c["flags_ok"], c["flags_total"]),
            "match_method_accuracy": ratio(c["method_ok"], c["method_total"]),
            "counts": dict(c),
        }


def evaluate_rfq(rfq_id: str, key: list[dict], ours: list[dict], mismatches: list[str],
                 sweep_rows: list[tuple[dict, bool]]) -> Tally:
    t = Tally()
    by_num = {ln["line"]: ln for ln in ours}
    key_nums = {k["line"] for k in key}

    for k in key:
        n = k["line"]
        t.c["key_lines"] += 1
        exp_part = key_part(k)
        if exp_part is not None:
            t.c["key_expects_part"] += 1
        else:
            t.c["key_expects_null"] += 1
        o = by_num.get(n)
        where = f"{rfq_id} line {n}"
        if o is None:
            mismatches.append(f"{where}: MISSING line (expected as_written={k.get('as_written')!r}, "
                              f"qty={k.get('quantity')}, unit={k.get('unit')}, part={exp_part})")
            continue

        qty_ok, unit_ok = same_qty(k.get("quantity"), o.get("quantity")), same_unit(k.get("unit"), o.get("unit"))
        if qty_ok and unit_ok:
            t.c["extraction_ok"] += 1
        else:
            mismatches.append(f"{where}: quantity/unit expected {k.get('quantity')} {k.get('unit')}, "
                              f"got {o.get('quantity')} {o.get('unit')}")
        if loose_text(k.get("as_written"), o.get("as_written")):
            t.c["as_written_loose_ok"] += 1
        elif "as_written" in k:
            mismatches.append(f"{where}: as_written expected {k.get('as_written')!r}, got {o.get('as_written')!r}")

        got_part = o.get("ridgeline_part_number")
        part_ok = got_part is not None and got_part == exp_part
        if got_part is not None:
            t.c["returned_part"] += 1
        if part_ok:
            t.c["part_correct"] += 1
        if exp_part is None and got_part is None:
            t.c["abstained_ok"] += 1
        if got_part != exp_part:
            mismatches.append(f"{where}: part expected {exp_part}, got {got_part} "
                              f"(method {o.get('match_method')}, confidence {o.get('confidence')})")

        if "flags" in k:
            t.c["flags_total"] += 1
            if sorted(k["flags"] or []) == sorted(o.get("flags") or []):
                t.c["flags_ok"] += 1
            else:
                mismatches.append(f"{where}: flags expected {sorted(k['flags'] or [])}, got {sorted(o.get('flags') or [])}")
        if "match_method" in k:
            t.c["method_total"] += 1
            if k["match_method"] == o.get("match_method"):
                t.c["method_ok"] += 1
            else:
                mismatches.append(f"{where}: match_method expected {k['match_method']}, got {o.get('match_method')}")

        sweep_rows.append((o, part_ok and qty_ok and unit_ok))

    for o in ours:
        if o["line"] not in key_nums:
            t.c["extra_lines"] += 1
            if o.get("ridgeline_part_number") is not None:
                t.c["returned_part"] += 1
            mismatches.append(f"{rfq_id} line {o['line']}: EXTRA line {o.get('as_written')!r}")
            sweep_rows.append((o, False))
    return t


def main() -> int:
    key_files = sorted(KEY_DIR.glob("*.json"))
    if not key_files:
        print("no answer keys found", file=sys.stderr)
        return 1

    total, per_rfq, mismatches, sweep_rows = Tally(), {}, [], []
    for kf in key_files:
        rfq_id = kf.stem
        key = load_lines(kf)
        out_path = OUT_DIR / f"{rfq_id}.json"
        if out_path.exists():
            ours = load_lines(out_path)
        else:
            ours = []
            mismatches.append(f"{rfq_id}: no output file at outputs/{out_path.name}")
        t = evaluate_rfq(rfq_id, key, ours, mismatches, sweep_rows)
        per_rfq[rfq_id] = t.metrics()
        total.add(t)

    m = total.metrics()
    print(f"Evaluated {len(key_files)} RFQs, {m['counts']['key_lines']} answer-key lines "
          f"(review threshold {REVIEW_THRESHOLD})\n")
    rows = [("extraction_accuracy", m["extraction_accuracy"]),
            ("as_written loose match", m["as_written_loose_match"]),
            ("match_precision", m["match_precision"]),
            ("match_recall", m["match_recall"]),
            ("abstention_accuracy", m["abstention_accuracy"]),
            ("flag_accuracy", m["flag_accuracy"]),
            ("match_method_accuracy", m["match_method_accuracy"])]
    for name, v in rows:
        print(f"  {name:<24} {'n/a (field not in key)' if v is None else f'{v:.3f}'}")

    print("\nPer RFQ:")
    print(f"  {'rfq':<20} {'extract':>8} {'prec':>6} {'recall':>7} {'abstain':>8} {'flags':>6} {'method':>7}")
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
    for rid, pm in per_rfq.items():
        print(f"  {rid:<20} {fmt(pm['extraction_accuracy']):>8} {fmt(pm['match_precision']):>6} "
              f"{fmt(pm['match_recall']):>7} {fmt(pm['abstention_accuracy']):>8} "
              f"{fmt(pm['flag_accuracy']):>6} {fmt(pm['match_method_accuracy']):>7}")

    print("\nThreshold sweep (a line is auto-accepted when it would not need review):")
    print(f"  {'threshold':>9} {'accepted':>9} {'wrong':>6} {'review_rate':>12}")
    sweep = []
    n_lines = len(sweep_rows)
    for th in SWEEP:
        accepted = [ok for ln, ok in sweep_rows if not needs_review_at(ln, th)]
        wrong = sum(1 for ok in accepted if not ok)
        review_rate = ratio(n_lines - len(accepted), n_lines)
        sweep.append({"threshold": th, "auto_accepted": len(accepted), "auto_accepted_wrong": wrong,
                      "review_rate": review_rate})
        mark = "  <- current" if abs(th - REVIEW_THRESHOLD) < 1e-9 else ""
        print(f"  {th:>9.2f} {len(accepted):>9} {wrong:>6} {fmt(review_rate):>12}{mark}")

    print(f"\nMismatches ({len(mismatches)}):")
    for line in mismatches:
        print(f"  - {line}")

    results = {
        "threshold": REVIEW_THRESHOLD,
        "extraction_accuracy": number(m["extraction_accuracy"]),
        "match_precision": number(m["match_precision"]),
        "match_recall": number(m["match_recall"]),
        "additional_metrics": {
            "as_written_loose_match": m["as_written_loose_match"],
            "abstention_accuracy": m["abstention_accuracy"],
            "flag_accuracy": m["flag_accuracy"],
            "match_method_accuracy": m["match_method_accuracy"],
            "counts": m["counts"],
            "per_rfq": per_rfq,
            "threshold_sweep": sweep,
            "mismatch_count": len(mismatches),
        },
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
