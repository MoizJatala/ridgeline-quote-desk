"""Text normalization and tokenization for description matching.

Spec values (sizes, threads, grades, ratings, series, materials) become tokens that
carry a family prefix, e.g. ``dim_1/2``, ``thr_1/2-13``, ``grade_8``, ``brg_6205``.
Every spec token in a request must also appear in a catalog description for that
product to be considered.
"""

import re

MATERIALS = {
    "brass", "stainless", "316", "304", "cellulose", "glass", "buna", "nitrile",
    "polyurethane", "nylon", "galvanized", "cobalt", "zirconia",
}

ABBREVIATIONS = {
    "fp": "full port",
    "hyd": "hydraulic",
    "gal": "gallon",
    "gals": "gallon",
    "elem": "element",
    "flg": "flange",
    "vlv": "valve",
    "brg": "bearing",
    "brgs": "bearing",
    "ss": "stainless",
    "sst": "stainless",
    "nbr": "buna",
    "thk": "thick",
    "bolt": "cap screw",
    "bolts": "cap screw",
    "large": "size_l",
    "medium": "size_m",
    "small": "size_s",
    "lbs": "lb",
}

STOPWORDS = {
    "in", "x", "of", "the", "a", "an", "and", "for", "to", "with", "both", "sides", "side",
    "per", "ea", "each", "qty", "same", "as", "above", "but", "spec", "line", "please",
    "need", "whatever", "equivalent", "have", "you", "that", "thats", "size", "approx",
    "box", "boxe", "case", "pack", "cs", "bx", "pk", "pr", "pair", "about",
}

SIZE_LETTERS = {"s": "size_s", "m": "size_m", "l": "size_l", "xl": "size_xl"}

# (pattern, replacement) applied in order to lowercased text.
_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"[″”“]", '"'),
    (r"\bo-?rings?\b", " oring "),
    (r"\bv-?belts?\b", " vbelt "),
    (r"#\s*(\d+)", r" no_\1 "),                                   # ANSI #40 chain
    (r"(\d+)\s*#", r"\1 lb"),                                     # 150# -> 150 lb
    (r"\b(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\b", r" dims_\1x\2x\3 "),   # 20x20x2
    (r"\bas568\s*-?\s*(\d{3})\b", r" oring_\1 "),
    (r"\boring\b[\s,]*(?:size|dash|no\.?)?\s*-?(\d{3})\b", r" oring oring_\1 "),  # o-ring 214 / size 214
    (r"\b(\d+)\s+(\d+/\d+)\b", r"\1-\2"),                         # 1 1/2 -> 1-1/2
    (r"(?<![\w/-])(\d+/\d+)-(\d{2})(?![\d/])", r" thr_\1-\2 dim_\1 "),  # 1/2-13
    (r"(?<![\w/-])(\d+-\d+/\d+)(?![\w/])", r" dim_\1 "),          # 1-1/2
    (r"(?<![\w/_-])(\d+/\d+)(?![\w/])", r" dim_\1 "),             # 3/4
    (r'(?<![\w/_.-])(\d+(?:\.\d+)?)\s*(?:"|inches\b|inch\b|in\b)', r" dim_\1 "),
    (r"\b(?:grade|gr)\.?\s*(\d+)\b", r" grade_\1 "),
    (r"\b(\d+)\s*(?:microns?|µm)\b", r" micron_\1 "),
    (r"\b(\d+(?:\.\d+)?)\s*hp\b", r" hp_\1 "),
    (r"\b(\d+)\s*rpm\b", r" rpm_\1 "),
    (r"\bmerv\s*(\d+)\b", r" merv_\1 "),
    (r"\bjic\s*-?\s*(\d{2})\b", r" jic jic_\1 "),
    (r"\b(45|90)\s*(?:degrees?|deg|°)?(?![\w/])", r" deg_\1 "),
    (r"\b(\d+)\s*lb\b", r" lb_\1 "),
    (r"\biso\s*(\d+)\b", r" iso_\1 "),
    (r"\baw\s*(\d+)\b", r" aw_\1 "),
    (r"\b(6[0-3]\d{2})\s*-?\s*(2rs|zz)\b", r" brg_\1 \2 "),       # 6204-2RS
    (r"\b(6[0-3]\d{2})\b", r" brg_\1 "),
    (r"\b(?:2rs|rs|sealed|seal)\b", " seal_2rs "),
    (r"\b(?:zz|shielded|shield)\b", " seal_zz "),
    (r"\b([ab])(\d{2})\b", r" belt_\1\2 "),                       # A42, B55
    (r"\b(?:ansi\s*)?a([1-9])\b", r" cut_a\1 "),                  # cut level A4
    (r"\bsize\s+(xl|l|m|s)\b", r" size_\1 "),
    (r"(?<=[a-z])-(?=[a-z])", " "),                               # cut-resistant -> cut resistant
    (r"(?<=\d)-(?=[a-z])", " "),                                  # 3-phase -> 3 phase
]
_COMPILED = [(re.compile(p), r) for p, r in _SUBSTITUTIONS]


def _singular(token: str) -> str:
    if "_" in token or len(token) <= 3 or token.endswith("ss") or not token.endswith("s"):
        return token
    return token[:-1]


def tokenize(text: str) -> set[str]:
    s = text.lower()
    for pattern, repl in _COMPILED:
        s = pattern.sub(repl, s)
    tokens: set[str] = set()
    for raw in re.split(r"[\s,;()]+", s):
        tok = raw.strip(".:-'\"")
        if not tok:
            continue
        if tok in SIZE_LETTERS:
            tokens.add(SIZE_LETTERS[tok])
            continue
        tok = ABBREVIATIONS.get(tok, tok)
        for part in tok.split():
            part = _singular(part)
            if part in STOPWORDS or (len(part) == 1 and "_" not in part):
                continue
            tokens.add(part)
    return tokens


def spec_tokens(tokens: set[str]) -> set[str]:
    return {t for t in tokens if "_" in t or t in MATERIALS}
