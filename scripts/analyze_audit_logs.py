#!/usr/bin/env python3
"""
Audit Log Analysis Tool

Provides comprehensive audit log analysis, searching, filtering, and compliance reporting.
Supports various output formats and detailed analysis of audit events.

Usage:
    python scripts/analyze_audit_logs.py [--search PATTERN] [--user USER] [--action ACTION] [--format html|json|csv]

Features:
- Advanced search and filtering
- Compliance reporting
- Security event analysis
- User activity tracking
- Performance metrics from audit logs
- Export to multiple formats
- Timeline analysis
- Anomaly detection
"""

import os
import sys
import json
import csv
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re
from collections import defaultdict, Counter

from scripts.utils import audit_logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/audit_analysis.log')
    ]
)
logger = logging.getLogger(__name__)


class AuditLogAnalyzer:
    """Comprehensive audit log analysis tool."""
    
    def __init__(self, log_file: str = "audit.log"):
        """
        Initialize audit log analyzer.
        
        Args:
            log_file: Path to audit log file
        """
        self.log_file = Path(log_file)
        self.audit_logger = audit_logger
        
        logger.info(f"Audit log analyzer initialized: {self.log_file}")
    
    def search_logs(
        self,
        search_pattern: Optional[str] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        level: Optional[str] = None,
        category: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Search audit logs with multiple filters.
        
        Args:
            search_pattern: Text pattern to search for
            user: Filter by user
            action: Filter by action
            resource: Filter by resource
            level: Filter by level
            category: Filter by category
            start_time: Start time filter
            end_time: End time filter
            limit: Maximum number of results
        
        Returns:
            List of matching audit events
        """
        try:
            # Use audit logger's search functionality
            events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                user=user,
                action=action,
                resource=resource,
                level=level,
                category=category,
                limit=limit
            )
            
            # Apply text search pattern if provided
            if search_pattern:
                pattern = re.compile(search_pattern, re.IGNORECASE)
                filtered_events = []
                
                for event in events:
                    # Search in various fields
                    searchable_text = " ".join([
                        str(event.get('user', '')),
                        str(event.get('action', '')),
                        str(event.get('resource', '')),
                        str(event.get('details', {})),
                        str(event.get('context', {}))
                    ])
                    
                    if pattern.search(searchable_text):
                        filtered_events.append(event)
                
                events = filtered_events
            
            logger.info(f"Found {len(events)} matching audit events")
            return events
            
        except Exception as e:
            logger.error(f"Failed to search audit logs: {e}")
            return []
    
    def analyze_compliance(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze compliance-related events.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Compliance analysis report
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get compliance events
            compliance_events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                category="compliance",
                limit=10000
            )
            
            # Get security events
            security_events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                category="security",
                limit=10000
            )
            
            # Get data modification events
            data_mod_events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                category="data_modification",
                limit=10000
            )
            
            # Analyze compliance events
            compliance_analysis = {
                "total_events": len(compliance_events),
                "events_by_level": Counter(event.get('level', 'unknown') for event in compliance_events),
                "events_by_action": Counter(event.get('action', 'unknown') for event in compliance_events),
                "compliance_rate": 0.0,
                "violations": []
            }
            
            # Calculate compliance rate
            compliant_events = sum(1 for event in compliance_events if event.get('outcome') == 'compliant')
            if compliance_events:
                compliance_analysis["compliance_rate"] = compliant_events / len(compliance_events)
            
            # Find violations
            for event in compliance_events:
                if event.get('outcome') != 'compliant':
                    compliance_analysis["violations"].append({
                        "timestamp": event.get('timestamp'),
                        "user": event.get('user'),
                        "action": event.get('action'),
                        "details": event.get('details', {}),
                        "error_message": event.get('error_message')
                    })
            
            # Analyze security events
            security_analysis = {
                "total_events": len(security_events),
                "events_by_level": Counter(event.get('level', 'unknown') for event in security_events),
                "events_by_action": Counter(event.get('action', 'unknown') for event in security_events),
                "suspicious_activities": []
            }
            
            # Find suspicious activities
            for event in security_events:
                if event.get('level') in ['warning', 'error', 'critical']:
                    security_analysis["suspicious_activities"].append({
                        "timestamp": event.get('timestamp'),
                        "user": event.get('user'),
                        "action": event.get('action'),
                        "level": event.get('level'),
                        "details": event.get('details', {}),
                        "ip_address": event.get('ip_address')
                    })
            
            # Analyze data modifications
            data_mod_analysis = {
                "total_events": len(data_mod_events),
                "events_by_resource": Counter(event.get('resource', 'unknown') for event in data_mod_events),
                "events_by_user": Counter(event.get('user', 'unknown') for event in data_mod_events),
                "modification_timeline": []
            }
            
            # Create modification timeline
            for event in data_mod_events:
                data_mod_analysis["modification_timeline"].append({
                    "timestamp": event.get('timestamp'),
                    "user": event.get('user'),
                    "resource": event.get('resource'),
                    "action": event.get('action'),
                    "details": event.get('details', {})
                })
            
            # Sort timeline by timestamp
            data_mod_analysis["modification_timeline"].sort(
                key=lambda x: x['timestamp'], reverse=True
            )
            
            return {
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": days
                },
                "compliance": compliance_analysis,
                "security": security_analysis,
                "data_modifications": data_mod_analysis,
                "summary": {
                    "total_compliance_events": len(compliance_events),
                    "total_security_events": len(security_events),
                    "total_data_modifications": len(data_mod_events),
                    "overall_compliance_rate": compliance_analysis["compliance_rate"],
                    "security_alerts": len(security_analysis["suspicious_activities"])
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze compliance: {e}")
            return {"error": str(e)}
    
    def analyze_user_activity(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze user activity patterns.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            User activity analysis report
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get all events for the period
            events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
            
            # Group events by user
            user_events = defaultdict(list)
            for event in events:
                user = event.get('user', 'unknown')
                user_events[user].append(event)
            
            # Analyze each user
            user_analysis = {}
            for user, user_event_list in user_events.items():
                # Count actions
                action_counts = Counter(event.get('action', 'unknown') for event in user_event_list)
                
                # Count resources accessed
                resource_counts = Counter(event.get('resource', 'unknown') for event in user_event_list)
                
                # Count by level
                level_counts = Counter(event.get('level', 'unknown') for event in user_event_list)
                
                # Calculate activity metrics
                total_events = len(user_event_list)
                error_events = sum(1 for event in user_event_list if event.get('level') in ['error', 'critical'])
                error_rate = error_events / total_events if total_events > 0 else 0
                
                # Find most active hours
                hour_counts = Counter()
                for event in user_event_list:
                    try:
                        timestamp = datetime.fromisoformat(event.get('timestamp', '').replace('Z', ''))
                        hour_counts[timestamp.hour] += 1
                    except:
                        pass
                
                most_active_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
                
                user_analysis[user] = {
                    "total_events": total_events,
                    "error_rate": error_rate,
                    "action_counts": dict(action_counts),
                    "resource_counts": dict(resource_counts),
                    "level_counts": dict(level_counts),
                    "most_active_hour": most_active_hour,
                    "hourly_distribution": dict(hour_counts),
                    "first_activity": min(event.get('timestamp', '') for event in user_event_list),
                    "last_activity": max(event.get('timestamp', '') for event in user_event_list)
                }
            
            # Find anomalies
            anomalies = self._detect_user_anomalies(user_analysis)
            
            return {
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": days
                },
                "user_analysis": user_analysis,
                "anomalies": anomalies,
                "summary": {
                    "total_users": len(user_analysis),
                    "most_active_user": max(user_analysis.items(), key=lambda x: x[1]['total_events'])[0] if user_analysis else None,
                    "total_events": sum(data['total_events'] for data in user_analysis.values()),
                    "anomaly_count": len(anomalies)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze user activity: {e}")
            return {"error": str(e)}
    
    def analyze_performance(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze performance metrics from audit logs.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Performance analysis report
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get workflow execution events
            workflow_events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                category="workflow",
                limit=10000
            )
            
            # Group by workflow
            workflow_metrics = defaultdict(list)
            for event in workflow_events:
                workflow_name = event.get('resource', 'unknown')
                duration_ms = event.get('duration_ms')
                if duration_ms is not None:
                    workflow_metrics[workflow_name].append(duration_ms)
            
            # Calculate performance metrics
            performance_analysis = {}
            for workflow_name, durations in workflow_metrics.items():
                if durations:
                    performance_analysis[workflow_name] = {
                        "total_executions": len(durations),
                        "avg_duration_ms": sum(durations) / len(durations),
                        "min_duration_ms": min(durations),
                        "max_duration_ms": max(durations),
                        "median_duration_ms": sorted(durations)[len(durations) // 2],
                        "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0],
                        "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if len(durations) > 1 else durations[0]
                    }
            
            # Find performance trends
            trends = self._analyze_performance_trends(workflow_events)
            
            return {
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "days": days
                },
                "workflow_metrics": performance_analysis,
                "trends": trends,
                "summary": {
                    "total_workflows": len(performance_analysis),
                    "total_executions": sum(data['total_executions'] for data in performance_analysis.values()),
                    "avg_overall_duration": sum(data['avg_duration_ms'] for data in performance_analysis.values()) / len(performance_analysis) if performance_analysis else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze performance: {e}")
            return {"error": str(e)}
    
    def generate_timeline(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Generate chronological timeline of events.
        
        Args:
            days: Number of days to include
        
        Returns:
            Timeline of events
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get all events
            events = self.audit_logger.search_logs(
                start_time=start_time,
                end_time=end_time,
                limit=5000
            )
            
            # Sort by timestamp
            events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            # Create timeline entries
            timeline = []
            for event in events:
                timeline.append({
                    "timestamp": event.get('timestamp'),
                    "level": event.get('level'),
                    "category": event.get('category'),
                    "user": event.get('user'),
                    "action": event.get('action'),
                    "resource": event.get('resource'),
                    "outcome": event.get('outcome'),
                    "details": event.get('details', {}),
                    "error_message": event.get('error_message')
                })
            
            return timeline
            
        except Exception as e:
            logger.error(f"Failed to generate timeline: {e}")
            return []
    
    def _detect_user_anomalies(self, user_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalous user behavior."""
        anomalies = []
        
        try:
            # Calculate baseline metrics
            total_events = sum(data['total_events'] for data in user_analysis.values())
            avg_events = total_events / len(user_analysis) if user_analysis else 0
            avg_error_rate = sum(data['error_rate'] for data in user_analysis.values()) / len(user_analysis) if user_analysis else 0
            
            for user, data in user_analysis.items():
                # High activity anomaly
                if data['total_events'] > avg_events * 3:
                    anomalies.append({
                        "type": "high_activity",
                        "user": user,
                        "severity": "medium",
                        "description": f"User {user} has {data['total_events']} events (avg: {avg_events:.1f})",
                        "details": data
                    })
                
                # High error rate anomaly
                if data['error_rate'] > avg_error_rate * 2 and data['error_rate'] > 0.1:
                    anomalies.append({
                        "type": "high_error_rate",
                        "user": user,
                        "severity": "high",
                        "description": f"User {user} has {data['error_rate']:.1%} error rate (avg: {avg_error_rate:.1%})",
                        "details": data
                    })
                
                # Unusual hours anomaly
                if data['most_active_hour'] is not None:
                    if data['most_active_hour'] < 6 or data['most_active_hour'] > 22:
                        anomalies.append({
                            "type": "unusual_hours",
                            "user": user,
                            "severity": "low",
                            "description": f"User {user} most active at hour {data['most_active_hour']}",
                            "details": data
                        })
            
        except Exception as e:
            logger.error(f"Failed to detect user anomalies: {e}")
        
        return anomalies
    
    def _analyze_performance_trends(self, workflow_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance trends over time."""
        try:
            # Group events by workflow and day
            daily_metrics = defaultdict(lambda: defaultdict(list))
            
            for event in workflow_events:
                workflow_name = event.get('resource', 'unknown')
                duration_ms = event.get('duration_ms')
                timestamp = event.get('timestamp')
                
                if duration_ms is not None and timestamp:
                    try:
                        event_date = datetime.fromisoformat(timestamp.replace('Z', '')).date()
                        daily_metrics[workflow_name][event_date].append(duration_ms)
                    except:
                        pass
            
            # Calculate daily averages
            trends = {}
            for workflow_name, daily_data in daily_metrics.items():
                daily_averages = []
                for date, durations in sorted(daily_data.items()):
                    if durations:
                        daily_averages.append({
                            "date": date.isoformat(),
                            "avg_duration_ms": sum(durations) / len(durations),
                            "execution_count": len(durations)
                        })
                
                trends[workflow_name] = daily_averages
            
            return trends
            
        except Exception as e:
            logger.error(f"Failed to analyze performance trends: {e}")
            return {}
    
    def export_to_csv(self, events: List[Dict[str, Any]], output_file: str) -> str:
        """Export events to CSV format."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                if not events:
                    return str(output_path)
                
                # Get all possible fieldnames
                fieldnames = set()
                for event in events:
                    fieldnames.update(event.keys())
                
                fieldnames = sorted(list(fieldnames))
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for event in events:
                    # Convert complex values to strings
                    row = {}
                    for key, value in event.items():
                        if isinstance(value, (dict, list)):
                            row[key] = json.dumps(value)
                        else:
                            row[key] = value
                    writer.writerow(row)
            
            logger.info(f"Exported {len(events)} events to CSV: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
            raise
    
    def export_to_json(self, data: Dict[str, Any], output_file: str) -> str:
        """Export data to JSON format."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(data, jsonfile, indent=2, default=str)
            
            logger.info(f"Exported data to JSON: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to export to JSON: {e}")
            raise


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Analyze audit logs")
    parser.add_argument(
        "--search",
        help="Search pattern (regex)"
    )
    parser.add_argument(
        "--user",
        help="Filter by user"
    )
    parser.add_argument(
        "--action",
        help="Filter by action"
    )
    parser.add_argument(
        "--resource",
        help="Filter by resource"
    )
    parser.add_argument(
        "--level",
        help="Filter by level"
    )
    parser.add_argument(
        "--category",
        help="Filter by category"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)"
    )
    parser.add_argument(
        "--format",
        choices=["html", "json", "csv"],
        default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--output-file",
        help="Output file path (default: auto-generated)"
    )
    parser.add_argument(
        "--analysis-type",
        choices=["search", "compliance", "user-activity", "performance", "timeline"],
        default="search",
        help="Type of analysis to perform (default: search)"
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize analyzer
        analyzer = AuditLogAnalyzer()
        
        # Perform analysis based on type
        if args.analysis_type == "search":
            # Search events
            events = analyzer.search_logs(
                search_pattern=args.search,
                user=args.user,
                action=args.action,
                resource=args.resource,
                level=args.level,
                category=args.category,
                limit=1000
            )
            
            if args.format == "csv":
                output_file = args.output_file or f"audit_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                result_file = analyzer.export_to_csv(events, output_file)
            else:
                output_file = args.output_file or f"audit_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                result_file = analyzer.export_to_json({"events": events, "count": len(events)}, output_file)
        
        elif args.analysis_type == "compliance":
            # Compliance analysis
            analysis = analyzer.analyze_compliance(args.days)
            output_file = args.output_file or f"compliance_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            result_file = analyzer.export_to_json(analysis, output_file)
        
        elif args.analysis_type == "user-activity":
            # User activity analysis
            analysis = analyzer.analyze_user_activity(args.days)
            output_file = args.output_file or f"user_activity_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            result_file = analyzer.export_to_json(analysis, output_file)
        
        elif args.analysis_type == "performance":
            # Performance analysis
            analysis = analyzer.analyze_performance(args.days)
            output_file = args.output_file or f"performance_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            result_file = analyzer.export_to_json(analysis, output_file)
        
        elif args.analysis_type == "timeline":
            # Timeline analysis
            timeline = analyzer.generate_timeline(args.days)
            output_file = args.output_file or f"audit_timeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            result_file = analyzer.export_to_json({"timeline": timeline, "count": len(timeline)}, output_file)
        
        print(f"Analysis completed: {result_file}")
        
        # Print summary
        if args.analysis_type == "search":
            print(f"Found {len(events)} matching events")
        elif args.analysis_type == "compliance":
            compliance_rate = analysis.get('summary', {}).get('overall_compliance_rate', 0)
            print(f"Compliance rate: {compliance_rate:.1%}")
        elif args.analysis_type == "user-activity":
            total_users = analysis.get('summary', {}).get('total_users', 0)
            print(f"Analyzed {total_users} users")
        elif args.analysis_type == "performance":
            total_workflows = analysis.get('summary', {}).get('total_workflows', 0)
            print(f"Analyzed {total_workflows} workflows")
        elif args.analysis_type == "timeline":
            print(f"Generated timeline with {len(timeline)} events")
        
    except Exception as e:
        logger.error(f"Failed to analyze audit logs: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
