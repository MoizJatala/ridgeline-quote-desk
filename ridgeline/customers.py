"""Match the sender to customers.csv by email domain or company name."""

import re

_SUFFIXES = re.compile(r"\b(co|company|inc|incorporated|llc|ltd|corp|corporation)\b\.?")


def _squash(name: str) -> str:
    name = _SUFFIXES.sub("", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


def match_customer(customers: list[dict[str, str]], sender_email: str | None,
                   customer_name: str | None) -> dict[str, str] | None:
    if sender_email and "@" in sender_email:
        domain = sender_email.rsplit("@", 1)[1].lower()
        label = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
        if len(label) >= 5:
            for c in customers:
                name = _squash(c["name"])
                if name == label or name.startswith(label) or label.startswith(name):
                    return c
    if customer_name:
        wanted = _squash(customer_name)
        for c in customers:
            if wanted and _squash(c["name"]) == wanted:
                return c
    return None
