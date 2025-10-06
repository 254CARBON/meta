# Drift Remediation Runbook

## Overview
This runbook provides step-by-step procedures for identifying, assessing, and remediating service drift issues detected by the 254Carbon Meta platform.

## Prerequisites
- Access to 254Carbon Meta repository
- GitHub access to affected service repositories
- Understanding of service dependencies and versioning
- Approval for changes affecting production services

## Drift Types and Severity

### High Severity
- **Missing Lock Files**: Service lacks `specs.lock.json` or equivalent
- **Major Version Lag**: Service pinned to major version significantly behind latest
- **Security Vulnerabilities**: Outdated dependencies with known CVEs
- **Breaking Changes**: Service using deprecated or removed APIs

### Medium Severity
- **Minor Version Lag**: Service pinned to minor version behind latest
- **Feature Lag**: Missing new features available in latest versions
- **Performance Issues**: Known performance improvements in newer versions

### Low Severity
- **Patch Version Lag**: Service pinned to patch version behind latest
- **Documentation Updates**: Missing documentation improvements
- **Minor Bug Fixes**: Missing non-critical bug fixes

## Step-by-Step Remediation Process

### 1. Assessment Phase

#### 1.1 Identify Drift Issues
```bash
# Run drift detection
python scripts/detect_drift.py --service <service-name> --verbose

# Review drift report
cat analysis/reports/drift/latest_drift_report.json
```

#### 1.2 Classify Drift Severity
- Review the drift report for severity levels
- Identify affected services and dependencies
- Assess impact on dependent services
- Check for breaking changes in target versions

#### 1.3 Impact Analysis
```bash
# Analyze impact on dependent services
python scripts/analyze_impact.py --service <service-name> --change-type spec_upgrade

# Review dependency graph
cat catalog/dependency-graph.yaml
```

### 2. Planning Phase

#### 2.1 Create Remediation Plan
- List all required changes
- Identify testing requirements
- Plan rollback strategy
- Set timeline and milestones

#### 2.2 Risk Assessment
- Evaluate breaking changes
- Assess testing coverage
- Review deployment complexity
- Identify potential issues

#### 2.3 Communication Plan
- Notify affected teams
- Schedule change windows
- Prepare rollback communications
- Document change procedures

### 3. Implementation Phase

#### 3.1 Update Dependencies
```bash
# For Python services
pip install --upgrade <package-name>
pip freeze > requirements.txt

# For Node.js services
npm update <package-name>
npm audit fix

# For Go services
go get -u <module-name>
go mod tidy
```

#### 3.2 Update Lock Files
```bash
# Generate new lock file
python scripts/spec_version_check.py --service <service-name> --update-lock

# Verify lock file
cat specs.lock.json
```

#### 3.3 Update Service Manifest
```yaml
# Update service-manifest.yaml
api_contracts:
  - "gateway-core@1.2.0"  # Updated version
dependencies:
  internal:
    - "auth-service@1.1.0"  # Updated version
  external:
    - "redis@7.0"
    - "postgresql@15"
```

#### 3.4 Code Changes
- Update imports and references
- Modify deprecated API calls
- Update configuration files
- Adjust error handling

### 4. Testing Phase

#### 4.1 Unit Tests
```bash
# Run unit tests
python -m pytest tests/
npm test
go test ./...
```

#### 4.2 Integration Tests
```bash
# Run integration tests
python -m pytest tests/integration/
npm run test:integration
go test -tags=integration ./...
```

#### 4.3 Compatibility Tests
- Test with dependent services
- Verify API contracts
- Check event schemas
- Validate data formats

### 5. Deployment Phase

#### 5.1 Pre-deployment Checks
```bash
# Validate service manifest
python scripts/validate_manifests.py --service <service-name>

# Check quality score
python scripts/compute_quality.py --service <service-name>

# Verify drift resolution
python scripts/detect_drift.py --service <service-name>
```

#### 5.2 Deployment Process
- Deploy to staging environment
- Run smoke tests
- Deploy to production
- Monitor for issues

#### 5.3 Post-deployment Verification
```bash
# Verify service health
curl -f https://<service-url>/health

# Check metrics
python scripts/ingest_observability.py --service <service-name>

# Validate drift resolution
python scripts/detect_drift.py --service <service-name>
```

### 6. Monitoring Phase

#### 6.1 Health Monitoring
- Monitor service health metrics
- Check error rates
- Review performance metrics
- Watch for alerts

#### 6.2 Drift Monitoring
```bash
# Schedule regular drift checks
python scripts/detect_drift.py --schedule daily

# Monitor drift trends
python scripts/analyze_quality_trends.py --service <service-name>
```

## Automated Remediation

### For Low-Risk Changes
```bash
# Automated patch updates
python scripts/auto_remediate_drift.py --service <service-name> --risk-level low

# Automated lock file generation
python scripts/spec_version_check.py --service <service-name> --auto-update
```

### For Medium-Risk Changes
```bash
# Semi-automated with approval
python scripts/auto_remediate_drift.py --service <service-name> --risk-level medium --require-approval
```

## Rollback Procedures

### 1. Immediate Rollback
```bash
# Rollback to previous version
git checkout <previous-commit>
docker build -t <service>:<previous-version> .
docker push <service>:<previous-version>

# Update deployment
kubectl set image deployment/<service> <service>=<service>:<previous-version>
```

### 2. Gradual Rollback
- Reduce traffic to new version
- Increase traffic to previous version
- Monitor for stability
- Complete rollback

### 3. Data Rollback
- Restore database backups if needed
- Revert configuration changes
- Update service dependencies
- Verify data consistency

## Common Issues and Solutions

### Issue: Breaking API Changes
**Solution:**
- Update API calls to new format
- Add compatibility layer if needed
- Update dependent services
- Test thoroughly

### Issue: Dependency Conflicts
**Solution:**
- Resolve version conflicts
- Update conflicting dependencies
- Test compatibility
- Consider alternative packages

### Issue: Performance Degradation
**Solution:**
- Profile performance bottlenecks
- Optimize code paths
- Update to performance-improved versions
- Monitor metrics

### Issue: Security Vulnerabilities
**Solution:**
- Update to secure versions immediately
- Apply security patches
- Review security policies
- Conduct security audit

## Prevention Strategies

### 1. Regular Updates
- Schedule regular dependency updates
- Monitor for security advisories
- Keep lock files current
- Update service manifests

### 2. Automated Monitoring
```bash
# Set up automated drift detection
python scripts/detect_drift.py --schedule daily --notify-on-drift

# Monitor quality trends
python scripts/analyze_quality_trends.py --schedule weekly
```

### 3. Best Practices
- Use semantic versioning
- Maintain comprehensive tests
- Document breaking changes
- Communicate updates early

## Escalation Procedures

### Level 1: Service Team
- Handle low-severity drift
- Update dependencies
- Test changes
- Deploy updates

### Level 2: Platform Team
- Handle medium-severity drift
- Coordinate multi-service updates
- Manage release trains
- Monitor system health

### Level 3: Architecture Team
- Handle high-severity drift
- Manage breaking changes
- Coordinate major updates
- Plan system evolution

## Contact Information

- **Platform Team**: platform-team@254carbon.com
- **SRE Team**: sre-team@254carbon.com
- **On-Call**: oncall@254carbon.com
- **Emergency**: +1-XXX-XXX-XXXX

## Related Documentation

- [Service Manifest Schema](../schemas/service-manifest.schema.json)
- [Drift Detection Guide](../docs/DRIFT_DETECTION.md)
- [Quality Scoring Guide](../docs/QUALITY_SCORING.md)
- [Release Trains Guide](../docs/RELEASE_TRAINS.md)

---

**Last Updated**: 2025-01-06  
**Version**: 1.0.0  
**Maintained by**: Platform Team
