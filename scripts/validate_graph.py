#!/usr/bin/env python3
"""
254Carbon Meta Repository - Dependency Graph Validation Script

Builds a service dependency graph from the catalog and validates it against
architecture rules (directionality, cycles, forbidden patterns, external allowlist).

Usage:
    python scripts/validate_graph.py [--catalog-file FILE] [--rules-file FILE]

Outputs:
- YAML graph (`catalog/dependency-graph.yaml`) and JSON violation report
  (`catalog/dependency-violations.json`) suitable for dashboards and PR comments.
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/graph-validation.log')
    ]
)
logger = logging.getLogger(__name__)


class DependencyType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass
class DependencyEdge:
    """Represents a dependency relationship."""
    from_service: str
    to_service: str
    dep_type: DependencyType
    description: str = ""


@dataclass
class DependencyGraph:
    """Directed graph representation of service dependencies."""
    nodes: Set[str] = field(default_factory=set)
    edges: List[DependencyEdge] = field(default_factory=list)
    adjacency_list: Dict[str, List[str]] = field(default_factory=dict)

    def add_node(self, node: str) -> None:
        """Add a node to the graph.

        Args:
            node: Service name to register in the graph.
        """
        self.nodes.add(node)
        if node not in self.adjacency_list:
            self.adjacency_list[node] = []

    def add_edge(self, from_node: str, to_node: str, dep_type: DependencyType, description: str = "") -> None:
        """Add a directed edge to the graph.

        Args:
            from_node: Source service (dependent).
            to_node: Target service (dependency).
            dep_type: INTERNAL or EXTERNAL dependency.
            description: Optional human-friendly description.
        """
        self.add_node(from_node)
        self.add_node(to_node)

        edge = DependencyEdge(from_node, to_node, dep_type, description)
        self.edges.append(edge)

        if to_node not in self.adjacency_list[from_node]:
            self.adjacency_list[from_node].append(to_node)

    def has_cycle(self) -> Tuple[bool, List[str]]:
        """Check for cycles using DFS.

        Returns:
            Tuple of (has_cycle, cycle_path). `cycle_path` is a best-effort
            list of nodes involved when a cycle is detected.
        """
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in self.adjacency_list.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in self.nodes:
            if node not in visited:
                if dfs(node):
                    # Extract cycle path (simplified)
                    cycle_path = [node]
                    return True, cycle_path

        return False, []

    def get_topological_order(self) -> List[str]:
        """Get topological ordering of nodes.

        Returns:
            A list of nodes in topological order, or an empty list if cycles
            prevent a valid ordering.
        """
        # Kahn's algorithm
        in_degree = {node: 0 for node in self.nodes}

        for node in self.nodes:
            for neighbor in self.adjacency_list.get(node, []):
                in_degree[neighbor] += 1

        queue = [node for node in self.nodes if in_degree[node] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in self.adjacency_list.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            # Cycle detected
            return []

        return result


class GraphValidator:
    """Validates dependency graph and rules."""

    def __init__(self, catalog_file: str = None, rules_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.rules_file = rules_file or "config/rules.yaml"

        # Load catalog
        self.catalog = self._load_catalog()

        # Load rules
        self.rules = self._load_rules()

        # Build dependency graph
        self.graph = self._build_dependency_graph()

    def _find_catalog_file(self, catalog_file: str = None) -> Path:
        """Find catalog file.

        Uses explicit `catalog_file` when provided, otherwise probes standard
        locations under `catalog/`.

        Args:
            catalog_file: Optional explicit path to a catalog file.

        Returns:
            Path to an existing YAML/JSON catalog file.

        Raises:
            FileNotFoundError: When no catalog file can be found.
        """
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
        """Load catalog from file.

        Returns:
            Parsed catalog object from YAML or JSON.
        """
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _load_rules(self) -> Dict[str, Any]:
        """Load validation rules.

        Returns:
            Rules dictionary from `self.rules_file`, or defaults if missing.
        """
        rules_path = Path(self.rules_file)

        if not rules_path.exists():
            logger.warning(f"Rules file not found: {rules_path}, using defaults")
            return self._get_default_rules()

        with open(rules_path) as f:
            return yaml.safe_load(f)

    def _get_default_rules(self) -> Dict[str, Any]:
        """Get default validation rules.

        Returns:
            Minimal rule set used when `rules_file` is not present.
        """
        return {
            "dependency": {
                "enforce_directionality": True,
                "forbid_cycles": True,
                "allowed_external": [
                    "redis", "clickhouse", "postgresql", "mongodb",
                    "elasticsearch", "kafka", "rabbitmq", "nginx"
                ]
            },
            "forbidden_reverse_edges": [
                {"pattern": "access -> data-processing"},
                {"pattern": "shared -> domain-specific"}
            ]
        }

    def _build_dependency_graph(self) -> DependencyGraph:
        """Build dependency graph from catalog.

        Returns:
            A `DependencyGraph` containing nodes and edges for internal deps.
        """
        logger.info("Building dependency graph...")
        graph = DependencyGraph()

        services = self.catalog.get('services', [])

        # Add all services as nodes
        for service in services:
            graph.add_node(service['name'])

        # Add dependency edges
        for service in services:
            service_name = service['name']
            dependencies = service.get('dependencies', {})

            # Internal dependencies
            internal_deps = dependencies.get('internal', [])
            for dep in internal_deps:
                if dep in graph.nodes:
                    graph.add_edge(service_name, dep, DependencyType.INTERNAL,
                                 f"{service_name} depends on {dep}")

            # External dependencies
            external_deps = dependencies.get('external', [])
            for dep in external_deps:
                graph.add_edge(service_name, dep, DependencyType.EXTERNAL,
                             f"{service_name} depends on external {dep}")

        logger.info(f"Built graph with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        return graph

    def validate_cycles(self) -> List[Dict[str, Any]]:
        """Check for dependency cycles.

        Returns:
            List with a single violation when cycles are detected, otherwise empty.
        """
        logger.info("Checking for dependency cycles...")

        has_cycle, cycle_path = self.graph.has_cycle()
        violations = []

        if has_cycle:
            violation = {
                "type": "cycle_detected",
                "severity": "error",
                "description": "Circular dependency detected in service graph",
                "details": {
                    "cycle_path": cycle_path,
                    "affected_services": list(self.graph.nodes)
                }
            }
            violations.append(violation)
            logger.error(f"Cycle detected: {' -> '.join(cycle_path)}")

        return violations

    def validate_external_dependencies(self) -> List[Dict[str, Any]]:
        """Validate external dependencies against whitelist.

        Returns:
            Violations for external dependencies not present in the allowlist.
        """
        logger.info("Validating external dependencies...")

        allowed_external = self.rules.get("dependency", {}).get("allowed_external", [])
        violations = []

        for edge in self.graph.edges:
            if edge.dep_type == DependencyType.EXTERNAL:
                if edge.to_service not in allowed_external:
                    violation = {
                        "type": "unauthorized_external_dependency",
                        "severity": "warning",
                        "description": f"External dependency not in allowed list: {edge.to_service}",
                        "details": {
                            "service": edge.from_service,
                            "dependency": edge.to_service,
                            "allowed_external": allowed_external
                        }
                    }
                    violations.append(violation)
                    logger.warning(f"Unauthorized external dependency: {edge.from_service} -> {edge.to_service}")

        return violations

    def validate_directionality(self) -> List[Dict[str, Any]]:
        """Validate directional cohesion rules.

        Returns:
            Violations for edges that go from a lower to a higher domain layer.
        """
        logger.info("Validating directional cohesion...")

        violations = []
        domain_layers_cfg = self.rules.get("dependency", {}).get("domain_layers", {})
        if isinstance(domain_layers_cfg, dict) and domain_layers_cfg:
            domain_layers = {str(domain): int(level) for domain, level in domain_layers_cfg.items()}
        else:
            domain_layers = {
                "infrastructure": 1,
                "shared": 2,
                "access": 3,
                "ingestion": 4,
                "data-processing": 5,
                "analytics": 6,
                "ml": 7,
                "observability": 8,
                "security": 9,
            }

        services = self.catalog.get('services', [])
        service_domains = {s['name']: s.get('domain') for s in services}

        for edge in self.graph.edges:
            if edge.dep_type == DependencyType.INTERNAL:
                from_domain = service_domains.get(edge.from_service)
                to_domain = service_domains.get(edge.to_service)

                if from_domain and to_domain:
                    from_layer = domain_layers.get(from_domain, 0)
                    to_layer = domain_layers.get(to_domain, 0)

                    # Check if higher layer depends on lower layer (should not happen)
                    if from_layer > 0 and to_layer > 0 and from_layer < to_layer:
                        violation = {
                            "type": "directional_violation",
                            "severity": "error",
                            "description": f"Reverse dependency: {from_domain} -> {to_domain}",
                            "details": {
                                "from_service": edge.from_service,
                                "to_service": edge.to_service,
                                "from_domain": from_domain,
                                "to_domain": to_domain
                            }
                        }
                        violations.append(violation)
                        logger.error(f"Directional violation: {edge.from_service} ({from_domain}) -> {edge.to_service} ({to_domain})")

        return violations

    def validate_forbidden_patterns(self) -> List[Dict[str, Any]]:
        """Validate against forbidden edge patterns.

        Returns:
            Violations for edges whose domain pairing matches configured
            `forbidden_reverse_edges` patterns.
        """
        logger.info("Validating against forbidden patterns...")

        forbidden_patterns = self.rules.get("forbidden_reverse_edges", [])
        violations = []

        for pattern in forbidden_patterns:
            pattern_str = pattern.get("pattern", "")

            for edge in self.graph.edges:
                if edge.dep_type == DependencyType.INTERNAL:
                    services = self.catalog.get('services', [])
                    from_domain = next((s.get('domain') for s in services if s['name'] == edge.from_service), None)
                    to_domain = next((s.get('domain') for s in services if s['name'] == edge.to_service), None)

                    if from_domain and to_domain:
                        edge_pattern = f"{from_domain} -> {to_domain}"
                        if edge_pattern == pattern_str:
                            violation = {
                                "type": "forbidden_pattern",
                                "severity": "error",
                                "description": f"Forbidden dependency pattern: {pattern_str}",
                                "details": {
                                    "pattern": pattern_str,
                                    "from_service": edge.from_service,
                                    "to_service": edge.to_service,
                                    "from_domain": from_domain,
                                    "to_domain": to_domain
                                }
                            }
                            violations.append(violation)
                            logger.error(f"Forbidden pattern: {edge.from_service} -> {edge.to_service} ({edge_pattern})")

        return violations

    def generate_dependency_graph_yaml(self) -> Dict[str, Any]:
        """Generate dependency graph YAML.

        Returns:
            A dictionary describing nodes grouped by domain and internal edges,
            suitable for serialization to YAML.
        """
        services = self.catalog.get('services', [])
        service_domains = {s['name']: s.get('domain') for s in services}

        # Group nodes by domain
        nodes_by_domain = {}
        for service in services:
            domain = service.get('domain', 'unknown')
            if domain not in nodes_by_domain:
                nodes_by_domain[domain] = []
            nodes_by_domain[domain].append(service['name'])

        # Build edges
        edges = []
        for edge in self.graph.edges:
            if edge.dep_type == DependencyType.INTERNAL:
                edges.append({
                    "from": edge.from_service,
                    "to": edge.to_service
                })

        # Generate graph YAML
        graph_yaml = {
            "metadata": {
                "generated_at": self.catalog.get('metadata', {}).get('generated_at'),
                "total_nodes": len(self.graph.nodes),
                "total_edges": len([e for e in self.graph.edges if e.dep_type == DependencyType.INTERNAL])
            },
            "nodes": nodes_by_domain,
            "edges": edges,
            "rules": self.rules
        }

        return graph_yaml

    def run_validation(self) -> Dict[str, Any]:
        """Run all validations and generate report.

        Returns:
            A report dictionary with metadata, violations, and summary stats.
        """
        logger.info("Running dependency graph validation...")

        violations = []

        # Run all validation checks
        validations = [
            ("cycles", self.validate_cycles),
            ("external_deps", self.validate_external_dependencies),
            ("directionality", self.validate_directionality),
            ("forbidden_patterns", self.validate_forbidden_patterns)
        ]

        for name, validation_func in validations:
            try:
                result = validation_func()
                violations.extend(result)
            except Exception as e:
                logger.error(f"Validation '{name}' failed: {e}")
                violations.append({
                    "type": "validation_error",
                    "severity": "error",
                    "description": f"Validation '{name}' failed: {e}",
                    "details": {}
                })

        # Generate outputs
        report = {
            "metadata": {
                "generated_at": self.catalog.get('metadata', {}).get('generated_at'),
                "catalog_services": len(self.catalog.get('services', [])),
                "graph_nodes": len(self.graph.nodes),
                "graph_edges": len([e for e in self.graph.edges if e.dep_type == DependencyType.INTERNAL]),
                "total_violations": len(violations)
            },
            "violations": violations,
            "summary": {
                "errors": len([v for v in violations if v.get('severity') == 'error']),
                "warnings": len([v for v in violations if v.get('severity') == 'warning']),
                "passed": len(violations) == 0
            }
        }

        # Save outputs
        self._save_outputs(report)

        # Log summary
        if report['summary']['passed']:
            logger.info("✓ All dependency validations passed")
        else:
            logger.error(f"✗ Found {len(violations)} violations ({report['summary']['errors']} errors, {report['summary']['warnings']} warnings)")

        return report

    def _save_outputs(self, report: Dict[str, Any]) -> None:
        """Save validation outputs to files.

        Args:
            report: Completed validation report to persist.
        """
        catalog_dir = Path("catalog")

        # Save dependency graph YAML
        graph_yaml = self.generate_dependency_graph_yaml()
        graph_file = catalog_dir / "dependency-graph.yaml"
        with open(graph_file, 'w') as f:
            yaml.dump(graph_yaml, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved dependency graph to {graph_file}")

        # Save violations report
        violations_file = catalog_dir / "dependency-violations.json"
        with open(violations_file, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Saved violations report to {violations_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate dependency graph and relationships")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--rules-file", type=str, help="Path to rules file (default: config/rules.yaml)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        validator = GraphValidator(args.catalog_file, args.rules_file)
        report = validator.run_validation()

        # Exit with error code if there are errors
        if report['summary']['errors'] > 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Graph validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
