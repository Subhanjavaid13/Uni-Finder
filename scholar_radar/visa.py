"""Money proof for student visas: how much, bank statement or not, scholarship letter accepted?"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import load_yaml

ALIASES = {
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "usa": "United States",
    "us": "United States",
    "america": "United States",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "uae": "United Arab Emirates",
    "czechia": "Czech Republic",
    "eu": "European Union",
}


@dataclass
class VisaMoney:
    country: str
    visa_type: str | None = None
    proof_of_funds: str | None = None
    bank_statement: str | None = None
    scholarship_letter_accepted: str = "unknown"
    visa_fee: str | None = None
    notes: str | None = None
    source: str | None = None


def _norm(text: str) -> str:
    """Lowercase ASCII words only, so 'Türkiye' and 'Turkiye' match."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", ascii_text.lower())).strip()


def load_visa_money(path: Path) -> dict[str, VisaMoney]:
    if not path.exists():
        return {}
    table: dict[str, VisaMoney] = {}
    for entry in load_yaml(path).get("countries", []):
        if not isinstance(entry, dict) or not entry.get("country"):
            continue
        known = VisaMoney.__dataclass_fields__
        info = VisaMoney(**{k: v for k, v in entry.items() if k in known})
        table[_norm(info.country)] = info
    return table


def lookup(country: str | None, table: dict[str, VisaMoney]) -> VisaMoney | None:
    """Find the visa-money entry for a country name written in any usual way."""
    if not country or not table:
        return None
    text = _norm(country)
    if text in table:
        return table[text]
    for alias, real in ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text) and _norm(real) in table:
            return table[_norm(real)]
    # "European Union (study in 2-3 countries)" -> European Union
    matches = [info for key, info in table.items() if key and key in text]
    return max(matches, key=lambda i: len(i.country)) if matches else None


def summary_line(info: VisaMoney) -> str:
    """One short line for an email card."""
    parts = []
    if info.proof_of_funds:
        parts.append(f"Show {info.proof_of_funds}")
    if info.bank_statement:
        parts.append(f"Bank statement: {info.bank_statement}")
    return " | ".join(parts) or "Check the embassy checklist"
