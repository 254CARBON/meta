Overview

- This index provides commentary for all files in the repository, including
  additional notes for formats that do not support inline comments (e.g., JSON).
- For JSON Schema files, inline annotations are added via "$comment" (draft-07),
  which validators ignore while preserving schema validity.

Files

- .gitignore — Ignore patterns for Python, build artifacts, and repo-specific outputs.
- Makefile — Top-level developer entrypoints for validation, build, drift, quality, etc.
- README.md — Authoritative guide and spec for this meta repository.
- requirements.txt — Runtime dependencies for scripts (pinned with lower bounds).
- pytest.ini — Test discovery patterns, coverage settings, and markers.
- tests/requirements.txt — Test-only dependencies used by CI and local testing.

Config

- config/rules.yaml — Validation rules for dependencies, quality, drift, and release.
- config/thresholds.yaml — Scoring weights and thresholds for quality and platform health.
- config/upgrade-policies.yaml — Auto-upgrade policies, PR templates, and safeguards.

Schemas (JSON)

- schemas/service-manifest.schema.json — Per-service manifest contract. Now includes $comment.
- schemas/service-index.schema.json — Aggregated catalog schema. Now includes $comment.
- schemas/quality-metrics.schema.json — Quality snapshot schema. Now includes $comment.
- schemas/agent-context.schema.json — AI agent context bundle schema. Now includes $comment.

Scripts

- scripts/analyze_architecture.py — Architecture heuristics and reporting; expanded module notes.
- scripts/analyze_impact.py — Change impact analysis wiring and helpers.
- scripts/assess_risk.py — Risk assessment for scoped service changes.
- scripts/build_catalog.py — Catalog construction, validation, and persistence.
- scripts/collect_manifests.py — Manages pulling service manifests from source repos.
- scripts/compute_quality.py — Aggregates per-service quality metrics and scoring.
- scripts/detect_drift.py — Detects spec/version drift and missing locks.
- scripts/generate_agent_context.py — Builds global AI context bundle from platform state.
- scripts/generate_upgrade_pr.py — Drafts upgrade PR content and summaries.
- scripts/ingest_observability.py — Ingests observability data (pluggable provider).
- scripts/meta_cli.py — Unified command-line entrypoint dispatching to script operations.
- scripts/plan_release_train.py — Release train planning scaffolding and output.
- scripts/render_report.py — Renders Jinja2 templates to Markdown reports.
- scripts/spec_version_check.py — Compares manifests to spec registry and proposes upgrades.
- scripts/validate_catalog.py — Validates catalog shape and content beyond schema.
- scripts/validate_graph.py — Builds and validates the dependency graph against rules.

Templates

- analysis/templates/drift-report.md.j2 — Drift report (Jinja) with header comment on inputs.
- analysis/templates/catalog-summary.md.j2 — Catalog overview (Jinja) with header comment on inputs.
- analysis/templates/dependency-violations.md.j2 — Dependency validation report with header comment.
- analysis/templates/quality-summary.md.j2 — Quality dashboard with header comment.

Workflows

- workflows/github/auto-upgrade.yml — Nightly/spec-triggered upgrade automation with a header comment.
- workflows/github/ingest-manifests.yml — Scheduled/dispatch manifest ingestion with a header comment.
- workflows/github/build-catalog.yml — Catalog build/validate/persist workflow with a header comment.
- workflows/github/quality-aggregate.yml — Nightly quality aggregation with a header comment.
- workflows/github/validate-catalog.yml — PR/main catalog validation with a header comment.

Tests and Fixtures

- tests/unit/* — Unit tests for schemas, catalog build, and reports.
- tests/integration/test_catalog_workflow.py — Smoke integration for environment wiring.
- tests/fixtures/sample-manifest.yaml — Sample manifest; now prefaced with YAML comments.
- tests/fixtures/sample-catalog.json — Sample catalog (JSON does not allow inline comments).
  See this index entry for purpose/context of the file. It represents an example catalog
  conforming to `schemas/service-index.schema.json` and is used for manual validation and docs.

Notes on JSON comment handling

- JSON does not support comments. For JSON Schema we use "$comment" (draft-07) where helpful.
- For JSON fixtures and outputs, commentary is provided here to avoid breaking consumers.

