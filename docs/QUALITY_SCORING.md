# Quality Scoring Methodology

> Complete specification for the 254Carbon platform composite quality scoring system

**Version:** 1.0.0  
**Last Updated:** 2025-10-06

---

## Table of Contents
1. Overview
2. Composite Score Formula
3. Scoring Dimensions
4. Weight Justification
5. Maturity Adjustments
6. Grade Assignment
7. Improvement Strategies

---

## 1. Overview

The 254Carbon platform uses a **composite quality score** (0-100) to assess service health and readiness. This score combines multiple dimensions weighted by importance and adjusted for service maturity.

### Design Goals

- **Holistic Assessment:** Consider multiple quality aspects
- **Maturity-Aware:** Different expectations for experimental vs stable
- **Actionable:** Clear improvement paths
- **Comparable:** Services can be ranked and compared
- **Automated:** Computed nightly without manual input

---

## 2. Composite Score Formula

### Base Formula

```
score = base_score
      + (coverage_component)
      + (security_component)
      + (policy_component)
      + (stability_component)
      - (drift_penalty)
      * maturity_multiplier
```

Where the score is clamped to `max(0, min(100, score))`

### Detailed Calculation

```python
# Step 1: Start with base score
score = 50  # Base score

# Step 2: Add coverage component (max 25 points)
coverage_score = (coverage / target_coverage) * 100 * 0.25 * 4
score += min(25, coverage_score)

# Step 3: Add security component (max 35 points)
vuln_penalty = (critical_vulns * 20) + (high_vulns * 10)
security_score = max(0, 100 - vuln_penalty) * 0.35
score += security_score

# Step 4: Add policy component (max 15 points)
if policy_failures == 0:
    score += 15 * 0.15  # Full bonus
else:
    policy_penalty = policy_failures * 5
    score -= policy_penalty * 0.15

# Step 5: Add stability component (max 10 points)
if deployment_freshness_days <= 7:
    score += 5 * 0.10
elif deployment_freshness_days > 30:
    score -= 10 * 0.10

# Step 6: Subtract drift penalty (max 20 points)
drift_penalty = min(drift_issues * 5, 20)
score -= drift_penalty * 0.15

# Step 7: Apply maturity multiplier
score = score * maturity_multiplier[maturity]

# Step 8: Clamp to valid range
score = max(0, min(100, int(score)))
```

---

## 3. Scoring Dimensions

### Dimension 1: Test Coverage (Weight: 0.25)

**Purpose:** Measure test suite completeness

**Calculation:**
```
coverage_points = (actual_coverage / target_coverage) * 25
```

**Targets by Maturity:**
- Experimental: 50% (0.50)
- Beta: 70% (0.70)
- Stable: 80% (0.80)
- Deprecated: 60% (0.60)

**Examples:**
- Service with 80% coverage (stable): `(0.80 / 0.80) * 25 = 25 points` ✅ Perfect
- Service with 60% coverage (stable): `(0.60 / 0.80) * 25 = 18.75 points` ⚠️ Below target
- Service with 70% coverage (beta): `(0.70 / 0.70) * 25 = 25 points` ✅ Perfect

### Dimension 2: Security (Weight: 0.35)

**Purpose:** Assess security posture and vulnerability status

**Calculation:**
```
vuln_penalty = (critical_vulns * 20) + (high_vulns * 10)
security_score = max(0, 100 - vuln_penalty)
security_points = security_score * 0.35
```

**Bonuses:**
- Signed images: +10 points
- SBOM present: +5 points

**Examples:**
- 0 critical, 0 high: `100 * 0.35 = 35 points` ✅ Perfect
- 1 critical, 0 high: `(100 - 20) * 0.35 = 28 points` 🔴 Critical issue
- 0 critical, 2 high: `(100 - 20) * 0.35 = 28 points` 🟠 High issues

### Dimension 3: Policy Compliance (Weight: 0.15)

**Purpose:** Ensure organizational policy adherence

**Calculation:**
```
if policy_failures == 0:
    policy_points = 15 * 0.15  # Full bonus for compliance
else:
    policy_penalty = policy_failures * 5
    policy_points = -(policy_penalty * 0.15)
```

**Examples:**
- 0 failures: `15 * 0.15 = 2.25 points` ✅ Bonus
- 1 failure: `-5 * 0.15 = -0.75 points` ⚠️ Penalty
- 3 failures: `-15 * 0.15 = -2.25 points` 🔴 Significant penalty

### Dimension 4: Stability (Weight: 0.10)

**Purpose:** Reward recent updates, penalize staleness

**Calculation:**
```
if days_since_deployment <= 7:
    stability_points = 5 * 0.10  # Recent deployment bonus
elif days_since_deployment > 30:
    stability_points = -10 * 0.10  # Staleness penalty
else:
    stability_points = 0  # Neutral
```

**Examples:**
- Deployed 3 days ago: `+0.5 points` 🟢 Fresh
- Deployed 45 days ago: `-1.0 points` 🟠 Stale
- Deployed 150 days ago: `-1.0 points` 🔴 Very stale

### Dimension 5: Drift Penalty (Weight: 0.15)

**Purpose:** Penalize services with specification drift

**Calculation:**
```
drift_penalty = min(drift_issues * 5, 20)  # Max 20 points
drift_points = -(drift_penalty * 0.15)
```

**Examples:**
- 0 drift issues: `0 points` ✅ Clean
- 2 drift issues: `-10 * 0.15 = -1.5 points` ⚠️ Some drift
- 5 drift issues: `-20 * 0.15 = -3.0 points` 🔴 High drift

---

## 4. Weight Justification

### Why These Weights?

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Security | 35% | **Most Critical** - Vulnerabilities can compromise entire platform |
| Coverage | 25% | **Very Important** - Tests prevent regressions and enable safe changes |
| Policy | 15% | **Important** - Ensures consistency and compliance |
| Drift | 15% | **Important** - Drift indicates technical debt accumulation |
| Stability | 10% | **Moderate** - Recent deployments show active maintenance |

### Weight Calibration

The weights were calibrated so that:

**Grade A (90+)** requires:
- Excellent security (0 critical vulns)
- High coverage (75%+)
- Full policy compliance
- Minimal drift

**Grade C (70-79)** allows:
- Good security (1-2 high vulns acceptable)
- Moderate coverage (60-70%)
- Some policy warnings
- Moderate drift (2-3 issues)

**Grade F (<60)** typically has:
- Critical security issues
- OR very low coverage (<50%)
- OR major policy failures
- OR excessive drift (5+ issues)

---

## 5. Maturity Adjustments

Services are evaluated differently based on maturity level:

### Experimental (Multiplier: 0.8)

**Philosophy:** Innovation over perfection

**Adjustments:**
- Coverage weight: 80% (lowered expectations)
- Security weight: 60% (more lenient)
- Stability weight: 50% (frequent changes expected)

**Example:** A service scoring 75 becomes `75 * 0.8 = 60` (Grade D → C)

**Rationale:** Early-stage services shouldn't be penalized for lack of polish

### Beta (Multiplier: 0.9)

**Philosophy:** Testing and hardening phase

**Adjustments:**
- Coverage weight: 90%
- Security weight: 80%
- Stability weight: 70%

**Example:** A service scoring 80 becomes `80 * 0.9 = 72` (Grade B → C)

**Rationale:** Getting close to production standards, but still maturing

### Stable (Multiplier: 1.0)

**Philosophy:** Production-ready expectations

**Adjustments:**
- Coverage weight: 100% (full expectations)
- Security weight: 100% (zero tolerance for critical vulns)
- Stability weight: 100% (should be maintained)

**Example:** A service scoring 85 stays `85 * 1.0 = 85` (Grade B)

**Rationale:** Production services must meet all standards

### Deprecated (Multiplier: 0.6)

**Philosophy:** Maintenance mode, migration in progress

**Adjustments:**
- Coverage weight: 60% (minimal maintenance)
- Security weight: 40% (security still matters but fixing is lower priority)
- Stability weight: 30% (updates not expected)

**Example:** A service scoring 70 becomes `70 * 0.6 = 42` (Grade C → F)

**Rationale:** Resources should focus on replacement services

---

## 6. Grade Assignment

### Grade Thresholds

| Grade | Range | Description | Status | Requirements |
|-------|-------|-------------|--------|--------------|
| **A** | 90-100 | Excellent | 🟢 | Coverage 90%+, 0 critical vulns, policy compliant |
| **B** | 80-89 | Good | 🟡 | Coverage 80%+, 0-1 high vulns, mostly compliant |
| **C** | 70-79 | Acceptable | 🟢 | Coverage 70%+, 0 critical vulns, some warnings OK |
| **D** | 60-69 | Needs Improvement | 🟠 | Below one or more thresholds, action required |
| **F** | 0-59 | Failing | 🔴 | Critical issues present, immediate attention needed |

### Grade Interpretation

**Grade A (Excellent):**
- Best practices followed
- Ready for critical path
- Can be reference implementation
- Safe for autonomous AI changes

**Grade B (Good):**
- Production-ready
- Minor improvements possible
- Safe for most changes
- Suitable for stable services

**Grade C (Acceptable):**
- Meets minimum standards
- Improvement recommended
- Careful with major changes
- Acceptable for beta services

**Grade D (Needs Improvement):**
- Below production standards
- Must improve before stable promotion
- Review before significant changes
- Require architect approval for changes

**Grade F (Failing):**
- Not production-ready
- Immediate intervention required
- Block new features until fixed
- Require platform team oversight

---

## 7. Improvement Strategies

### Strategy 1: From F to D (0-59 → 60-69)

**Focus:** Address critical blockers

**Actions:**
1. **Fix Security Issues:**
   - Resolve all critical vulnerabilities immediately
   - Address high vulnerabilities within 30 days
   
2. **Basic Test Coverage:**
   - Achieve minimum 50% coverage
   - Cover critical paths with tests
   
3. **Policy Compliance:**
   - Review and fix policy failures
   - Document any exemptions needed

**Timeline:** 2-3 weeks  
**Effort:** High - requires focused team effort

### Strategy 2: From D to C (60-69 → 70-79)

**Focus:** Meet minimum production standards

**Actions:**
1. **Increase Coverage:**
   - Reach 70% test coverage
   - Add integration tests
   
2. **Security Hardening:**
   - Eliminate remaining vulnerabilities
   - Enable image signing
   
3. **Reduce Drift:**
   - Update outdated dependencies
   - Align with latest specs

**Timeline:** 1-2 weeks  
**Effort:** Medium - standard engineering practices

### Strategy 3: From C to B (70-79 → 80-89)

**Focus:** Achieve good quality

**Actions:**
1. **Coverage Excellence:**
   - Reach 80%+ test coverage
   - Add edge case tests
   
2. **Zero Critical Issues:**
   - Maintain zero critical vulnerabilities
   - Proactive dependency updates
   
3. **Full Compliance:**
   - Pass all policy checks
   - Generate SBOM

**Timeline:** 1 week  
**Effort:** Low-Medium - incremental improvements

### Strategy 4: From B to A (80-89 → 90-100)

**Focus:** Excellence and best practices

**Actions:**
1. **Coverage Mastery:**
   - Reach 90%+ test coverage
   - Comprehensive integration tests
   - Performance tests
   
2. **Proactive Security:**
   - Automated dependency scanning
   - Regular security audits
   - Signed artifacts
   
3. **Zero Drift:**
   - Automated spec upgrades
   - Continuous alignment
   - Documentation excellence

**Timeline:** Ongoing  
**Effort:** Continuous improvement culture

---

## Appendix A: Scoring Examples

### Example 1: High-Quality Stable Service

```yaml
service: gateway
maturity: stable
coverage: 0.85
critical_vulns: 0
high_vulns: 0
policy_failures: 0
deployment_days: 5
drift_issues: 0
```

**Calculation:**
```
Base: 50
Coverage: (0.85 / 0.80) * 25 = 26.56 → 25 (capped)
Security: (100 - 0) * 0.35 = 35
Policy: 15 * 0.15 = 2.25
Stability: 5 * 0.10 = 0.50
Drift: 0
Maturity: * 1.0
Total: 50 + 25 + 35 + 2.25 + 0.50 = 112.75 → 100 (capped)
Grade: A
```

### Example 2: Beta Service with Issues

```yaml
service: streaming
maturity: beta
coverage: 0.65
critical_vulns: 1
high_vulns: 2
policy_failures: 1
deployment_days: 45
drift_issues: 2
```

**Calculation:**
```
Base: 50
Coverage: (0.65 / 0.70) * 25 = 23.21
Security: (100 - 20 - 20) * 0.35 = 21
Policy: -5 * 0.15 = -0.75
Stability: -10 * 0.10 = -1.0
Drift: -10 * 0.15 = -1.5
Subtotal: 50 + 23.21 + 21 - 0.75 - 1.0 - 1.5 = 90.96
Maturity: * 0.9
Total: 90.96 * 0.9 = 81.86 → 82
Grade: B
```

### Example 3: Failing Service

```yaml
service: enrichment
maturity: beta
coverage: 0.45
critical_vulns: 2
high_vulns: 3
policy_failures: 3
deployment_days: 120
drift_issues: 5
```

**Calculation:**
```
Base: 50
Coverage: (0.45 / 0.70) * 25 = 16.07
Security: (100 - 40 - 30) * 0.35 = 10.5
Policy: -15 * 0.15 = -2.25
Stability: -10 * 0.10 = -1.0
Drift: -20 * 0.15 = -3.0
Subtotal: 50 + 16.07 + 10.5 - 2.25 - 1.0 - 3.0 = 70.32
Maturity: * 0.9
Total: 70.32 * 0.9 = 63.29 → 63
Grade: D
```

---

## Appendix B: Configuration Reference

All thresholds and weights are configured in `config/thresholds.yaml`:

```yaml
quality:
  base_score: 50
  
  weights:
    coverage: 0.25
    security: 0.35
    policy: 0.15
    stability: 0.10
    drift: 0.15
  
  coverage:
    target: 0.75
    excellent_threshold: 0.90
    good_threshold: 0.80
    acceptable_threshold: 0.70
    poor_threshold: 0.50
  
  security:
    max_critical_vulns: 0
    max_high_vulns: 2
    signed_images_bonus: 10
    sbom_bonus: 5
  
  drift:
    penalty_per_issue: 5
    max_penalty: 20
  
maturity_multipliers:
  experimental: {coverage_weight: 0.8}
  beta: {coverage_weight: 0.9}
  stable: {coverage_weight: 1.0}
  deprecated: {coverage_weight: 0.6}
```

---

## Appendix C: Quality Score FAQ

**Q: Why is security weighted so heavily (35%)?**  
A: Security vulnerabilities can compromise the entire platform. Zero critical vulnerabilities is non-negotiable for production services.

**Q: Can a service get 100/100?**  
A: Yes, with perfect coverage (90%+), zero vulnerabilities, full policy compliance, recent deployment, and zero drift.

**Q: Why does drift affect quality?**  
A: Drift indicates outdated dependencies and specifications, which increases technical debt and security risk over time.

**Q: How often are scores recomputed?**  
A: Nightly via the quality-aggregate.yml workflow, and on-demand via `meta quality compute`.

**Q: Can I customize weights for my organization?**  
A: Yes, edit `config/thresholds.yaml` to adjust weights. Ensure weights still sum to appropriate totals.

---

*📚 Part of the 254Carbon Meta documentation suite*  
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [DRIFT_DETECTION.md](DRIFT_DETECTION.md)*
