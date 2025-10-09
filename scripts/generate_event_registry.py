#!/usr/bin/env python3
"""
Generate Event Registry from Specs Repository
=============================================

Synchronizes ``config/events-registry.yaml`` with the canonical schemas in the
`254carbon-specs` repository. The registry aggregates event identifiers from:

1. ``CONTRACTS_MANIFEST.yaml`` (``events`` section)
2. File stems under ``events/`` (e.g., ``events/avro/.../*.avsc``)

Usage
-----
    python scripts/generate_event_registry.py
    python scripts/generate_event_registry.py --specs-root ../specs
    python scripts/generate_event_registry.py --output-file config/events-registry.yaml
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Set

import yaml


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


META_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPECS_ROOT = (META_ROOT / ".." / "specs").resolve()
DEFAULT_OUTPUT_FILE = META_ROOT / "config" / "events-registry.yaml"


def load_manifest_events(specs_root: Path) -> Set[str]:
    """Read events declared in CONTRACTS_MANIFEST.yaml."""
    manifest_path = specs_root / "CONTRACTS_MANIFEST.yaml"
    if not manifest_path.exists():
        logger.warning("Contracts manifest not found: %s", manifest_path)
        return set()

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:
        logger.error("Failed to parse contracts manifest: %s", exc)
        return set()

    events_section = data.get("events", {})
    if isinstance(events_section, dict):
        return {str(name).strip() for name in events_section.keys()}
    return set()


def load_event_files(specs_root: Path) -> Set[str]:
    """Collect event identifiers from files under specs/events/."""
    events_dir = specs_root / "events"
    if not events_dir.exists():
        logger.warning("Events directory not found: %s", events_dir)
        return set()

    identifiers: Set[str] = set()
    for path in events_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".avsc", ".json", ".yaml", ".yml"}:
            identifiers.add(path.stem)
    return identifiers


def save_registry(events: Set[str], output_path: Path) -> None:
    """Persist sorted event list to YAML."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "events": sorted(events)
    }
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate events registry from specs repository")
    parser.add_argument("--specs-root", default=str(DEFAULT_SPECS_ROOT), help="Path to specs repository")
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE), help="Output YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Print registry instead of writing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    specs_root = Path(args.specs_root).resolve()
    output_path = Path(args.output_file)

    events = set()
    events |= load_manifest_events(specs_root)
    events |= load_event_files(specs_root)

    if not events:
        logger.warning("No events discovered under %s", specs_root)
        return

    logger.info("Discovered %d event schemas", len(events))

    if args.dry_run:
        print(yaml.safe_dump({"events": sorted(events)}, sort_keys=False))
        return

    save_registry(events, output_path)
    logger.info("Wrote events registry to %s", output_path)


if __name__ == "__main__":
    main()
