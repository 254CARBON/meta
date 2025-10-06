# Operational Procedures

> Complete guide for 254Carbon platform operations, troubleshooting, and maintenance

**Version:** 1.0.0
**Last Updated:** 2025-10-06

---

## Table of Contents

1. Daily Operations
2. Weekly Maintenance
3. Troubleshooting Guide
4. Performance Tuning
5. Disaster Recovery
6. Backup/Restore Procedures
7. On-Call Runbook
8. Monitoring & Alerting

---

## 1. Daily Operations

### 1.1 Health Check Dashboard

**Time:** 9:00 AM UTC (Daily)

**Purpose:** Verify platform health and identify issues early

**Commands:**

```bash
# Generate platform overview dashboard
python scripts/meta_cli.py report render --report-type catalog --input-file catalog/service-index.yaml --output-file /tmp/daily-overview.md

# Check quality scores
python scripts/meta_cli.py quality compute --catalog-file catalog/service-index.yaml

# Detect drift issues
python scripts/meta_cli.py drift detect --catalog-file catalog/service-index.yaml
```

**Expected Output:**
- ✅ All services show quality scores >70
- ✅ No critical drift issues detected
- ✅ No failing workflows in last 24 hours

**Actions if Issues Found:**
1. Review failing workflows in GitHub Actions
2. Check drift report for critical issues
3. Alert service owners for quality issues <70

### 1.2 Catalog Validation

**Time:** 11:00 AM UTC (Daily)

**Purpose:** Ensure catalog integrity and catch data issues

```bash
# Validate catalog structure
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml --strict --report

# Validate dependency graph
python scripts/meta_cli.py graph validate --catalog-file catalog/service-index.yaml

# Check for missing manifests
python scripts/meta_cli.py collect manifests --dry-run
```

**Expected Output:**
- ✅ All services have valid manifests
- ✅ No circular dependencies detected
- ✅ All external dependencies are whitelisted

### 1.3 Observability Data Ingestion

**Time:** 2:00 PM UTC (Daily)

**Purpose:** Collect performance metrics for trend analysis

```bash
# Ingest Prometheus metrics
python scripts/meta_cli.py observability ingest --system prometheus --config-file config/observability-prometheus.yaml

# Generate quality trends
python scripts/analyze_quality_trends.py --output-dir analysis/reports/
```

**Expected Output:**
- ✅ Metrics collected successfully
- ✅ Trend analysis shows stable or improving quality

---

## 2. Weekly Maintenance

### 2.1 Release Train Planning

**Time:** Monday 10:00 AM UTC (Weekly)

**Purpose:** Plan and prepare release trains for the week

```bash
# Generate release train plan
python scripts/meta_cli.py release plan --train weekly-$(date +%Y%m%d) --output-file release-trains.yaml

# Validate release train
python scripts/validate_release_train.py --plan-file release-trains.yaml

# Check upgrade eligibility
python scripts/check_upgrade_eligibility.py --catalog-file catalog/service-index.yaml
```

**Expected Output:**
- ✅ Release train plan generated with 5-10 services
- ✅ All participants meet quality thresholds (>80)
- ✅ No blocking dependencies identified

### 2.2 Comprehensive Quality Assessment

**Time:** Tuesday 2:00 PM UTC (Weekly)

**Purpose:** Deep dive into platform quality metrics

```bash
# Compute detailed quality scores
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml --thresholds-file config/thresholds.yaml

# Generate quality summary report
python scripts/post_quality_summary.py --quality-file analysis/reports/quality-summary.md

# Create quality issues for failing services
python scripts/create_quality_issues.py --catalog-file catalog/service-index.yaml
```

**Expected Output:**
- ✅ All services have quality scores computed
- ✅ Issues created for services <70 quality score
- ✅ Summary report posted to team channels

### 2.3 Architecture Review

**Time:** Wednesday 10:00 AM UTC (Weekly)

**Purpose:** Review architectural health and anti-patterns

```bash
# Analyze architecture patterns
python scripts/analyze_architecture.py --catalog-file catalog/service-index.yaml

# Generate architecture suggestions
python scripts/meta_cli.py architecture suggest --catalog-file catalog/service-index.yaml

# Validate dependency graph rules
python scripts/validate_graph.py --catalog-file catalog/service-index.yaml --rules-file config/rules.yaml
```

**Expected Output:**
- ✅ No architectural violations detected
- ✅ Dependency graph follows layering rules
- ✅ Suggestions generated for improvements

### 2.4 Historical Data Management

**Time:** Thursday 3:00 PM UTC (Weekly)

**Purpose:** Maintain historical data and clean up old records

```bash
# Archive old quality data
python scripts/manage_historical_data.py --action archive --days-old 90

# Clean up old drift reports
python scripts/manage_historical_data.py --action cleanup --pattern "drift-*.json" --days-old 30

# Generate historical trends
python scripts/analyze_quality_trends.py --historical --output-dir analysis/reports/
```

**Expected Output:**
- ✅ Old data archived successfully
- ✅ Disk space freed up (>100MB)
- ✅ Historical trends generated

---

## 3. Troubleshooting Guide

### 3.1 Common Error Scenarios

#### Scenario 1: Catalog Build Fails

**Symptoms:**
- `python scripts/meta_cli.py catalog build` exits with error code
- Missing services in catalog
- Manifest validation errors

**Diagnosis Steps:**
```bash
# Check which manifests are failing
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml --report

# Test individual manifest
python scripts/validate_catalog.py --manifest manifests/collected/service-manifest.yaml

# Check GitHub API rate limits
python scripts/collect_manifests.py --dry-run
```

**Resolution:**
1. Fix manifest validation errors (see section 3.2)
2. Check service repository accessibility
3. Verify GitHub token permissions
4. Retry with `--force` flag if temporary issue

#### Scenario 2: Quality Scores Dropping

**Symptoms:**
- Multiple services show quality <70
- Quality trend shows downward trajectory
- CI/CD pipelines failing quality gates

**Diagnosis Steps:**
```bash
# Generate detailed quality report
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml --debug

# Check recent changes
python scripts/analyze_quality_trends.py --since "7 days ago"

# Review drift issues
python scripts/detect_drift.py --catalog-file catalog/service-index.yaml
```

**Resolution:**
1. Address critical vulnerabilities immediately
2. Increase test coverage for failing services
3. Update outdated dependencies
4. Review and fix policy violations

#### Scenario 3: Drift Detection Timeout

**Symptoms:**
- Drift detection takes >30 minutes
- GitHub API rate limit exceeded
- Incomplete drift reports

**Diagnosis Steps:**
```bash
# Check GitHub API status
curl -s https://api.github.com/zen

# Monitor rate limit usage
python scripts/collect_manifests.py --dry-run

# Check for large spec repositories
python scripts/detect_drift.py --specs-repo 254carbon/254carbon-specs --debug
```

**Resolution:**
1. Use GitHub token with higher rate limits
2. Implement caching for spec repositories
3. Split large spec repos into smaller chunks
4. Add retry logic with exponential backoff

#### Scenario 4: Release Train Execution Fails

**Symptoms:**
- Release train shows "FAILED" status
- Services fail to deploy in sequence
- Rollback procedures not triggered

**Diagnosis Steps:**
```bash
# Check execution logs
python scripts/execute_release_train.py --train-name Q4-upgrade --dry-run

# Verify service dependencies
python scripts/analyze_impact.py --pr 123 --catalog-file catalog/service-index.yaml

# Check deployment pipeline status
python scripts/monitor_upgrade_prs.py --train-name Q4-upgrade
```

**Resolution:**
1. Verify all prerequisite services are healthy
2. Check deployment pipeline configuration
3. Ensure proper service dependency order
4. Manually trigger rollback if needed

### 3.2 Manifest Validation Errors

#### Common Validation Issues

**Issue:** Missing required fields
```yaml
# ❌ Missing 'name' field
api_contracts:
  - gateway-core@1.0.0

# ✅ Correct
name: my-service
api_contracts:
  - gateway-core@1.0.0
```

**Issue:** Invalid dependency format
```yaml
# ❌ Wrong format
dependencies:
  internal: gateway-core  # Should be list

# ✅ Correct
dependencies:
  internal:
    - gateway-core@1.0.0
```

**Issue:** Circular dependency
```yaml
# ❌ Creates cycle
dependencies:
  internal:
    - service-b@1.0.0  # service-b depends on service-a

# service-b manifest:
dependencies:
  internal:
    - service-a@1.0.0  # Creates cycle
```

### 3.3 Performance Issues

#### Slow Catalog Operations

**Symptoms:**
- Catalog build takes >10 minutes
- Large number of GitHub API calls

**Optimizations:**
1. Enable manifest caching (see section 4.2)
2. Use parallel manifest collection
3. Filter repositories by organization/team
4. Implement incremental catalog updates

#### Memory Usage Issues

**Symptoms:**
- Scripts crash with out-of-memory errors
- System becomes unresponsive during operations

**Optimizations:**
1. Process large catalogs in chunks
2. Use streaming for historical data
3. Implement memory cleanup in long-running scripts
4. Monitor memory usage in production

---

## 4. Performance Tuning

### 4.1 Database Optimization

**Catalog Query Optimization:**
```bash
# Use indexed queries for large catalogs
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml --optimize-queries

# Enable catalog caching
export META_CACHE_DIR=/tmp/meta-cache
python scripts/meta_cli.py catalog build --use-cache
```

**Memory Management:**
```python
# Configure memory limits
export META_MAX_MEMORY=2GB

# Enable garbage collection
export META_GC_THRESHOLD=100MB
```

### 4.2 Caching Strategy

**File-based Caching:**
```bash
# Enable persistent caching
export META_CACHE_STRATEGY=file
export META_CACHE_DIR=/var/cache/meta

# Set cache TTL (time-to-live)
export META_CACHE_TTL=3600  # 1 hour
```

**Memory-based Caching:**
```bash
# Enable in-memory caching for hot data
export META_CACHE_STRATEGY=memory
export META_CACHE_SIZE=1GB
```

### 4.3 Parallel Processing

**Manifest Collection:**
```bash
# Use multiple workers for collection
python scripts/collect_manifests.py --workers 10 --batch-size 50

# Enable concurrent quality computation
python scripts/compute_quality.py --parallel --workers 5
```

---

## 5. Disaster Recovery

### 5.1 Data Recovery Procedures

**Scenario:** Catalog corruption or loss

**Recovery Steps:**
```bash
# 1. Restore from backup
cp /backups/catalog/service-index-$(date -d '1 day ago' +%Y%m%d).yaml catalog/service-index.yaml

# 2. Validate restored catalog
python scripts/meta_cli.py catalog validate --catalog-file catalog/service-index.yaml --strict

# 3. Rebuild if validation fails
python scripts/meta_cli.py catalog build --force

# 4. Verify quality scores
python scripts/meta_cli.py quality compute --catalog-file catalog/service-index.yaml
```

**Scenario:** Historical data loss

**Recovery Steps:**
```bash
# 1. Restore from archival storage
python scripts/manage_historical_data.py --action restore --backup-file /backups/historical-$(date +%Y%m%d).tar.gz

# 2. Verify data integrity
python scripts/validate_catalog.py --historical-data analysis/reports/

# 3. Regenerate missing reports
python scripts/analyze_quality_trends.py --regenerate-missing
```

### 5.2 Service Restoration

**Scenario:** Service manifest corruption

**Recovery Steps:**
```bash
# 1. Identify corrupted service
python scripts/meta_cli.py catalog validate --report | grep -i error

# 2. Collect fresh manifest
python scripts/collect_manifests.py --repo-filter corrupted-service

# 3. Validate new manifest
python scripts/validate_catalog.py --manifest manifests/collected/corrupted-service.yaml

# 4. Rebuild catalog
python scripts/meta_cli.py catalog build --force
```

### 5.3 Platform Recovery

**Scenario:** Complete platform outage

**Recovery Steps:**
1. **Phase 1:** Restore core services (gateway, auth)
2. **Phase 2:** Restore data services (databases, caches)
3. **Phase 3:** Restore application services
4. **Phase 4:** Validate platform health
5. **Phase 5:** Resume normal operations

---

## 6. Backup/Restore Procedures

### 6.1 Automated Backups

**Daily Backups (2:00 AM UTC):**
```bash
# Catalog and manifests
tar -czf /backups/catalog-$(date +%Y%m%d).tar.gz catalog/ manifests/

# Historical data
tar -czf /backups/historical-$(date +%Y%m%d).tar.gz analysis/reports/

# Configuration
cp -r config/ /backups/config-$(date +%Y%m%d)/
```

**Weekly Backups (Sunday 3:00 AM UTC):**
```bash
# Full platform state
tar -czf /backups/full-$(date +%Y%m%d).tar.gz catalog/ manifests/ analysis/ config/
```

### 6.2 Manual Backup

**Ad-hoc backup for critical changes:**
```bash
# Backup before major catalog changes
cp catalog/service-index.yaml /backups/pre-change-$(date +%Y%m%d-%H%M%S).yaml

# Backup before release train execution
cp release-trains.yaml /backups/pre-release-$(date +%Y%m%d-%H%M%S).yaml
```

### 6.3 Restore Procedures

**Restore from backup:**
```bash
# Stop all operations
# systemctl stop meta-services

# Restore catalog
cp /backups/catalog-20250106.tar.gz catalog/
cd catalog && tar -xzf catalog-20250106.tar.gz

# Restore configuration
cp -r /backups/config-20250106/* config/

# Validate restored data
python scripts/meta_cli.py catalog validate --strict

# Restart services
# systemctl start meta-services
```

---

## 7. On-Call Runbook

### 7.1 Alert Response Procedures

**Critical Alert (P0):** Quality score <60 or critical drift detected

**Response Time:** <30 minutes

1. **Acknowledge alert** in monitoring system
2. **Assess impact** using dashboard
3. **Notify stakeholders** if service impact
4. **Begin remediation** per troubleshooting guide
5. **Update status** every 30 minutes until resolved

**High Alert (P1):** Quality score 60-70 or high drift detected

**Response Time:** <2 hours

1. **Acknowledge alert** in monitoring system
2. **Investigate root cause** using diagnostic commands
3. **Implement fix** or create remediation plan
4. **Monitor progress** until resolved

### 7.2 Escalation Procedures

**Escalation Path:**
1. **Primary On-Call** (Platform Engineer)
2. **Secondary On-Call** (Senior Platform Engineer)
3. **Platform Team Lead**
4. **Engineering Director**

**Escalation Triggers:**
- Issue not resolved within SLA time
- Multiple services affected
- Critical business impact
- Security vulnerability detected

### 7.3 Post-Incident Review

**Required for all P0/P1 incidents:**

1. **Document incident** in runbook
2. **Root cause analysis** within 48 hours
3. **Action items** assigned with owners
4. **Preventive measures** implemented
5. **Team review** conducted

---

## 8. Monitoring & Alerting

### 8.1 Key Metrics to Monitor

**Platform Health:**
- Catalog build success rate (>95%)
- Average quality score trend (improving/stable)
- Drift detection completion time (<15 minutes)
- API response times (<2 seconds)

**Service Health:**
- Individual service quality scores (>70)
- Deployment success rates (>98%)
- Error rates per service (<1%)
- Response time percentiles (P95 <500ms)

### 8.2 Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Quality Score | <75 | <65 | Alert service owner |
| Drift Issues | >5 | >10 | Immediate remediation |
| Build Failures | >2/day | >5/day | Investigate pipeline |
| API Errors | >1% | >5% | Check external services |

### 8.3 Monitoring Tools

**Primary Dashboard:**
- Platform overview with real-time metrics
- Service health status grid
- Recent activity feed
- Alert summary

**Log Aggregation:**
- Centralized logging for all scripts
- Error pattern analysis
- Performance trend visualization
- Audit trail for changes

---

## Appendix A: Emergency Commands

### A.1 Quick Diagnostics

```bash
# Platform health check
python scripts/meta_cli.py status

# Quick quality check
python scripts/compute_quality.py --catalog-file catalog/service-index.yaml --quick

# Emergency catalog rebuild
python scripts/meta_cli.py catalog build --force --debug

# Check for blocking issues
python scripts/detect_drift.py --catalog-file catalog/service-index.yaml --critical-only
```

### A.2 Emergency Contacts

**Platform Team:**
- Primary: platform-team@254carbon.com
- Emergency: +1-555-PLATFORM
- Slack: #platform-emergency

**Infrastructure:**
- Primary: infra-team@254carbon.com
- Emergency: +1-555-INFRA
- Slack: #infrastructure

**Security:**
- Primary: security@254carbon.com
- Emergency: +1-555-SECURITY
- Slack: #security-incidents

---

*📚 Part of the 254Carbon Meta documentation suite*
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [CLI_REFERENCE.md](CLI_REFERENCE.md), [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)*