# Release Trains Documentation

## Overview

Release trains in the 254Carbon Meta platform provide coordinated, multi-service release orchestration capabilities. This system enables teams to coordinate releases across multiple services while maintaining consistency, quality gates, and rollback capabilities.

## Table of Contents

1. [Concepts](#concepts)
2. [Release Train Lifecycle](#release-train-lifecycle)
3. [Configuration](#configuration)
4. [Quality Gates](#quality-gates)
5. [Monitoring and Progress Tracking](#monitoring-and-progress-tracking)
6. [Rollback Procedures](#rollback-procedures)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

## Concepts

### Release Train

A **release train** is a coordinated set of service releases that are planned, executed, and monitored together. Release trains ensure that:

- Multiple services are released in a coordinated manner
- Dependencies between services are respected
- Quality gates are enforced across all participants
- Rollback procedures are available if issues arise

### Key Components

- **Train Name**: Unique identifier for the release train
- **Participants**: List of services included in the release
- **Target Version**: The version to which services will be upgraded
- **Quality Gates**: Conditions that must be met before release
- **Dependencies**: External requirements (specs, libraries, etc.)
- **Status**: Current state of the release train

### Release Train Status

| Status | Description |
|--------|-------------|
| `planning` | Release train is being planned and configured |
| `validating` | Quality gates and dependencies are being validated |
| `staging` | Release artifacts are being prepared |
| `executing` | Services are being released in sequence |
| `verifying` | Post-release health checks are being performed |
| `completed` | Release train completed successfully |
| `failed` | Release train failed and requires intervention |
| `rolled_back` | Release train was rolled back due to issues |
| `paused` | Release train is temporarily paused |

## Release Train Lifecycle

### 1. Planning Phase

During the planning phase, teams define:

- **Scope**: Which services will be included
- **Timeline**: When the release will occur
- **Dependencies**: What external requirements must be met
- **Quality Gates**: What conditions must be satisfied

#### Example Planning Configuration

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

### 2. Validation Phase

The validation phase ensures that:

- All participants meet quality requirements
- Dependencies are satisfied
- No blocking issues exist
- Rollback plans are in place

#### Validation Checks

- **Quality Score**: All services must meet minimum quality thresholds
- **Security**: No critical vulnerabilities in any participant
- **Dependencies**: All required specs and libraries are available
- **Health Status**: All services are healthy before release
- **Backup Availability**: Rollback artifacts are available

### 3. Staging Phase

During staging, the system:

- Prepares release artifacts
- Validates deployment configurations
- Sets up monitoring and alerting
- Prepares rollback procedures

### 4. Execution Phase

Services are released in dependency order:

1. **Dependency Analysis**: Determine optimal release sequence
2. **Sequential Release**: Release services one by one
3. **Health Verification**: Verify each service after release
4. **Progress Tracking**: Monitor overall progress

#### Release Sequence Example

```
1. curve (no dependencies)
2. backtesting (depends on curve)
3. scenario (depends on curve, backtesting)
```

### 5. Verification Phase

Post-release verification includes:

- **Health Checks**: Verify all services are healthy
- **Performance Monitoring**: Check for performance regressions
- **Integration Testing**: Verify service interactions
- **User Acceptance**: Confirm functionality works as expected

### 6. Completion

Upon successful completion:

- **Status Update**: Mark train as completed
- **Documentation**: Update release notes and documentation
- **Monitoring**: Continue monitoring for issues
- **Cleanup**: Clean up temporary resources

## Configuration

### Release Train Definition

Release trains are defined in `catalog/release-trains.yaml`:

```yaml
trains:
  - name: <train-name>
    target_version: <version>
    participants:
      - <service1>
      - <service2>
    dependencies:
      - spec: <spec-name> >=<version>
      - library: <library-name> >=<version>
    gates:
      - all_participants_quality >=<score>
      - no_open_critical_vulns
      - all_services_healthy
    status: <status>
    schedule:
      start_time: <iso-timestamp>
      estimated_duration: <duration>
    rollback:
      enabled: true
      timeout: <duration>
      health_check_threshold: <percentage>
```

### Quality Gates Configuration

Quality gates are defined in `config/upgrade-policies.yaml`:

```yaml
release_trains:
  quality_gates:
    min_quality_score: 80
    max_critical_vulns: 0
    min_coverage: 75
    max_failure_rate: 5
  validation:
    health_check_timeout: 300
    dependency_check_timeout: 60
    rollback_timeout: 600
  notifications:
    enabled: true
    channels: ["slack", "email"]
    stakeholders: ["platform-team", "release-managers"]
```

## Quality Gates

### Standard Quality Gates

1. **Quality Score**: All participants must meet minimum quality score
2. **Security**: No critical vulnerabilities in any participant
3. **Coverage**: Test coverage must meet minimum threshold
4. **Health**: All services must be healthy before release
5. **Dependencies**: All required dependencies must be available

### Custom Quality Gates

Teams can define custom quality gates:

```yaml
gates:
  - custom: "performance_regression < 10%"
  - custom: "user_acceptance_tests_pass"
  - custom: "security_scan_clean"
```

### Gate Evaluation

Quality gates are evaluated:

- **Before Release**: All gates must pass
- **During Release**: Critical gates are re-evaluated
- **After Release**: Gates are verified post-release

## Monitoring and Progress Tracking

### Real-time Monitoring

The release train monitoring system provides:

- **Progress Tracking**: Real-time progress updates
- **Health Monitoring**: Continuous health checks
- **Performance Metrics**: Performance monitoring during release
- **Alert System**: Notifications for issues

### Monitoring Dashboard

The monitoring dashboard shows:

- **Overall Progress**: Percentage completion
- **Service Status**: Individual service status
- **Health Metrics**: Health status of all services
- **Performance Trends**: Performance metrics over time
- **Issue Tracking**: Current issues and resolutions

### Progress Tracking

Progress is tracked at multiple levels:

1. **Train Level**: Overall release train progress
2. **Service Level**: Individual service release progress
3. **Gate Level**: Quality gate evaluation progress
4. **Dependency Level**: Dependency resolution progress

## Rollback Procedures

### Automatic Rollback

The system can automatically trigger rollback when:

- **Health Check Failures**: Health checks fail beyond threshold
- **Performance Regression**: Performance degrades significantly
- **Error Rate Increase**: Error rates exceed acceptable limits
- **Dependency Issues**: Critical dependencies become unavailable

### Manual Rollback

Manual rollback can be triggered:

- **Command Line**: Using the rollback script
- **Dashboard**: Through the monitoring dashboard
- **API**: Via the rollback API endpoint

### Rollback Process

1. **Assessment**: Evaluate rollback necessity
2. **Planning**: Create rollback plan
3. **Execution**: Execute rollback in reverse order
4. **Verification**: Verify rollback success
5. **Documentation**: Document rollback reasons and outcomes

#### Rollback Command Example

```bash
python scripts/rollback_release_train.py \
  --train-name Q4-curve-upgrade \
  --reason "Performance regression detected" \
  --dry-run
```

## Best Practices

### Planning Best Practices

1. **Scope Management**: Keep release trains focused and manageable
2. **Dependency Analysis**: Thoroughly analyze service dependencies
3. **Quality Gates**: Set appropriate quality thresholds
4. **Timeline Planning**: Allow adequate time for each phase
5. **Stakeholder Communication**: Keep all stakeholders informed

### Execution Best Practices

1. **Sequential Release**: Release services in dependency order
2. **Health Verification**: Verify each service after release
3. **Progress Monitoring**: Continuously monitor progress
4. **Issue Response**: Respond quickly to issues
5. **Documentation**: Document all decisions and actions

### Rollback Best Practices

1. **Rollback Planning**: Plan rollback procedures in advance
2. **Backup Verification**: Ensure backups are available
3. **Quick Response**: Respond quickly to rollback triggers
4. **Communication**: Communicate rollback status clearly
5. **Post-Rollback Analysis**: Analyze rollback causes

### Monitoring Best Practices

1. **Comprehensive Monitoring**: Monitor all critical metrics
2. **Alert Configuration**: Configure appropriate alerts
3. **Dashboard Usage**: Use dashboards for visibility
4. **Trend Analysis**: Analyze trends over time
5. **Continuous Improvement**: Continuously improve monitoring

## Troubleshooting

### Common Issues

#### Release Train Stuck in Validation

**Symptoms**: Release train remains in validation phase
**Causes**: Quality gates failing, dependencies unavailable
**Solutions**:
- Check quality gate status
- Verify dependency availability
- Review validation logs
- Adjust quality thresholds if appropriate

#### Service Release Failure

**Symptoms**: Individual service release fails
**Causes**: Deployment issues, configuration problems
**Solutions**:
- Check deployment logs
- Verify service configuration
- Test deployment manually
- Consider rollback if critical

#### Health Check Failures

**Symptoms**: Health checks failing after release
**Causes**: Service issues, configuration problems
**Solutions**:
- Check service logs
- Verify health check endpoints
- Review service configuration
- Consider rollback if persistent

#### Performance Regression

**Symptoms**: Performance degradation after release
**Causes**: Code issues, configuration problems
**Solutions**:
- Analyze performance metrics
- Check for code changes
- Review configuration changes
- Consider rollback if significant

### Debugging Commands

#### Check Release Train Status

```bash
python scripts/monitor_release_progress.py --train-name <name> --status
```

#### Validate Release Train

```bash
python scripts/plan_release_train.py --train <name> --validate
```

#### Check Service Health

```bash
python scripts/generate_monitoring_report.py --service <name>
```

#### Analyze Rollback Options

```bash
python scripts/rollback_release_train.py --train-name <name> --dry-run
```

### Log Analysis

#### Release Train Logs

- **Location**: `analysis/reports/release_monitoring.log`
- **Content**: Release train execution logs
- **Analysis**: Check for errors, warnings, and progress

#### Service Logs

- **Location**: Service-specific log files
- **Content**: Service deployment and health logs
- **Analysis**: Check for deployment issues and errors

#### Audit Logs

- **Location**: `analysis/reports/audit.log`
- **Content**: Audit trail of all actions
- **Analysis**: Track all changes and decisions

## API Reference

### Release Train Management

#### Create Release Train

```bash
POST /api/v1/release-trains
Content-Type: application/json

{
  "name": "Q4-curve-upgrade",
  "target_version": "curve-service:2.0.0",
  "participants": ["curve", "backtesting", "scenario"],
  "dependencies": [{"spec": "curves-api", "version": ">=2.0.0"}],
  "gates": ["all_participants_quality >=80", "no_open_critical_vulns"]
}
```

#### Get Release Train Status

```bash
GET /api/v1/release-trains/{train-name}/status
```

#### Update Release Train

```bash
PUT /api/v1/release-trains/{train-name}
Content-Type: application/json

{
  "status": "executing",
  "progress": 45.5
}
```

#### Delete Release Train

```bash
DELETE /api/v1/release-trains/{train-name}
```

### Service Management

#### Get Service Status

```bash
GET /api/v1/services/{service-name}/status
```

#### Update Service Status

```bash
PUT /api/v1/services/{service-name}/status
Content-Type: application/json

{
  "status": "deployed",
  "version": "2.0.0",
  "health_status": "healthy"
}
```

### Monitoring

#### Get Monitoring Data

```bash
GET /api/v1/monitoring/release-trains/{train-name}
```

#### Get Health Metrics

```bash
GET /api/v1/monitoring/health/{service-name}
```

#### Get Performance Metrics

```bash
GET /api/v1/monitoring/performance/{service-name}
```

### Rollback

#### Trigger Rollback

```bash
POST /api/v1/release-trains/{train-name}/rollback
Content-Type: application/json

{
  "reason": "Performance regression detected",
  "force": false
}
```

#### Get Rollback Status

```bash
GET /api/v1/release-trains/{train-name}/rollback/status
```

## Conclusion

Release trains provide a powerful mechanism for coordinating multi-service releases while maintaining quality, consistency, and reliability. By following the best practices outlined in this documentation and using the provided tools and APIs, teams can successfully manage complex release scenarios with confidence.

For additional support or questions, please refer to the troubleshooting section or contact the platform team.
