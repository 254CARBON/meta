#!/usr/bin/env python3
"""
254Carbon Meta Repository - Historical Data Management

Manages archival, retention, and querying of historical platform data.

Usage:
    python scripts/manage_historical_data.py --archive --retention-days 90
    python scripts/manage_historical_data.py --query --service gateway --days 30
"""

import os
import sys
import json
import yaml
import argparse
import logging
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import gzip
import csv


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/historical-data.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DataRetentionPolicy:
    """Data retention policy configuration."""
    quality_snapshots_days: int = 90
    drift_reports_days: int = 30
    catalog_snapshots_days: int = 365
    execution_logs_days: int = 30
    max_storage_gb: float = 10.0


@dataclass
class HistoricalSnapshot:
    """Represents a historical data snapshot."""
    file_path: Path
    data_type: str  # 'quality', 'drift', 'catalog', 'execution'
    timestamp: datetime
    file_size_bytes: int
    compressed: bool


class HistoricalDataManager:
    """Manages historical platform data with retention and querying."""

    def __init__(self, base_dir: str = "analysis/historical"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Load retention policy
        self.policy = self._load_retention_policy()

    def _load_retention_policy(self) -> DataRetentionPolicy:
        """Load data retention policy."""
        policy_file = Path("config/retention-policy.yaml")

        if policy_file.exists():
            with open(policy_file) as f:
                config = yaml.safe_load(f)

            return DataRetentionPolicy(**config.get('retention', {}))
        else:
            logger.info("Using default retention policy")
            return DataRetentionPolicy()

    def archive_current_data(self, data_types: List[str] = None) -> List[HistoricalSnapshot]:
        """Archive current data snapshots to historical storage."""
        logger.info("Archiving current data to historical storage...")

        if not data_types:
            data_types = ['quality', 'drift', 'catalog', 'execution']

        archived_snapshots = []

        for data_type in data_types:
            snapshots = self._archive_data_type(data_type)
            archived_snapshots.extend(snapshots)

        logger.info(f"Archived {len(archived_snapshots)} snapshots")
        return archived_snapshots

    def _archive_data_type(self, data_type: str) -> List[HistoricalSnapshot]:
        """Archive snapshots for a specific data type."""
        archived = []

        # Define source and destination paths
        source_paths = self._get_source_paths(data_type)
        dest_dir = self.base_dir / data_type
        dest_dir.mkdir(exist_ok=True)

        for source_path in source_paths:
            if source_path.exists():
                try:
                    # Generate timestamped filename
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{data_type}_{timestamp}.json"

                    if data_type == 'quality' and 'latest' in source_path.name:
                        filename = f"quality_{timestamp}.json"
                    elif data_type == 'drift' and 'latest' in source_path.name:
                        filename = f"drift_{timestamp}.json"

                    dest_path = dest_dir / filename

                    # Copy file
                    shutil.copy2(source_path, dest_path)

                    # Create snapshot record
                    snapshot = HistoricalSnapshot(
                        file_path=dest_path,
                        data_type=data_type,
                        timestamp=datetime.now(timezone.utc),
                        file_size_bytes=dest_path.stat().st_size,
                        compressed=False
                    )

                    archived.append(snapshot)
                    logger.info(f"Archived {data_type} snapshot: {filename}")

                except Exception as e:
                    logger.error(f"Failed to archive {data_type} from {source_path}: {e}")

        return archived

    def _get_source_paths(self, data_type: str) -> List[Path]:
        """Get source file paths for a data type."""
        sources = []

        if data_type == 'quality':
            # Quality snapshots
            sources.append(Path("catalog/latest_quality_snapshot.json"))
            sources.append(Path("catalog/quality-snapshot.json"))
        elif data_type == 'drift':
            # Drift reports
            sources.append(Path("catalog/latest_drift_report.json"))
        elif data_type == 'catalog':
            # Catalog snapshots
            sources.append(Path("catalog/service-index.json"))
            sources.append(Path("catalog/service-index.yaml"))
        elif data_type == 'execution':
            # Execution logs and reports
            sources.extend(Path("analysis/reports").glob("*execution*.json"))

        return sources

    def enforce_retention_policy(self) -> Dict[str, int]:
        """Enforce data retention policy by removing old files."""
        logger.info("Enforcing data retention policy...")

        cleanup_stats = {'files_removed': 0, 'space_freed_bytes': 0}

        # Define retention periods
        retention_periods = {
            'quality': timedelta(days=self.policy.quality_snapshots_days),
            'drift': timedelta(days=self.policy.drift_reports_days),
            'catalog': timedelta(days=self.policy.catalog_snapshots_days),
            'execution': timedelta(days=self.policy.execution_logs_days)
        }

        # Check each data type directory
        for data_type, retention_period in retention_periods.items():
            type_dir = self.base_dir / data_type
            if not type_dir.exists():
                continue

            cutoff_date = datetime.now(timezone.utc) - retention_period

            # Find and remove old files
            for file_path in type_dir.glob(f"{data_type}_*.json"):
                try:
                    # Parse timestamp from filename
                    filename = file_path.stem
                    timestamp_str = filename.replace(f"{data_type}_", "")

                    file_timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                    if file_timestamp < cutoff_date:
                        file_size = file_path.stat().st_size
                        file_path.unlink()

                        cleanup_stats['files_removed'] += 1
                        cleanup_stats['space_freed_bytes'] += file_size

                        logger.info(f"Removed old {data_type} snapshot: {file_path.name}")

                except (ValueError, OSError) as e:
                    logger.warning(f"Failed to process {data_type} file {file_path}: {e}")

        logger.info(f"Retention cleanup complete: {cleanup_stats['files_removed']} files removed, {cleanup_stats['space_freed_bytes']/1024/1024:.1f}MB freed")
        return cleanup_stats

    def query_historical_data(self, data_type: str, service_name: str = None,
                            start_date: datetime = None, end_date: datetime = None) -> List[Dict[str, Any]]:
        """Query historical data for a service or data type."""
        logger.info(f"Querying historical {data_type} data...")

        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        query_results = []

        # Find relevant files
        data_dir = self.base_dir / data_type
        if not data_dir.exists():
            logger.warning(f"Historical data directory not found: {data_dir}")
            return query_results

        for snapshot_file in data_dir.glob(f"{data_type}_*.json"):
            try:
                # Parse timestamp from filename
                filename = snapshot_file.stem
                timestamp_str = filename.replace(f"{data_type}_", "")

                file_timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                # Check if file is in date range
                if start_date <= file_timestamp <= end_date:
                    # Load and filter data
                    with open(snapshot_file) as f:
                        data = json.load(f)

                    if service_name:
                        # Filter for specific service
                        if data_type == 'quality' and 'services' in data:
                            service_data = data['services'].get(service_name)
                            if service_data:
                                query_results.append({
                                    'timestamp': file_timestamp.isoformat(),
                                    'service': service_name,
                                    'data': service_data
                                })
                        elif data_type == 'drift' and 'issues' in data:
                            service_issues = [i for i in data['issues'] if i.get('service') == service_name]
                            if service_issues:
                                query_results.append({
                                    'timestamp': file_timestamp.isoformat(),
                                    'service': service_name,
                                    'data': {'issues': service_issues}
                                })
                    else:
                        # Return full snapshot
                        query_results.append({
                            'timestamp': file_timestamp.isoformat(),
                            'data': data
                        })

            except Exception as e:
                logger.warning(f"Failed to process historical file {snapshot_file}: {e}")

        # Sort by timestamp
        query_results.sort(key=lambda x: x['timestamp'])
        logger.info(f"Found {len(query_results)} historical records for {data_type}")

        return query_results

    def compress_old_snapshots(self, days_threshold: int = 7) -> int:
        """Compress snapshots older than threshold days."""
        logger.info(f"Compressing snapshots older than {days_threshold} days...")

        compressed_count = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

        # Process each data type directory
        for data_type in ['quality', 'drift', 'catalog', 'execution']:
            data_dir = self.base_dir / data_type
            if not data_dir.exists():
                continue

            for snapshot_file in data_dir.glob(f"{data_type}_*.json"):
                try:
                    # Parse timestamp from filename
                    filename = snapshot_file.stem
                    timestamp_str = filename.replace(f"{data_type}_", "")

                    file_timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                    if file_timestamp < cutoff_date and not snapshot_file.name.endswith('.gz'):
                        # Compress file
                        compressed_path = snapshot_file.with_suffix('.json.gz')

                        with open(snapshot_file, 'rb') as f_in:
                            with gzip.open(compressed_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)

                        # Remove original file
                        snapshot_file.unlink()

                        compressed_count += 1
                        logger.info(f"Compressed {data_type} snapshot: {snapshot_file.name}")

                except Exception as e:
                    logger.warning(f"Failed to compress {data_type} file {snapshot_file}: {e}")

        logger.info(f"Compressed {compressed_count} historical snapshots")
        return compressed_count

    def export_time_series_data(self, data_type: str, service_name: str = None,
                              start_date: datetime = None, end_date: datetime = None,
                              output_format: str = "csv") -> Optional[str]:
        """Export time-series data to CSV or JSON format."""
        logger.info(f"Exporting {data_type} time-series data...")

        # Query historical data
        historical_data = self.query_historical_data(data_type, service_name, start_date, end_date)

        if not historical_data:
            logger.warning(f"No historical data found for {data_type}")
            return None

        # Prepare export data
        export_data = []

        for record in historical_data:
            timestamp = record['timestamp']
            data = record.get('data', {})

            if service_name and data_type == 'quality':
                # Extract service-specific metrics
                service_data = data.get('services', {}).get(service_name, {})
                export_data.append({
                    'timestamp': timestamp,
                    'service': service_name,
                    'score': service_data.get('score', 0),
                    'grade': service_data.get('grade', 'F'),
                    'coverage': service_data.get('metrics', {}).get('coverage', 0),
                    'critical_vulns': service_data.get('metrics', {}).get('critical_vulns', 0)
                })
            elif service_name and data_type == 'drift':
                # Extract service-specific drift data
                service_issues = data.get('issues', [])
                export_data.append({
                    'timestamp': timestamp,
                    'service': service_name,
                    'drift_issues': len(service_issues),
                    'high_severity_issues': len([i for i in service_issues if i.get('severity') in ['high', 'error']])
                })
            else:
                # Export full snapshot metadata
                export_data.append({
                    'timestamp': timestamp,
                    'total_services': data.get('metadata', {}).get('total_services', 0),
                    'avg_score': data.get('global', {}).get('avg_score', 0) if data_type == 'quality' else 0
                })

        # Export to requested format
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{data_type}_{service_name or 'all'}_{timestamp}.{output_format}"

        if output_format == 'csv':
            return self._export_to_csv(export_data, filename)
        elif output_format == 'json':
            return self._export_to_json(export_data, filename)
        else:
            logger.error(f"Unsupported export format: {output_format}")
            return None

    def _export_to_csv(self, data: List[Dict[str, Any]], filename: str) -> str:
        """Export data to CSV format."""
        if not data:
            return None

        # Determine CSV columns from first row
        fieldnames = list(data[0].keys())

        # Create CSV file
        csv_path = self.base_dir / filename
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Exported {len(data)} records to {csv_path}")
        return str(csv_path)

    def _export_to_json(self, data: List[Dict[str, Any]], filename: str) -> str:
        """Export data to JSON format."""
        json_path = self.base_dir / filename

        export_data = {
            'metadata': {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'record_count': len(data),
                'columns': list(data[0].keys()) if data else []
            },
            'data': data
        }

        with open(json_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(data)} records to {json_path}")
        return str(json_path)

    def get_storage_summary(self) -> Dict[str, Any]:
        """Get storage usage summary."""
        summary = {
            'total_files': 0,
            'total_size_bytes': 0,
            'data_types': {},
            'oldest_snapshot': None,
            'newest_snapshot': None
        }

        # Analyze each data type directory
        for data_type in ['quality', 'drift', 'catalog', 'execution']:
            type_dir = self.base_dir / data_type
            if not type_dir.exists():
                continue

            type_stats = {
                'files': 0,
                'size_bytes': 0,
                'compressed_files': 0,
                'oldest': None,
                'newest': None
            }

            for file_path in type_dir.glob("*"):
                if file_path.is_file():
                    type_stats['files'] += 1
                    file_size = file_path.stat().st_size
                    type_stats['size_bytes'] += file_size

                    # Track oldest/newest
                    file_timestamp = self._extract_timestamp_from_filename(file_path.name, data_type)
                    if file_timestamp:
                        if not type_stats['oldest'] or file_timestamp < type_stats['oldest']:
                            type_stats['oldest'] = file_timestamp
                        if not type_stats['newest'] or file_timestamp > type_stats['newest']:
                            type_stats['newest'] = file_timestamp

                    # Check if compressed
                    if file_path.suffix == '.gz':
                        type_stats['compressed_files'] += 1

            summary['data_types'][data_type] = type_stats
            summary['total_files'] += type_stats['files']
            summary['total_size_bytes'] += type_stats['size_bytes']

        # Set global oldest/newest
        all_timestamps = []
        for type_stats in summary['data_types'].values():
            if type_stats['oldest']:
                all_timestamps.append(type_stats['oldest'])
            if type_stats['newest']:
                all_timestamps.append(type_stats['newest'])

        if all_timestamps:
            summary['oldest_snapshot'] = min(all_timestamps).isoformat()
            summary['newest_snapshot'] = max(all_timestamps).isoformat()

        return summary

    def _extract_timestamp_from_filename(self, filename: str, data_type: str) -> Optional[datetime]:
        """Extract timestamp from filename."""
        try:
            # Expected format: {data_type}_YYYYMMDD_HHMMSS.json
            timestamp_str = filename.replace(f"{data_type}_", "").replace(".json.gz", "").replace(".json", "")
            return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        except (ValueError, AttributeError):
            return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Manage historical platform data")
    parser.add_argument("--archive", action="store_true", help="Archive current data to historical storage")
    parser.add_argument("--retention-days", type=int, default=90, help="Retention period in days")
    parser.add_argument("--query", action="store_true", help="Query historical data")
    parser.add_argument("--data-type", choices=["quality", "drift", "catalog", "execution"],
                       help="Data type to query")
    parser.add_argument("--service", type=str, help="Specific service to query")
    parser.add_argument("--days", type=int, default=30, help="Days to look back for query")
    parser.add_argument("--export", type=str, choices=["csv", "json"], help="Export format")
    parser.add_argument("--compress", action="store_true", help="Compress old snapshots")
    parser.add_argument("--compress-threshold-days", type=int, default=7,
                       help="Compress snapshots older than N days")
    parser.add_argument("--storage-summary", action="store_true", help="Show storage usage summary")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        manager = HistoricalDataManager()

        if args.archive:
            # Archive current data
            snapshots = manager.archive_current_data()
            print(f"✅ Archived {len(snapshots)} snapshots")

        if args.query and args.data_type:
            # Query historical data
            start_date = datetime.now(timezone.utc) - timedelta(days=args.days)
            results = manager.query_historical_data(
                args.data_type, args.service, start_date
            )

            print(f"📊 Found {len(results)} historical records")

            if args.export:
                # Export results
                export_path = manager.export_time_series_data(
                    args.data_type, args.service, start_date, output_format=args.export
                )
                if export_path:
                    print(f"📁 Exported data to {export_path}")

        if args.compress:
            # Compress old snapshots
            compressed = manager.compress_old_snapshots(args.compress_threshold_days)
            print(f"🗜️ Compressed {compressed} snapshots")

        if args.storage_summary:
            # Show storage summary
            summary = manager.get_storage_summary()
            print("\n💾 Historical Data Storage Summary:")
            print(f"  Total Files: {summary['total_files']}")
            print(f"  Total Size: {summary['total_size_bytes']/1024/1024:.1f}MB")

            for data_type, stats in summary['data_types'].items():
                print(f"  {data_type.title()}: {stats['files']} files, {stats['size_bytes']/1024/1024:.1f}MB")

            if summary['oldest_snapshot']:
                print(f"  Oldest Snapshot: {summary['oldest_snapshot']}")
            if summary['newest_snapshot']:
                print(f"  Newest Snapshot: {summary['newest_snapshot']}")

    except Exception as e:
        logger.error(f"Historical data management failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
