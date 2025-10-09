# 254Carbon Meta Repository Makefile
#
# Purpose
# - Provide a single point to run common operations locally and in CI.
# - Targets are thin wrappers around scripts under `scripts/`.
#
# Notes for maintainers
# - Keep target names stable; workflows and docs may reference them.
# - Prefer adding new targets that call existing scripts to avoid duplication.
# - Ensure any new targets are safe to run idempotently in CI.

.PHONY: help install validate build-catalog quality drift agent-context all clean test

PYTHON := python3
PIP := pip3

# Default target
help:
	@echo "254Carbon Meta Repository - Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  install     - Install Python dependencies"
	@echo ""
	@echo "Core Operations:"
	@echo "  validate    - Validate catalog and schemas"
	@echo "  build-catalog - Build service catalog from manifests"
	@echo "  quality     - Compute quality metrics"
	@echo "  drift       - Detect drift and generate reports"
	@echo "  agent-context - Generate AI agent global context"
	@echo ""
	@echo "Full Pipeline:"
	@echo "  all         - Run full pipeline (validate + build + quality + drift)"
	@echo ""
	@echo "Development:"
	@echo "  test        - Run test suite"
	@echo "  clean       - Remove generated files"
	@echo ""
	@echo "Utilities:"
	@echo "  collect-manifests - Collect manifests from repositories"
	@echo "  validate-graph    - Validate dependency graph"
	@echo "  spec-version-check - Check for spec version updates"

# Install dependencies
install:
	$(PIP) install -r requirements.txt

# Validate catalog and schemas
validate: install
	$(PYTHON) scripts/validate_catalog.py
	$(PYTHON) scripts/validate_graph.py

# Build service catalog
build-catalog: install
	$(PYTHON) scripts/build_catalog.py

# Compute quality metrics
quality: install
	$(PYTHON) scripts/compute_quality.py

# Detect drift and generate reports
drift: install
	$(PYTHON) scripts/detect_drift.py
	$(PYTHON) scripts/spec_version_check.py

# Generate AI agent context
agent-context: install
	$(PYTHON) scripts/generate_agent_context.py

# Collect manifests from repositories
collect-manifests: install
	$(PYTHON) scripts/collect_manifests.py

# Aggregate manifests from the local workspace
collect-local: install
	$(PYTHON) scripts/aggregate_local_manifests.py

# Refresh quality overrides from CI artifacts
quality-refresh: install
	$(PYTHON) scripts/update_quality_overrides.py

# Generate events registry from specs repository
registry-events: install
	$(PYTHON) scripts/generate_event_registry.py

# Validate dependency graph
validate-graph: install
	$(PYTHON) scripts/validate_graph.py

# Check for spec version updates
spec-version-check: install
	$(PYTHON) scripts/spec_version_check.py

# Run full pipeline
all: validate build-catalog quality drift agent-context

# Run test suite
test: install
	pytest tests/ -v

# Remove generated files
clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/
	rm -rf catalog/dependency-violations.json
	rm -rf catalog/quality-snapshot.json
	rm -rf catalog/spec-version-report.json
	rm -rf analysis/reports/
	rm -rf ai/global-context/agent-context.json
	rm -rf ai/global-context/risk-cues.json
