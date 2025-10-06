# CLI Reference

> Complete reference for the 254Carbon Meta command-line interface

**Version:** 1.0.0
**Last Updated:** 2025-10-06

---

## Table of Contents

1. Overview
2. Installation & Setup
3. Command Reference
4. Usage Examples
5. Common Workflows
6. Environment Variables
7. Troubleshooting
8. Advanced Usage

---

## 1. Overview

The `meta_cli.py` script provides a unified command-line interface for all 254Carbon platform operations. It serves as a thin wrapper around individual scripts with consistent UX and basic logging.

**Key Features:**
- ✅ Unified interface for all meta operations
- ✅ Consistent error handling and logging
- ✅ Environment variable support
- ✅ JSON output for scripting
- ✅ Debug mode for troubleshooting

**Usage Pattern:**
```bash
python scripts/meta_cli.py <category> <subcommand> [options]
```

---

## 2. Installation & Setup

### 2.1 Prerequisites

- Python 3.8+
- Required dependencies: `pip install -r requirements.txt`
- GitHub token with appropriate permissions

### 2.2 Environment Setup

```bash
# Clone the meta repository
git clone https://github.com/254carbon/meta.git
cd meta

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export GITHUB_TOKEN="your_github_token"
export META_LOG_LEVEL="INFO"
```

### 2.3 Quick Test

```bash
# Test installation
python scripts/meta_cli.py status

# Verify all commands available
python scripts/meta_cli.py --help
```

---

## 3. Command Reference

### 3.1 Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--help` | Show help message | - |
| `--debug` | Enable debug logging | `False` |
| `--json` | Output results as JSON | `False` |
| `--log-level` | Set logging level (DEBUG, INFO, WARN, ERROR) | `INFO` |

### 3.2 Catalog Commands

#### `catalog build`
Build the service catalog from collected manifests.

**Options:**
- `--validate-only` - Only validate, don't save results
- `--force` - Continue despite errors
- `--debug` - Enable debug logging

**Examples:**
```bash
# Build catalog with validation
python scripts/meta_cli.py catalog build

# Build with force override
python scripts/meta_cli.py catalog build --force

# Validate only (don't save)
python scripts/meta_cli.py catalog build --validate-only
```

#### `catalog validate`
Validate catalog structure and content.

**Options:**
- `--catalog-file` - Specific catalog file to validate
- `--strict` - Enable strict validation mode
- `--report` - Generate validation report

**Examples:**
```bash
# Validate default catalog
python scripts/meta_cli.py catalog validate

# Validate specific file with report
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml --report

# Strict validation
python scripts/meta_cli.py catalog validate --strict
```

### 3.3 Quality Commands

#### `quality compute`
Compute quality scores for all services.

**Options:**
- `--catalog-file` - Catalog file to use
- `--thresholds-file` - Thresholds configuration file
- `--debug` - Enable debug logging

**Examples:**
```bash
# Compute quality scores
python scripts/meta_cli.py quality compute

# Use specific catalog and thresholds
python scripts/meta_cli.py quality compute --catalog-file catalog/service-index.yaml --thresholds-file config/thresholds.yaml

# Debug mode for troubleshooting
python scripts/meta_cli.py quality compute --debug
```

### 3.4 Drift Commands

#### `drift detect`
Detect drift issues across services.

**Options:**
- `--catalog-file` - Catalog file to use
- `--specs-repo` - Specs repository to check against
- `--debug` - Enable debug logging

**Examples:**
```bash
# Detect drift issues
python scripts/meta_cli.py drift detect

# Use specific catalog
python scripts/meta_cli.py drift detect --catalog-file catalog/service-index.yaml

# Check against specific specs repo
python scripts/meta_cli.py drift detect --specs-repo 254carbon/254carbon-specs
```

### 3.5 Upgrade Commands

#### `upgrade plan`
Plan service upgrades.

**Options:**
- `--dry-run` - Show what would be upgraded
- `--auto-upgrade` - Auto-generate upgrade PRs
- `--catalog-file` - Catalog file to use

**Examples:**
```bash
# Plan upgrades (dry run)
python scripts/meta_cli.py upgrade plan --dry-run

# Plan with auto-upgrade enabled
python scripts/meta_cli.py upgrade plan --auto-upgrade

# Use specific catalog
python scripts/meta_cli.py upgrade plan --catalog-file catalog/service-index.yaml
```

#### `upgrade generate`
Generate upgrade PRs for specific services.

**Options:**
- `--service` - Service to upgrade (required)
- `--spec-version` - Spec version to upgrade to (required)
- `--dry-run` - Show what would be generated

**Examples:**
```bash
# Generate upgrade PR for gateway service
python scripts/meta_cli.py upgrade generate --service gateway --spec-version 1.3.0

# Dry run to see what would be generated
python scripts/meta_cli.py upgrade generate --service gateway --spec-version 1.3.0 --dry-run
```

### 3.6 Release Commands

#### `release plan`
Plan release trains.

**Options:**
- `--train` - Release train name (required)
- `--dry-run` - Show plan without executing
- `--output-file` - Save plan to file

**Examples:**
```bash
# Plan weekly release train
python scripts/meta_cli.py release plan --train weekly-$(date +%Y%m%d)

# Dry run to review plan
python scripts/meta_cli.py release plan --train Q4-upgrade --dry-run

# Save plan to file
python scripts/meta_cli.py release plan --train Q4-upgrade --output-file release-trains.yaml
```

### 3.7 Impact Commands

#### `impact analyze`
Analyze impact of changes.

**Options:**
- `--pr` - Pull request number (required)
- `--github-token` - GitHub token for API access
- `--catalog-file` - Catalog file to use

**Examples:**
```bash
# Analyze impact of PR #123
python scripts/meta_cli.py impact analyze --pr 123

# Use specific catalog
python scripts/meta_cli.py impact analyze --pr 123 --catalog-file catalog/service-index.yaml
```

### 3.8 Architecture Commands

#### `architecture suggest`
Suggest architecture improvements.

**Options:**
- `--catalog-file` - Catalog file to use
- `--output-format` - Output format (json, markdown)

**Examples:**
```bash
# Get architecture suggestions
python scripts/meta_cli.py architecture suggest

# Markdown format for documentation
python scripts/meta_cli.py architecture suggest --output-format markdown
```

### 3.9 Agent Context Commands

#### `agent-context generate`
Generate AI agent context bundles.

**Options:**
- `--catalog-file` - Catalog file to use
- `--drift-file` - Drift report file
- `--quality-file` - Quality snapshot file

**Examples:**
```bash
# Generate agent context
python scripts/meta_cli.py agent-context generate

# Include specific files
python scripts/meta_cli.py agent-context generate --drift-file analysis/reports/drift-report.json --quality-file analysis/reports/quality-summary.json
```

### 3.10 Risk Commands

#### `risk assess`
Assess service risk for changes.

**Options:**
- `--service` - Service to assess (required)
- `--change-type` - Type of change being assessed
- `--change-scope` - Scope of change (minor, medium, major)

**Examples:**
```bash
# Assess risk for gateway service
python scripts/meta_cli.py risk assess --service gateway

# Specify change details
python scripts/meta_cli.py risk assess --service gateway --change-type "API contract update" --change-scope major
```

### 3.11 Observability Commands

#### `observability ingest`
Ingest observability data.

**Options:**
- `--system` - Observability system (prometheus, datadog)
- `--config-file` - Observability configuration file
- `--service` - Specific service to collect metrics for

**Examples:**
```bash
# Ingest from Prometheus
python scripts/meta_cli.py observability ingest --system prometheus --config-file config/observability-prometheus.yaml

# Collect metrics for specific service
python scripts/meta_cli.py observability ingest --system prometheus --service gateway
```

### 3.12 Report Commands

#### `report render`
Render reports from data files.

**Options:**
- `--report-type` - Type of report (drift, dependency, catalog, quality) (required)
- `--input-file` - Input report file (required)
- `--output-file` - Output markdown file

**Examples:**
```bash
# Render drift report
python scripts/meta_cli.py report render --report-type drift --input-file analysis/reports/drift-report.json --output-file drift-summary.md

# Render quality report
python scripts/meta_cli.py report render --report-type quality --input-file analysis/reports/quality-summary.json --output-file quality-summary.md
```

### 3.13 Graph Commands

#### `graph validate`
Validate dependency graph.

**Options:**
- `--catalog-file` - Catalog file to use
- `--rules-file` - Rules configuration file

**Examples:**
```bash
# Validate dependency graph
python scripts/meta_cli.py graph validate

# Use custom rules
python scripts/meta_cli.py graph validate --rules-file config/custom-rules.yaml
```

### 3.14 Collect Commands

#### `collect manifests`
Collect service manifests from repositories.

**Options:**
- `--dry-run` - Show what would be collected
- `--repo-filter` - Repository name filter
- `--org` - GitHub organization

**Examples:**
```bash
# Collect manifests (dry run)
python scripts/meta_cli.py collect manifests --dry-run

# Collect from specific org
python scripts/meta_cli.py collect manifests --org 254carbon

# Filter by repository name
python scripts/meta_cli.py collect manifests --repo-filter gateway
```

### 3.15 Status Command

#### `status`
Show platform status overview.

**Examples:**
```bash
# Show platform status
python scripts/meta_cli.py status
```

---

## 4. Usage Examples

### 4.1 Daily Operations

```bash
# Morning health check
python scripts/meta_cli.py status
python scripts/meta_cli.py quality compute
python scripts/meta_cli.py drift detect

# Validate catalog integrity
python scripts/meta_cli.py catalog validate --strict

# Check for upgrade opportunities
python scripts/meta_cli.py upgrade plan --dry-run
```

### 4.2 Service Onboarding

```bash
# Validate new service manifest
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml

# Generate agent context for new service
python scripts/meta_cli.py agent-context generate

# Assess risk for new service deployment
python scripts/meta_cli.py risk assess --service new-service --change-scope minor
```

### 4.3 Release Management

```bash
# Plan release train
python scripts/meta_cli.py release plan --train Q4-$(date +%Y%m%d) --output-file release-plan.yaml

# Analyze impact of release PR
python scripts/meta_cli.py impact analyze --pr 456

# Generate upgrade PRs for train
python scripts/meta_cli.py upgrade generate --service gateway --spec-version 1.3.0
```

### 4.4 Troubleshooting

```bash
# Debug catalog build issues
python scripts/meta_cli.py catalog build --debug

# Detailed quality analysis
python scripts/meta_cli.py quality compute --debug

# Comprehensive drift detection
python scripts/meta_cli.py drift detect --debug
```

---

## 5. Common Workflows

### 5.1 Weekly Quality Review

```bash
#!/bin/bash
# weekly-quality-review.sh

echo "=== 254Carbon Weekly Quality Review ==="
echo "Date: $(date)"

# 1. Compute latest quality scores
echo "Computing quality scores..."
python scripts/meta_cli.py quality compute

# 2. Generate quality summary
echo "Generating quality summary..."
python scripts/meta_cli.py report render \
  --report-type quality \
  --input-file analysis/reports/quality-summary.json \
  --output-file /tmp/weekly-quality.md

# 3. Check for services needing attention
echo "Checking for issues..."
python scripts/create_quality_issues.py --catalog-file catalog/service-index.yaml

# 4. Generate trend analysis
echo "Generating trends..."
python scripts/analyze_quality_trends.py --output-dir analysis/reports/

echo "Weekly review complete!"
```

### 5.2 Release Train Execution

```bash
#!/bin/bash
# execute-release-train.sh

TRAIN_NAME="Q4-$(date +%Y%m%d)"

echo "=== Executing Release Train: $TRAIN_NAME ==="

# 1. Plan the release train
echo "Planning release train..."
python scripts/meta_cli.py release plan --train "$TRAIN_NAME" --output-file release-trains.yaml

# 2. Validate the plan
echo "Validating release train..."
python scripts/validate_release_train.py --plan-file release-trains.yaml

# 3. Execute the train (if validation passes)
echo "Executing release train..."
python scripts/execute_release_train.py --train-name "$TRAIN_NAME"

echo "Release train execution complete!"
```

### 5.3 Drift Remediation

```bash
#!/bin/bash
# remediate-drift.sh

echo "=== Drift Remediation ==="

# 1. Detect drift issues
echo "Detecting drift..."
python scripts/meta_cli.py drift detect --catalog-file catalog/service-index.yaml

# 2. Generate remediation plan
echo "Generating remediation plan..."
python scripts/generate_upgrade_pr.py --drift-report analysis/reports/drift-report.json --auto-generate

# 3. Apply eligible upgrades
echo "Applying eligible upgrades..."
python scripts/auto_merge_patches.py --catalog-file catalog/service-index.yaml

echo "Drift remediation complete!"
```

---

## 6. Environment Variables

### 6.1 Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub API token | `ghp_...` |
| `META_LOG_LEVEL` | Logging level | `INFO`, `DEBUG` |

### 6.2 Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `META_CACHE_DIR` | Cache directory | `/tmp/meta-cache` |
| `META_CACHE_TTL` | Cache time-to-live (seconds) | `3600` |
| `META_PARALLEL_WORKERS` | Number of parallel workers | `5` |
| `META_REQUEST_TIMEOUT` | HTTP request timeout (seconds) | `30` |
| `META_RETRY_ATTEMPTS` | Number of retry attempts | `3` |
| `META_DEBUG` | Enable debug mode | `false` |

### 6.3 Configuration Files

You can also configure these via files:

```bash
# Create config file
cat > ~/.254carbon-meta.conf << EOF
GITHUB_TOKEN=your_token_here
META_LOG_LEVEL=INFO
META_CACHE_DIR=/var/cache/meta
EOF

# Source in your scripts
source ~/.254carbon-meta.conf
```

---

## 7. Troubleshooting

### 7.1 Common Issues

#### Issue 1: Authentication Errors

**Symptoms:**
```
GitHub API rate limit exceeded
Authentication failed
```

**Solutions:**
```bash
# Check token permissions
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Test token scopes
python scripts/meta_cli.py status

# Generate new token if needed
# Go to GitHub Settings > Developer settings > Personal access tokens
```

#### Issue 2: Import Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'requests'
ImportError: cannot import name 'something'
```

**Solutions:**
```bash
# Install missing dependencies
pip install -r requirements.txt

# Update pip
pip install --upgrade pip

# Check Python version
python --version  # Should be 3.8+
```

#### Issue 3: Permission Errors

**Symptoms:**
```
Permission denied: '/path/to/file'
Operation not permitted
```

**Solutions:**
```bash
# Check file permissions
ls -la catalog/service-index.yaml

# Fix permissions if needed
chmod 644 catalog/service-index.yaml

# Run with appropriate user
sudo -u meta-user python scripts/meta_cli.py catalog build
```

#### Issue 4: Network Issues

**Symptoms:**
```
Connection timeout
DNS resolution failed
SSL certificate error
```

**Solutions:**
```bash
# Test network connectivity
ping github.com

# Check DNS
nslookup github.com

# Test with different timeout
META_REQUEST_TIMEOUT=60 python scripts/meta_cli.py drift detect

# Use proxy if needed
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
```

### 7.2 Debug Mode

Enable debug mode for detailed troubleshooting:

```bash
# Enable debug logging
export META_LOG_LEVEL=DEBUG
python scripts/meta_cli.py --debug catalog build

# JSON output for scripting
python scripts/meta_cli.py --json quality compute

# Verbose error messages
python scripts/meta_cli.py --debug drift detect 2>&1 | tee debug.log
```

### 7.3 Log Analysis

Common log patterns and their meanings:

```
INFO - Operation completed successfully
WARN - Non-critical issues detected, continuing
ERROR - Operation failed, check details
DEBUG - Detailed execution information
```

**Log Locations:**
- Console output (default)
- `meta.log` (if `META_LOG_FILE` set)
- System journal (if running as service)

---

## 8. Advanced Usage

### 8.1 Custom Configuration

Create custom configuration files:

```python
# config/custom-thresholds.yaml
quality:
  weights:
    coverage: 0.30    # Custom weight
    security: 0.40    # Custom weight
    policy: 0.15      # Custom weight
    stability: 0.10   # Custom weight
    drift: 0.05       # Custom weight

  coverage:
    target: 0.80      # Custom target
```

### 8.2 Scripting Integration

Use CLI in shell scripts:

```bash
#!/bin/bash
# check-platform-health.sh

# Get quality scores as JSON
QUALITY=$(python scripts/meta_cli.py --json quality compute)

# Check if any services below threshold
LOW_QUALITY=$(echo "$QUALITY" | jq '.services[] | select(.score < 70) | .name')

if [ ! -z "$LOW_QUALITY" ]; then
    echo "Services with low quality scores:"
    echo "$LOW_QUALITY"
    exit 1
fi

echo "All services meet quality standards"
```

### 8.3 Batch Operations

Process multiple services or repositories:

```bash
# Process all services in catalog
python scripts/meta_cli.py quality compute --catalog-file catalog/service-index.yaml

# Filter by domain
python scripts/meta_cli.py collect manifests --repo-filter "gateway|auth|user"

# Batch upgrade generation
for service in gateway auth user; do
    python scripts/meta_cli.py upgrade generate --service "$service" --spec-version latest
done
```

### 8.4 Performance Optimization

Optimize for large catalogs:

```bash
# Use parallel processing
export META_PARALLEL_WORKERS=10

# Enable caching
export META_CACHE_DIR=/tmp/meta-cache
export META_CACHE_TTL=7200  # 2 hours

# Reduce logging verbosity
export META_LOG_LEVEL=WARN

# Use faster collection
python scripts/collect_manifests.py --batch-size 50 --workers 10
```

---

## Appendix A: Complete Command Matrix

| Category | Subcommand | Description | Required Args | Optional Args |
|----------|------------|-------------|---------------|---------------|
| `catalog` | `build` | Build service catalog | - | `--validate-only`, `--force`, `--debug` |
| `catalog` | `validate` | Validate catalog | - | `--catalog-file`, `--strict`, `--report` |
| `quality` | `compute` | Compute quality scores | - | `--catalog-file`, `--thresholds-file`, `--debug` |
| `drift` | `detect` | Detect drift issues | - | `--catalog-file`, `--specs-repo`, `--debug` |
| `upgrade` | `plan` | Plan upgrades | - | `--dry-run`, `--auto-upgrade`, `--catalog-file` |
| `upgrade` | `generate` | Generate upgrade PRs | `--service`, `--spec-version` | `--dry-run` |
| `release` | `plan` | Plan release trains | `--train` | `--dry-run`, `--output-file` |
| `impact` | `analyze` | Analyze change impact | `--pr` | `--github-token`, `--catalog-file` |
| `architecture` | `suggest` | Suggest improvements | - | `--catalog-file`, `--output-format` |
| `agent-context` | `generate` | Generate AI context | - | `--catalog-file`, `--drift-file`, `--quality-file` |
| `risk` | `assess` | Assess service risk | `--service` | `--change-type`, `--change-scope` |
| `observability` | `ingest` | Ingest metrics | - | `--system`, `--config-file`, `--service` |
| `report` | `render` | Render reports | `--report-type`, `--input-file` | `--output-file` |
| `graph` | `validate` | Validate graph | - | `--catalog-file`, `--rules-file` |
| `collect` | `manifests` | Collect manifests | - | `--dry-run`, `--repo-filter`, `--org` |
| - | `status` | Show platform status | - | - |

---

## Appendix B: Exit Codes

| Code | Description | Meaning |
|------|-------------|---------|
| `0` | Success | Operation completed successfully |
| `1` | General Error | Operation failed with error |
| `2` | Configuration Error | Invalid configuration or missing files |
| `3` | Network Error | Network connectivity issues |
| `4` | Authentication Error | Invalid or missing credentials |
| `5` | Permission Error | Insufficient permissions |
| `6` | Validation Error | Input validation failed |
| `7` | Timeout Error | Operation timed out |

---

*📚 Part of the 254Carbon Meta documentation suite*
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [OPERATIONS.md](OPERATIONS.md), [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)*
