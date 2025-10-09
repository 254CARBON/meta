#!/usr/bin/env python3
"""
Local Service Manifest Aggregator
=================================

Purpose
-------
Aggregate `service-manifest.yaml` files that live inside the monorepo into the
Meta repository's canonical manifest format. The resulting normalized manifests
are written to ``manifests/collected`` so that downstream catalog, quality, and
drift pipelines can operate without relying on GitHub collection workflows.

Usage
-----
    python scripts/aggregate_local_manifests.py [--workspace-root PATH]
                                                [--output-dir PATH]
                                                [--dry-run]

Highlights
----------
* Scans known service repositories (access, ingestion, analytics, data-processing,
  ml, etc.) for ``service-manifest.yaml`` files.
* Normalizes heterogeneous manifest shapes into the schema expected by Meta.
* Applies light heuristics for missing fields (e.g., default versions, inferred
  domains, and reasonable quality/security defaults).
* Produces a ``collection-summary.json`` alongside the normalized manifests.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

# Configure logging for CLI friendliness
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

META_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = META_ROOT / "config"
QUALITY_OVERRIDES_FILE = CONFIG_DIR / "quality-overrides.yaml"


def _read_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML content from ``path`` and return a dictionary."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            if not isinstance(data, dict):
                raise ValueError(f"Manifest {path} does not contain a YAML mapping")
            return data
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Failed to parse manifest %s: %s", path, exc)
        return {}


def _get_nested(data: Dict[str, Any], keys: Sequence[str]) -> Any:
    """Safely fetch a nested value following ``keys`` from ``data``."""
    current: Any = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _first_present(data: Dict[str, Any], candidates: Sequence[Sequence[str]]) -> Any:
    """Return the first non-empty nested value from ``candidates``."""
    for path in candidates:
        value = _get_nested(data, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _slugify(value: str, *, keep_dashes: bool = True) -> str:
    """Convert ``value`` into a lowercase service identifier."""
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("_", "-")
    cleaned = re.sub(r"^service[-_]", "", cleaned)
    if keep_dashes:
        cleaned = re.sub(r"[^a-z0-9-]+", "-", cleaned)
    else:
        cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "unknown-service"


def _normalize_runtime(value: Optional[str]) -> str:
    """Normalize runtime strings into the allowed schema values."""
    if not value:
        return "python"

    value_lc = value.lower()
    if "python" in value_lc:
        return "python"
    if any(keyword in value_lc for keyword in ("node", "javascript", "typescript")):
        return "nodejs"
    if "go" in value_lc:
        return "go"
    if any(keyword in value_lc for keyword in ("java", "jvm")):
        return "java"
    return "docker"


def _normalize_version(value: Optional[str]) -> str:
    """Return a semantic version string, defaulting when missing."""
    if isinstance(value, (int, float)):
        value = str(value)

    if isinstance(value, str):
        match = re.match(r"^\d+\.\d+\.\d+", value.strip())
        if match:
            return match.group(0)
    return "0.1.0"


def _ensure_list(value: Any) -> List[Any]:
    """Coerce ``value`` into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_string_list(items: Iterable[Any], formatter: Optional[Callable[[str], str]] = None) -> List[str]:
    """Convert arbitrary iterable ``items`` into a list of formatted strings."""
    fmt = formatter or _slugify
    results: List[str] = []
    for item in items:
        if isinstance(item, dict):
            candidate = item.get("name") or item.get("id") or item.get("service")
            if candidate:
                results.append(fmt(str(candidate)))
            else:
                for key in ("dependency", "target", "module"):
                    if key in item and item[key]:
                        results.append(fmt(str(item[key])))
                        break
        elif isinstance(item, str):
            results.append(fmt(item))
        else:
            results.append(fmt(str(item)))
    return sorted({value for value in results if value})


def _format_contract(value: str) -> str:
    """Return a cleaned contract string while preserving spec@version shape."""
    return value.strip()


def _format_event(value: str) -> str:
    """Return a trimmed event string (dot notation retained)."""
    cleaned = value.strip()
    if cleaned in {"", "*"}:
        return ""
    cleaned = cleaned.replace(" ", "").replace("_", "-")
    return cleaned.lower()


def _flatten_dependency_dict(dep_dict: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Convert a dependency dictionary into internal/external lists.

    The helper understands common shapes used across the repos (plain lists,
    ``{"internal": [...], "external": [...]}``, topic dictionaries, etc.).
    Anything that cannot be safely identified as internal is treated as external.
    """
    internals: List[str] = []
    externals: List[str] = []

    for key, raw_value in dep_dict.items():
        values = _ensure_list(raw_value)

        if key in {"internal", "services", "internal_services"}:
            internals.extend(_extract_string_list(values, formatter=_slugify))
        elif key in {"external", "databases", "queues", "cache", "storage", "events", "apis"}:
            externals.extend(_extract_string_list(values, formatter=_slugify))
        else:
            # Mixed / nested structure – inspect values to decide.
            for item in values:
                if isinstance(item, dict):
                    dep_type = (item.get("type") or item.get("category") or item.get("kind") or "").lower()
                    name = item.get("name") or item.get("service") or item.get("target")
                    if dep_type in {"internal", "service"}:
                        internals.extend(_extract_string_list([name], formatter=_slugify))
                    elif dep_type:
                        externals.extend(_extract_string_list([name], formatter=_slugify))
                    else:
                        externals.extend(_extract_string_list([item], formatter=_slugify))
                else:
                    externals.extend(_extract_string_list([item], formatter=_slugify))

    return sorted({*internals}), sorted({*externals})


def _extract_dependencies(raw: Any) -> Dict[str, List[str]]:
    """Normalize raw dependency information into the canonical structure."""
    internal: List[str] = []
    external: List[str] = []

    if isinstance(raw, dict):
        internal, external = _flatten_dependency_dict(raw)
    elif isinstance(raw, list):
        internal_candidates: List[Any] = []
        external_candidates: List[Any] = []

        for item in raw:
            if isinstance(item, dict):
                dep_type = (item.get("type") or item.get("category") or item.get("kind") or "").lower()
                target = item.get("name") or item.get("service") or item.get("target")
                if dep_type in {"internal", "service"}:
                    internal_candidates.append(target or item)
                elif dep_type:
                    external_candidates.append(target or item)
                else:
                    external_candidates.append(item)
            else:
                external_candidates.append(item)

        internal = _extract_string_list(internal_candidates, formatter=_slugify)
        external = _extract_string_list(external_candidates, formatter=_slugify)
    elif isinstance(raw, str):
        external = _extract_string_list([raw], formatter=_slugify)

    return {
        "internal": internal,
        "external": external
    }


def _default_quality(maturity: str) -> Dict[str, Any]:
    """Return baseline quality placeholders tuned per maturity."""
    maturity_defaults = {
        "experimental": 0.55,
        "beta": 0.65,
        "stable": 0.8,
        "deprecated": 0.5
    }
    coverage = maturity_defaults.get(maturity, 0.6)
    return {
        "coverage": round(coverage, 2),
        "lint_pass": True,
        "open_critical_vulns": 0
    }


def _normalize_quality(raw: Any, maturity: str) -> Dict[str, Any]:
    """Normalize quality information while respecting schema expectations."""
    if isinstance(raw, dict):
        normalized: Dict[str, Any] = {}
        if "coverage" in raw:
            try:
                normalized["coverage"] = float(raw["coverage"])
            except (TypeError, ValueError):
                normalized["coverage"] = _default_quality(maturity)["coverage"]
        if "lint_pass" in raw:
            normalized["lint_pass"] = bool(raw["lint_pass"])
        if "open_critical_vulns" in raw:
            normalized["open_critical_vulns"] = int(raw["open_critical_vulns"])

        if normalized:
            # Ensure mandatory keys exist for downstream consumption
            normalized.setdefault("coverage", _default_quality(maturity)["coverage"])
            normalized.setdefault("lint_pass", True)
            normalized.setdefault("open_critical_vulns", 0)
            return normalized

    return _default_quality(maturity)


def _normalize_security(raw: Any) -> Dict[str, bool]:
    """Normalize security posture data into schema-friendly booleans."""
    if not isinstance(raw, dict):
        return {"signed_images": False, "policy_pass": False}

    signed = raw.get("signed_images")
    if signed is None:
        signed = bool(raw.get("image_signing") or raw.get("sigstore") or raw.get("cosign"))

    policy_pass = raw.get("policy_pass")
    if policy_pass is None:
        policy_pass = bool(raw)  # Assume presence implies some baseline policy

    return {
        "signed_images": bool(signed),
        "policy_pass": bool(policy_pass)
    }


def _normalize_events(raw_in: Any, raw_out: Any) -> Tuple[List[str], List[str]]:
    """Normalize event lists used by analytics and ingestion manifests."""
    def _to_event_list(raw: Any) -> List[str]:
        if isinstance(raw, dict):
            return _extract_string_list(raw.values(), formatter=_format_event)
        return _extract_string_list(_ensure_list(raw), formatter=_format_event)

    return _to_event_list(raw_in), _to_event_list(raw_out)


@dataclass(frozen=True)
class RepoConfig:
    """Repository specific configuration derived from top-level directory."""
    slug: str
    default_domain: str


class LocalManifestAggregator:
    """Aggregate and normalize local service manifests."""

    DOMAIN_ALIASES = {
        "data": "data-processing",
        "data_processing": "data-processing",
        "data-processing": "data-processing",
        "analytics": "analytics",
        "ml": "ml",
        "machine-learning": "ml",
        "ingestion": "ingestion",
        "access": "access",
        "security": "security",
        "observability": "observability",
        "shared": "shared",
        "platform": "shared",
        "infra": "infrastructure",
        "infrastructure": "infrastructure"
    }

    def __init__(self, workspace_root: Path, output_dir: Path, repo_map: Dict[str, RepoConfig]):
        self.workspace_root = workspace_root
        self.output_dir = output_dir
        self.repo_map = repo_map
        self.meta_root = META_ROOT
        self.quality_overrides = self._load_quality_overrides()

    def aggregate(self, dry_run: bool = False) -> Dict[str, Dict[str, Any]]:
        """Aggregate manifests and optionally persist them."""
        aggregated: Dict[str, Dict[str, Any]] = {}
        collection_items: List[Dict[str, Any]] = []

        for repo_dir, repo_cfg in self.repo_map.items():
            repo_path = self.workspace_root / repo_dir
            if not repo_path.exists():
                logger.debug("Skipping missing repository directory: %s", repo_path)
                continue

            manifest_paths = sorted(repo_path.rglob("service-manifest.yaml"))
            logger.info("Found %d manifests under %s", len(manifest_paths), repo_dir)

            for manifest_path in manifest_paths:
                raw_manifest = _read_yaml(manifest_path)
                if not raw_manifest:
                    continue

                normalized = self._normalize_manifest(
                    raw_manifest,
                    manifest_path,
                    repo_dir,
                    repo_cfg
                )
                if not normalized:
                    continue

                normalized = self._apply_overrides(normalized)

                service_name = normalized["name"]
                if service_name in aggregated:
                    suffix = _slugify(repo_cfg.slug, keep_dashes=False)
                    deduped_name = f"{service_name}-{suffix}"
                    logger.warning(
                        "Service name '%s' already collected; renaming to '%s' (source: %s)",
                        service_name,
                        deduped_name,
                        manifest_path
                    )
                    normalized["name"] = deduped_name
                    service_name = deduped_name

                aggregated[service_name] = normalized
                collection_items.append({
                    "name": service_name,
                    "repo": normalized["repo"],
                    "domain": normalized["domain"],
                    "source_manifest": str(manifest_path.relative_to(self.workspace_root)),
                    "last_update": normalized["last_update"]
                })

        if dry_run:
            logger.info("Dry-run enabled: skipping manifest writes")
            return aggregated

        self._write_manifests(aggregated)
        self._write_summary(collection_items)
        return aggregated

    def _normalize_manifest(
        self,
        raw: Dict[str, Any],
        manifest_path: Path,
        repo_dir: str,
        repo_cfg: RepoConfig
    ) -> Optional[Dict[str, Any]]:
        """Normalize an individual manifest into canonical structure."""
        service_name_raw = _first_present(raw, [
            ("name",),
            ("service_name",),
            ("metadata", "name"),
            ("service", "name")
        ]) or manifest_path.parent.name
        service_name = _slugify(str(service_name_raw))

        version = _normalize_version(_first_present(raw, [
            ("version",),
            ("metadata", "version"),
            ("spec", "version"),
            ("service", "version")
        ]))

        domain_raw = _first_present(raw, [
            ("domain",),
            ("metadata", "domain"),
            ("spec", "domain")
        ]) or repo_cfg.default_domain
        domain = self.DOMAIN_ALIASES.get(str(domain_raw).lower(), repo_cfg.default_domain)

        maturity_raw = _first_present(raw, [
            ("maturity",),
            ("metadata", "maturity"),
            ("service", "maturity")
        ]) or "beta"
        maturity = str(maturity_raw).lower()
        if maturity not in {"experimental", "beta", "stable", "deprecated"}:
            maturity = "beta"

        runtime_raw = _first_present(raw, [
            ("runtime",),
            ("metadata", "runtime"),
            ("spec", "runtime"),
            ("service", "runtime")
        ])
        runtime = _normalize_runtime(runtime_raw)

        api_contracts = _extract_string_list(
            _ensure_list(_first_present(raw, [
                ("api_contracts",),
                ("apiContracts",),
                ("metadata", "api_contracts"),
                ("contracts", "apis"),
                ("spec", "api_contracts")
            ])),
            formatter=_format_contract
        )

        events_in, events_out = _normalize_events(
            _first_present(raw, [
                ("events_in",),
                ("events", "consumes"),
                ("spec", "events", "consumes")
            ]),
            _first_present(raw, [
                ("events_out",),
                ("events", "produces"),
                ("spec", "events", "produces")
            ])
        )

        dependencies_raw = _first_present(raw, [
            ("dependencies",),
            ("spec", "dependencies"),
            ("service", "dependencies")
        ]) or {}
        dependencies = _extract_dependencies(dependencies_raw)

        quality_raw = raw.get("quality")
        quality = _normalize_quality(quality_raw, maturity)

        security_raw = raw.get("security")
        security = _normalize_security(security_raw)

        last_update = datetime.fromtimestamp(
            manifest_path.stat().st_mtime,
            tz=timezone.utc
        ).isoformat()

        repo_url = f"https://github.com/254carbon/{repo_cfg.slug}"
        service_rel_path = manifest_path.parent.relative_to(self.workspace_root / repo_dir)

        normalized_manifest: Dict[str, Any] = {
            "name": service_name,
            "repo": repo_url,
            "path": str(service_rel_path).replace("\\", "/"),
            "domain": domain,
            "version": version,
            "maturity": maturity,
            "runtime": runtime,
            "api_contracts": api_contracts,
            "events_in": events_in,
            "events_out": events_out,
            "dependencies": dependencies,
            "quality": quality,
            "security": security,
            "last_update": last_update
        }

        return normalized_manifest

    def _load_quality_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Load optional quality/security overrides from configuration."""
        overrides_path = QUALITY_OVERRIDES_FILE

        if not overrides_path.exists():
            logger.debug("Quality overrides file not found: %s", overrides_path)
            return {}

        try:
            with overrides_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to load quality overrides: %s", exc)
            return {}

        services_cfg = data.get("services", {})
        normalized: Dict[str, Dict[str, Any]] = {}

        for service_name, payload in services_cfg.items():
            if not isinstance(payload, dict):
                continue
            normalized[_slugify(service_name)] = payload

        return normalized

    def _apply_overrides(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Apply quality/security overrides to the normalized manifest."""
        overrides = self.quality_overrides.get(manifest["name"])
        if not overrides:
            return manifest

        updated = dict(manifest)

        if "quality" in overrides:
            quality_overrides = overrides["quality"]
            if isinstance(quality_overrides, dict):
                quality_section = dict(updated.get("quality", {}))
                for field in ("coverage", "lint_pass", "open_critical_vulns"):
                    if field in quality_overrides:
                        quality_section[field] = quality_overrides[field]
                updated["quality"] = quality_section

        if "security" in overrides:
            security_overrides = overrides["security"]
            if isinstance(security_overrides, dict):
                security_section = dict(updated.get("security", {}))
                for field in ("signed_images", "policy_pass"):
                    if field in security_overrides:
                        security_section[field] = bool(security_overrides[field])
                updated["security"] = security_section

        return updated

    def _write_manifests(self, manifests: Dict[str, Dict[str, Any]]) -> None:
        """Persist normalized manifests into ``self.output_dir``."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Clear previous artifacts to avoid stale service data lingering
        for existing in self.output_dir.glob("*.yaml"):
            existing.unlink(missing_ok=True)

        for service_name, manifest in sorted(manifests.items()):
            destination = self.output_dir / f"{service_name}.yaml"
            with destination.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(manifest, handle, sort_keys=False)
        logger.info("Wrote %d normalized manifests to %s", len(manifests), self.output_dir)

    def _write_summary(self, items: List[Dict[str, Any]]) -> None:
        """Write a collection summary JSON file for auditing."""
        summary = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total_services": len(items),
            "services": sorted(items, key=lambda entry: entry["name"])
        }
        summary_path = self.output_dir / "collection-summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
        logger.info("Collection summary written to %s", summary_path)


def _default_repo_map() -> Dict[str, RepoConfig]:
    """Default mapping of monorepo directories to GitHub repos/domains."""
    return {
        "access": RepoConfig(slug="254carbon-access", default_domain="access"),
        "analytics": RepoConfig(slug="254carbon-analytics", default_domain="analytics"),
        "data-processing": RepoConfig(slug="254carbon-data-processing", default_domain="data-processing"),
        "ingestion": RepoConfig(slug="254carbon-ingestion", default_domain="ingestion"),
        "ml": RepoConfig(slug="254carbon-ml", default_domain="ml"),
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Aggregate local service manifests into meta format")
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Path to the monorepo workspace root (default: two levels up from this script)"
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "manifests" / "collected"),
        help="Directory to write normalized manifests (default: meta/manifests/collected)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect manifests without writing files"
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    output_dir = Path(args.output_dir).resolve()

    repo_map = _default_repo_map()
    aggregator = LocalManifestAggregator(
        workspace_root=workspace_root,
        output_dir=output_dir,
        repo_map=repo_map
    )
    manifests = aggregator.aggregate(dry_run=args.dry_run)
    logger.info("Aggregated %d services", len(manifests))


if __name__ == "__main__":
    main()
