"""Loading the YAML config files into validated models."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from snorkel.models import SourcesConfig, SpotConfig


def config_dir() -> Path:
    override = os.environ.get("SNORKEL_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "config"


def load_spots(path: Path | None = None) -> list[SpotConfig]:
    path = path or config_dir() / "spots.yaml"
    raw = yaml.safe_load(path.read_text())
    spots = [SpotConfig.model_validate(item) for item in raw]
    ids = [s.id for s in spots]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate spot ids in {path}")
    return spots


def load_sources(path: Path | None = None) -> SourcesConfig:
    path = path or config_dir() / "sources.yaml"
    return SourcesConfig.model_validate(yaml.safe_load(path.read_text()))
