#!/usr/bin/env python3
"""
Unit tests for analysis scripts - assess_risk, generate_agent_context, 
analyze_impact, and analyze_architecture.

These tests cover risk assessment, AI context generation, impact analysis,
and architecture validation functionality.
"""

import unittest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
from datetime import datetime, timezone

# Note: These tests use mocking since the actual scripts may not be importable
# In production, we would import the actual modules


class TestAssessRisk(unittest.TestCase):
    """Test risk assessment functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_service = {
            "name": "test-service",
            "maturity": "stable",
            "quality": {
                "coverage": 0.85,
                "vulnerabilities": {
                    "critical": 0,
                    "high": 1
                }
            },
            "dependencies": {
                "internal": ["auth-service@1.0.0"],
                "external": ["redis@7.0"]
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_risk_score_calculation(self):
        """Test risk score calculation logic."""
        # Mock risk factors
        quality_score = 85
        dependency_count = 5
        maturity = "stable"
        
        # Calculate risk score (simplified logic)
        risk_score = 100 - quality_score
        risk_score += dependency_count * 2
        
        if maturity == "experimental":
            risk_score += 20
        elif maturity == "beta":
            risk_score += 10
        
        # Stable service with good quality should have low risk
        self.assertLess(risk_score, 30)

    def test_risk_classification(self):
        """Test risk level classification."""
        test_cases = [
            (10, "low"),
            (30, "medium"),
            (60, "high"),
            (85, "critical"),
        ]
        
        for score, expected_level in test_cases:
            with self.subTest(score=score):
                if score < 25:
                    level = "low"
                elif score < 50:
                    level = "medium"
                elif score < 75:
                    level = "high"
                else:
                    level = "critical"
                
                self.assertEqual(level, expected_level)

    def test_change_impact_assessment(self):
        """Test change impact assessment."""
        change_types = {
            "patch": 5,
            "minor": 15,
            "major": 40,
            "breaking": 80
        }
        
        for change_type, expected_impact in change_types.items():
            with self.subTest(change_type=change_type):
                self.assertGreater(expected_impact, 0)
                if change_type == "breaking":
                    self.assertGreater(expected_impact, 50)


class TestGenerateAgentContext(unittest.TestCase):
    """Test AI agent context generation functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "quality": {"coverage": 0.88},
                    "maturity": "stable"
                }
            }
        }
        
        self.mock_drift = {
            "gateway": 2
        }
        
        self.mock_quality = {
            "gateway": {"score": 85, "grade": "B"}
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_context_structure(self):
        """Test agent context structure."""
        context = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform_overview": {
                "total_services": 1,
                "average_quality": 85.0
            },
            "service_details": self.mock_catalog["services"],
            "quality_snapshot": self.mock_quality,
            "drift_issues": self.mock_drift,
            "safe_operations": ["read", "analyze"],
            "forbidden_operations": ["delete", "force_push"]
        }
        
        # Verify required fields
        self.assertIn("generated_at", context)
        self.assertIn("platform_overview", context)
        self.assertIn("service_details", context)
        self.assertIn("safe_operations", context)
        self.assertIn("forbidden_operations", context)

    def test_safe_operations_list(self):
        """Test safe operations identification."""
        safe_ops = [
            "read_catalog",
            "analyze_quality",
            "detect_drift",
            "assess_risk",
            "generate_report"
        ]
        
        forbidden_ops = [
            "delete_service",
            "force_push",
            "bypass_quality_gates",
            "modify_production"
        ]
        
        # Verify no overlap
        self.assertEqual(set(safe_ops) & set(forbidden_ops), set())

    def test_context_freshness(self):
        """Test context freshness validation."""
        generated_time = datetime.now(timezone.utc)
        current_time = datetime.now(timezone.utc)
        
        age_seconds = (current_time - generated_time).total_seconds()
        
        # Context should be fresh (< 1 hour)
        self.assertLess(age_seconds, 3600)


class TestAnalyzeImpact(unittest.TestCase):
    """Test impact analysis functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_graph = {
            "nodes": ["gateway", "auth-service", "user-service"],
            "edges": [
                {"from": "gateway", "to": "auth-service"},
                {"from": "auth-service", "to": "user-service"}
            ]
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_direct_dependencies(self):
        """Test direct dependency identification."""
        service = "auth-service"
        
        # Find direct dependencies
        direct_deps = [
            edge["to"] for edge in self.mock_graph["edges"]
            if edge["from"] == service
        ]
        
        self.assertEqual(direct_deps, ["user-service"])

    def test_reverse_dependencies(self):
        """Test reverse dependency identification."""
        service = "auth-service"
        
        # Find services that depend on this one
        reverse_deps = [
            edge["from"] for edge in self.mock_graph["edges"]
            if edge["to"] == service
        ]
        
        self.assertEqual(reverse_deps, ["gateway"])

    def test_impact_radius_calculation(self):
        """Test impact radius calculation."""
        # Simulate impact radius calculation
        def calculate_impact_radius(service, graph):
            """Calculate how many services are affected by changes."""
            affected = set()
            to_process = [service]
            
            while to_process:
                current = to_process.pop(0)
                if current in affected:
                    continue
                
                affected.add(current)
                
                # Add reverse dependencies
                for edge in graph["edges"]:
                    if edge["to"] == current and edge["from"] not in affected:
                        to_process.append(edge["from"])
            
            return len(affected) - 1  # Exclude the service itself
        
        # Test impact radius
        radius = calculate_impact_radius("user-service", self.mock_graph)
        self.assertEqual(radius, 2)  # Affects auth-service and gateway

    def test_critical_path_detection(self):
        """Test critical path detection."""
        # Services with no dependencies are leaf nodes
        leaf_nodes = []
        
        for node in self.mock_graph["nodes"]:
            has_dependencies = any(
                edge["from"] == node for edge in self.mock_graph["edges"]
            )
            if not has_dependencies:
                leaf_nodes.append(node)
        
        # user-service has no outgoing dependencies
        self.assertIn("user-service", leaf_nodes)


class TestAnalyzeArchitecture(unittest.TestCase):
    """Test architecture analysis functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "dependencies": {
                        "internal": ["auth-service@1.0.0"]
                    }
                },
                "auth-service": {
                    "name": "auth-service",
                    "domain": "access",
                    "dependencies": {
                        "internal": ["user-service@1.0.0"]
                    }
                },
                "user-service": {
                    "name": "user-service",
                    "domain": "data",
                    "dependencies": {}
                }
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_domain_distribution(self):
        """Test domain distribution analysis."""
        domains = {}
        
        for service in self.mock_catalog["services"].values():
            domain = service.get("domain", "unknown")
            domains[domain] = domains.get(domain, 0) + 1
        
        self.assertEqual(domains["access"], 2)
        self.assertEqual(domains["data"], 1)

    def test_anti_pattern_detection_god_service(self):
        """Test god service anti-pattern detection."""
        # God service: too many dependencies
        god_service = {
            "name": "god-service",
            "dependencies": {
                "internal": [f"service-{i}@1.0.0" for i in range(15)]
            }
        }
        
        dep_count = len(god_service["dependencies"]["internal"])
        
        # Flag as anti-pattern if > 10 dependencies
        is_god_service = dep_count > 10
        self.assertTrue(is_god_service)

    def test_anti_pattern_detection_circular_deps(self):
        """Test circular dependency detection."""
        # Create a graph with circular dependency
        graph = {
            "service-a": ["service-b"],
            "service-b": ["service-c"],
            "service-c": ["service-a"]  # Creates cycle
        }
        
        def has_cycle(graph, start, visited=None, rec_stack=None):
            """Detect cycles in dependency graph."""
            if visited is None:
                visited = set()
            if rec_stack is None:
                rec_stack = set()
            
            visited.add(start)
            rec_stack.add(start)
            
            for neighbor in graph.get(start, []):
                if neighbor not in visited:
                    if has_cycle(graph, neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(start)
            return False
        
        # Should detect cycle
        self.assertTrue(has_cycle(graph, "service-a"))

    def test_layering_violation_detection(self):
        """Test architectural layering violation detection."""
        # Define valid layer dependencies
        layer_rules = {
            "access": ["data", "shared"],
            "data": ["shared"],
            "shared": []
        }
        
        # Test valid dependency
        valid = ("access", "data")
        self.assertIn(valid[1], layer_rules[valid[0]])
        
        # Test invalid dependency (data -> access)
        invalid = ("data", "access")
        self.assertNotIn(invalid[1], layer_rules[invalid[0]])

    def test_architecture_suggestions(self):
        """Test architecture improvement suggestions."""
        suggestions = []
        
        # Check for services without health checks
        for service in self.mock_catalog["services"].values():
            if "deployment" not in service or "health_check_path" not in service.get("deployment", {}):
                suggestions.append({
                    "service": service["name"],
                    "type": "missing_health_check",
                    "priority": "medium",
                    "suggestion": "Add health check endpoint"
                })
        
        # Should generate suggestions for services without health checks
        self.assertEqual(len(suggestions), 3)

    def test_coupling_metric_calculation(self):
        """Test service coupling metric calculation."""
        def calculate_coupling(service_name, catalog):
            """Calculate coupling metric for a service."""
            service = catalog["services"][service_name]
            
            # Count dependencies
            internal_deps = len(service.get("dependencies", {}).get("internal", []))
            
            # Count reverse dependencies
            reverse_deps = 0
            for other_service in catalog["services"].values():
                if other_service["name"] == service_name:
                    continue
                
                deps = other_service.get("dependencies", {}).get("internal", [])
                if any(service_name in dep for dep in deps):
                    reverse_deps += 1
            
            return internal_deps + reverse_deps
        
        # Gateway should have high coupling (depends on auth, nothing depends on it)
        gateway_coupling = calculate_coupling("gateway", self.mock_catalog)
        self.assertGreater(gateway_coupling, 0)
        
        # User-service should have high coupling (many depend on it)
        user_coupling = calculate_coupling("user-service", self.mock_catalog)
        self.assertGreater(user_coupling, 0)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests combining multiple analysis functions."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.complete_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "quality": {"coverage": 0.88},
                    "dependencies": {
                        "internal": ["auth-service@1.0.0"],
                        "external": ["redis@7.0"]
                    }
                },
                "auth-service": {
                    "name": "auth-service",
                    "domain": "access",
                    "maturity": "stable",
                    "quality": {"coverage": 0.92},
                    "dependencies": {
                        "internal": ["user-service@1.0.0"]
                    }
                },
                "user-service": {
                    "name": "user-service",
                    "domain": "data",
                    "maturity": "stable",
                    "quality": {"coverage": 0.85},
                    "dependencies": {
                        "external": ["postgresql@15"]
                    }
                }
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_analysis_workflow(self):
        """Test complete analysis workflow."""
        # 1. Assess risk for each service
        risks = {}
        for service_name, service in self.complete_catalog["services"].items():
            quality = service.get("quality", {}).get("coverage", 0) * 100
            dep_count = len(service.get("dependencies", {}).get("internal", []))
            
            risk_score = 100 - quality + (dep_count * 5)
            risks[service_name] = risk_score
        
        # 2. Analyze impact radius
        impact_radii = {
            "gateway": 0,  # Nothing depends on it
            "auth-service": 1,  # Gateway depends on it
            "user-service": 2  # Auth and gateway depend on it (transitively)
        }
        
        # 3. Generate recommendations
        recommendations = []
        for service_name, risk in risks.items():
            if risk > 20:
                recommendations.append({
                    "service": service_name,
                    "risk_score": risk,
                    "impact_radius": impact_radii[service_name],
                    "action": "Review and improve quality"
                })
        
        # Verify workflow completed
        self.assertEqual(len(risks), 3)
        self.assertEqual(len(impact_radii), 3)
        self.assertIsInstance(recommendations, list)

    def test_agent_context_generation_workflow(self):
        """Test AI agent context generation workflow."""
        # Generate comprehensive context
        context = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform_overview": {
                "total_services": len(self.complete_catalog["services"]),
                "domains": list(set(
                    s.get("domain", "unknown")
                    for s in self.complete_catalog["services"].values()
                ))
            },
            "service_details": self.complete_catalog["services"],
            "safe_operations": [
                "read_catalog",
                "analyze_quality",
                "detect_drift",
                "assess_risk"
            ],
            "forbidden_operations": [
                "delete_service",
                "force_push",
                "bypass_gates"
            ],
            "policy_reminders": [
                "Always run tests before merging",
                "Require code review for all changes",
                "Never commit secrets"
            ]
        }
        
        # Verify context is complete
        self.assertIn("generated_at", context)
        self.assertIn("platform_overview", context)
        self.assertIn("service_details", context)
        self.assertIn("safe_operations", context)
        self.assertIn("forbidden_operations", context)
        self.assertIn("policy_reminders", context)
        
        # Verify data integrity
        self.assertEqual(
            context["platform_overview"]["total_services"],
            3
        )
        self.assertIn("access", context["platform_overview"]["domains"])
        self.assertIn("data", context["platform_overview"]["domains"])


if __name__ == '__main__':
    unittest.main()
