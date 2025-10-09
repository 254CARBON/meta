#!/usr/bin/env python3
"""
254Carbon Meta Repository - Unified CLI Interface

Provides a single command-line interface for all meta operations, delegating to
scripts for catalog build/validation, quality, drift, upgrades, release planning,
impact analysis, architecture suggestions, and more.

Usage:
    python scripts/meta_cli.py catalog build
    python scripts/meta_cli.py quality compute
    python scripts/meta_cli.py quality refresh-overrides
    python scripts/meta_cli.py drift detect
    python scripts/meta_cli.py upgrade plan --service gateway
    python scripts/meta_cli.py release plan --train Q4-upgrade
    python scripts/meta_cli.py impact analyze --pr 123
    python scripts/meta_cli.py architecture suggest
    python scripts/meta_cli.py registry events

Notes:
- Thin wrapper around individual scripts with a consistent UX and basic logging.
- Useful for local workflows and CI steps where one entrypoint is preferred.
"""

import os
import sys
import json
import yaml
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetaCLI:
    """Unified CLI for 254Carbon Meta operations."""

    def __init__(self):
        self.scripts_dir = Path(__file__).parent
        self.project_root = self.scripts_dir.parent

    def run_catalog_build(self, args: argparse.Namespace) -> None:
        """Build service catalog.

        Args:
            args: Parsed CLI args with flags: validate_only, force, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "build_catalog.py")]

        if args.validate_only:
            cmd.append("--validate-only")
        if args.force:
            cmd.append("--force")
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Catalog build")

    def run_quality_compute(self, args: argparse.Namespace) -> None:
        """Compute quality scores.

        Args:
            args: Parsed CLI args with optional catalog_file, thresholds_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "compute_quality.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.thresholds_file:
            cmd.extend(["--thresholds-file", args.thresholds_file])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Quality computation")

    def run_quality_refresh_overrides(self, args: argparse.Namespace) -> None:
        """Refresh quality overrides from CI artifacts.

        Args:
            args: Parsed CLI args with optional coverage_file, output_file, dry_run, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "update_quality_overrides.py")]

        if args.coverage_file:
            cmd.extend(["--coverage-file", args.coverage_file])
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.dry_run:
            cmd.append("--dry-run")
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Quality overrides refresh")

    def run_drift_detect(self, args: argparse.Namespace) -> None:
        """Detect drift issues.

        Args:
            args: Parsed CLI args with optional catalog_file, specs_repo, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "detect_drift.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.specs_repo:
            cmd.extend(["--specs-repo", args.specs_repo])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Drift detection")

    def run_upgrade_plan(self, args: argparse.Namespace) -> None:
        """Plan specification upgrades.

        Args:
            args: Parsed CLI args with flags: dry_run, auto_upgrade, catalog_file,
                  specs_repo, upgrade_policies, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "spec_version_check.py")]

        if args.dry_run:
            cmd.append("--dry-run")
        if args.auto_upgrade:
            cmd.append("--auto-upgrade")
        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.specs_repo:
            cmd.extend(["--specs-repo", args.specs_repo])
        if args.upgrade_policies:
            cmd.extend(["--upgrade-policies", args.upgrade_policies])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Upgrade planning")

    def run_release_plan(self, args: argparse.Namespace) -> None:
        """Plan release train execution.

        Args:
            args: Parsed CLI args with --train, optional dry_run, output_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "plan_release_train.py")]

        if args.dry_run:
            cmd.append("--dry-run")
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.debug:
            cmd.append("--debug")

        # Add required train argument
        cmd.extend(["--train", args.train])

        self._run_command(cmd, "Release train planning")

    def run_impact_analyze(self, args: argparse.Namespace) -> None:
        """Analyze change impact.

        Args:
            args: Parsed CLI args with pr, optional github_token, catalog_file,
                  output_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "analyze_impact.py")]

        if args.github_token:
            cmd.extend(["--github-token", args.github_token])
        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.debug:
            cmd.append("--debug")

        # Add required PR argument
        cmd.extend(["--pr", str(args.pr)])

        self._run_command(cmd, "Impact analysis")

    def run_architecture_suggest(self, args: argparse.Namespace) -> None:
        """Analyze architecture and suggest improvements.

        Args:
            args: Parsed CLI args with optional catalog_file, output_format, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "analyze_architecture.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.output_format:
            cmd.extend(["--output-format", args.output_format])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Architecture analysis")

    def run_observability_ingest(self, args: argparse.Namespace) -> None:
        """Ingest observability data.

        Args:
            args: Parsed CLI args with system, config_file, service, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "ingest_observability.py")]

        if args.system:
            cmd.extend(["--system", args.system])
        if args.config_file:
            cmd.extend(["--config-file", args.config_file])
        if args.service:
            cmd.extend(["--service", args.service])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Observability ingestion")

    def run_risk_assess(self, args: argparse.Namespace) -> None:
        """Assess service risk.

        Args:
            args: Parsed CLI args with service, change_type, change_scope,
                  catalog_file, drift_file, quality_file, output_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "assess_risk.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.drift_file:
            cmd.extend(["--drift-file", args.drift_file])
        if args.quality_file:
            cmd.extend(["--quality-file", args.quality_file])
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.debug:
            cmd.append("--debug")

        # Add required arguments
        cmd.extend(["--service", args.service])
        if args.change_type:
            cmd.extend(["--change-type", args.change_type])
        if args.change_scope:
            cmd.extend(["--change-scope", args.change_scope])

        self._run_command(cmd, "Risk assessment")

    def run_agent_context_generate(self, args: argparse.Namespace) -> None:
        """Generate AI agent context.

        Args:
            args: Parsed CLI args with optional catalog_file, drift_file,
                  quality_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "generate_agent_context.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.drift_file:
            cmd.extend(["--drift-file", args.drift_file])
        if args.quality_file:
            cmd.extend(["--quality-file", args.quality_file])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "AI agent context generation")

    def run_report_render(self, args: argparse.Namespace) -> None:
        """Render reports.

        Args:
            args: Parsed CLI args with report_type, input_file, optional output_file,
                  templates_dir, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "render_report.py")]

        if args.report_type:
            cmd.extend(["--report-type", args.report_type])
        if args.input_file:
            cmd.extend(["--input-file", args.input_file])
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.templates_dir:
            cmd.extend(["--templates-dir", args.templates_dir])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Report rendering")

    def run_validate_catalog(self, args: argparse.Namespace) -> None:
        """Validate catalog.

        Args:
            args: Parsed CLI args with optional catalog_file, strict, report, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "validate_catalog.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.strict:
            cmd.append("--strict")
        if args.report:
            cmd.append("--report")
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Catalog validation")

    def run_graph_validate(self, args: argparse.Namespace) -> None:
        """Validate dependency graph.

        Args:
            args: Parsed CLI args with optional catalog_file, rules_file, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "validate_graph.py")]

        if args.catalog_file:
            cmd.extend(["--catalog-file", args.catalog_file])
        if args.rules_file:
            cmd.extend(["--rules-file", args.rules_file])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Dependency graph validation")

    def run_collect_manifests(self, args: argparse.Namespace) -> None:
        """Collect service manifests.

        Args:
            args: Parsed CLI args with dry_run, repo_filter, org, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "collect_manifests.py")]

        if args.dry_run:
            cmd.append("--dry-run")
        if args.repo_filter:
            cmd.extend(["--repo-filter", args.repo_filter])
        if args.org:
            cmd.extend(["--org", args.org])
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Manifest collection")

    def run_collect_local_manifests(self, args: argparse.Namespace) -> None:
        """Aggregate manifests from the local workspace.

        Args:
            args: Parsed CLI args with optional workspace_root, output_dir, and dry_run flags.
        """
        cmd = [sys.executable, str(self.scripts_dir / "aggregate_local_manifests.py")]

        if args.workspace_root:
            cmd.extend(["--workspace-root", args.workspace_root])
        if args.output_dir:
            cmd.extend(["--output-dir", args.output_dir])
        if args.dry_run:
            cmd.append("--dry-run")

        self._run_command(cmd, "Local manifest aggregation")

    def run_registry_events(self, args: argparse.Namespace) -> None:
        """Generate events registry from specs repository.

        Args:
            args: Parsed CLI args with optional specs_root, output_file, dry_run, debug.
        """
        cmd = [sys.executable, str(self.scripts_dir / "generate_event_registry.py")]

        if args.specs_root:
            cmd.extend(["--specs-root", args.specs_root])
        if args.output_file:
            cmd.extend(["--output-file", args.output_file])
        if args.dry_run:
            cmd.append("--dry-run")
        if args.debug:
            cmd.append("--debug")

        self._run_command(cmd, "Event registry generation")

    def _run_command(self, cmd: List[str], operation_name: str) -> None:
        """Run a subprocess command.

        Args:
            cmd: Full command list (argv) to execute.
            operation_name: Friendly name for logging and error messages.
        """
        logger.info(f"Running {operation_name}: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False  # Don't raise on non-zero exit
            )

            # Print stdout
            if result.stdout:
                print(result.stdout)

            # Print stderr as warnings
            if result.stderr:
                print(f"Warning: {result.stderr}", file=sys.stderr)

            if result.returncode != 0:
                logger.error(f"{operation_name} failed with exit code {result.returncode}")
                sys.exit(result.returncode)

        except FileNotFoundError:
            logger.error(f"Script not found: {cmd[1]}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error running {operation_name}: {e}")
            sys.exit(1)

    def show_status(self, args: argparse.Namespace) -> None:
        """Show platform status.

        Args:
            args: Parsed CLI args (unused).
        """
        print("📊 254Carbon Meta Platform Status")
        print("=" * 50)

        # Check if catalog exists
        catalog_path = Path("catalog/service-index.yaml")
        if catalog_path.exists():
            print("✅ Service Catalog: Available")
            with open(catalog_path) as f:
                catalog = yaml.safe_load(f)
            services_count = len(catalog.get('services', []))
            print(f"   Services: {services_count}")
        else:
            print("❌ Service Catalog: Missing")
            print("   Run: meta catalog build")

        # Check quality snapshot
        quality_path = Path("catalog/latest_quality_snapshot.json")
        if quality_path.exists():
            print("✅ Quality Metrics: Available")
            with open(quality_path) as f:
                quality = json.load(f)
            avg_score = quality.get('global', {}).get('avg_score', 0)
            print(f"   Average Score: {avg_score:.1f}/100")
        else:
            print("❌ Quality Metrics: Missing")
            print("   Run: meta quality compute")

        # Check drift report
        drift_path = Path("catalog/latest_drift_report.json")
        if drift_path.exists():
            print("✅ Drift Analysis: Available")
            with open(drift_path) as f:
                drift = json.load(f)
            total_issues = drift.get('metadata', {}).get('total_issues', 0)
            print(f"   Issues: {total_issues}")
        else:
            print("❌ Drift Analysis: Missing")
            print("   Run: meta drift detect")

        # Check AI context
        context_path = Path("ai/global-context/agent-context.json")
        if context_path.exists():
            print("✅ AI Agent Context: Available")
        else:
            print("❌ AI Agent Context: Missing")
            print("   Run: meta agent-context generate")

        # Check architecture analysis
        arch_path = Path("analysis/reports/architecture/latest_architecture_health.json")
        if arch_path.exists():
            print("✅ Architecture Analysis: Available")
            with open(arch_path) as f:
                arch = json.load(f)
            score = arch.get('overall_health', {}).get('score', 0)
            print(f"   Health Score: {score}/100")
        else:
            print("❌ Architecture Analysis: Missing")
            print("   Run: meta architecture suggest")

        print("\n🎯 Quick Actions:")
        print("  meta catalog build      - Build service catalog")
        print("  meta quality compute    - Compute quality scores")
        print("  meta quality refresh-overrides - Regenerate quality overrides from CI")
        print("  meta drift detect       - Detect drift issues")
        print("  meta upgrade plan       - Check for upgrades")
        print("  meta architecture suggest - Analyze architecture")
        print("  meta registry events    - Sync event registry with specs")

    def show_help(self) -> None:
        """Show comprehensive help."""
        print("254Carbon Meta CLI - Platform Governance Tool")
        print("=" * 50)
        print()
        print("Available Commands:")
        print()
        print("📋 CATALOG OPERATIONS")
        print("  catalog build           Build service catalog from manifests")
        print("  catalog validate        Validate catalog integrity")
        print("  collect manifests       Collect manifests from repositories")
        print("  collect local           Aggregate manifests from local workspace")
        print()
        print("📊 QUALITY OPERATIONS")
        print("  quality compute         Compute quality scores for all services")
        print("  quality refresh-overrides Regenerate overrides from CI artifacts")
        print("  quality report          Generate quality dashboard report")
        print()
        print("🔍 DRIFT OPERATIONS")
        print("  drift detect            Detect version and spec drift")
        print("  drift report            Generate drift analysis report")
        print()
        print("📚 REGISTRY")
        print("  registry events         Generate events registry from specs")
        print()
        print("⬆️ UPGRADE OPERATIONS")
        print("  upgrade plan            Plan specification upgrades")
        print("  upgrade generate        Generate upgrade PRs")
        print()
        print("🚂 RELEASE OPERATIONS")
        print("  release plan            Plan release train execution")
        print("  release execute         Execute release train")
        print()
        print("🤖 AI OPERATIONS")
        print("  agent-context generate  Generate AI agent context bundle")
        print("  risk assess             Assess service risk levels")
        print()
        print("🔗 OBSERVABILITY")
        print("  observability ingest    Ingest SLA/SLO metrics")
        print()
        print("🔍 IMPACT ANALYSIS")
        print("  impact analyze          Analyze change impact across services")
        print()
        print("🏗️ ARCHITECTURE")
        print("  architecture suggest    Analyze architecture and suggest improvements")
        print()
        print("📈 REPORTING")
        print("  report render           Render reports using templates")
        print()
        print("📊 PLATFORM STATUS")
        print("  status                  Show platform health status")
        print()
        print("Examples:")
        print("  meta catalog build")
        print("  meta quality compute")
        print("  meta drift detect")
        print("  meta upgrade plan --service gateway")
        print("  meta release plan --train Q4-upgrade")
        print("  meta impact analyze --pr 123")
        print("  meta architecture suggest")


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the main argument parser.

    Returns:
        Configured `argparse.ArgumentParser` with subcommands wired to meta operations.

    Notes:
        Uses RawDescriptionHelpFormatter for multiline epilog examples.
        Subparsers are grouped by domain (catalog, quality, drift, upgrade, etc.).
    """
    parser = argparse.ArgumentParser(
        prog='meta',
        description='254Carbon Meta Repository CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  meta catalog build
  meta quality compute
  meta drift detect
  meta upgrade plan --service gateway
  meta release plan --train Q4-upgrade
  meta impact analyze --pr 123
  meta architecture suggest
        """
    )

    # Global options
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Catalog commands
    catalog_parser = subparsers.add_parser('catalog', help='Catalog operations')
    catalog_subparsers = catalog_parser.add_subparsers(dest='subcommand')

    build_parser = catalog_subparsers.add_parser('build', help='Build service catalog')
    build_parser.add_argument("--validate-only", action="store_true", help="Only validate, don't save")
    build_parser.add_argument("--force", action="store_true", help="Continue despite errors")

    validate_parser = catalog_subparsers.add_parser('validate', help='Validate catalog')
    validate_parser.add_argument("--catalog-file", help="Catalog file to validate")
    validate_parser.add_argument("--strict", action="store_true", help="Strict validation")
    validate_parser.add_argument("--report", action="store_true", help="Generate validation report")

    # Quality commands
    quality_parser = subparsers.add_parser('quality', help='Quality operations')
    quality_subparsers = quality_parser.add_subparsers(dest='subcommand')

    compute_parser = quality_subparsers.add_parser('compute', help='Compute quality scores')
    compute_parser.add_argument("--catalog-file", help="Catalog file to use")
    compute_parser.add_argument("--thresholds-file", help="Thresholds configuration file")

    refresh_parser = quality_subparsers.add_parser('refresh-overrides', help='Regenerate quality overrides from CI results')
    refresh_parser.add_argument("--coverage-file", help="Coverage summary file")
    refresh_parser.add_argument("--output-file", help="Output overrides file")
    refresh_parser.add_argument("--dry-run", action="store_true", help="Print overrides without writing")

    # Drift commands
    drift_parser = subparsers.add_parser('drift', help='Drift detection operations')
    drift_subparsers = drift_parser.add_subparsers(dest='subcommand')

    detect_parser = drift_subparsers.add_parser('detect', help='Detect drift issues')
    detect_parser.add_argument("--catalog-file", help="Catalog file to use")
    detect_parser.add_argument("--specs-repo", default="254carbon/254carbon-specs", help="Specs repository")

    # Upgrade commands
    upgrade_parser = subparsers.add_parser('upgrade', help='Upgrade operations')
    upgrade_subparsers = upgrade_parser.add_subparsers(dest='subcommand')

    plan_parser = upgrade_subparsers.add_parser('plan', help='Plan upgrades')
    plan_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    plan_parser.add_argument("--auto-upgrade", action="store_true", help="Auto-generate PRs")
    plan_parser.add_argument("--catalog-file", help="Catalog file to use")
    plan_parser.add_argument("--specs-repo", default="254carbon/254carbon-specs", help="Specs repository")
    plan_parser.add_argument("--upgrade-policies", help="Upgrade policies file")

    generate_parser = upgrade_subparsers.add_parser('generate', help='Generate upgrade PRs')
    generate_parser.add_argument("--service", required=True, help="Service to upgrade")
    generate_parser.add_argument("--spec-version", required=True, help="Spec version to upgrade to")
    generate_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    generate_parser.add_argument("--github-token", help="GitHub token")

    # Release commands
    release_parser = subparsers.add_parser('release', help='Release train operations')
    release_subparsers = release_parser.add_subparsers(dest='subcommand')

    plan_release_parser = release_subparsers.add_parser('plan', help='Plan release train')
    plan_release_parser.add_argument("--train", required=True, help="Release train name")
    plan_release_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    plan_release_parser.add_argument("--output-file", help="Output file for plan")

    # Impact analysis commands
    impact_parser = subparsers.add_parser('impact', help='Impact analysis operations')
    impact_subparsers = impact_parser.add_subparsers(dest='subcommand')

    analyze_parser = impact_subparsers.add_parser('analyze', help='Analyze change impact')
    analyze_parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    analyze_parser.add_argument("--github-token", help="GitHub token")
    analyze_parser.add_argument("--catalog-file", help="Catalog file to use")
    analyze_parser.add_argument("--output-file", help="Output file for report")

    # Architecture commands
    architecture_parser = subparsers.add_parser('architecture', help='Architecture operations')
    architecture_subparsers = architecture_parser.add_subparsers(dest='subcommand')

    suggest_parser = architecture_subparsers.add_parser('suggest', help='Suggest architecture improvements')
    suggest_parser.add_argument("--catalog-file", help="Catalog file to use")
    suggest_parser.add_argument("--output-format", choices=["json", "markdown"], default="markdown")

    # Registry commands
    registry_parser = subparsers.add_parser('registry', help='Registry maintenance operations')
    registry_subparsers = registry_parser.add_subparsers(dest='subcommand')

    events_registry_parser = registry_subparsers.add_parser('events', help='Generate events registry from specs')
    events_registry_parser.add_argument("--specs-root", help="Path to specs repository")
    events_registry_parser.add_argument("--output-file", help="Output file for registry")
    events_registry_parser.add_argument("--dry-run", action="store_true", help="Preview registry without writing")

    # AI agent commands
    agent_parser = subparsers.add_parser('agent-context', help='AI agent operations')
    agent_subparsers = agent_parser.add_subparsers(dest='subcommand')

    generate_parser = agent_subparsers.add_parser('generate', help='Generate AI agent context')
    generate_parser.add_argument("--catalog-file", help="Catalog file to use")
    generate_parser.add_argument("--drift-file", help="Drift report file")
    generate_parser.add_argument("--quality-file", help="Quality snapshot file")

    # Risk assessment commands
    risk_parser = subparsers.add_parser('risk', help='Risk assessment operations')
    risk_subparsers = risk_parser.add_subparsers(dest='subcommand')

    assess_parser = risk_subparsers.add_parser('assess', help='Assess service risk')
    assess_parser.add_argument("--service", required=True, help="Service to assess")
    assess_parser.add_argument("--change-type", help="Type of change being assessed")
    assess_parser.add_argument("--change-scope", choices=["minor", "medium", "major"], default="minor")
    assess_parser.add_argument("--catalog-file", help="Catalog file to use")
    assess_parser.add_argument("--drift-file", help="Drift report file")
    assess_parser.add_argument("--quality-file", help="Quality snapshot file")
    assess_parser.add_argument("--output-file", help="Output file for report")

    # Observability commands
    observability_parser = subparsers.add_parser('observability', help='Observability operations')
    observability_subparsers = observability_parser.add_subparsers(dest='subcommand')

    ingest_parser = observability_subparsers.add_parser('ingest', help='Ingest observability data')
    ingest_parser.add_argument("--system", choices=["prometheus", "datadog"], default="prometheus")
    ingest_parser.add_argument("--config-file", help="Observability config file")
    ingest_parser.add_argument("--service", help="Specific service to collect metrics for")

    # Reporting commands
    report_parser = subparsers.add_parser('report', help='Report generation operations')
    report_subparsers = report_parser.add_subparsers(dest='subcommand')

    render_parser = report_subparsers.add_parser('render', help='Render reports')
    render_parser.add_argument("--report-type", required=True, choices=['drift', 'dependency', 'catalog', 'quality'])
    render_parser.add_argument("--input-file", required=True, help="Input report file")
    render_parser.add_argument("--output-file", help="Output markdown file")
    render_parser.add_argument("--templates-dir", default="analysis/templates")

    # Utility commands
    subparsers.add_parser('status', help='Show platform status')

    # Graph validation commands
    graph_parser = subparsers.add_parser('graph', help='Dependency graph operations')
    graph_subparsers = graph_parser.add_subparsers(dest='subcommand')

    validate_graph_parser = graph_subparsers.add_parser('validate', help='Validate dependency graph')
    validate_graph_parser.add_argument("--catalog-file", help="Catalog file to use")
    validate_graph_parser.add_argument("--rules-file", default="config/rules.yaml")

    # Collect manifests commands
    collect_parser = subparsers.add_parser('collect', help='Manifest collection operations')
    collect_subparsers = collect_parser.add_subparsers(dest='subcommand')

    manifests_parser = collect_subparsers.add_parser('manifests', help='Collect service manifests')
    manifests_parser.add_argument("--dry-run", action="store_true")
    manifests_parser.add_argument("--repo-filter", help="Repository name filter")
    manifests_parser.add_argument("--org", default="254carbon")

    local_collect_parser = collect_subparsers.add_parser('local', help='Aggregate local workspace manifests')
    local_collect_parser.add_argument("--workspace-root", help="Workspace root to scan (defaults to repo root)")
    local_collect_parser.add_argument("--output-dir", help="Output directory for normalized manifests")
    local_collect_parser.add_argument("--dry-run", action="store_true", help="Collect without writing files")

    return parser


def main():
    """Main CLI entry point.

    Parses command line arguments and dispatches to the appropriate MetaCLI
    method. Handles basic debug/verbosity and prints friendly help when
    commands or subcommands are omitted.
    """
    parser = create_argument_parser()
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    else:
        # Reduce logging for cleaner output
        logging.getLogger().setLevel(logging.WARNING)

    # Handle commands
    cli = MetaCLI()

    try:
        if args.command == 'catalog':
            if args.subcommand == 'build':
                cli.run_catalog_build(args)
            elif args.subcommand == 'validate':
                cli.run_validate_catalog(args)
            else:
                parser.print_help()
        elif args.command == 'quality':
            if args.subcommand == 'compute':
                cli.run_quality_compute(args)
            elif args.subcommand == 'refresh-overrides':
                cli.run_quality_refresh_overrides(args)
            else:
                parser.print_help()
        elif args.command == 'drift':
            if args.subcommand == 'detect':
                cli.run_drift_detect(args)
            else:
                parser.print_help()
        elif args.command == 'upgrade':
            if args.subcommand == 'plan':
                cli.run_upgrade_plan(args)
            elif args.subcommand == 'generate':
                cli.run_upgrade_plan(args)  # Use same script for now
            else:
                parser.print_help()
        elif args.command == 'release':
            if args.subcommand == 'plan':
                cli.run_release_plan(args)
            else:
                parser.print_help()
        elif args.command == 'impact':
            if args.subcommand == 'analyze':
                cli.run_impact_analyze(args)
            else:
                parser.print_help()
        elif args.command == 'architecture':
            if args.subcommand == 'suggest':
                cli.run_architecture_suggest(args)
            else:
                parser.print_help()
        elif args.command == 'agent-context':
            if args.subcommand == 'generate':
                cli.run_agent_context_generate(args)
            else:
                parser.print_help()
        elif args.command == 'risk':
            if args.subcommand == 'assess':
                cli.run_risk_assess(args)
            else:
                parser.print_help()
        elif args.command == 'observability':
            if args.subcommand == 'ingest':
                cli.run_observability_ingest(args)
            else:
                parser.print_help()
        elif args.command == 'report':
            if args.subcommand == 'render':
                cli.run_report_render(args)
            else:
                parser.print_help()
        elif args.command == 'graph':
            if args.subcommand == 'validate':
                cli.run_graph_validate(args)
            else:
                parser.print_help()
        elif args.command == 'registry':
            if args.subcommand == 'events':
                cli.run_registry_events(args)
            else:
                parser.print_help()
        elif args.command == 'collect':
            if args.subcommand == 'manifests':
                cli.run_collect_manifests(args)
            elif args.subcommand == 'local':
                cli.run_collect_local_manifests(args)
            else:
                parser.print_help()
        elif args.command == 'status':
            cli.show_status(args)
        else:
            cli.show_help()

    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"CLI operation failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
