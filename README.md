
# 254Carbon Meta Repository (`254carbon-meta`)

> Central governance, catalog, automation, quality intelligence, release coordination, and AI agent orchestration hub for the 254Carbon multi‑repo platform.

This repository is the “control plane” for:
- Service Catalog & Dependency Graph
- Version + Contract Drift Detection
- Cross‑repo Release Orchestration (optional progressive adoption)
- Quality & Security Score Aggregation
- Architecture & Policy Conformance Checks
- AI Agent Global Context & Task Routing
- Change Risk Insights & Upgrade Assist (spec/lib propagation)
- Automated Backlog Signals (e.g. outdated dependencies, stale manifests)

---

## Table of Contents
1. Mission & Scope  
2. Non‑Goals  
3. Core Responsibilities  
4. Repository Structure  
5. Service Catalog Model  
6. Dependency Graph & Validation  
7. Version & Contract Drift Detection  
8. Quality Metrics Aggregation  
9. Release Coordination (Optional Mode)  
10. AI Agent Orchestration Layer  
11. Automation Workflows Overview  
12. Security & Policy Conformance Signals  
13. Data Files & Schemas  
14. How Other Repos Integrate  
15. Operational Dashboards (Generated Artifacts)  
16. Configuration & Customization  
17. Local Development & Testing  
18. Extending the Meta Model  
19. Failure / Degradation Modes  
20. Roadmap & Maturity Stages  
21. Contribution Workflow  
22. Glossary  
23. License / Ownership  
24. Quick Reference Commands  

---

## 1. Mission & Scope

| Objective | Description |
|-----------|-------------|
| Single Source Catalog | Canonical index of every deployable service & its metadata. |
| Holistic Visibility | Aggregate health, quality, security, and version signals. |
| Consistency Enforcement | Detect drift between declared & actual (spec pins, manifests, dependencies). |
| Guided Upgrades | Automate “upgrade PRs” for shared libs & schemas. |
| Release Alignment | (Optional) orchestrate coordinated multi-service milestone tags. |
| Agent Awareness | Provide structured global context to AI coding agents safely. |
| Policy Feedback Loop | Surface conformance & remediation tasks automatically. |

---

## 2. Non‑Goals

| Out of Scope | Reason |
|--------------|--------|
| Actual service code | Lives in domain repos (access, ingestion, ml, etc.). |
| Runtime infra provisioning | In `254carbon-infra`. |
| Observability dashboards | In `254carbon-observability`. |
| Security policy authoring | In `254carbon-security`. |
| Business domain specifications | In `254carbon-specs`. |

---

## 3. Core Responsibilities

1. Maintain the multi‑repo service index (authoritative YAML).  
2. Validate each `service-manifest.yaml` (collected from source repos).  
3. Generate dependency graph & detect illegal reverse edges.  
4. Aggregate coverage, vulnerability counts, and lint status into composite quality scores.  
5. Detect outdated spec versions vs `specs.lock.json` entries (upgrade assist).  
6. Produce risk & drift reports (PR comments / artifacts).  
7. Provide AI agent global context bundle (machine-consumable).  
8. Optionally coordinate multi-service “release trains” or lockstep migrations.  

---

## 4. Repository Structure

```
/
  catalog/
    service-index.yaml             # Canonical aggregated index
    service-index.schema.json      # Validation schema
    dependency-graph.yaml          # Directed acyclic graph (DAG) spec
    dependency-violations.json     # Last analysis output
    quality-snapshot.json          # Aggregated metrics (generated)
    spec-version-report.json       # Spec pin vs latest delta
    release-trains.yaml            # (Optional) coordinated releases
  manifests/
    collected/                     # Raw collected service-manifest copies (by repo/commit)
  analysis/
    reports/
      drift/
      risk/
      quality/
      security/
    templates/
      drift-report.md.hbs
      quality-summary.md.hbs
  workflows/
    github/
      ingest-manifests.yml
      build-catalog.yml
      validate-catalog.yml
      quality-aggregate.yml
      drift-detect.yml
      release-train.yml
      agent-context-pack.yml
  schemas/
    service-manifest.schema.json
    quality-metrics.schema.json
    agent-context.schema.json
  scripts/
    collect_manifests.py
    build_catalog.py
    validate_graph.py
    compute_quality.py
    detect_drift.py
    spec_version_check.py
    render_report.py
    generate_agent_context.py
    plan_release_train.py
    diff_manifests.py
  ai/
    global-context/
      agent-context.json           # Exported consolidated context
      agent-guidelines.md
      risk-cues.json
  config/
    rules.yaml                     # Policy & validation toggles
    thresholds.yaml                # Quality + drift thresholds
    upgrade-policies.yaml          # Automatic PR rules
  docs/
    CATALOG_MODEL.md
    DEP_GRAPH_RULES.md
    DRIFT_DETECTION.md
    QUALITY_SCORING.md
    RELEASE_TRAINS.md
    AGENT_INTEGRATION.md
    EXTENDING_META.md
  .agent/
    context.yaml                   # Meta repo’s own agent descriptor
  Makefile
  README.md
  CHANGELOG.md
```

---

## 5. Service Catalog Model

`catalog/service-index.yaml` (authoritative after build):

```yaml
services:
  - name: gateway
    repo: https://github.com/254carbon/254carbon-access
    path: service-gateway
    domain: access
    version: 1.1.0
    maturity: stable
    runtime: python
    api_contracts:
      - gateway-core@1.1.0
    events_in:
      - pricing.curve.updates.v1
    events_out:
      - metrics.request.count.v1
    dependencies:
      internal: [auth, entitlements, metrics]
      external: [redis, clickhouse]
    quality:
      coverage: 0.78
      lint_pass: true
      open_critical_vulns: 0
    security:
      signed_images: true
      policy_pass: true
    last_update: 2025-10-05T22:11:04Z
```

Minimal required fields:
- `name`
- `repo`
- `domain`
- `version`
- `maturity`
- `dependencies` (internal/external arrays)
- At least one timestamp or commit reference

Optional extended fields (scored only if present):
- `quality.coverage`
- `security.signed_images`
- `events_in`/`events_out`
- `api_contracts`

Validation Schema: `schemas/service-manifest.schema.json`.

---

## 6. Dependency Graph & Validation

Graph file: `catalog/dependency-graph.yaml`

```yaml
nodes:
  - gateway
  - streaming
  - auth
  - entitlements
  - metrics
  - normalization
  - enrichment
  - aggregation
  - projection
  - curve
  - backtesting
  - scenario
edges:
  - from: gateway
    to: auth
  - from: gateway
    to: entitlements
  - from: streaming
    to: auth
  - from: aggregation
    to: normalization
  - from: projection
    to: aggregation
rules:
  forbidden_reverse_edges:
    - pattern: "access -> data-processing"
```

Validation checks:
| Rule | Description |
|------|-------------|
| Acyclic | Reject cycles. |
| Directional Cohesion | No “upward” dependency (lower layer calling higher). |
| Allowed External Set | External dependencies must match whitelisted tech (e.g., redis, clickhouse). |
| Edge Completeness | Each manifest dependency appears in graph; warn if not. |

`validate_graph.py` outputs `dependency-violations.json`.

---

## 7. Version & Contract Drift Detection

Inputs:
- `specs.lock.json` from each service (collected).
- Latest spec index from `254carbon-specs` repository.

Drift categories:
| Drift Type | Example | Severity |
|------------|---------|----------|
| Spec Lag | service pins gateway-core@1.0.0 but latest is 1.2.0 | moderate |
| Missing Lock | service absent specs.lock.json | high |
| Manifest Version Not Bumped | code changes detected (commit count) but version static | low |
| Event Schema Unknown | event in manifest not found in spec index | high |
| Dep Version Divergence | shared-libs major mismatch | high |

Report: `analysis/reports/drift/<timestamp>-drift-report.json` + rendered markdown.

Automatic PRs (if enabled by `upgrade-policies.yaml`) for:
- Minor spec upgrades (backward compatible)
- Patch library updates
- Renovate / automation synergy (meta acts as orchestrator)

---

## 8. Quality Metrics Aggregation

Per service metrics (merged):
- Test coverage
- Lint status
- Critical / High vulnerabilities open
- Policy pass/fail counts
- Build reproducibility (image signed, sbom present)
- Mean PR lead time (optional future)
- Deployment freshness (version age)

Composite quality score (0–100):
```
score = base(50)
+ coverage_weight * coverage
+ security_weight * (1 - vuln_ratio)
+ policy_bonus (if all pass)
- drift_penalty
```
Config in `config/thresholds.yaml`.

Output: `catalog/quality-snapshot.json`.

Example:
```json
{
  "generated_at": "2025-10-05T22:30:12Z",
  "services": {
    "gateway": {
      "coverage": 0.78,
      "lint_pass": true,
      "vuln_critical": 0,
      "score": 92
    },
    "aggregation": {
      "coverage": 0.61,
      "lint_pass": true,
      "vuln_critical": 1,
      "score": 71
    }
  },
  "global": {
    "avg_score": 81.5,
    "services_below_threshold": ["aggregation"]
  }
}
```

---

## 9. Release Coordination (Optional Mode)

`release-trains.yaml`:

```yaml
trains:
  - name: Q4-curve-upgrade
    target_version: "curve-service:2.0.0"
    participants:
      - curve
      - backtesting
      - scenario
    dependencies:
      - spec: curves-api >=2.0.0
    gates:
      - all_participants_quality >=80
      - no_open_critical_vulns
    status: planning
```

Workflow `release-train.yml`:
1. Validate participants have compatible spec pins.
2. Verify quality gates.
3. Tag repos (if configured) sequentially or in waves.
4. Emit summary report & update `status: released`.

---

## 10. AI Agent Orchestration Layer

File: `ai/global-context/agent-context.json`  
Contains:
- All service manifest distilled metadata
- Domain layering map
- Known drift hotspots
- Safe automated task types (e.g., “upgrade spec minor”, “add missing coverage harness”)
- Forbidden operations (schema structural change w/o spec PR link)

`risk-cues.json` prioritized hints:
```json
{
  "high_risk": ["aggregation", "projection"],
  "low_coverage": ["scenario"],
  "spec_lag": ["gateway"]
}
```

Agents should consult `agent-guidelines.md`:
- Never modify `service-index.yaml` manually.
- Use upgrade script + PR template.
- Report unsupported changes via issue template.

---

## 11. Automation Workflows Overview

| Workflow | Trigger | Output |
|----------|---------|--------|
| ingest-manifests | Scheduled / manual dispatch | Collect raw manifests |
| build-catalog | Post ingest | Updated service-index.yaml |
| validate-catalog | On catalog change | Lint + schema + dependency validation |
| quality-aggregate | Nightly | quality-snapshot.json + PR comment (optional) |
| drift-detect | Nightly & PR | drift report + optional issues/PRs |
| spec_version_check | After spec repo release event | Opens upgrade PRs |
| agent-context-pack | After catalog/quality change | Refreshes global AI context |
| release-train | Manual dispatch | Coordinated tagging & summary |

---

## 12. Security & Policy Conformance Signals

Meta does not define policies—**it aggregates**:
- Policy pass/fail counts from `254carbon-security` workflow artifacts.
- Image signature verification results.
- SBOM presence flags.
- Alert threshold (if any service below min quality → highlight).

Security status block appended to PR comments:
```
Security Summary:
- Signed Images (all services): 93%
- Critical Vulnerabilities (open): 1 (aggregation)
- Policy Failures: 0 blocking / 2 advisory
```

---

## 13. Data Files & Schemas

| File | Schema | Purpose |
|------|--------|---------|
| `service-index.yaml` | `service-index.schema.json` | Canonical service directory |
| `dependency-graph.yaml` | internal | Connectivity & validation |
| `quality-snapshot.json` | `quality-metrics.schema.json` | Central quality data |
| `agent-context.json` | `agent-context.schema.json` | AI orchestrator global context |
| `spec-version-report.json` | internal | Drift vs latest specifications |
| `release-trains.yaml` | internal | Coordinated release definitions |

Schema evolution is version-controlled; backward-incompatible schema changes require a `CHANGELOG` entry.

---

## 14. How Other Repos Integrate

Each service repo:
1. Exposes `service-manifest.yaml`.
2. On CI success, emits artifact `manifest.json` + `specs.lock.json`.
3. Meta ingestion job pulls artifacts via GitHub API.

Optional: Repos label PRs with:
- `affects:catalog`
- `affects:contracts`
- `affects:security`

Meta uses these labels to weight drift expectations (prevent false positives during active migrations).

---

## 15. Operational Dashboards (Generated)

Artifacts deployed (optionally to Pages or summary branch):
- `catalog-summary.md`
- `quality-leaderboard.md`
- `drift-dashboard.md`
- `release-train-status.md`
- `agent-task-opportunities.md` (list of low-risk auto improvements)

Each updated via workflow after nightly aggregation.

---

## 16. Configuration & Customization

`config/rules.yaml` example:
```yaml
dependency:
  enforce_directionality: true
  forbid_cycles: true
quality:
  min_score: 70
  fail_under: 60
drift:
  block_on_missing_lock: true
  warn_on_minor_spec_lag: true
upgrades:
  auto_minor_spec: true
  auto_patch_libs: true
  require_review_for_major: true
```

`config/thresholds.yaml` example:
```yaml
coverage:
  target: 0.75
  weight: 0.25
security:
  max_critical_vulns: 0
  weight: 0.35
policy:
  weight: 0.15
stability:
  weight: 0.10
drift:
  penalty_weight: 0.15
```

---

## 17. Local Development & Testing

Setup (Python 3.12 assumed):
```bash
make install
make validate
make build-catalog
make quality
make drift
```

Dry-run upgrade simulation:
```bash
python scripts/spec_version_check.py --dry-run
```

Generate agent context:
```bash
make agent-context
```

---

## 18. Extending the Meta Model

Add new service attribute:
1. Update `schemas/service-manifest.schema.json`.
2. Adjust `build_catalog.py` to merge field.
3. Update `QUALITY_SCORING.md` if it impacts scoring.
4. Re-run `make validate`.

Introduce new drift rule:
1. Extend `detect_drift.py`.
2. Add config toggle in `rules.yaml`.
3. Provide test fixtures under `tests/drift/`.

---

## 19. Failure / Degradation Modes

| Failure | Impact | Mitigation |
|---------|--------|-----------|
| Ingestion job failure | Stale catalog | Retry with exponential backoff |
| Partial manifest collection | Incomplete quality view | Mark missing services with `status: unknown` |
| Spec repo unreachable | Drift false negatives | Cache last successful spec index |
| Release train plan error | Blocked coordinated release | Fallback to per-service tagging |
| AI context generation fail | Agents operate on stale context | Keep previous `agent-context.json` version |
| Quality script crash | No updated snapshot | Unit tests & schema guards |

---

## 20. Roadmap & Maturity Stages

| Stage | Capability | Status |
|-------|------------|--------|
| M1 | Basic catalog aggregation | Complete (baseline) |
| M2 | Dependency direction enforcement | In progress |
| M3 | Drift detection (spec & manifest) | In progress |
| M4 | Quality scoring composite | Planned |
| M5 | Auto upgrade PRs (minor specs / patches) | Planned |
| M6 | Release train orchestration | Planned |
| M7 | AI risk-aware task planner | Future |
| M8 | SLA / SLO ingestion (observability link) | Future |
| M9 | Cross-domain change impact analysis | Future |
| M10 | Architecture evolution suggestions | Future |

---

## 21. Contribution Workflow

1. Open issue describing: feature, rule extension, scoring change.
2. Branch name:  
   - `feat/catalog-<slug>`  
   - `chore/scoring-weights`  
   - `fix/drift-edge-case`
3. Implement → add/update tests.
4. Run:
   ```bash
   make all
   ```
5. PR with description; include:
   - Schema changes
   - Backward compatibility notes
   - Migration steps (if any)
6. Reviewer verifies generated artifacts reproducible:
   ```bash
   make reproducible-check
   ```

Commit message examples:
- `feat(catalog): add service runtime memory footprint tracking`
- `fix(drift): handle missing specs.lock gracefully`
- `chore(quality): adjust coverage weight`

---

## 22. Glossary

| Term | Definition |
|------|------------|
| Service Manifest | Per-service metadata file describing contract + runtime traits |
| Catalog | Aggregated, validated collection of all service manifests |
| Drift | Divergence between expected state (catalog/spec version) and reality |
| Release Train | Coordinated set of service version rollouts |
| Quality Score | Composite metric evaluating readiness & health |
| Spec Lag | Service pinned older contract than latest available version |
| Upgrade Assist | Automated or suggested PR to bump dependency/contract |
| Risk Cue | Heuristic signal highlighting potential agent attention areas |
| Directionality | Architectural layering rule (lower layers do not depend upward) |

---

## 23. License / Ownership

Internal while platform architecture stabilizes.  
Ownership: Architecture & Platform Governance (single developer + AI agents).  
Future: Portions (catalog schema + tooling) may be open-sourced under Apache 2.0.

---

## 24. Quick Reference Commands

```bash
# Full pipeline locally
make all

# Only catalog build (collect + aggregate)
make build-catalog

# Validate graph & manifests
make validate

# Compute quality snapshot
make quality

# Detect drift
make drift

# Generate AI global context
make agent-context

# Plan release train (simulate)
python scripts/plan_release_train.py --train Q4-curve-upgrade --dry-run
```

---

> “The meta layer is the **platform brain**: synthesizing distributed signals into actionable, trustworthy guidance so evolution stays intentional—not accidental.”

---
````
