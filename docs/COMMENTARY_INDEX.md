Overview

- This index provides commentary for the repository, including additional notes for formats that
  do not support inline comments (e.g., JSON). It complements inline docstrings and header blocks
  present across scripts, configs, and templates.
- For JSON Schema files, inline annotations are added via "$comment" (draft-07), which validators
  ignore while preserving schema validity.

Top-Level Files

- .gitignore — Ignore patterns for Python, build artifacts, and repo-specific outputs.
- Makefile — Top-level developer entrypoints for validation, build, drift, quality, etc.
- README.md — Authoritative guide and spec for this meta repository.
- requirements.txt — Runtime dependencies for scripts (pinned with lower bounds).
- pytest.ini — Test discovery patterns, coverage settings, and markers.
- audit.log — Structured audit trail produced by scripts/utils/audit_logger.py (generated artifact).

Configuration (YAML)

- config/rules.yaml — Validation rules for dependencies, quality, drift, and release.
- config/thresholds.yaml — Scoring weights and thresholds for quality and platform health.
- config/upgrade-policies.yaml — Auto-upgrade policies, PR templates, and safeguards.
- config/discovery.yaml — Service discovery rules, indicators, domain classification, and scoring.
- config/observability-prometheus.yaml — Prometheus queries, SLO targets, and alert thresholds for ingest.

Schemas (JSON)

- schemas/service-manifest.schema.json — Per-service manifest contract. Includes $comment annotations.
- schemas/service-index.schema.json — Aggregated catalog schema. Includes $comment annotations.
- schemas/quality-metrics.schema.json — Quality snapshot schema. Includes $comment annotations.
- schemas/agent-context.schema.json — AI agent context bundle schema. Includes $comment annotations.

Scripts (Core)

- scripts/meta_cli.py — Unified CLI entry that dispatches to all operations.
- scripts/build_catalog.py — Catalog construction, validation, and persistence.
- scripts/validate_catalog.py — Catalog shape/content validation beyond schema.
- scripts/validate_graph.py — Dependency graph construction and rule validation.
- scripts/compute_quality.py — Per-service quality metrics aggregation and scoring.
- scripts/detect_drift.py — Spec/version drift detection and report generation.
- scripts/spec_version_check.py — Spec registry comparison and upgrade planning.
- scripts/render_report.py — Renders Jinja2 templates to Markdown/HTML reports.

Scripts (Operations and Insights)

- scripts/analyze_architecture.py — Architecture heuristics and health scoring.
- scripts/analyze_impact.py — PR change impact analysis and reporting.
- scripts/analyze_audit_logs.py — Audit log mining and anomaly detection.
- scripts/analyze_quality_trends.py — Historical quality trend aggregation.
- scripts/ingest_observability.py — Observability metric ingestion (provider-pluggable).
- scripts/generate_dashboard.py — Dashboard HTML generation from snapshots.
- scripts/generate_monitoring_report.py — Aggregated monitoring summaries for stakeholders.
- scripts/post_quality_summary.py — Posts quality summaries to destinations (e.g., PRs/Slack).

Scripts (Release and Upgrades)

- scripts/plan_release_train.py — Release train planning and output serialization.
- scripts/execute_release_train.py — Orchestrates release train execution (guarded by gates).
- scripts/monitor_release_progress.py — Monitors release train progress and statuses.
- scripts/monitor_upgrade_prs.py — Monitors auto-upgrade PR status and metrics.
- scripts/generate_upgrade_pr.py — Generates content for spec/dependency upgrade PRs.
- scripts/auto_merge_patches.py — Auto-merges eligible patch-level upgrades (policy-constrained).
- scripts/check_upgrade_eligibility.py — Determines upgrade eligibility based on rules.

Scripts (Catalog and Manifests)

- scripts/collect_manifests.py — Collects service manifests from source repositories.
- scripts/validate_manifests.py — Validates individual manifest files in isolation.
- scripts/diff_manifests.py — Diffs manifest changes between snapshots for review.
- scripts/discover_services.py — Discovers likely services from repository heuristics.

Scripts (Context and Risk)

- scripts/generate_agent_context.py — Builds global AI agent context bundle from platform state.
- scripts/assess_risk.py — Risk assessment for scoped service changes.
- scripts/comment_quality_changes.py — Comments on PRs about notable quality changes.

Utilities

- scripts/utils/circuit_breaker.py — Circuit breaker pattern implementation for resiliency.
- scripts/utils/retry_decorator.py — Exponential backoff retry utilities.
- scripts/utils/redis_client.py — Redis client with file-based fallback caching.
- scripts/utils/execution_monitor.py — Execution time/memory/health monitoring.
- scripts/utils/audit_logger.py — Structured audit logging for compliance.
- scripts/utils/cache_manager.py — On-disk cache utilities (if present in workflows).
- scripts/utils/error_recovery.py — Error categorization and recovery helpers.
- scripts/utils/integration_example.py — Example integration for reference/testing.
- scripts/adapters/base_adapter.py — Base adapter for manifest extraction.
- scripts/adapters/docker_compose_adapter.py — Adapter to extract manifests from docker-compose files.

Templates (Jinja2)

- analysis/templates/drift-report.md.j2 — Drift report (Jinja) with header on inputs.
- analysis/templates/catalog-summary.md.j2 — Catalog overview (Jinja) with header on inputs.
- analysis/templates/dependency-violations.md.j2 — Dependency violations report with header.
- analysis/templates/quality-summary.md.j2 — Quality dashboard with header.
- analysis/templates/dashboards/overview.html.j2 — Platform overview dashboard (now prefaced with HTML header comment).
- analysis/templates/dashboards/service.html.j2 — Service dashboard (now prefaced with HTML header comment).
- analysis/templates/dashboards/team.html.j2 — Team dashboard (now prefaced with HTML header comment).
- analysis/templates/dashboards/quality_trends.html.j2 — Quality trends dashboard (now prefaced with HTML header comment).
- analysis/templates/dashboards/realtime_health.html.j2 — Realtime health dashboard (now prefaced with HTML header comment).
- analysis/templates/dashboards/release_calendar.html.j2 — Release calendar dashboard (now prefaced with HTML header comment).

Workflows (GitHub Actions)

- workflows/github/auto-upgrade.yml — Nightly/spec-triggered upgrade automation (header added).
- workflows/github/ingest-manifests.yml — Scheduled/dispatch manifest ingestion (header present).
- workflows/github/build-catalog.yml — Catalog build/validate/persist (header present).
- workflows/github/quality-aggregate.yml — Nightly quality aggregation (header present).
- workflows/github/validate-catalog.yml — PR/main catalog validation (header present).
- workflows/github/drift-detect.yml — Nightly drift detection and optional issue filing (header added).
- workflows/github/impact-analysis.yml — PR impact analysis and commenting (header added).
- workflows/github/release-train.yml — Manual release train orchestration (header added).
- workflows/github/agent-context-pack.yml — Generate AI agent context bundle (header added).

Tests and Fixtures

- tests/unit/* — Unit tests for schemas, catalog build, graph, analysis, and utilities.
- tests/integration/test_catalog_workflow.py — End-to-end catalog build/validate smoke test.
- tests/integration/test_github_operations.py — GitHub operations integration surface.
- tests/integration/test_release_train.py — Release train planning orchestration tests.
- tests/integration/test_end_to_end.py — Broad integration coverage for CLI workflows.
- tests/unit/test_report_rendering.py — Report rendering and templating tests.
- tests/unit/test_analysis_scripts.py — Analysis scripts behavior tests.
- tests/unit/test_drift_detection.py — Drift detection logic tests.
- tests/unit/test_validate_graph.py — Graph validation rule tests.
- tests/unit/test_schemas.py — JSON Schema validation tests.
- tests/unit/test_spec_version_check.py — Spec version checking logic tests.
- tests/unit/test_infrastructure_scripts.py — Infra-related script tests.
- tests/unit/test_build_catalog.py — Catalog builder behavior tests.
- tests/unit/test_compute_quality.py — Quality computation tests.
- tests/fixtures/sample-manifest.yaml — Sample manifest; prefaced with YAML comments.
- tests/fixtures/specs-index.sample.json — Sample specs index (JSON; see notes below).
- tests/fixtures/sample-catalog.json — Sample catalog (JSON; see notes below).
- tests/fixtures/realistic-catalog.json — Larger example catalog (JSON; see notes below).

Generated Artifacts (Do not hand-edit)

- manifests/collection.log — Collection run log.
- catalog/* — Generated catalogs, logs, and summaries.
- analysis/reports/** — Generated reports and logs.
- cache_fallback/** — File-based cache entries for offline operation.

Notes on JSON comment handling

- JSON does not support comments. For JSON Schema we use "$comment" (draft-07) where helpful.
- For JSON fixtures and outputs, commentary is provided here to avoid breaking consumers.
