#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Summary Notifications

Posts quality summaries to Slack/Discord channels.

Usage:
    python scripts/post_quality_summary.py [--webhook-type slack|discord]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/quality-notifications.log')
    ]
)
logger = logging.getLogger(__name__)


class NotificationClient:
    """Client for posting notifications to various platforms."""

    def __init__(self, webhook_type: str = "slack"):
        self.webhook_type = webhook_type

    def post_to_slack(self, webhook_url: str, message: str, channel: str = None) -> bool:
        """Post message to Slack."""
        payload = {
            "text": message,
            "mrkdwn": True
        }

        if channel:
            payload["channel"] = channel

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Posted quality summary to Slack")
            return True
        except Exception as e:
            logger.error(f"Failed to post to Slack: {e}")
            return False

    def post_to_discord(self, webhook_url: str, message: str, username: str = "254Carbon Meta",
                       avatar_url: str = None) -> bool:
        """Post message to Discord."""
        payload = {
            "content": message,
            "username": username
        }

        if avatar_url:
            payload["avatar_url"] = avatar_url

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Posted quality summary to Discord")
            return True
        except Exception as e:
            logger.error(f"Failed to post to Discord: {e}")
            return False


class QualityNotificationManager:
    """Manages quality summary notifications."""

    def __init__(self):
        # Load quality data
        self.quality_data = self._load_quality_data()

    def _load_quality_data(self) -> Dict[str, Any]:
        """Load latest quality snapshot."""
        quality_file = Path("catalog/latest_quality_snapshot.json")

        if not quality_file.exists():
            logger.error("No quality data found. Run 'make quality' first.")
            return {}

        try:
            with open(quality_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load quality data: {e}")
            return {}

    def generate_slack_message(self) -> str:
        """Generate Slack-formatted quality summary."""
        if not self.quality_data:
            return "❌ No quality data available"

        global_data = self.quality_data.get('global', {})
        services = self.quality_data.get('services', {})

        avg_score = global_data.get('avg_score', 0)
        total_services = len(services)

        # Determine overall health
        if avg_score >= 85:
            health_icon = "🟢"
            health_status = "Excellent"
        elif avg_score >= 75:
            health_icon = "🟡"
            health_status = "Good"
        elif avg_score >= 65:
            health_icon = "🟠"
            health_status = "Fair"
        else:
            health_icon = "🔴"
            health_status = "Needs Attention"

        # Count issues
        failing_services = len([s for s in services.values() if s.get('status') == 'failing'])
        warning_services = len([s for s in services.values() if s.get('status') == 'warning'])

        # Generate grade distribution
        grade_distribution = global_data.get('grade_distribution', {})
        grade_summary = ", ".join([f"{grade}: {count}" for grade, count in grade_distribution.items()])

        message = f"""📊 *Quality Summary* - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

{health_icon} *Platform Health:* {health_status} ({avg_score:.1f})
📈 *Services:* {total_services} total
🎯 *Grade Distribution:* {grade_summary}

⚠️ *Issues:*
• Failing: {failing_services} services
• Warning: {warning_services} services

🔍 *Recent Trends:* Quality monitoring active
📋 *Full Report:* [View Dashboard](https://github.com/254carbon/254carbon-meta)

---
*🤖 Automated by 254Carbon Meta*
"""

        return message

    def generate_discord_message(self) -> str:
        """Generate Discord-formatted quality summary."""
        if not self.quality_data:
            return "❌ No quality data available"

        global_data = self.quality_data.get('global', {})
        services = self.quality_data.get('services', {})

        avg_score = global_data.get('avg_score', 0)
        total_services = len(services)

        # Determine overall health with emoji
        if avg_score >= 85:
            health_emoji = "🟢"
            health_status = "Excellent"
        elif avg_score >= 75:
            health_emoji = "🟡"
            health_status = "Good"
        elif avg_score >= 65:
            health_emoji = "🟠"
            health_status = "Fair"
        else:
            health_emoji = "🔴"
            health_status = "Needs Attention"

        # Count issues
        failing_services = len([s for s in services.values() if s.get('status') == 'failing'])
        warning_services = len([s for s in services.values() if s.get('status') == 'warning'])

        # Generate grade distribution
        grade_distribution = global_data.get('grade_distribution', {})
        grade_summary = " | ".join([f"{grade}: {count}" for grade, count in grade_distribution.items()])

        message = f"""📊 **Quality Summary** - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

{health_emoji} **Platform Health:** {health_status} ({avg_score:.1f}/100)
📈 **Services:** {total_services} total
🎯 **Grade Distribution:** {grade_summary}

⚠️ **Issues:**
• Failing: {failing_services} services
• Warning: {warning_services} services

🔍 **Recent Trends:** Quality monitoring active
📋 **Full Report:** https://github.com/254carbon/254carbon-meta

---
🤖 Automated by 254Carbon Meta
"""

        return message

    def post_notifications(self, webhook_type: str = "slack") -> bool:
        """Post quality summary to configured webhooks."""
        success = False

        if webhook_type == "slack" or webhook_type == "both":
            slack_webhook = os.getenv("SLACK_WEBHOOK")
            if slack_webhook:
                client = NotificationClient("slack")
                message = self.generate_slack_message()
                if client.post_to_slack(slack_webhook, message, "#platform-health"):
                    success = True

        if webhook_type == "discord" or webhook_type == "both":
            discord_webhook = os.getenv("DISCORD_WEBHOOK")
            if discord_webhook:
                client = NotificationClient("discord")
                message = self.generate_discord_message()
                if client.post_to_discord(discord_webhook, message):
                    success = True

        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Post quality summaries to notification channels")
    parser.add_argument("--webhook-type", choices=["slack", "discord", "both"], default="slack",
                       help="Type of webhook to use (default: slack)")
    parser.add_argument("--dry-run", action="store_true", help="Show message without posting")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        manager = QualityNotificationManager()

        if args.dry_run:
            # Show what would be posted
            if args.webhook_type in ["slack", "both"]:
                print("Slack Message:")
                print("-" * 40)
                print(manager.generate_slack_message())

            if args.webhook_type in ["discord", "both"]:
                print("\nDiscord Message:")
                print("-" * 40)
                print(manager.generate_discord_message())
        else:
            # Post to webhooks
            success = manager.post_notifications(args.webhook_type)

            if success:
                print("✅ Quality summary posted successfully")
            else:
                print("❌ Failed to post quality summary")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Quality notification posting failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
