#!/usr/bin/env python3
"""
Generate Quality Overrides from CI Artifacts
============================================

Reads coverage and security metrics emitted by CI pipelines and rewrites
``config/quality-overrides.yaml`` so the catalog build always reflects the
latest ground truth without manual edits.

Inputs
------
- Coverage summary JSON/YAML (default: ``analysis/quality/coverage_summary.json``)
  containing a ``services`` array with per-service metrics.

Example coverage payload::

    {
      "services": [
        {
          "name": "gateway",
          "coverage": 0.88,
          "lint_pass": true,
          "open_critical_vulns": 0,
          "signed_images": true,
          "policy_pass": true
        }
      ]
    }

Usage
-----
    python scripts/update_quality_overrides.py
    python scripts/update_quality_overrides.py --coverage-file path/to/coverage.json
    python scripts/update_quality_overrides.py --output-file config/quality-overrides.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


META_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COVERAGE_FILE = META_ROOT / "analysis" / "quality" / "coverage_summary.json"
DEFAULT_OUTPUT_FILE = META_ROOT / "config" / "quality-overrides.yaml"


def slugify(value: str) -> str:
    """Normalize service identifiers to lowercase hyphenated form."""
    cleaned = value.strip().lower().replace("_", "-")
    cleaned = cleaned.replace(" ", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def load_structured_file(path: Path) -> Dict[str, Any]:
    """Load JSON or YAML file into a dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        content = handle.read().strip()

    if not content:
        return {}

    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(content) or {}
        return json.loads(content)
    except Exception as exc:
        raise ValueError(f"Failed to parse {path}: {exc}") from exc


def load_coverage_data(path: Path) -> List[Dict[str, Any]]:
    """Load per-service coverage metrics."""
    payload = load_structured_file(path)

    if isinstance(payload, list):
        services = payload
    else:
        services = payload.get("services", [])

    normalized: List[Dict[str, Any]] = []
    for entry in services:
        if not isinstance(entry, dict):
            continue
        name = entry.get("service") or entry.get("name")
        if not name:
            continue
        normalized.append({"name": slugify(str(name)), **entry})

    return normalized


def build_overrides(coverage_data: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Transform coverage data into the overrides YAML structure."""
    overrides: Dict[str, Dict[str, Any]] = {}

    for entry in coverage_data:
        service = entry.get("name")
        if not service:
            continue

        override: Dict[str, Any] = {}
        quality: Dict[str, Any] = {}
        security: Dict[str, Any] = {}

        if "coverage" in entry:
            try:
                quality["coverage"] = round(float(entry["coverage"]), 2)
            except (TypeError, ValueError):
                logger.warning("Invalid coverage for %s, skipping value", service)
        if "lint_pass" in entry:
            quality["lint_pass"] = bool(entry["lint_pass"])
        if "open_critical_vulns" in entry:
            try:
                quality["open_critical_vulns"] = int(entry["open_critical_vulns"])
            except (TypeError, ValueError):
                logger.warning("Invalid critical vuln count for %s", service)

        if quality:
            override["quality"] = quality

        if "signed_images" in entry:
            security["signed_images"] = bool(entry["signed_images"])
        if "policy_pass" in entry:
            security["policy_pass"] = bool(entry["policy_pass"])

        if security:
            override["security"] = security

        if override:
            overrides[service] = override

    return {"services": dict(sorted(overrides.items(), key=lambda item: item[0]))}


def save_yaml(data: Dict[str, Any], path: Path) -> None:
    """Persist overrides to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate quality overrides from CI artifacts")
    parser.add_argument("--coverage-file", default=str(DEFAULT_COVERAGE_FILE), help="Coverage summary (JSON/YAML)")
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE), help="Output overrides YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Print overrides instead of writing to disk")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    coverage_path = Path(args.coverage_file)
    output_path = Path(args.output_file)

    coverage_data = load_coverage_data(coverage_path)
    if not coverage_data:
        logger.warning("No coverage data found in %s – no overrides generated", coverage_path)
        return

    overrides = build_overrides(coverage_data)

    if args.dry_run:
        print(yaml.safe_dump(overrides, sort_keys=False))
        return

    save_yaml(overrides, output_path)
    logger.info("Wrote quality overrides for %d services to %s", len(overrides["services"]), output_path)


if __name__ == "__main__":
    main()
