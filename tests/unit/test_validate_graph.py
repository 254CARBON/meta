#!/usr/bin/env python3
"""
Unit tests for validate_graph.py - Dependency graph validation functionality.

Tests cover:
- DependencyGraph: cycle detection, topological sorting, edge management
- GraphValidator: all validation methods, file loading, rule application
- Integration scenarios with realistic catalog data
"""

import unittest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import the classes we want to test
from scripts.validate_graph import (
    DependencyType,
    DependencyEdge,
    DependencyGraph,
    GraphValidator
)


class TestDependencyGraph(unittest.TestCase):
    """Test DependencyGraph class functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.graph = DependencyGraph()

    def test_add_node(self):
        """Test adding nodes to the graph."""
        # Add a single node
        self.graph.add_node("service-a")

        self.assertIn("service-a", self.graph.nodes)
        self.assertEqual(len(self.graph.nodes), 1)

        # Add another node
        self.graph.add_node("service-b")

        self.assertIn("service-b", self.graph.nodes)
        self.assertEqual(len(self.graph.nodes), 2)

        # Adding duplicate node should not increase count
        self.graph.add_node("service-a")
        self.assertEqual(len(self.graph.nodes), 2)

    def test_add_edge(self):
        """Test adding edges to the graph."""
        self.graph.add_node("service-a")
        self.graph.add_node("service-b")

        # Add internal dependency edge
        self.graph.add_edge(
            "service-a", "service-b", DependencyType.INTERNAL, "Service A depends on Service B"
        )

        self.assertEqual(len(self.graph.edges), 1)
        self.assertEqual(self.graph.edges[0].from_service, "service-a")
        self.assertEqual(self.graph.edges[0].to_service, "service-b")
        self.assertIn("service-b", self.graph.adjacency_list["service-a"])

        # Test edge properties
        edge = self.graph.edges[0]
        self.assertEqual(edge.from_service, "service-a")
        self.assertEqual(edge.to_service, "service-b")
        self.assertEqual(edge.dep_type, DependencyType.INTERNAL)
        self.assertEqual(edge.description, "Service A depends on Service B")

    def test_has_cycle_no_cycle(self):
        """Test cycle detection with no cycles present."""
        # Create a simple acyclic graph: A -> B -> C
        self.graph.add_node("service-a")
        self.graph.add_node("service-b")
        self.graph.add_node("service-c")

        self.graph.add_edge("service-a", "service-b", DependencyType.INTERNAL)
        self.graph.add_edge("service-b", "service-c", DependencyType.INTERNAL)

        has_cycle, cycle_path = self.graph.has_cycle()

        self.assertFalse(has_cycle)
        self.assertEqual(cycle_path, [])

    def test_has_cycle_with_cycle(self):
        """Test cycle detection with cycles present."""
        # Create a graph with a cycle: A -> B -> C -> A
        self.graph.add_node("service-a")
        self.graph.add_node("service-b")
        self.graph.add_node("service-c")

        self.graph.add_edge("service-a", "service-b", DependencyType.INTERNAL)
        self.graph.add_edge("service-b", "service-c", DependencyType.INTERNAL)
        self.graph.add_edge("service-c", "service-a", DependencyType.INTERNAL)

        has_cycle, cycle_path = self.graph.has_cycle()

        self.assertTrue(has_cycle)
        self.assertIsNotNone(cycle_path)
        self.assertEqual(len(cycle_path), 1)
        self.assertIn(cycle_path[0], ["service-a", "service-b", "service-c"])

    def test_get_topological_order_acyclic(self):
        """Test topological sorting of acyclic graph."""
        # Create a simple acyclic graph: A -> B -> C
        self.graph.add_node("service-a")
        self.graph.add_node("service-b")
        self.graph.add_node("service-c")

        self.graph.add_edge("service-a", "service-b", DependencyType.INTERNAL)
        self.graph.add_edge("service-b", "service-c", DependencyType.INTERNAL)

        order = self.graph.get_topological_order()

        # Should be in dependency order (A before B before C)
        self.assertEqual(len(order), 3)
        a_idx = order.index("service-a")
        b_idx = order.index("service-b")
        c_idx = order.index("service-c")

        self.assertLess(a_idx, b_idx)
        self.assertLess(b_idx, c_idx)

    def test_get_topological_order_with_cycle(self):
        """Test topological sorting fails with cyclic graph."""
        # Create a graph with a cycle
        self.graph.add_node("service-a")
        self.graph.add_node("service-b")
        self.graph.add_node("service-c")

        self.graph.add_edge("service-a", "service-b", DependencyType.INTERNAL)
        self.graph.add_edge("service-b", "service-c", DependencyType.INTERNAL)
        self.graph.add_edge("service-c", "service-a", DependencyType.INTERNAL)

        # Topological order should return empty list for cyclic graphs
        order = self.graph.get_topological_order()
        self.assertEqual(order, [])

    def test_complex_dependency_graph(self):
        """Test with a more complex realistic dependency graph."""
        # Create a realistic service dependency graph
        services = [
            "gateway", "auth-service", "user-service", "streaming-service",
            "data-processor", "ml-engine", "notification-service"
        ]

        for service in services:
            self.graph.add_node(service)

        # Add realistic dependencies
        dependencies = [
            ("gateway", "auth-service", DependencyType.INTERNAL),
            ("gateway", "user-service", DependencyType.INTERNAL),
            ("auth-service", "user-service", DependencyType.INTERNAL),
            ("streaming-service", "data-processor", DependencyType.INTERNAL),
            ("data-processor", "ml-engine", DependencyType.INTERNAL),
            ("notification-service", "user-service", DependencyType.INTERNAL),
            ("user-service", "redis", DependencyType.EXTERNAL),
            ("data-processor", "postgresql", DependencyType.EXTERNAL),
        ]

        for from_service, to_service, dep_type in dependencies:
            self.graph.add_edge(from_service, to_service, dep_type)

        # Verify no cycles
        has_cycle, cycle_path = self.graph.has_cycle()
        self.assertFalse(has_cycle)

        # Verify topological order exists
        order = self.graph.get_topological_order()
        self.assertEqual(len(order), len(services) + 2)  # +2 for external deps

        # Verify dependency order
        gateway_idx = order.index("gateway")
        auth_idx = order.index("auth-service")
        user_idx = order.index("user-service")

        self.assertLess(gateway_idx, auth_idx)
        self.assertLess(auth_idx, user_idx)


class TestGraphValidator(unittest.TestCase):
    """Test GraphValidator class functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.catalog_file = Path(self.temp_dir) / "catalog.json"
        self.rules_file = Path(self.temp_dir) / "rules.yaml"

        # Create mock catalog
        self.mock_catalog = {
            "services": [
                {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "dependencies": {
                        "internal": ["auth-service@1.0.0"],
                        "external": ["redis@7.0"]
                    }
                },
                {
                    "name": "auth-service",
                    "domain": "access",
                    "maturity": "stable",
                    "dependencies": {
                        "internal": ["user-service@1.0.0"],
                        "external": ["postgresql@15"]
                    }
                },
                {
                    "name": "user-service",
                    "domain": "data",
                    "maturity": "stable",
                    "dependencies": {
                        "external": ["redis@7.0"]
                    }
                }
            ]
        }

        # Create mock rules
        self.mock_rules = {
            "external_allowlist": ["redis", "postgresql", "kafka"],
            "forbidden_patterns": [
                {"from_domain": "data", "to_domain": "access"}
            ],
            "layering_rules": {
                "access": ["shared", "data", "ml"],
                "data": ["shared", "ml"],
                "ml": ["shared"],
                "shared": []
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_defaults(self):
        """Test GraphValidator initialization with default files."""
        with patch('scripts.validate_graph.Path.exists') as mock_exists:
            mock_exists.return_value = True

            with patch('scripts.validate_graph.GraphValidator._load_catalog') as mock_load_catalog:
                with patch('scripts.validate_graph.GraphValidator._load_rules') as mock_load_rules:
                    mock_load_catalog.return_value = self.mock_catalog
                    mock_load_rules.return_value = self.mock_rules

                    validator = GraphValidator()

                    self.assertIsNotNone(validator.catalog_path)
                    self.assertIsNotNone(validator.rules_file)

    def test_initialization_with_custom_files(self):
        """Test GraphValidator initialization with custom files."""
        validator = GraphValidator(
            catalog_file=str(self.catalog_file),
            rules_file=str(self.rules_file)
        )

        self.assertEqual(validator.catalog_file, self.catalog_file)
        self.assertEqual(validator.rules_file, self.rules_file)

    def test_load_catalog(self):
        """Test catalog loading functionality."""
        # Write mock catalog to file
        with open(self.catalog_file, 'w') as f:
            json.dump(self.mock_catalog, f)

        validator = GraphValidator(catalog_file=str(self.catalog_file))
        catalog = validator._load_catalog()

        self.assertEqual(catalog, self.mock_catalog)
        self.assertIn("services", catalog)
        self.assertEqual(len(catalog["services"]), 3)

    def test_load_rules(self):
        """Test rules loading functionality."""
        # Write mock rules to file
        with open(self.rules_file, 'w') as f:
            yaml.dump(self.mock_rules, f)

        validator = GraphValidator(rules_file=str(self.rules_file))
        rules = validator._load_rules()

        self.assertEqual(rules, self.mock_rules)
        self.assertIn("external_allowlist", rules)
        self.assertIn("forbidden_patterns", rules)

    def test_get_default_rules(self):
        """Test default rules generation."""
        validator = GraphValidator()
        rules = validator._get_default_rules()

        self.assertIn("external_allowlist", rules)
        self.assertIn("forbidden_patterns", rules)
        self.assertIn("layering_rules", rules)

        # Check default external allowlist
        self.assertIn("redis", rules["external_allowlist"])
        self.assertIn("postgresql", rules["external_allowlist"])

    def test_build_dependency_graph(self):
        """Test dependency graph building from catalog."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        graph = validator._build_dependency_graph()

        # Check nodes
        self.assertIn("gateway", graph.nodes)
        self.assertIn("auth-service", graph.nodes)
        self.assertIn("user-service", graph.nodes)
        self.assertIn("redis", graph.nodes)  # External dependency
        self.assertIn("postgresql", graph.nodes)  # External dependency

        # Check edges
        self.assertIn("gateway", graph.edges)
        self.assertIn("auth-service", graph.edges["gateway"])
        self.assertIn("user-service", graph.edges["auth-service"])

    def test_validate_cycles_no_cycles(self):
        """Test cycle validation with no cycles."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_cycles()

        # Should have no cycle violations
        cycle_violations = [v for v in violations if v["type"] == "cycle"]
        self.assertEqual(len(cycle_violations), 0)

    def test_validate_cycles_with_cycles(self):
        """Test cycle validation with cycles present."""
        # Create catalog with circular dependency
        cyclic_catalog = {
            "services": {
                "service-a": {
                    "name": "service-a",
                    "dependencies": {
                        "internal": ["service-b@1.0.0"]
                    }
                },
                "service-b": {
                    "name": "service-b",
                    "dependencies": {
                        "internal": ["service-a@1.0.0"]
                    }
                }
            }
        }

        validator = GraphValidator()
        validator.catalog = cyclic_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_cycles()

        # Should detect cycle violation
        cycle_violations = [v for v in violations if v["type"] == "cycle"]
        self.assertEqual(len(cycle_violations), 1)

        violation = cycle_violations[0]
        self.assertIn("cycle", violation["description"].lower())
        self.assertEqual(violation["severity"], "critical")

    def test_validate_external_dependencies_allowed(self):
        """Test external dependency validation with allowed dependencies."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_external_dependencies()

        # Should have no violations for allowed external deps
        self.assertEqual(len(violations), 0)

    def test_validate_external_dependencies_forbidden(self):
        """Test external dependency validation with forbidden dependencies."""
        # Create catalog with forbidden external dependency
        forbidden_catalog = {
            "services": {
                "test-service": {
                    "name": "test-service",
                    "dependencies": {
                        "external": ["mongodb@5.0"]  # Not in allowlist
                    }
                }
            }
        }

        validator = GraphValidator()
        validator.catalog = forbidden_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_external_dependencies()

        # Should detect forbidden dependency violation
        forbidden_violations = [v for v in violations if v["type"] == "forbidden_external"]
        self.assertEqual(len(forbidden_violations), 1)

        violation = forbidden_violations[0]
        self.assertIn("mongodb", violation["description"])
        self.assertEqual(violation["severity"], "high")

    def test_validate_directionality_valid(self):
        """Test directionality validation with valid dependencies."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_directionality()

        # Should have no directionality violations
        direction_violations = [v for v in violations if v["type"] == "invalid_direction"]
        self.assertEqual(len(direction_violations), 0)

    def test_validate_directionality_invalid(self):
        """Test directionality validation with invalid dependencies."""
        # Create catalog with invalid directionality (data depends on access)
        invalid_catalog = {
            "services": {
                "data-service": {
                    "name": "data-service",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["access-service@1.0.0"]
                    }
                },
                "access-service": {
                    "name": "access-service",
                    "domain": "access",
                    "dependencies": {}
                }
            }
        }

        validator = GraphValidator()
        validator.catalog = invalid_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_directionality()

        # Should detect directionality violation
        direction_violations = [v for v in violations if v["type"] == "invalid_direction"]
        self.assertEqual(len(direction_violations), 1)

        violation = direction_violations[0]
        self.assertIn("data", violation["description"])
        self.assertIn("access", violation["description"])

    def test_validate_forbidden_patterns(self):
        """Test forbidden pattern validation."""
        # Create catalog with forbidden pattern
        forbidden_catalog = {
            "services": {
                "data-service": {
                    "name": "data-service",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["access-service@1.0.0"]
                    }
                },
                "access-service": {
                    "name": "access-service",
                    "domain": "access",
                    "dependencies": {}
                }
            }
        }

        validator = GraphValidator()
        validator.catalog = forbidden_catalog
        validator.rules = self.mock_rules

        violations = validator.validate_forbidden_patterns()

        # Should detect forbidden pattern violation
        pattern_violations = [v for v in violations if v["type"] == "forbidden_pattern"]
        self.assertEqual(len(pattern_violations), 1)

    def test_generate_dependency_graph_yaml(self):
        """Test dependency graph YAML generation."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        graph_yaml = validator.generate_dependency_graph_yaml()

        # Check structure
        self.assertIn("nodes", graph_yaml)
        self.assertIn("edges", graph_yaml)
        self.assertIn("metadata", graph_yaml)

        # Check nodes
        nodes = graph_yaml["nodes"]
        self.assertIn("gateway", nodes)
        self.assertIn("auth-service", nodes)
        self.assertIn("user-service", nodes)

        # Check edges
        edges = graph_yaml["edges"]
        self.assertGreater(len(edges), 0)

        # Check metadata
        metadata = graph_yaml["metadata"]
        self.assertIn("generated_at", metadata)
        self.assertIn("service_count", metadata)

    def test_run_validation(self):
        """Test complete validation run."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        report = validator.run_validation()

        # Check report structure
        self.assertIn("validation_timestamp", report)
        self.assertIn("total_violations", report)
        self.assertIn("violations", report)
        self.assertIn("graph", report)

        # Check violations list
        violations = report["violations"]
        self.assertIsInstance(violations, list)

        # Check graph data
        graph = report["graph"]
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)

    def test_save_outputs(self):
        """Test output file saving."""
        validator = GraphValidator()
        validator.catalog = self.mock_catalog
        validator.rules = self.mock_rules

        # Create mock report
        report = {
            "validation_timestamp": "2025-01-06T10:00:00Z",
            "total_violations": 0,
            "violations": [],
            "graph": validator.generate_dependency_graph_yaml()
        }

        # Mock the catalog file path
        validator.catalog_file = Path(self.temp_dir) / "catalog.json"

        with patch('scripts.validate_graph.yaml.dump') as mock_yaml_dump:
            with patch('scripts.validate_graph.json.dump') as mock_json_dump:
                validator._save_outputs(report)

                # Verify YAML was saved for graph
                mock_yaml_dump.assert_called_once()

                # Verify JSON was saved for violations
                mock_json_dump.assert_called_once()


class TestGraphValidationIntegration(unittest.TestCase):
    """Integration tests for graph validation with realistic scenarios."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

        # Create realistic catalog with multiple domains
        self.realistic_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "dependencies": {
                        "internal": ["auth-service@1.0.0", "user-service@1.0.0"],
                        "external": ["redis@7.0"]
                    }
                },
                "auth-service": {
                    "name": "auth-service",
                    "domain": "access",
                    "maturity": "stable",
                    "dependencies": {
                        "internal": ["user-service@1.0.0"],
                        "external": ["postgresql@15"]
                    }
                },
                "user-service": {
                    "name": "user-service",
                    "domain": "data",
                    "maturity": "stable",
                    "dependencies": {
                        "external": ["redis@7.0", "postgresql@15"]
                    }
                },
                "streaming-service": {
                    "name": "streaming-service",
                    "domain": "data",
                    "maturity": "beta",
                    "dependencies": {
                        "internal": ["data-processor@1.0.0"],
                        "external": ["kafka@3.5"]
                    }
                },
                "data-processor": {
                    "name": "data-processor",
                    "domain": "data",
                    "maturity": "stable",
                    "dependencies": {
                        "external": ["postgresql@15", "redis@7.0"]
                    }
                },
                "ml-engine": {
                    "name": "ml-engine",
                    "domain": "ml",
                    "maturity": "experimental",
                    "dependencies": {
                        "internal": ["data-processor@1.0.0"],
                        "external": ["tensorflow@2.0"]
                    }
                },
                "notification-service": {
                    "name": "notification-service",
                    "domain": "shared",
                    "maturity": "stable",
                    "dependencies": {
                        "internal": ["user-service@1.0.0"],
                        "external": ["redis@7.0"]
                    }
                }
            }
        }

        # Write catalog to file
        self.catalog_file = Path(self.temp_dir) / "catalog.json"
        with open(self.catalog_file, 'w') as f:
            json.dump(self.realistic_catalog, f)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_realistic_catalog_validation(self):
        """Test validation with realistic multi-domain catalog."""
        validator = GraphValidator(catalog_file=str(self.catalog_file))

        # Load the catalog
        catalog = validator._load_catalog()
        self.assertEqual(len(catalog["services"]), 7)

        # Build dependency graph
        graph = validator._build_dependency_graph()
        self.assertEqual(len(graph.nodes), 9)  # 7 services + 2 external deps

        # Run validation
        report = validator.run_validation()

        # Should have no violations in this well-formed catalog
        self.assertEqual(report["total_violations"], 0)
        self.assertEqual(len(report["violations"]), 0)

        # Check graph structure
        graph_data = report["graph"]
        self.assertIn("gateway", graph_data["nodes"])
        self.assertGreater(len(graph_data["edges"]), 0)

    def test_catalog_with_violations(self):
        """Test validation with catalog containing violations."""
        # Create catalog with violations
        violating_catalog = {
            "services": {
                "bad-service": {
                    "name": "bad-service",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["access-service@1.0.0"],  # Invalid direction
                        "external": ["forbidden-db@1.0.0"]   # Not in allowlist
                    }
                },
                "access-service": {
                    "name": "access-service",
                    "domain": "access",
                    "dependencies": {}
                }
            }
        }

        # Write violating catalog
        violating_file = Path(self.temp_dir) / "violating-catalog.json"
        with open(violating_file, 'w') as f:
            json.dump(violating_catalog, f)

        validator = GraphValidator(catalog_file=str(violating_file))

        # Run validation
        report = validator.run_validation()

        # Should detect multiple violations
        self.assertGreater(report["total_violations"], 0)
        violations = report["violations"]

        # Check for specific violation types
        violation_types = [v["type"] for v in violations]
        self.assertIn("invalid_direction", violation_types)
        self.assertIn("forbidden_external", violation_types)

    def test_cycle_detection_integration(self):
        """Test cycle detection in realistic scenario."""
        # Create catalog with circular dependency
        cyclic_catalog = {
            "services": {
                "service-a": {
                    "name": "service-a",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["service-b@1.0.0"]
                    }
                },
                "service-b": {
                    "name": "service-b",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["service-c@1.0.0"]
                    }
                },
                "service-c": {
                    "name": "service-c",
                    "domain": "data",
                    "dependencies": {
                        "internal": ["service-a@1.0.0"]  # Creates cycle
                    }
                }
            }
        }

        cyclic_file = Path(self.temp_dir) / "cyclic-catalog.json"
        with open(cyclic_file, 'w') as f:
            json.dump(cyclic_catalog, f)

        validator = GraphValidator(catalog_file=str(cyclic_file))

        # Run validation
        report = validator.run_validation()

        # Should detect cycle violation
        self.assertGreater(report["total_violations"], 0)
        cycle_violations = [v for v in report["violations"] if v["type"] == "cycle"]
        self.assertEqual(len(cycle_violations), 1)

        violation = cycle_violations[0]
        self.assertIn("cycle", violation["description"].lower())


if __name__ == '__main__':
    unittest.main()
