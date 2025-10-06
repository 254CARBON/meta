# Service Integration Guide

> Step-by-step guide for onboarding new services to the 254Carbon platform

**Version:** 1.0.0
**Last Updated:** 2025-10-06

---

## Table of Contents

1. Overview
2. Prerequisites
3. Creating Service Manifests
4. GitHub Workflow Setup
5. Testing Integration
6. Observability Integration
7. Notification Setup
8. Security Best Practices
9. Troubleshooting

---

## 1. Overview

This guide walks you through integrating a new service into the 254Carbon platform. The integration process ensures your service:

- ✅ Is discoverable in the service catalog
- ✅ Follows platform conventions and standards
- ✅ Has proper quality gates and monitoring
- ✅ Can participate in automated upgrades and releases
- ✅ Integrates with platform observability

**Estimated Time:** 2-4 hours for complete integration

---

## 2. Prerequisites

Before starting integration, ensure you have:

### 2.1 Repository Setup

- ✅ Service repository exists in `254carbon` GitHub organization
- ✅ Repository has proper branch protection rules
- ✅ CI/CD pipeline configured (GitHub Actions or similar)
- ✅ Dockerfile or deployment configuration present

### 2.2 Team Access

- ✅ GitHub token with `repo` and `workflow` scopes
- ✅ Access to 254Carbon Slack channels
- ✅ PagerDuty service configured (if applicable)

### 2.3 Development Environment

- ✅ Python 3.8+ installed
- ✅ `254carbon/meta` repository cloned locally
- ✅ Required dependencies installed: `pip install -r requirements.txt`

---

## 3. Creating Service Manifests

### 3.1 Manifest Location

Create `service-manifest.yaml` in your repository root:

```yaml
# Example: gateway/service-manifest.yaml
name: gateway
repository: 254carbon/gateway
path: .

# Classification
domain: access
maturity: stable

# API contracts this service provides/consumes
api_contracts:
  - gateway-core@1.2.0
  - auth-service@2.1.0

# Event schemas this service emits/consumes
events_in:
  - user.login.v1
events_out:
  - user.session.created.v1

# Dependencies
dependencies:
  internal:
    - auth-service@2.1.0
    - user-service@1.5.0
  external:
    - redis@7.0
    - postgresql@15

# Quality and security
quality:
  coverage: 0.85
  vulnerabilities:
    critical: 0
    high: 1
    medium: 3
    low: 7

# Deployment and operations
deployment:
  frequency: daily
  rollback_time: 15  # minutes
  health_check_path: /health

# Metadata
description: "API Gateway service handling authentication and routing"
team: platform-team
slack_channel: "#gateway"
pagerduty_service: "P123456"
```

### 3.2 Required Fields

All service manifests **MUST** include:

#### Identity Fields
```yaml
name: your-service-name          # Required: unique identifier
repository: 254carbon/your-repo  # Required: GitHub repository
path: .                          # Required: path within repo
```

#### Classification Fields
```yaml
domain: access    # Required: access, data, ml, shared, or external
maturity: stable  # Required: experimental, beta, stable, or deprecated
```

#### Contract Fields
```yaml
api_contracts: []  # Required: list of API contracts used
events_in: []      # Required: events this service consumes
events_out: []     # Required: events this service emits
```

#### Dependency Fields
```yaml
dependencies:      # Required: internal and external dependencies
  internal: []     # Services within 254Carbon platform
  external: []     # External systems and libraries
```

### 3.3 Optional Fields

#### Quality Information
```yaml
quality:
  coverage: 0.85              # Test coverage percentage
  last_lint: "2025-01-06"     # Last successful lint check
  vulnerabilities:            # Security scan results
    critical: 0
    high: 1
    medium: 3
    low: 7
```

#### Deployment Configuration
```yaml
deployment:
  frequency: daily           # How often deployments occur
  rollback_time: 15          # Minutes to rollback automatically
  health_check_path: /health # Health check endpoint
  canary_percentage: 10      # Percentage for canary deployments
```

#### Team Information
```yaml
team: platform-team           # Owning team
slack_channel: "#gateway"     # Team communication channel
pagerduty_service: "P123456"  # On-call rotation
documentation_url: "https://docs.254carbon.com/gateway"
```

### 3.4 Validation

Validate your manifest before committing:

```bash
# Test manifest locally
cd 254carbon/meta
python scripts/validate_catalog.py --manifest path/to/your/service-manifest.yaml

# Check for common issues
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml
```

**Common Validation Errors:**

1. **Missing required fields** - Ensure all required fields are present
2. **Invalid dependency format** - Use `service@version` format
3. **Circular dependencies** - Check dependency graph for cycles
4. **Unknown API contracts** - Verify contract names exist in spec registry

---

## 4. GitHub Workflow Setup

### 4.1 Required Workflows

Create these workflows in `.github/workflows/`:

#### 1. Manifest Collection (`manifest-collection.yml`)

```yaml
name: Collect Service Manifest

on:
  push:
    branches: [main, develop]
    paths: ['service-manifest.yaml']
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Collect manifest
        run: |
          cd 254carbon/meta
          python scripts/collect_manifests.py --repo ${{ github.repository }}
```

#### 2. Quality Gates (`quality-gates.yml`)

```yaml
name: Quality Gates

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: 254carbon/meta
          path: meta
      - name: Compute quality
        run: |
          cd meta
          python scripts/compute_quality.py --catalog-file catalog/service-index.yaml
      - name: Check thresholds
        run: |
          python scripts/create_quality_issues.py --catalog-file catalog/service-index.yaml
```

#### 3. Drift Detection (`drift-detection.yml`)

```yaml
name: Drift Detection

on:
  schedule:
    - cron: '0 1 * * *'  # Daily at 1 AM UTC
  workflow_dispatch:

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: 254carbon/meta
          path: meta
      - name: Detect drift
        run: |
          cd meta
          python scripts/detect_drift.py --catalog-file catalog/service-index.yaml
```

#### 4. Impact Analysis (`impact-analysis.yml`)

```yaml
name: Impact Analysis

on:
  pull_request:
    branches: [main]

jobs:
  impact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: 254carbon/meta
          path: meta
      - name: Analyze impact
        run: |
          cd meta
          python scripts/meta_cli.py impact analyze --pr ${{ github.event.number }}
```

### 4.2 Workflow Configuration

#### Environment Variables

Create `.github/workflows/env.yml`:

```yaml
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK }}
  PAGERDUTY_TOKEN: ${{ secrets.PAGERDUTY_TOKEN }}
```

#### Branch Protection Rules

Configure these rules for `main` branch:

- ✅ Require pull request reviews (1+ approval)
- ✅ Require status checks to pass
- ✅ Require branches to be up to date
- ✅ Restrict pushes to specific roles

---

## 5. Testing Integration

### 5.1 Local Testing

Test your integration locally before deploying:

```bash
# 1. Test manifest validation
cd 254carbon/meta
python scripts/validate_catalog.py --manifest ../your-service/service-manifest.yaml

# 2. Test catalog inclusion
python scripts/meta_cli.py catalog build --validate-only

# 3. Test quality computation
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml

# 4. Test drift detection
python scripts/detect_drift.py --catalog-file catalog/service-index.yaml
```

### 5.2 Staging Environment

Deploy to staging first:

```bash
# 1. Create staging branch
git checkout -b feature/your-service-integration

# 2. Commit manifest and workflows
git add service-manifest.yaml .github/workflows/
git commit -m "feat: integrate service with 254Carbon platform"

# 3. Create pull request
gh pr create --title "Add service integration" --body "Complete service integration with 254Carbon platform"

# 4. Monitor workflow execution
gh pr checks
```

### 5.3 Integration Checklist

Before merging to main:

- [ ] Manifest validates without errors
- [ ] Workflows execute successfully in PR
- [ ] Quality score meets minimum threshold (>70)
- [ ] No drift issues detected
- [ ] Impact analysis passes
- [ ] Team review completed

---

## 6. Observability Integration

### 6.1 Metrics Collection

Configure observability data collection:

#### Prometheus Metrics

Create `prometheus.yml` in your service:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'your-service'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
```

#### Custom Metrics

Add these metrics to your application:

```python
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUESTS = Counter('requests_total', 'Total requests', ['method', 'endpoint'])
LATENCY = Histogram('request_duration_seconds', 'Request latency')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')
```

### 6.2 Logging Configuration

Configure structured logging:

```python
import json
import logging

# Structured logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': record.created,
            'level': record.levelname,
            'service': 'your-service',
            'message': record.getMessage(),
            'trace_id': getattr(record, 'trace_id', None)
        }
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
```

### 6.3 Distributed Tracing

Implement distributed tracing:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Configure tracing
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Jaeger export
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger-agent.monitoring",
    agent_port=6831,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
```

---

## 7. Notification Setup

### 7.1 Slack Integration

Configure Slack notifications for important events:

#### Bot Setup

1. Create Slack app at https://api.slack.com/apps
2. Add `chat:write` and `incoming-webhook` scopes
3. Install app to your team's workspace
4. Copy webhook URL to repository secrets

#### Notification Configuration

Create `slack-notifications.yml`:

```yaml
notifications:
  quality_issues:
    enabled: true
    channel: "#platform-alerts"
    threshold: 70

  drift_detected:
    enabled: true
    channel: "#platform-alerts"
    severity: ["high", "critical"]

  deployment_success:
    enabled: true
    channel: "#deployments"
    environment: ["staging", "production"]
```

### 7.2 PagerDuty Integration

Configure PagerDuty for critical alerts:

#### Service Setup

1. Create service in PagerDuty
2. Generate integration key
3. Add key to repository secrets as `PAGERDUTY_TOKEN`

#### Escalation Policy

Create escalation policy:
- **Level 1:** Service owner (15 minutes)
- **Level 2:** Platform team (30 minutes)
- **Level 3:** Engineering director (immediate)

### 7.3 Email Notifications

Configure email alerts for weekly reports:

```yaml
email_notifications:
  quality_summary:
    enabled: true
    recipients:
      - platform-team@254carbon.com
    frequency: weekly
    day: monday

  drift_report:
    enabled: true
    recipients:
      - service-owners@254carbon.com
    frequency: daily
    include_details: true
```

---

## 8. Security Best Practices

### 8.1 Secret Management

**Do NOT commit secrets to code:**

```yaml
# ❌ Never do this
api_key: "sk-1234567890abcdef"
database_password: "super-secret-password"

# ✅ Use GitHub secrets instead
api_key: ${{ secrets.STRIPE_SECRET_KEY }}
database_password: ${{ secrets.DB_PASSWORD }}
```

**Required Secrets:**
- `GITHUB_TOKEN` - For GitHub API access
- `SLACK_WEBHOOK` - For Slack notifications
- `PAGERDUTY_TOKEN` - For PagerDuty integration

### 8.2 Vulnerability Scanning

Enable security scanning in your workflows:

```yaml
# Add to quality-gates.yml
- name: Security scan
  uses: securecodewarrior/github-action-sast@master
  with:
    language: python
    severity_threshold: high

- name: Dependency check
  run: |
    python -m safety check
    python -m bandit -r .
```

### 8.3 Access Control

Configure proper access controls:

#### Repository Permissions

- **Read access:** CI/CD systems, monitoring tools
- **Write access:** Service owners, platform team
- **Admin access:** Platform team leads only

#### API Access

- Use service accounts for automated access
- Implement token rotation (90-day expiry)
- Audit API usage regularly

---

## 9. Troubleshooting

### 9.1 Common Integration Issues

#### Issue 1: Manifest Not Found

**Symptoms:** Service not appearing in catalog

**Diagnosis:**
```bash
# Check if manifest exists
python scripts/collect_manifests.py --repo 254carbon/your-service

# Validate manifest format
python scripts/validate_catalog.py --manifest service-manifest.yaml
```

**Resolution:**
1. Ensure `service-manifest.yaml` exists in repository root
2. Check file permissions and accessibility
3. Validate YAML syntax and required fields

#### Issue 2: Quality Score Too Low

**Symptoms:** Workflows failing quality gates

**Diagnosis:**
```bash
# Check detailed quality breakdown
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml --debug

# Review quality requirements
cat config/thresholds.yaml
```

**Resolution:**
1. Increase test coverage (target: 80%+)
2. Fix security vulnerabilities
3. Address policy violations
4. Update dependencies to latest versions

#### Issue 3: Drift Detection Failures

**Symptoms:** Drift detection timing out or failing

**Diagnosis:**
```bash
# Check drift detection logs
python scripts/detect_drift.py --catalog-file catalog/service-index.yaml --debug

# Verify spec repository access
python scripts/spec_version_check.py --specs-repo 254carbon/254carbon-specs
```

**Resolution:**
1. Check GitHub token permissions and rate limits
2. Verify spec repository exists and is accessible
3. Update to latest spec versions if available
4. Add exemptions for intentional version pins

#### Issue 4: Notification Failures

**Symptoms:** Alerts not being sent

**Diagnosis:**
```bash
# Test Slack webhook
curl -X POST -H 'Content-type: application/json' --data '{"text":"Test message"}' $SLACK_WEBHOOK

# Test PagerDuty integration
python scripts/send_notifications.py --test --channel slack
```

**Resolution:**
1. Verify webhook URLs and tokens in secrets
2. Check network connectivity to external services
3. Review notification configuration in workflows

### 9.2 Getting Help

**Support Channels:**

1. **Documentation:** Check this guide and related docs
2. **Team Chat:** Ask in `#platform-integration`
3. **GitHub Issues:** Create issue in `254carbon/meta` repository
4. **Office Hours:** Join weekly platform office hours

**Escalation Path:**
1. Service team lead
2. Platform integration specialist
3. Platform team lead
4. Engineering director

---

## Appendix A: Complete Example

### A.1 Service Manifest Template

```yaml
name: example-service
repository: 254carbon/example-service
path: .

# Classification
domain: data
maturity: beta

# API contracts
api_contracts:
  - data-processing@1.0.0
  - streaming@2.1.0

# Events
events_in:
  - data.ingestion.requested.v1
events_out:
  - data.processing.completed.v1
  - data.processing.failed.v1

# Dependencies
dependencies:
  internal:
    - streaming@2.1.0
    - gateway@1.2.0
  external:
    - redis@7.0
    - kafka@3.5

# Quality metrics
quality:
  coverage: 0.78
  last_lint: "2025-01-06"
  vulnerabilities:
    critical: 0
    high: 0
    medium: 2
    low: 5

# Deployment info
deployment:
  frequency: weekly
  rollback_time: 30
  health_check_path: /api/health
  canary_percentage: 25

# Team info
team: data-team
slack_channel: "#data-services"
pagerduty_service: "P789012"
description: "Example service demonstrating integration patterns"
documentation_url: "https://docs.254carbon.com/example-service"
```

### A.2 Workflow Example

```yaml
name: Service Integration

on:
  push:
    branches: [main]
    paths: ['service-manifest.yaml']
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate manifest
        run: |
          python scripts/validate_catalog.py --manifest service-manifest.yaml

      - name: Check quality
        run: |
          python scripts/compute_quality.py --catalog-file catalog/service-index.yaml

      - name: Detect drift
        run: |
          python scripts/detect_drift.py --catalog-file catalog/service-index.yaml
```

---

*📚 Part of the 254Carbon Meta documentation suite*
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [OPERATIONS.md](OPERATIONS.md), [CLI_REFERENCE.md](CLI_REFERENCE.md)*
