# Drift Detection

> Complete specification for the 254Carbon platform drift detection and remediation system

**Version:** 1.0.0  
**Last Updated:** 2025-10-06

---

## Table of Contents
1. Overview
2. Drift Taxonomy
3. Severity Classification
4. Detection Algorithms
5. Automated Remediation
6. False Positive Handling
7. Integration with Upgrades

---

## 1. Overview

**Drift** is divergence between expected state (declared in catalog/specs) and actual state (reality). The drift detection system identifies these discrepancies early before they cause production issues.

### Why Drift Matters

- **Security Risk:** Outdated dependencies may have known vulnerabilities
- **Technical Debt:** Drift accumulates and becomes harder to fix
- **Compatibility Issues:** Mismatched versions break integrations
- **Operational Risk:** Unexpected behavior from outdated components

### Detection Frequency

- **Nightly:** Automated drift detection at 1 AM UTC
- **On-Demand:** Via `meta drift detect` command
- **PR-Triggered:** When catalog or manifest changes

---

## 2. Drift Taxonomy

### Type 1: Spec Lag

**Definition:** Service pins older specification version than latest available

**Example:**
```yaml
# Service manifest
api_contracts:
  - gateway-core@1.1.0  # Service pins this

# Spec registry  
gateway-core: latest = 1.3.0  # Latest available

# Drift: 2 minor versions behind
```

**Severity Factors:**
- Minor lag (1-2 versions): **Low to Moderate**
- Major version lag: **High**
- Security patches in newer version: **Critical**

**Detection:** Compare pinned versions in `api_contracts` against spec registry

### Type 2: Missing Lock File

**Definition:** Service uses API contracts but lacks `specs.lock.json`

**Example:**
```yaml
# Service has contracts
api_contracts:
  - gateway-core@1.1.0

# But specs.lock.json is missing ❌
```

**Severity:** **High** - Cannot reproduce exact dependencies

**Detection:** Check for `specs.lock.json` presence when `api_contracts` exist

### Type 3: Version Staleness

**Definition:** Service version unchanged for extended period despite code changes

**Example:**
```yaml
version: 1.0.0
last_update: 2024-01-15  # 9 months ago
# But git log shows 50+ commits since then
```

**Severity:**
- 90-180 days: **Moderate**
- 180+ days: **High**

**Detection:** Compare `last_update` timestamp against current date

### Type 4: Event Schema Unknown

**Definition:** Service references event not found in event registry

**Example:**
```yaml
events_out:
  - pricing.curve.update.v1  # Typo! Should be 'updates'
```

**Severity:** **High** - Consumers may fail to process events

**Detection:** Validate event names against event schema registry

### Type 5: Dependency Version Divergence

**Definition:** Multiple services use different versions of shared dependency

**Example:**
```yaml
# Service A
dependencies:
  external: [redis@6.0]

# Service B  
dependencies:
  external: [redis@7.2]  # Different major version!
```

**Severity:** **Moderate** - Can cause runtime incompatibilities

**Detection:** Analyze external dependency versions across all services

---

## 3. Severity Classification

### Critical (Immediate Action)

**Criteria:**
- Missing lock file for stable service
- Major version lag (2+ major versions)
- Security patches available in newer version
- Breaking API changes in current pin

**Response Time:** <24 hours  
**Automated Action:** Create GitHub issue, alert platform team

### High (Urgent)

**Criteria:**
- Minor version lag (5+ minor versions)
- Version staleness (180+ days)
- Event schema not found in registry
- Major dependency divergence

**Response Time:** <7 days  
**Automated Action:** Create GitHub issue

### Moderate (Important)

**Criteria:**
- Minor version lag (2-4 minor versions)
- Version staleness (90-180 days)
- Minor dependency divergence
- Policy warnings accumulating

**Response Time:** <30 days  
**Automated Action:** Flag in drift report, optional issue creation

### Low (Monitor)

**Criteria:**
- Patch version lag (1-2 patches behind)
- Recent staleness (30-90 days)
- Cosmetic manifest inconsistencies

**Response Time:** Next sprint  
**Automated Action:** Include in drift report

---

## 4. Detection Algorithms

### Algorithm 1: Spec Lag Detection

```python
def detect_spec_lag(service):
    issues = []
    
    for contract in service.api_contracts:
        spec_name, pinned_version = contract.split('@')
        
        latest_version = spec_registry.get_latest(spec_name)
        
        if compare_versions(pinned_version, latest_version) < 0:
            # Calculate lag
            major_lag = latest.major - pinned.major
            minor_lag = latest.minor - pinned.minor
            
            if major_lag > 0:
                severity = "high"
            elif minor_lag > 2:
                severity = "moderate"
            else:
                severity = "low"
            
            issues.append({
                'type': 'spec_lag',
                'severity': severity,
                'current': pinned_version,
                'latest': latest_version
            })
    
    return issues
```

**Time Complexity:** O(n) where n = number of API contracts  
**Data Sources:** Service manifests, Spec registry

### Algorithm 2: Staleness Detection

```python
def detect_staleness(service):
    last_update = parse_iso(service.last_update)
    now = datetime.now(timezone.utc)
    
    days_old = (now - last_update).days
    
    if days_old > 180:
        severity = "high"
        message = f"Service version is {days_old} days old (>180 days)"
    elif days_old > 90:
        severity = "moderate"
        message = f"Service version is {days_old} days old (>90 days)"
    else:
        return None  # Not stale enough
    
    return {
        'type': 'version_staleness',
        'severity': severity,
        'days_old': days_old,
        'message': message
    }
```

**Time Complexity:** O(1) per service  
**Data Sources:** Service manifests (last_update field)

### Algorithm 3: Missing Lock Detection

```python
def detect_missing_locks(service):
    has_contracts = len(service.api_contracts) > 0
    has_lock_file = service._has_lock_file  # Metadata from collection
    
    if has_contracts and not has_lock_file:
        return {
            'type': 'missing_lock',
            'severity': 'high',
            'message': 'Service uses API contracts but missing specs.lock.json',
            'remediation': 'Generate specs.lock.json to pin exact dependencies'
        }
    
    return None
```

**Time Complexity:** O(1) per service  
**Data Sources:** Service manifests, Repository file listings

---

## 5. Automated Remediation

### Auto-Upgrade Eligibility

Not all drift triggers automatic upgrades. Eligibility criteria:

**Patch Upgrades (Auto-Approved):**
- ✅ Spec lag of 1-2 patch versions
- ✅ No breaking changes in changelog
- ✅ Service quality score >= 70
- ✅ Policy: `auto_upgrade.patch = true`

**Minor Upgrades (Auto-Approved with Tests):**
- ✅ Spec lag of 1-3 minor versions
- ✅ Backward compatible changes only
- ✅ Service quality score >= 80
- ✅ CI tests must pass
- ✅ Policy: `auto_upgrade.minor = true`

**Major Upgrades (Manual Review Required):**
- ❌ No automatic upgrades
- ✅ Manual PR creation only
- ✅ Architecture review required
- ✅ Policy: `auto_upgrade.major = false`

### Remediation Workflow

```
1. Detect Drift
   ↓
2. Classify Severity
   ↓
3. Check Auto-Upgrade Policy
   ↓
4. If Eligible:
   a. Generate upgrade PR
   b. Run CI tests
   c. Auto-merge if patch + tests pass
   ↓
5. If Manual:
   a. Create GitHub issue
   b. Assign to service owner
   c. Set priority based on severity
```

### Remediation Scripts

| Drift Type | Automated? | Script | Policy Config |
|------------|------------|--------|---------------|
| Spec lag (patch) | ✅ Yes | `generate_upgrade_pr.py` | `auto_upgrade.patch: true` |
| Spec lag (minor) | ✅ Yes | `generate_upgrade_pr.py` | `auto_upgrade.minor: true` |
| Spec lag (major) | ❌ No | Issue creation | `auto_upgrade.major: false` |
| Missing lock | ⚠️ Partial | Can generate lock file | Manual verification needed |
| Staleness | ❌ No | Alert only | Requires code changes |
| Unknown events | ❌ No | Issue creation | Schema registration needed |

---

## 6. False Positive Handling

### Scenario 1: Intentional Version Pin

**Situation:** Service intentionally pins older version due to compatibility

**Solution:**
```yaml
# Add exemption annotation
api_contracts:
  - gateway-core@1.0.0  # Pinned: Waiting for gateway-core@2.x breaking change review
```

**Configuration:**
```yaml
# config/rules.yaml
drift:
  exemptions:
    - service: my-service
      spec: gateway-core
      reason: "Waiting for breaking change review"
      expires: "2025-12-31"
```

### Scenario 2: Active Migration

**Situation:** Service in middle of major upgrade, temporary drift expected

**Solution:**
- Label PR with `affects:contracts`
- Drift detection weights this appropriately
- Exemption granted for 14 days

### Scenario 3: Deprecated Spec

**Situation:** Service pins spec that's deprecated but still supported

**Solution:**
- Mark spec as deprecated in registry
- Drift detection changes severity to "low"
- Plan migration timeline

---

## 7. Integration with Upgrades

### Drift → Upgrade Pipeline

```
Nightly Drift Detection (1 AM)
   ↓
Spec Version Check (4 AM)
   ↓
Upgrade Eligibility Analysis
   ↓
Auto-Upgrade PR Generation
   ↓
CI Validation
   ↓
Auto-Merge (patches) or Manual Review (minor/major)
```

### Drift Report → Action Items

**High Severity Drift:**
1. Create GitHub issue
2. Assign to service owner  
3. Set due date based on severity
4. Add to sprint backlog
5. Track resolution

**Moderate Severity Drift:**
1. Include in weekly drift report
2. Email service owners
3. Add to next planning meeting
4. Track as technical debt

**Low Severity Drift:**
1. Include in drift dashboard
2. Monitor trends
3. Address opportunistically
4. Batch with other improvements

### Metrics Tracked

- **Drift Detection Rate:** % of services with drift
- **Mean Time to Remediation (MTTR):** Days from detection to fix
- **Auto-Upgrade Success Rate:** % of auto-upgrades that succeed
- **Drift Accumulation Rate:** New drift issues per week
- **Drift Resolution Rate:** Resolved issues per week

**Target KPIs:**
- Drift detection rate: <10% of services
- MTTR for high severity: <7 days
- Auto-upgrade success rate: >95%
- Net drift reduction: 10% per month

---

*📚 Part of the 254Carbon Meta documentation suite*  
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [QUALITY_SCORING.md](QUALITY_SCORING.md)*
