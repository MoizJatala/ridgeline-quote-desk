"""Stage 3: deterministic matching of extracted lines to Ridgeline part numbers.

Part numbers come only from products.csv and cross_reference.csv.
"""

import re
from dataclasses import dataclass, field

from . import config
from .catalog import Catalog, normalize_part_number
from .normalize import spec_tokens, tokenize

RL_PATTERN = re.compile(r"\bRL\d{6}\b", re.IGNORECASE)


@dataclass
class MatchResult:
    part_number: str | None = None
    method: str | None = None
    confidence: float | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Matcher:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._indexed = [
            (pn, tokens, spec_tokens(tokens))
            for pn, desc in catalog.descriptions
            for tokens in [tokenize(desc)]
        ]

    # --- step 1 -------------------------------------------------------------
    def _ridgeline(self, candidates: list[str]) -> MatchResult | None:
        for raw in candidates:
            pn = normalize_part_number(raw)
            if pn in self.catalog.products:
                return MatchResult(self.catalog.products[pn]["part_number"], "ridgeline_part_number",
                                   config.RIDGELINE_CONFIDENCE)
        return None

    # --- step 2 -------------------------------------------------------------
    def _cross_reference(self, candidates: list[str]) -> MatchResult | None:
        for raw in candidates:
            rows = self.catalog.xref.get(normalize_part_number(raw))
            if not rows:
                continue
            targets = sorted({r["ridgeline_part_number"] for r in rows})
            if len(targets) > 1:
                return MatchResult(
                    flags=["needs_human_review"],
                    notes=[f"{raw} maps to more than one Ridgeline part in cross_reference ({', '.join(targets)})"],
                    method=None,
                )
            row = rows[0]
            conf = config.XREF_BASE_CONFIDENCE
            notes = [f"cross_reference: {row['competitor']} {row['competitor_part_number']} -> {row['ridgeline_part_number']}"]
            if row["notes"]:
                penalty = config.XREF_NOTE_PENALTIES.get(row["notes"].lower(), config.XREF_OTHER_NOTE_PENALTY)
                conf -= penalty
                notes.append(f"cross_reference note '{row['notes']}' (-{penalty:.2f})")
            if not row["last_verified"]:
                conf -= config.XREF_BLANK_VERIFIED_PENALTY
                notes.append(f"last_verified is blank (-{config.XREF_BLANK_VERIFIED_PENALTY:.2f})")
            elif row["last_verified"] < config.XREF_STALE_BEFORE:
                conf -= config.XREF_STALE_PENALTY
                notes.append(f"last_verified {row['last_verified']} is before {config.XREF_STALE_BEFORE} "
                             f"(-{config.XREF_STALE_PENALTY:.2f})")
            pn = row["ridgeline_part_number"]
            if normalize_part_number(pn) not in self.catalog.products:
                return MatchResult(flags=["needs_human_review"],
                                   notes=[f"cross_reference target {pn} is not in products.csv"])
            return MatchResult(pn, "cross_reference", round(conf, 2), notes=notes)
        return None

    # --- step 3 -------------------------------------------------------------
    def _description(self, description: str) -> MatchResult | None:
        query = tokenize(description)
        if not query:
            return None
        q_spec = spec_tokens(query)
        scored = []
        for pn, tokens, _ in self._indexed:
            if not q_spec <= tokens:
                continue  # every spec in the request must agree
            overlap = len(query & tokens)
            if overlap == 0:
                continue
            coverage = overlap / len(query)
            jaccard = overlap / len(query | tokens)
            scored.append((0.8 * coverage + 0.2 * jaccard, pn))
        if not scored:
            return None
        scored.sort(reverse=True)
        best, pn = scored[0]
        if best < config.DESC_MIN_SCORE:
            return None
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        margin = best - runner_up
        conf = best - max(0.0, config.DESC_MARGIN_TARGET - margin)
        conf = round(min(config.DESC_CONFIDENCE_CAP, max(0.0, conf)), 2)
        note = f"description match score {best:.2f}"
        if len(scored) > 1:
            note += f", runner-up {scored[1][1]} at {runner_up:.2f}"
        return MatchResult(pn, "description", conf, notes=[note])

    # --- discontinued -------------------------------------------------------
    def _apply_replacement(self, result: MatchResult) -> MatchResult:
        product = self.catalog.products.get(normalize_part_number(result.part_number or ""))
        if not product or product["status"] != "discontinued":
            return result
        replacement = product["replaced_by"]
        if replacement and normalize_part_number(replacement) in self.catalog.products:
            result.notes.append(f"{product['part_number']} is discontinued; replaced by {replacement}")
            result.part_number = self.catalog.products[normalize_part_number(replacement)]["part_number"]
            result.flags.append("discontinued_replaced")
        else:
            result.notes.append(f"{product['part_number']} is discontinued with no replacement listed")
            result.flags.append("needs_human_review")
        return result

    # --- entry point --------------------------------------------------------
    def match(self, as_written: str, part_number: str | None, description: str | None,
              unresolved_reason: str | None) -> MatchResult:
        if unresolved_reason:
            return MatchResult(flags=["needs_human_review"], notes=[f"unresolved: {unresolved_reason}"])

        pn_candidates = [part_number] if part_number else []
        pn_candidates += [m.group(0) for m in RL_PATTERN.finditer(as_written)]

        notes: list[str] = []
        result = self._ridgeline(pn_candidates)
        if result is None:
            if part_number and RL_PATTERN.fullmatch(part_number.strip()):
                notes.append(f"{part_number} is not in products.csv")
            result = self._cross_reference(pn_candidates)
            if result is not None and result.part_number is None:
                result.notes = notes + result.notes
                return result  # ambiguous cross reference: stop, a person decides
        if result is None and description:
            if part_number:
                notes.append(f"{part_number} not found in products.csv or cross_reference.csv")
            result = self._description(description)
        if result is None:
            if description:
                notes.append("no catalog product matched the description")
                return MatchResult(flags=["not_carried"], notes=notes)
            notes.append("no description and no known part number")
            return MatchResult(flags=["needs_human_review"], notes=notes)
        result.notes = notes + result.notes
        return self._apply_replacement(result)
