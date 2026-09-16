"""Loads the profile, sources and environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader. Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Profile:
    raw: dict[str, Any]

    @property
    def nationality(self) -> str:
        return self.raw.get("nationality", "")

    @property
    def cgpa(self) -> float | None:
        return self.raw.get("education", {}).get("cgpa")

    @property
    def cgpa_scale(self) -> float:
        return float(self.raw.get("education", {}).get("cgpa_scale", 4.0))

    @property
    def degree_level(self) -> str:
        return self.raw.get("target", {}).get("degree_level", "masters")

    @property
    def fields(self) -> list[str]:
        return self.raw.get("target", {}).get("fields", [])

    @property
    def preferred_regions(self) -> list[str]:
        return self.raw.get("target", {}).get("preferred_regions", [])

    @property
    def excluded_countries(self) -> list[str]:
        return [c.lower() for c in self.raw.get("target", {}).get("excluded_countries", [])]

    @property
    def intake_years(self) -> list[int]:
        return self.raw.get("target", {}).get("intake_years", [])

    @property
    def english(self) -> dict[str, Any]:
        return self.raw.get("english", {})

    @property
    def work_experience_years(self) -> float:
        return float(self.raw.get("work_experience_years", 0) or 0)

    @property
    def requirements(self) -> dict[str, Any]:
        return self.raw.get("requirements", {})

    @property
    def email(self) -> dict[str, Any]:
        return self.raw.get("email", {})


@dataclass
class Sources:
    official_pages: list[dict[str, Any]] = field(default_factory=list)
    rss_feeds: list[dict[str, Any]] = field(default_factory=list)
    search: dict[str, Any] = field(default_factory=dict)
    relevance_keywords: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Settings:
    profile: Profile
    sources: Sources
    seed_path: Path
    state_path: Path
    output_dir: Path
    visa_path: Path | None = None


def load_settings(config_dir: Path = CONFIG_DIR, data_dir: Path = DATA_DIR,
                  output_dir: Path = OUTPUT_DIR) -> Settings:
    load_dotenv()
    profile = Profile(load_yaml(config_dir / "profile.yaml"))
    src = load_yaml(config_dir / "sources.yaml")
    sources = Sources(
        official_pages=src.get("official_pages", []),
        rss_feeds=src.get("rss_feeds", []),
        search=src.get("search", {}),
        relevance_keywords=src.get("relevance_keywords", {}),
    )
    return Settings(
        profile=profile,
        sources=sources,
        seed_path=config_dir / "scholarships_seed.yaml",
        state_path=data_dir / "state.json",
        output_dir=output_dir,
        visa_path=config_dir / "visa_money.yaml",
    )


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default
