"""Loads the curated seed database of recurring fully funded scholarships."""

from __future__ import annotations

from pathlib import Path

from .config import load_yaml
from .models import Opportunity


def load_seed(path: Path) -> list[Opportunity]:
    if not path.exists():
        return []
    opportunities = []
    for entry in load_yaml(path).get("scholarships", []):
        data = {k: v for k, v in entry.items() if v is not None}
        opportunities.append(Opportunity.from_dict({**data, "source": "seed"}))
    return opportunities
