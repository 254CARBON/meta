#!/usr/bin/env python3
"""
254Carbon Meta Repository - AI Agent Context Generator

Generates comprehensive context bundles for AI coding agents, consolidating
catalog facts, drift hotspots, quality signals, domain maps, and safe/forbidden
operation guidance for autonomous tooling.

Usage:
    python scripts/generate_agent_context.py [--catalog-file FILE] [--drift-file FILE]

Highlights:
- Creates structured data suitable for task selection and risk-aware automation.
- Emits supportive markdown artifacts (guidelines, task opportunities) to help
  human-in-the-loop workflows.

Outputs:
- JSON bundle at `ai/global-context/agent-context.json` plus markdown helpers in
  the same directory.
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('ai/global-context/context-generation.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ServiceContext:
    """Agent-friendly service representation."""
    name: str
    domain: str
    maturity: str
    version: str
    runtime: str
    dependencies_internal: List[str]
    dependencies_external: List[str]
    api_contracts: List[str]
    events_produced: List[str]
    events_consumed: List[str]
    quality_score: float
    risk_level: str


@dataclass
class DomainContext:
    """Domain architecture information."""
    name: str
    services: List[str]
    description: str
    dependencies: List[str]
    risk_level: str


@dataclass
class RiskCue:
    """Risk assessment hint for agents."""
    service: str
    risk_type: str
    severity: str
    description: str
    recommended_action: str


@dataclass
class AgentContext:
    """Complete AI agent context bundle."""
    metadata: Dict[str, Any]
    services: Dict[str, ServiceContext]
    domains: Dict[str, DomainContext]
    drift_hotspots: List[str]
    risk_cues: List[RiskCue]
    safe_operations: List[str]
    forbidden_operations: List[str]
    policy_reminders: List[str]
    recent_changes: List[Dict[str, Any]]
    current_focus: List[str]


class AgentContextGenerator:
    """Generates AI agent context bundles."""

    def __init__(self, catalog_file: str = None, drift_file: str = None, quality_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.drift_file = drift_file or "catalog/latest_drift_report.json"
        self.quality_file = quality_file or "catalog/latest_quality_snapshot.json"

        # Load data sources
        self.catalog = self._load_catalog()
        self.drift_data = self._load_drift_data()
        self.quality_data = self._load_quality_data()

        # Output directory
        self.context_dir = Path("ai/global-context")
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def _find_catalog_file(self, catalog_file: str = None) -> Path:
        """Find catalog file."""
        if catalog_file:
            return Path(catalog_file)

        # Default locations
        yaml_path = Path("catalog/service-index.yaml")
        json_path = Path("catalog/service-index.json")

        if yaml_path.exists():
            return yaml_path
        elif json_path.exists():
            return json_path
        else:
            raise FileNotFoundError("No catalog file found. Run 'make build-catalog' first.")

    def _load_catalog(self) -> Dict[str, Any]:
        """Load service catalog."""
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _load_drift_data(self) -> Dict[str, Any]:
        """Load drift report data."""
        drift_path = Path(self.drift_file)

        if not drift_path.exists():
            logger.warning(f"Drift file not found: {drift_path}")
            return {}

        try:
            with open(drift_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load drift data: {e}")
            return {}

    def _load_quality_data(self) -> Dict[str, Any]:
        """Load quality snapshot data."""
        quality_path = Path(self.quality_file)

        if not quality_path.exists():
            logger.warning(f"Quality file not found: {quality_path}")
            return {}

        try:
            with open(quality_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load quality data: {e}")
            return {}

    def _build_service_context(self, service: Dict[str, Any]) -> ServiceContext:
        """Build agent-friendly service context."""
        # Determine risk level based on quality and drift
        quality_score = service.get('quality', {}).get('score', 50)
        drift_issues = len([i for i in self.drift_data.get('issues', [])
                           if i.get('service') == service['name']])

        if quality_score < 60 or drift_issues > 3:
            risk_level = "high"
        elif quality_score < 75 or drift_issues > 0:
            risk_level = "medium"
        else:
            risk_level = "low"

        return ServiceContext(
            name=service['name'],
            domain=service['domain'],
            maturity=service['maturity'],
            version=service['version'],
            runtime=service.get('runtime', 'unknown'),
            dependencies_internal=service.get('dependencies', {}).get('internal', []),
            dependencies_external=service.get('dependencies', {}).get('external', []),
            api_contracts=service.get('api_contracts', []),
            events_produced=service.get('events_out', []),
            events_consumed=service.get('events_in', []),
            quality_score=quality_score,
            risk_level=risk_level
        )

    def _build_domain_context(self) -> Dict[str, DomainContext]:
        """Build domain architecture map."""
        services = self.catalog.get('services', [])
        domains = {}

        # Group services by domain
        for service in services:
            domain = service['domain']
            if domain not in domains:
                domains[domain] = {
                    'services': [],
                    'dependencies': set()
                }
            domains[domain]['services'].append(service['name'])

        # Calculate domain dependencies and risk
        for domain_name, domain_data in domains.items():
            # Find external dependencies for this domain
            external_deps = set()
            for service_name in domain_data['services']:
                service = next(s for s in services if s['name'] == service_name)
                external_deps.update(service.get('dependencies', {}).get('external', []))

            # Determine domain risk level
            domain_services = [s for s in services if s['domain'] == domain_name]
            avg_quality = sum(s.get('quality', {}).get('score', 50) for s in domain_services) / len(domain_services)

            risk_level = "high" if avg_quality < 70 else "medium" if avg_quality < 80 else "low"

            domains[domain_name] = DomainContext(
                name=domain_name,
                services=domain_data['services'],
                description=f"{domain_name.title()} domain services",
                dependencies=list(external_deps),
                risk_level=risk_level
            )

        return {k: v for k, v in domains.items()}

    def _extract_drift_hotspots(self) -> List[str]:
        """Extract services with high drift from drift data."""
        hotspots = []

        # Services with high-severity drift issues
        for issue in self.drift_data.get('issues', []):
            if issue.get('severity') in ['high', 'error']:
                service = issue.get('service')
                if service and service not in hotspots:
                    hotspots.append(service)

        # Services with many drift issues
        issue_counts = {}
        for issue in self.drift_data.get('issues', []):
            service = issue.get('service')
            if service:
                issue_counts[service] = issue_counts.get(service, 0) + 1

        for service, count in issue_counts.items():
            if count >= 3 and service not in hotspots:
                hotspots.append(service)

        return hotspots

    def _generate_risk_cues(self) -> List[RiskCue]:
        """Generate risk assessment hints."""
        cues = []

        # Quality-based risk cues
        services = self.catalog.get('services', [])
        for service in services:
            quality_score = service.get('quality', {}).get('score', 50)

            if quality_score < 60:
                cues.append(RiskCue(
                    service=service['name'],
                    risk_type="quality",
                    severity="high",
                    description=f"Low quality score: {quality_score}/100",
                    recommended_action="Review and improve quality before making changes"
                ))

        # Drift-based risk cues
        for issue in self.drift_data.get('issues', []):
            if issue.get('severity') in ['high', 'error']:
                cues.append(RiskCue(
                    service=issue.get('service', 'unknown'),
                    risk_type="drift",
                    severity=issue.get('severity'),
                    description=issue.get('description', ''),
                    recommended_action="Address drift issues before proceeding"
                ))

        # Dependency-based risk cues
        for service in services:
            internal_deps = service.get('dependencies', {}).get('internal', [])
            if len(internal_deps) > 5:
                cues.append(RiskCue(
                    service=service['name'],
                    risk_type="coupling",
                    severity="medium",
                    description=f"High coupling: depends on {len(internal_deps)} services",
                    recommended_action="Consider reducing dependencies or improving abstraction"
                ))

        return cues

    def _get_safe_operations(self) -> List[str]:
        """Get list of safe operations for agents."""
        return [
            "upgrade_spec_minor",
            "upgrade_spec_patch",
            "add_missing_coverage",
            "fix_lint_issues",
            "update_readme_docs",
            "add_error_handling",
            "improve_logging",
            "add_input_validation"
        ]

    def _get_forbidden_operations(self) -> List[str]:
        """Get list of forbidden operations for agents."""
        return [
            "schema_breaking_changes",
            "major_version_bumps",
            "domain_boundary_changes",
            "dependency_direction_changes",
            "security_policy_changes",
            "database_schema_changes",
            "authentication_changes",
            "authorization_changes"
        ]

    def _get_policy_reminders(self) -> List[str]:
        """Get policy reminders for agents."""
        return [
            "Always run tests before submitting changes",
            "Ensure backward compatibility for minor changes",
            "Document breaking changes clearly",
            "Update related documentation",
            "Consider impact on dependent services",
            "Follow established naming conventions",
            "Include proper error handling",
            "Add logging for debugging"
        ]

    def _get_recent_changes(self) -> List[Dict[str, Any]]:
        """Get recent changes (placeholder for now)."""
        # In a real implementation, this would fetch recent commits,
        # PRs, or deployment history
        return [
            {
                "service": "gateway",
                "type": "spec_upgrade",
                "description": "Upgraded gateway-core to v1.2.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "impact": "low"
            }
        ]

    def _determine_current_focus(self) -> List[str]:
        """Determine current platform focus areas."""
        focus_areas = []

        # Based on drift hotspots
        drift_hotspots = self._extract_drift_hotspots()
        if drift_hotspots:
            focus_areas.append(f"Address drift issues in: {', '.join(drift_hotspots[:3])}")

        # Based on quality issues
        quality_services = self.quality_data.get('services', {})
        low_quality = [name for name, data in quality_services.items() if data.get('score', 100) < 70]
        if low_quality:
            focus_areas.append(f"Improve quality for: {', '.join(low_quality[:3])}")

        # Based on risk cues
        risk_cues = self._generate_risk_cues()
        high_risk = [cue.service for cue in risk_cues if cue.severity == 'high']
        if high_risk:
            focus_areas.append(f"Handle high-risk services: {', '.join(high_risk[:3])}")

        return focus_areas

    def generate_agent_context(self) -> AgentContext:
        """Generate complete AI agent context."""
        logger.info("Generating AI agent context bundle...")

        # Build service contexts
        services = self.catalog.get('services', [])
        service_contexts = {}

        for service in services:
            service_context = self._build_service_context(service)
            service_contexts[service.name] = service_context

        # Build domain contexts
        domain_contexts = self._build_domain_context()

        # Generate risk and focus information
        drift_hotspots = self._extract_drift_hotspots()
        risk_cues = self._generate_risk_cues()
        current_focus = self._determine_current_focus()

        # Create complete context
        context = AgentContext(
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "catalog_version": self.catalog.get('metadata', {}).get('version', '1.0.0'),
                "total_services": len(services),
                "total_domains": len(domain_contexts),
                "context_version": "2.0"
            },
            services=service_contexts,
            domains=domain_contexts,
            drift_hotspots=drift_hotspots,
            risk_cues=risk_cues,
            safe_operations=self._get_safe_operations(),
            forbidden_operations=self._get_forbidden_operations(),
            policy_reminders=self._get_policy_reminders(),
            recent_changes=self._get_recent_changes(),
            current_focus=current_focus
        )

        logger.info(f"Generated context for {len(services)} services across {len(domain_contexts)} domains")
        return context

    def save_agent_context(self, context: AgentContext) -> None:
        """Save agent context to files."""
        # Save main context JSON
        context_file = self.context_dir / "agent-context.json"
        context_dict = asdict(context)

        # Convert dataclasses to dict for JSON serialization
        def convert_dataclasses(obj):
            if hasattr(obj, '__dict__'):
                return {k: convert_dataclasses(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, list):
                return [convert_dataclasses(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: convert_dataclasses(v) for k, v in obj.items()}
            else:
                return obj

        with open(context_file, 'w') as f:
            json.dump(convert_dataclasses(context_dict), f, indent=2)

        logger.info(f"Saved agent context to {context_file}")

        # Generate human-readable guidelines
        self._generate_agent_guidelines(context)

        # Generate task opportunities
        self._generate_task_opportunities(context)

    def _generate_agent_guidelines(self, context: AgentContext) -> None:
        """Generate human-readable agent guidelines."""
        guidelines = f"""# AI Agent Guidelines for 254Carbon Platform

**Generated:** {context.metadata['generated_at']}
**Platform Status:** {len(context.services)} services, {len(context.domains)} domains

## 🎯 Mission
You are an AI coding assistant for the 254Carbon platform. Your goal is to improve code quality, maintainability, and reliability while respecting the established architecture and policies.

## 🏗️ Platform Architecture

### Domains
{chr(10).join(f"- **{domain.name.title()}**: {len(domain.services)} services ({domain.risk_level} risk)")}

### Key Services by Risk
- **High Risk:** {', '.join([s for s, svc in context.services.items() if svc.risk_level == 'high'][:5])}
- **Medium Risk:** {', '.join([s for s, svc in context.services.items() if svc.risk_level == 'medium'][:5])}
- **Low Risk:** {', '.join([s for s, svc in context.services.items() if svc.risk_level == 'low'][:5])}

## ✅ Safe Operations

You can safely perform these operations:

{chr(10).join(f"- {op.replace('_', ' ').title()}" for op in context.safe_operations)}

## ❌ Forbidden Operations

Never perform these operations without human oversight:

{chr(10).join(f"- {op.replace('_', ' ').title()}" for op in context.forbidden_operations)}

## 🚨 Current Focus Areas

{chr(10).join(f"- {focus}" for focus in context.current_focus)}

## 🎯 Drift Hotspots

Services requiring immediate attention:

{chr(10).join(f"- **{service}**: High drift activity" for service in context.drift_hotspots[:10])}

## 📋 Policy Reminders

{chr(10).join(f"- {reminder}" for reminder in context.policy_reminders)}

## 🔍 Risk Assessment

### High-Risk Services
{chr(10).join(f"- **{cue.service}** ({cue.risk_type}): {cue.description}" for cue in context.risk_cues if cue.severity == 'high')}

### Guidelines for Risky Changes
1. **Always start small** - Make minimal changes first
2. **Run comprehensive tests** - Verify all affected services
3. **Document thoroughly** - Explain rationale and impact
4. **Seek review** - Get human approval for significant changes
5. **Monitor closely** - Watch for unexpected side effects

## 🤖 Agent Behavior

### When to Act
- Low-risk improvements (coverage, lint, docs)
- Minor spec upgrades (patch/minor versions)
- Obvious bug fixes with clear reproduction steps

### When to Escalate
- Any breaking changes
- Major version upgrades
- Security-sensitive changes
- Architecture modifications
- High-risk service modifications

### Communication
- Always explain your reasoning
- Document what you're changing and why
- Mention potential side effects
- Suggest testing strategies

---
*Generated by 254Carbon Meta - Context Version {context.metadata['context_version']}*
"""

        guidelines_file = self.context_dir / "agent-guidelines.md"
        with open(guidelines_file, 'w') as f:
            f.write(guidelines)

        logger.info(f"Saved agent guidelines to {guidelines_file}")

    def _generate_task_opportunities(self, context: AgentContext) -> None:
        """Generate task opportunities for agents."""
        opportunities = []

        # Coverage improvement opportunities
        low_coverage = [
            (name, svc) for name, svc in context.services.items()
            if svc.quality_score < 80 and svc.maturity in ['stable', 'beta']
        ]

        for service_name, service in low_coverage[:10]:
            opportunities.append({
                "type": "coverage_improvement",
                "service": service_name,
                "priority": "medium",
                "description": f"Improve test coverage for {service_name} (currently {service.quality_score:.1f})",
                "effort": "low",
                "risk": "low",
                "safe_to_automate": True
            })

        # Drift remediation opportunities
        for hotspot in context.drift_hotspots[:5]:
            opportunities.append({
                "type": "drift_remediation",
                "service": hotspot,
                "priority": "high",
                "description": f"Address drift issues in {hotspot}",
                "effort": "medium",
                "risk": "medium",
                "safe_to_automate": False
            })

        # Spec upgrade opportunities (safe ones only)
        safe_upgrades = [
            op for op in context.safe_operations
            if 'upgrade' in op and 'minor' in op or 'patch' in op
        ]

        if safe_upgrades:
            opportunities.append({
                "type": "spec_upgrade",
                "service": "multiple",
                "priority": "low",
                "description": f"Apply safe spec upgrades: {', '.join(safe_upgrades)}",
                "effort": "low",
                "risk": "low",
                "safe_to_automate": True
            })

        # Generate markdown
        tasks_md = f"""# 🎯 AI Agent Task Opportunities

**Generated:** {context.metadata['generated_at']}
**Total Opportunities:** {len(opportunities)}

## 📋 Available Tasks

| Type | Service | Priority | Description | Effort | Risk | Automation |
|------|---------|----------|-------------|--------|------|------------|
{chr(10).join(f"| {opp['type'].replace('_', ' ').title()} | {opp['service']} | {opp['priority'].title()} | {opp['description']} | {opp['effort'].title()} | {opp['risk'].title()} | {'✅' if opp['safe_to_automate'] else '❌'} |" for opp in opportunities[:20])}

## 🚀 Recommended Starting Points

### Low-Risk, High-Impact (Start Here)
{chr(10).join(f"- **{opp['type'].replace('_', ' ').title()}**: {opp['description']}" for opp in opportunities if opp['risk'] == 'low' and opp['safe_to_automate'][:3])}

### Medium-Risk, Good Impact
{chr(10).join(f"- **{opp['type'].replace('_', ' ').title()}**: {opp['description']}" for opp in opportunities if opp['risk'] == 'medium'[:3])}

### High-Risk (Requires Human Oversight)
{chr(10).join(f"- **{opp['type'].replace('_', ' ').title()}**: {opp['description']}" for opp in opportunities if opp['risk'] == 'high'[:3])}

## 🎯 Task Selection Guidelines

### Choose Tasks That:
- **Align with current focus areas** (see agent-guidelines.md)
- **Have low/medium risk** for autonomous execution
- **Address drift hotspots** when possible
- **Improve overall platform quality**

### Avoid Tasks That:
- **Involve breaking changes** without human approval
- **Affect high-risk services** without oversight
- **Require domain boundary changes**
- **Impact security or authentication**

## 📊 Task Metrics

- **Low Risk Tasks:** {len([o for o in opportunities if o['risk'] == 'low'])}
- **Medium Risk Tasks:** {len([o for o in opportunities if o['risk'] == 'medium'])}
- **High Risk Tasks:** {len([o for o in opportunities if o['risk'] == 'high'])}
- **Automation Safe:** {len([o for o in opportunities if o['safe_to_automate']])}

---
*🤖 Generated by 254Carbon Meta - Prioritized for autonomous execution*
"""

        tasks_file = self.context_dir / "task-opportunities.md"
        with open(tasks_file, 'w') as f:
            f.write(tasks_md)

        logger.info(f"Saved task opportunities to {tasks_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate AI agent context bundle")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--drift-file", type=str, help="Path to drift report file")
    parser.add_argument("--quality-file", type=str, help="Path to quality snapshot file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        generator = AgentContextGenerator(args.catalog_file, args.drift_file, args.quality_file)
        context = generator.generate_agent_context()
        generator.save_agent_context(context)

        logger.info("✅ AI agent context generated successfully")

        # Print summary
        print("\n🤖 AI Agent Context Summary:")
        print(f"  Services: {len(context.services)}")
        print(f"  Domains: {len(context.domains)}")
        print(f"  Drift Hotspots: {len(context.drift_hotspots)}")
        print(f"  Risk Cues: {len(context.risk_cues)}")
        print(f"  Safe Operations: {len(context.safe_operations)}")
        print(f"  Current Focus: {len(context.current_focus)} areas")

    except Exception as e:
        logger.error(f"Agent context generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
