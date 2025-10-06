#!/usr/bin/env python3
"""
Monitoring Report Generator

Generates comprehensive monitoring reports for script health, performance trends,
and resource usage. Provides visualization of execution metrics and system health.

Usage:
    python scripts/generate_monitoring_report.py [--output-format html|json|markdown] [--time-range 7d]

Features:
- Script health status and trends
- Performance metrics visualization
- Resource usage analysis
- Error rate tracking
- Circuit breaker status
- Audit log summary
- System recommendations
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import time

from scripts.utils import ExecutionMonitor, audit_logger, redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/monitoring.log')
    ]
)
logger = logging.getLogger(__name__)


class MonitoringReportGenerator:
    """Generates comprehensive monitoring reports."""
    
    def __init__(self, output_format: str = "html", time_range_days: int = 7):
        """
        Initialize monitoring report generator.
        
        Args:
            output_format: Output format (html, json, markdown)
            time_range_days: Time range for analysis in days
        """
        self.output_format = output_format
        self.time_range_days = time_range_days
        self.end_time = datetime.now()
        self.start_time = self.end_time - timedelta(days=time_range_days)
        
        # Get utility instances
        self.execution_monitor = ExecutionMonitor.get_instance()
        self.audit_logger = audit_logger
        self.redis_client = redis_client
        
        logger.info(f"Monitoring report generator initialized: {output_format} format, {time_range_days} days")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        logger.info("Generating monitoring report...")
        
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "time_range": {
                    "start": self.start_time.isoformat(),
                    "end": self.end_time.isoformat(),
                    "days": self.time_range_days
                },
                "format": self.output_format
            },
            "execution_metrics": self._get_execution_metrics(),
            "system_health": self._get_system_health(),
            "performance_trends": self._get_performance_trends(),
            "error_analysis": self._get_error_analysis(),
            "audit_summary": self._get_audit_summary(),
            "redis_status": self._get_redis_status(),
            "recommendations": self._get_recommendations()
        }
        
        return report
    
    def _get_execution_metrics(self) -> Dict[str, Any]:
        """Get execution metrics from execution monitor."""
        try:
            metrics = self.execution_monitor.get_metrics()
            health_status = self.execution_monitor.get_health_status()
            
            return {
                "health_status": health_status,
                "script_metrics": metrics.get("all_scripts", {}),
                "current_executions": metrics.get("current_executions", 0),
                "total_scripts": metrics.get("total_scripts_monitored", 0)
            }
        except Exception as e:
            logger.error(f"Failed to get execution metrics: {e}")
            return {"error": str(e)}
    
    def _get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        try:
            # Get execution monitor health
            exec_health = self.execution_monitor.get_health_status()
            
            # Get Redis status
            redis_stats = self.redis_client.get_stats()
            
            # Get audit log statistics
            audit_stats = self.audit_logger.get_statistics(self.time_range_days)
            
            # Calculate overall health score
            health_score = self._calculate_health_score(exec_health, redis_stats, audit_stats)
            
            return {
                "overall_score": health_score,
                "execution_monitor": exec_health,
                "redis_status": {
                    "available": redis_stats["redis_available"],
                    "circuit_breaker_state": redis_stats["circuit_breaker_state"],
                    "hit_rate": redis_stats["hit_rate"]
                },
                "audit_health": {
                    "total_events": audit_stats["total_events"],
                    "error_rate": audit_stats["error_rate"],
                    "events_by_level": audit_stats["events_by_level"]
                }
            }
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {"error": str(e)}
    
    def _get_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends."""
        try:
            metrics = self.execution_monitor.get_metrics()
            trends = {}
            
            for script_name, script_data in metrics.get("all_scripts", {}).items():
                if script_data and "stats" in script_data:
                    stats = script_data["stats"]
                    trends[script_name] = {
                        "avg_duration": stats.get("avg_duration", 0),
                        "trend": stats.get("recent_trend", "stable"),
                        "success_rate": stats.get("success_rate", 0),
                        "total_executions": stats.get("total_executions", 0),
                        "last_execution": stats.get("last_execution"),
                        "performance_grade": self._grade_performance(stats)
                    }
            
            return trends
        except Exception as e:
            logger.error(f"Failed to get performance trends: {e}")
            return {"error": str(e)}
    
    def _get_error_analysis(self) -> Dict[str, Any]:
        """Analyze error patterns and rates."""
        try:
            # Get execution monitor errors
            metrics = self.execution_monitor.get_metrics()
            error_summary = {}
            
            for script_name, script_data in metrics.get("all_scripts", {}).items():
                if script_data and "stats" in script_data:
                    stats = script_data["stats"]
                    error_summary[script_name] = {
                        "failed_executions": stats.get("failed_executions", 0),
                        "success_rate": stats.get("success_rate", 0),
                        "last_failure": stats.get("last_failure"),
                        "error_rate": 1 - stats.get("success_rate", 1)
                    }
            
            # Get audit log errors
            audit_stats = self.audit_logger.get_statistics(self.time_range_days)
            
            return {
                "script_errors": error_summary,
                "audit_errors": {
                    "total_events": audit_stats["total_events"],
                    "error_rate": audit_stats["error_rate"],
                    "events_by_level": audit_stats["events_by_level"]
                },
                "top_error_sources": self._get_top_error_sources(error_summary)
            }
        except Exception as e:
            logger.error(f"Failed to get error analysis: {e}")
            return {"error": str(e)}
    
    def _get_audit_summary(self) -> Dict[str, Any]:
        """Get audit log summary."""
        try:
            stats = self.audit_logger.get_statistics(self.time_range_days)
            
            return {
                "total_events": stats["total_events"],
                "events_by_level": stats["events_by_level"],
                "events_by_category": stats["events_by_category"],
                "events_by_user": stats["events_by_user"],
                "events_by_action": stats["events_by_action"],
                "daily_counts": stats["daily_counts"],
                "error_rate": stats["error_rate"],
                "top_resources": stats["top_resources"]
            }
        except Exception as e:
            logger.error(f"Failed to get audit summary: {e}")
            return {"error": str(e)}
    
    def _get_redis_status(self) -> Dict[str, Any]:
        """Get Redis client status and statistics."""
        try:
            stats = self.redis_client.get_stats()
            
            return {
                "available": stats["redis_available"],
                "circuit_breaker_state": stats["circuit_breaker_state"],
                "hit_rate": stats["hit_rate"],
                "operations": stats["stats"],
                "fallback_dir": stats["fallback_dir"],
                "config": stats["config"]
            }
        except Exception as e:
            logger.error(f"Failed to get Redis status: {e}")
            return {"error": str(e)}
    
    def _get_recommendations(self) -> List[Dict[str, Any]]:
        """Generate system recommendations."""
        recommendations = []
        
        try:
            # Get current metrics
            exec_health = self.execution_monitor.get_health_status()
            redis_stats = self.redis_client.get_stats()
            audit_stats = self.audit_logger.get_statistics(self.time_range_days)
            
            # Execution monitor recommendations
            if exec_health["health_percentage"] < 80:
                recommendations.append({
                    "category": "execution_monitor",
                    "priority": "high",
                    "title": "Low Script Health Score",
                    "description": f"Script health is {exec_health['health_percentage']:.1f}%. Investigate failing scripts.",
                    "action": "Review failed scripts and fix underlying issues"
                })
            
            # Redis recommendations
            if not redis_stats["redis_available"]:
                recommendations.append({
                    "category": "redis",
                    "priority": "medium",
                    "title": "Redis Unavailable",
                    "description": "Redis is not available, using file-based fallback only.",
                    "action": "Check Redis connection and configuration"
                })
            
            if redis_stats["hit_rate"] < 0.7:
                recommendations.append({
                    "category": "redis",
                    "priority": "low",
                    "title": "Low Cache Hit Rate",
                    "description": f"Cache hit rate is {redis_stats['hit_rate']:.1%}. Consider optimizing cache strategy.",
                    "action": "Review cache TTL settings and usage patterns"
                })
            
            # Audit log recommendations
            if audit_stats["error_rate"] > 0.1:
                recommendations.append({
                    "category": "audit",
                    "priority": "medium",
                    "title": "High Error Rate",
                    "description": f"Error rate is {audit_stats['error_rate']:.1%}. Investigate error sources.",
                    "action": "Review error logs and fix underlying issues"
                })
            
            # Performance recommendations
            metrics = self.execution_monitor.get_metrics()
            for script_name, script_data in metrics.get("all_scripts", {}).items():
                if script_data and "stats" in script_data:
                    stats = script_data["stats"]
                    if stats.get("recent_trend") == "degrading":
                        recommendations.append({
                            "category": "performance",
                            "priority": "medium",
                            "title": f"Performance Degradation: {script_name}",
                            "description": f"Script {script_name} shows degrading performance trend.",
                            "action": "Investigate performance bottlenecks and optimize"
                        })
            
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            recommendations.append({
                "category": "system",
                "priority": "high",
                "title": "Report Generation Error",
                "description": f"Failed to generate recommendations: {e}",
                "action": "Check system logs and fix underlying issues"
            })
        
        return recommendations
    
    def _calculate_health_score(self, exec_health: Dict, redis_stats: Dict, audit_stats: Dict) -> float:
        """Calculate overall health score."""
        try:
            # Execution monitor health (40% weight)
            exec_score = exec_health.get("health_percentage", 0) / 100
            
            # Redis health (30% weight)
            redis_score = 1.0 if redis_stats.get("redis_available", False) else 0.5
            if redis_stats.get("hit_rate", 0) < 0.5:
                redis_score *= 0.8
            
            # Audit health (30% weight)
            audit_score = 1.0 - audit_stats.get("error_rate", 0)
            
            # Weighted average
            overall_score = (exec_score * 0.4 + redis_score * 0.3 + audit_score * 0.3)
            
            return min(1.0, max(0.0, overall_score))
            
        except Exception as e:
            logger.error(f"Failed to calculate health score: {e}")
            return 0.5  # Default to medium health
    
    def _grade_performance(self, stats: Dict[str, Any]) -> str:
        """Grade performance based on metrics."""
        try:
            success_rate = stats.get("success_rate", 0)
            avg_duration = stats.get("avg_duration", 0)
            trend = stats.get("recent_trend", "stable")
            
            if success_rate >= 0.95 and trend in ["stable", "improving"]:
                return "A"
            elif success_rate >= 0.9 and trend != "degrading":
                return "B"
            elif success_rate >= 0.8:
                return "C"
            else:
                return "D"
                
        except Exception:
            return "F"
    
    def _get_top_error_sources(self, error_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get top error sources."""
        try:
            error_sources = []
            
            for script_name, data in error_summary.items():
                error_rate = data.get("error_rate", 0)
                if error_rate > 0:
                    error_sources.append({
                        "script": script_name,
                        "error_rate": error_rate,
                        "failed_executions": data.get("failed_executions", 0)
                    })
            
            # Sort by error rate
            error_sources.sort(key=lambda x: x["error_rate"], reverse=True)
            
            return error_sources[:5]  # Top 5
            
        except Exception as e:
            logger.error(f"Failed to get top error sources: {e}")
            return []
    
    def save_report(self, report: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """Save report to file."""
        try:
            if not output_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"analysis/reports/monitoring_report_{timestamp}.{self.output_format}"
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.output_format == "json":
                with open(output_path, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
            
            elif self.output_format == "html":
                html_content = self._generate_html_report(report)
                with open(output_path, 'w') as f:
                    f.write(html_content)
            
            elif self.output_format == "markdown":
                markdown_content = self._generate_markdown_report(report)
                with open(output_path, 'w') as f:
                    f.write(markdown_content)
            
            else:
                raise ValueError(f"Unsupported output format: {self.output_format}")
            
            logger.info(f"Report saved to: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            raise
    
    def _generate_html_report(self, report: Dict[str, Any]) -> str:
        """Generate HTML report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>254Carbon Meta - Monitoring Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; background-color: #e8f4f8; border-radius: 3px; }}
        .health-score {{ font-size: 24px; font-weight: bold; }}
        .recommendation {{ margin: 10px 0; padding: 10px; border-left: 4px solid #007acc; background-color: #f9f9f9; }}
        .error {{ border-left-color: #ff4444; }}
        .warning {{ border-left-color: #ffaa00; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>254Carbon Meta - Monitoring Report</h1>
        <p>Generated: {report['metadata']['generated_at']}</p>
        <p>Time Range: {report['metadata']['time_range']['start']} to {report['metadata']['time_range']['end']}</p>
    </div>
    
    <div class="section">
        <h2>System Health</h2>
        <div class="metric">
            <span class="health-score">{report['system_health']['overall_score']:.1%}</span>
            <br>Overall Health Score
        </div>
    </div>
    
    <div class="section">
        <h2>Execution Metrics</h2>
        <p>Total Scripts Monitored: {report['execution_metrics']['total_scripts']}</p>
        <p>Current Executions: {report['execution_metrics']['current_executions']}</p>
    </div>
    
    <div class="section">
        <h2>Performance Trends</h2>
        <table>
            <tr><th>Script</th><th>Avg Duration</th><th>Trend</th><th>Success Rate</th><th>Grade</th></tr>
"""
        
        for script_name, data in report['performance_trends'].items():
            if isinstance(data, dict) and 'avg_duration' in data:
                html += f"""
            <tr>
                <td>{script_name}</td>
                <td>{data['avg_duration']:.3f}s</td>
                <td>{data['trend']}</td>
                <td>{data['success_rate']:.1%}</td>
                <td>{data['performance_grade']}</td>
            </tr>
"""
        
        html += """
        </table>
    </div>
    
    <div class="section">
        <h2>Recommendations</h2>
"""
        
        for rec in report['recommendations']:
            priority_class = "error" if rec['priority'] == 'high' else "warning" if rec['priority'] == 'medium' else ""
            html += f"""
        <div class="recommendation {priority_class}">
            <h4>{rec['title']} ({rec['priority'].upper()})</h4>
            <p>{rec['description']}</p>
            <p><strong>Action:</strong> {rec['action']}</p>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        
        return html
    
    def _generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """Generate Markdown report."""
        md = f"""# 254Carbon Meta - Monitoring Report

**Generated:** {report['metadata']['generated_at']}  
**Time Range:** {report['metadata']['time_range']['start']} to {report['metadata']['time_range']['end']}

## System Health

**Overall Health Score:** {report['system_health']['overall_score']:.1%}

## Execution Metrics

- **Total Scripts Monitored:** {report['execution_metrics']['total_scripts']}
- **Current Executions:** {report['execution_metrics']['current_executions']}

## Performance Trends

| Script | Avg Duration | Trend | Success Rate | Grade |
|--------|-------------|-------|--------------|-------|
"""
        
        for script_name, data in report['performance_trends'].items():
            if isinstance(data, dict) and 'avg_duration' in data:
                md += f"| {script_name} | {data['avg_duration']:.3f}s | {data['trend']} | {data['success_rate']:.1%} | {data['performance_grade']} |\n"
        
        md += "\n## Recommendations\n\n"
        
        for rec in report['recommendations']:
            priority_emoji = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
            md += f"### {priority_emoji} {rec['title']} ({rec['priority'].upper()})\n\n"
            md += f"**Description:** {rec['description']}\n\n"
            md += f"**Action:** {rec['action']}\n\n"
        
        return md


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Generate monitoring report")
    parser.add_argument(
        "--output-format",
        choices=["html", "json", "markdown"],
        default="html",
        help="Output format (default: html)"
    )
    parser.add_argument(
        "--time-range",
        type=int,
        default=7,
        help="Time range in days (default: 7)"
    )
    parser.add_argument(
        "--output-file",
        help="Output file path (default: auto-generated)"
    )
    
    args = parser.parse_args()
    
    try:
        # Generate report
        generator = MonitoringReportGenerator(
            output_format=args.output_format,
            time_range_days=args.time_range
        )
        
        report = generator.generate_report()
        
        # Save report
        output_file = generator.save_report(report, args.output_file)
        
        print(f"Monitoring report generated: {output_file}")
        
        # Print summary
        health_score = report['system_health']['overall_score']
        print(f"Overall Health Score: {health_score:.1%}")
        
        if health_score < 0.8:
            print("⚠️  System health is below optimal. Check recommendations.")
        else:
            print("✅ System health is good.")
        
    except Exception as e:
        logger.error(f"Failed to generate monitoring report: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
