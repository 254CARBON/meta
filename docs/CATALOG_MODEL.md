# Service Catalog Model

> Complete specification for 254Carbon service manifests and catalog structure

**Version:** 1.0.0  
**Last Updated:** 2025-10-06

---

## Table of Contents
1. Overview
2. Required Fields
3. Optional Fields
4. Field Validation Rules
5. Examples by Domain
6. Best Practices
7. Anti-Patterns
8. Schema Evolution

---

## 1. Overview

The service catalog is the canonical source of truth for all deployable services in the 254Carbon platform. Each service **MUST** provide a `service-manifest.yaml` file that describes:

- **Identity**: Unique name, repository, and path
- **Classification**: Domain and maturity level
- **Contracts**: API contracts and event schemas
- **Dependencies**: Internal services and external systems
- **Quality**: Coverage, lint status, vulnerabilities
- **Security**: Image signing and policy compliance

The aggregated catalog (`catalog/service-index.yaml`) is built from these individual manifests through the ingestion and validation pipeline.

---

## 2. Required Fields

These fields **MUST** be present in every service manifest:

### `name` (string, pattern: `^[a-z][a-z0-9-]*[a-z0-9]$`)
**Purpose:** Unique identifier for the service across the platform  
**Example:** `gateway`, `streaming`, `curve-processor`  
**Validation:** 
- Must start with lowercase letter
- Can contain lowercase letters, numbers, and hyphens
- Must end with letter or number
- Min length: 2, Max length: 50

**Best Practice:** Use descriptive names that indicate the service's primary function

### `repo` (string, format: URI)
**Purpose:** GitHub repository URL where service code lives  
**Example:** `https://github.com/254carbon/254carbon-access`  
**Validation:** Must be valid HTTPS URL pointing to 254carbon organization

### `domain` (string, enum)
**Purpose:** Business domain classification for architectural layering  
**Valid Values:**
- `infrastructure` - Core infrastructure services (layer 1)
- `shared` - Shared utilities and libraries (layer 2)
- `access` - Access control and API gateway (layer 3)
- `data-processing` - Data ingestion and processing (layer 4)
- `ml` - Machine learning and analytics (layer 5)

**Architecture Rule:** Lower numbered layers cannot depend on higher layers

### `version` (string, pattern: `^\d+\.\d+\.\d+$`)
**Purpose:** Current service version following semantic versioning  
**Example:** `1.2.3`, `0.1.0`, `2.0.0`  
**Validation:** Must be valid semver (MAJOR.MINOR.PATCH)

### `maturity` (string, enum)
**Purpose:** Service maturity and stability level  
**Valid Values:**
- `experimental` - Early development, unstable API
- `beta` - Feature complete, testing in progress
- `stable` - Production-ready, stable API
- `deprecated` - Legacy, plan migration

**Quality Impact:** Maturity affects quality score multipliers

### `dependencies` (object)
**Purpose:** Declare service dependencies for graph validation  
**Structure:**
```yaml
dependencies:
  internal:  # List of internal 254Carbon services
    - auth
    - metrics
  external:  # List of external systems/databases
    - redis
    - postgresql
```

**Validation:**
- Both `internal` and `external` arrays are required (can be empty)
- Internal dependencies must reference valid service names
- External dependencies must be in whitelist (see `config/rules.yaml`)

---

## 3. Optional Fields

These fields are **recommended** but not strictly required:

### `path` (string)
**Purpose:** Path within repository to service code  
**Example:** `service-gateway`, `services/streaming`  
**When to Use:** Always - helps with repository navigation

### `runtime` (string, enum)
**Purpose:** Runtime environment for the service  
**Valid Values:** `python`, `nodejs`, `go`, `java`, `docker`  
**When to Use:** Required for data-processing and ml domains

### `api_contracts` (array of strings, pattern: `{name}@{version}`)
**Purpose:** API contracts this service implements  
**Example:** 
```yaml
api_contracts:
  - gateway-core@1.1.0
  - auth-spec@2.0.0
```

**Validation:** Each contract must follow pattern `spec-name@semver`  
**Impact:** Used for drift detection and upgrade planning

### `events_in` (array of strings, pattern: `{domain}.{entity}.{action}.v{N}`)
**Purpose:** Events this service consumes  
**Example:**
```yaml
events_in:
  - pricing.curve.updates.v1
  - user.auth.events.v1
```

**Validation:** Must follow pattern `domain.entity.action.vN`  
**Impact:** Used for event-driven architecture mapping

### `events_out` (array of strings, pattern: `{domain}.{entity}.{action}.v{N}`)
**Purpose:** Events this service produces  
**Example:**
```yaml
events_out:
  - metrics.request.count.v1
  - gateway.health.status.v1
```

### `quality` (object)
**Purpose:** Quality metrics for the service  
**Structure:**
```yaml
quality:
  coverage: 0.78            # Test coverage (0.0-1.0)
  lint_pass: true           # Lint check status
  open_critical_vulns: 0    # Critical vulnerabilities
  open_high_vulns: 1        # High severity vulnerabilities
```

**When to Use:** Required for stable/beta services  
**Impact:** Directly used in quality scoring

### `security` (object)
**Purpose:** Security posture indicators  
**Structure:**
```yaml
security:
  signed_images: true    # Container images are signed
  policy_pass: true      # Security policies pass
```

**When to Use:** Required for stable services, recommended for beta

### `last_update` (string, format: ISO 8601)
**Purpose:** Timestamp of last manifest update  
**Example:** `2025-10-05T22:11:04Z`  
**Auto-populated:** By ingestion scripts

---

## 4. Field Validation Rules

### String Patterns

| Field | Pattern | Example | Invalid |
|-------|---------|---------|---------|
| name | `^[a-z][a-z0-9-]*[a-z0-9]$` | `gateway`, `auth-service` | `Gateway`, `auth_service`, `-gateway` |
| version | `^\d+\.\d+\.\d+$` | `1.2.3`, `0.1.0` | `1.2`, `v1.2.3`, `1.2.3-beta` |
| api_contract | `^[a-z0-9-]+@[0-9]+\.[0-9]+\.[0-9]+$` | `gateway-core@1.1.0` | `GatewayCore@1.1`, `gateway-core-1.1.0` |
| event | `^[a-z0-9-]+\.[a-z0-9-]+\.[a-z0-9-]+\.v[0-9]+$` | `pricing.curve.updates.v1` | `Pricing.Curve.Updates.v1`, `pricing-curve-updates-v1` |

### Numeric Ranges

| Field | Min | Max | Type |
|-------|-----|-----|------|
| quality.coverage | 0.0 | 1.0 | float |
| quality.open_critical_vulns | 0 | - | integer |
| quality.open_high_vulns | 0 | - | integer |

### Cross-Field Validation

1. **Dependency Resolution:** All `dependencies.internal` entries must reference existing services
2. **API Contract Format:** All `api_contracts` must use @ syntax with valid semver
3. **Event Naming:** Events must follow domain.entity.action.version pattern
4. **Maturity Constraints:**
   - `experimental`: No quality requirements
   - `beta`: quality.coverage >= 0.70 recommended
   - `stable`: quality.coverage >= 0.80 AND security.signed_images required
   - `deprecated`: No new dependencies allowed

---

## 5. Examples by Domain

### Example 1: Access Domain (Gateway Service)

```yaml
name: gateway
repo: https://github.com/254carbon/254carbon-access
path: service-gateway
domain: access
version: 1.1.0
maturity: stable
runtime: python
api_contracts:
  - gateway-core@1.1.0
  - auth-spec@2.0.0
events_in:
  - pricing.curve.updates.v1
  - user.auth.events.v1
events_out:
  - metrics.request.count.v1
  - gateway.health.status.v1
dependencies:
  internal:
    - auth
    - entitlements
    - metrics
  external:
    - redis
    - postgresql
quality:
  coverage: 0.78
  lint_pass: true
  open_critical_vulns: 0
  open_high_vulns: 1
security:
  signed_images: true
  policy_pass: true
last_update: "2025-10-05T22:11:04Z"
```

### Example 2: Data Processing Domain

```yaml
name: normalization
repo: https://github.com/254carbon/254carbon-data-processing
path: service-normalization
domain: data-processing
version: 1.2.0
maturity: stable
runtime: python
api_contracts:
  - data-processing-api@1.2.0
events_in:
  - data.raw.events.v1
events_out:
  - data.normalized.events.v1
dependencies:
  internal:
    - auth
  external:
    - clickhouse
    - kafka
quality:
  coverage: 0.82
  lint_pass: true
  open_critical_vulns: 0
security:
  signed_images: true
  policy_pass: true
last_update: "2025-10-05T19:15:00Z"
```

### Example 3: ML Domain

```yaml
name: curve
repo: https://github.com/254carbon/254carbon-ml
path: service-curve
domain: ml
version: 1.5.0
maturity: stable
runtime: python
api_contracts:
  - curves-api@1.5.0
events_in:
  - pricing.market.data.v1
events_out:
  - pricing.curve.updates.v1
dependencies:
  internal:
    - projection
    - aggregation
  external:
    - clickhouse
    - redis
quality:
  coverage: 0.74
  lint_pass: true
  open_critical_vulns: 0
security:
  signed_images: true
  policy_pass: true
last_update: "2025-10-05T15:20:00Z"
```

### Example 4: Shared Domain

```yaml
name: metrics
repo: https://github.com/254carbon/254carbon-shared
path: service-metrics
domain: shared
version: 2.0.0
maturity: stable
runtime: go
api_contracts:
  - metrics-api@2.0.0
events_in:
  - metrics.request.count.v1
  - gateway.health.status.v1
events_out:
  - metrics.aggregated.v1
dependencies:
  internal: []
  external:
    - clickhouse
    - prometheus
quality:
  coverage: 0.91
  lint_pass: true
  open_critical_vulns: 0
security:
  signed_images: true
  policy_pass: true
last_update: "2025-10-05T14:00:00Z"
```

### Example 5: Experimental Service

```yaml
name: scenario
repo: https://github.com/254carbon/254carbon-ml
path: service-scenario
domain: ml
version: 0.2.0
maturity: experimental
runtime: python
api_contracts: []
events_in:
  - pricing.curve.updates.v1
events_out:
  - scenario.results.v1
dependencies:
  internal:
    - curve
  external:
    - redis
quality:
  coverage: 0.55
  lint_pass: false
  open_critical_vulns: 1
security:
  signed_images: false
  policy_pass: false
last_update: "2025-10-05T12:00:00Z"
```

---

## 6. Best Practices

### Naming Conventions
✅ **DO:**
- Use kebab-case for service names (`data-processor`, `auth-service`)
- Use descriptive names that indicate function (`normalization`, `gateway`)
- Keep names concise but clear (prefer `auth` over `authentication-service`)

❌ **DON'T:**
- Use camelCase or snake_case (`dataProcessor`, `auth_service`)
- Use generic names (`service1`, `app`, `backend`)
- Include domain in name (`access-gateway` → just `gateway`)

### Version Management
✅ **DO:**
- Bump version on every manifest change
- Follow semantic versioning strictly
- Tag releases in Git to match manifest version

❌ **DON'T:**
- Use version ranges or wildcards
- Skip version bumps for "minor" changes
- Use pre-release tags in production manifests

### Dependency Management
✅ **DO:**
- Explicitly list all runtime dependencies
- Keep external dependency list minimal
- Document why each dependency is needed (in service docs)

❌ **DON'T:**
- Add circular dependencies
- Depend on services in higher layers
- Use undeclared "implicit" dependencies

### Quality Metrics
✅ **DO:**
- Update quality metrics after every major release
- Set realistic targets based on maturity
- Track trends over time

❌ **DON'T:**
- Inflate coverage numbers
- Ignore security vulnerabilities
- Skip quality metrics for stable services

---

## 7. Anti-Patterns

### Anti-Pattern 1: God Service
**Problem:** Single service with too many responsibilities

```yaml
# ❌ BAD: Too many API contracts and events
api_contracts:
  - user-management@1.0.0
  - order-processing@1.0.0
  - payment-gateway@1.0.0
  - inventory-management@1.0.0
  - notification-service@1.0.0
```

**Solution:** Split into focused microservices

### Anti-Pattern 2: Missing Quality Data
**Problem:** Stable service without quality metrics

```yaml
# ❌ BAD: Stable service missing quality data
maturity: stable
# quality: missing!
```

**Solution:** Always provide quality metrics for stable/beta services

### Anti-Pattern 3: Circular Dependencies
**Problem:** Services depending on each other

```yaml
# Service A depends on B
dependencies:
  internal: [service-b]

# Service B depends on A  
dependencies:
  internal: [service-a]  # ❌ Creates cycle!
```

**Solution:** Introduce abstraction layer or use event-driven communication

### Anti-Pattern 4: Wrong Domain Classification
**Problem:** Service in wrong architectural layer

```yaml
# ❌ BAD: Gateway in data-processing domain
name: gateway
domain: data-processing  # Wrong! Should be 'access'
```

**Solution:** Place services in correct domain based on responsibility

---

## 8. Schema Evolution

### Adding Optional Fields (Minor Change)

**Process:**
1. Update `schemas/service-manifest.schema.json` with new optional field
2. Document field in this document
3. Update validation scripts to handle new field
4. No migration needed - field is optional

**Example:**
```json
"sbom_url": {
  "type": "string",
  "format": "uri",
  "description": "URL to Software Bill of Materials"
}
```

### Adding Required Fields (Major Change)

**Process:**
1. Add field as optional first
2. Give services 30 days to adopt
3. Monitor adoption rate (target: 90%+)
4. Promote to required in schema
5. Update validation to enforce

**Migration Strategy:**
- Auto-generate missing required fields where possible
- Create GitHub issues for services needing manual updates
- Block catalog updates for non-compliant services

### Changing Field Types (Breaking Change)

**Process:**
1. **DO NOT DO THIS** - Instead:
2. Add new field with new name/type
3. Deprecate old field
4. Support both during transition (90 days)
5. Remove deprecated field

**Example:**
```yaml
# Old field (deprecated)
coverage: "78%"  

# New field (correct type)
coverage_percentage: 0.78
```

### Removing Fields (Breaking Change)

**Process:**
1. Mark field as deprecated in schema
2. Update docs to indicate deprecation
3. Wait for 90-day deprecation period
4. Verify no services use the field
5. Remove from schema

---

## Appendix A: Complete Field Reference

| Field | Type | Required | Pattern/Enum | Default |
|-------|------|----------|--------------|---------|
| name | string | ✅ | `^[a-z][a-z0-9-]*[a-z0-9]$` | - |
| repo | string | ✅ | URI format | - |
| path | string | ❌ | - | - |
| domain | string | ✅ | enum | - |
| version | string | ✅ | semver | - |
| maturity | string | ✅ | enum | - |
| runtime | string | ❌ | enum | - |
| api_contracts | array | ❌ | `name@version` | [] |
| events_in | array | ❌ | `domain.entity.action.vN` | [] |
| events_out | array | ❌ | `domain.entity.action.vN` | [] |
| dependencies.internal | array | ✅ | service names | [] |
| dependencies.external | array | ✅ | system names | [] |
| quality.coverage | number | ❌ | 0.0-1.0 | - |
| quality.lint_pass | boolean | ❌ | - | - |
| quality.open_critical_vulns | integer | ❌ | >= 0 | - |
| security.signed_images | boolean | ❌ | - | - |
| security.policy_pass | boolean | ❌ | - | - |
| last_update | string | ❌ | ISO 8601 | auto |

---

## Appendix B: Validation Checklist

Before submitting a new service manifest:

- [ ] All required fields present
- [ ] Service name follows pattern
- [ ] Version is valid semver
- [ ] Domain is correct architectural layer
- [ ] No circular dependencies
- [ ] External dependencies are whitelisted
- [ ] API contracts use @ syntax
- [ ] Events follow naming pattern
- [ ] Quality metrics for stable/beta services
- [ ] Security fields for stable services
- [ ] Manifest validates against schema
- [ ] Service appears correctly in catalog

---

*📚 Part of the 254Carbon Meta documentation suite*  
*See also: [DEP_GRAPH_RULES.md](DEP_GRAPH_RULES.md), [QUALITY_SCORING.md](QUALITY_SCORING.md)*
