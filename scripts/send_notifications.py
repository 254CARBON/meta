#!/usr/bin/env python3
"""
254Carbon Meta Repository - Unified Notification System

Sends notifications to multiple channels with templates and retry logic.

Usage:
    python scripts/send_notifications.py --type quality --channel slack --priority high
"""

import os
import sys
import json
import yaml
import argparse
import logging
import smtplib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import jinja2


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/notifications.log')
    ]
)
logger = logging.getLogger(__name__)


class NotificationClient:
    """Client for sending notifications to various platforms."""

    def __init__(self):
        # Configure retry strategy for HTTP requests
        self.retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self.adapter = HTTPAdapter(max_retries=self.retry_strategy)

    def send_slack_message(self, webhook_url: str, message: str, channel: str = None) -> bool:
        """Send message to Slack."""
        payload = {
            "text": message,
            "mrkdwn": True
        }

        if channel:
            payload["channel"] = channel

        try:
            session = requests.Session()
            session.mount("https://", self.adapter)

            response = session.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info("✅ Notification sent to Slack")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send Slack notification: {e}")
            return False

    def send_discord_message(self, webhook_url: str, message: str, username: str = "254Carbon Meta") -> bool:
        """Send message to Discord."""
        payload = {
            "content": message,
            "username": username
        }

        try:
            session = requests.Session()
            session.mount("https://", self.adapter)

            response = session.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info("✅ Notification sent to Discord")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send Discord notification: {e}")
            return False

    def send_email(self, smtp_server: str, smtp_port: int, username: str, password: str,
                  to_addresses: List[str], subject: str, body: str) -> bool:
        """Send email notification."""
        try:
            msg = MimeText(body, "html")
            msg['Subject'] = subject
            msg['From'] = username
            msg['To'] = ", ".join(to_addresses)

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
            server.quit()

            logger.info(f"✅ Email notification sent to {len(to_addresses)} recipients")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send email notification: {e}")
            return False


class NotificationManager:
    """Manages notification sending with templates and routing."""

    def __init__(self, config_file: str = None):
        self.config_file = config_file or "config/notifications.yaml"

        # Load configuration
        self.config = self._load_config()

        # Initialize notification client
        self.client = NotificationClient()

        # Setup Jinja2 for templating
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("analysis/templates/notifications/"),
            autoescape=True
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load notification configuration."""
        config_path = Path(self.config_file)

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default notification configuration."""
        return {
            'channels': {
                'slack': {
                    'webhook': os.getenv('SLACK_WEBHOOK'),
                    'default_channel': '#platform-health'
                },
                'discord': {
                    'webhook': os.getenv('DISCORD_WEBHOOK'),
                    'username': '254Carbon Meta'
                },
                'email': {
                    'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                    'smtp_port': int(os.getenv('SMTP_PORT', '587')),
                    'username': os.getenv('SMTP_USERNAME'),
                    'password': os.getenv('SMTP_PASSWORD'),
                    'default_recipients': os.getenv('NOTIFICATION_EMAILS', '').split(',')
                }
            },
            'templates': {
                'quality_summary': 'quality-summary-notification.md.j2',
                'drift_alert': 'drift-alert-notification.md.j2',
                'release_status': 'release-status-notification.md.j2',
                'error_alert': 'error-alert-notification.md.j2'
            },
            'routing': {
                'high_priority': {
                    'slack': ['#platform-alerts', '#engineering'],
                    'discord': ['#alerts'],
                    'email': ['platform-team@254carbon.com', 'engineering@254carbon.com']
                },
                'medium_priority': {
                    'slack': ['#platform-health'],
                    'discord': ['#updates'],
                    'email': ['platform-team@254carbon.com']
                },
                'low_priority': {
                    'slack': ['#platform-updates'],
                    'discord': ['#info'],
                    'email': []
                }
            }
        }

    def send_notification(self, notification_type: str, priority: str = "medium",
                         data: Dict[str, Any] = None, custom_message: str = None) -> bool:
        """Send notification through configured channels."""
        logger.info(f"Sending {priority} priority {notification_type} notification")

        if not data:
            data = {}

        # Determine routing based on priority
        routing = self.config.get('routing', {}).get(priority, {})

        success_count = 0
        total_channels = 0

        # Send to Slack
        slack_channels = routing.get('slack', [])
        for channel in slack_channels:
            if self._send_slack_notification(notification_type, priority, data, custom_message, channel):
                success_count += 1
            total_channels += 1

        # Send to Discord
        discord_channels = routing.get('discord', [])
        for channel in discord_channels:
            if self._send_discord_notification(notification_type, priority, data, custom_message, channel):
                success_count += 1
            total_channels += 1

        # Send email
        email_recipients = routing.get('email', [])
        if email_recipients:
            if self._send_email_notification(notification_type, priority, data, custom_message, email_recipients):
                success_count += 1
            total_channels += 1

        logger.info(f"Notification sent to {success_count}/{total_channels} channels")
        return success_count > 0

    def _send_slack_notification(self, notification_type: str, priority: str,
                                data: Dict[str, Any], custom_message: str, channel: str) -> bool:
        """Send notification to Slack."""
        webhook = self.config.get('channels', {}).get('slack', {}).get('webhook')
        if not webhook:
            logger.warning("Slack webhook not configured")
            return False

        # Generate message
        if custom_message:
            message = custom_message
        else:
            message = self._generate_slack_message(notification_type, priority, data)

        return self.client.send_slack_message(webhook, message, channel)

    def _send_discord_notification(self, notification_type: str, priority: str,
                                  data: Dict[str, Any], custom_message: str, channel: str) -> bool:
        """Send notification to Discord."""
        webhook = self.config.get('channels', {}).get('discord', {}).get('webhook')
        if not webhook:
            logger.warning("Discord webhook not configured")
            return False

        # Generate message
        if custom_message:
            message = custom_message
        else:
            message = self._generate_discord_message(notification_type, priority, data)

        return self.client.send_discord_message(webhook, message)

    def _send_email_notification(self, notification_type: str, priority: str,
                                data: Dict[str, Any], custom_message: str, recipients: List[str]) -> bool:
        """Send notification via email."""
        email_config = self.config.get('channels', {}).get('email', {})

        required_fields = ['smtp_server', 'smtp_port', 'username', 'password']
        if not all(field in email_config for field in required_fields):
            logger.warning("Email configuration incomplete")
            return False

        # Generate message
        if custom_message:
            body = custom_message
        else:
            body = self._generate_email_message(notification_type, priority, data)

        subject = f"254Carbon Meta - {notification_type.replace('_', ' ').title()} ({priority})"

        return self.client.send_email(
            email_config['smtp_server'],
            email_config['smtp_port'],
            email_config['username'],
            email_config['password'],
            recipients,
            subject,
            body
        )

    def _generate_slack_message(self, notification_type: str, priority: str, data: Dict[str, Any]) -> str:
        """Generate Slack-formatted message."""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        # Priority emoji
        priority_emojis = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }

        emoji = priority_emojis.get(priority, 'ℹ️')

        # Base message
        message = f"""{emoji} *254Carbon Meta Notification*

*Type:* {notification_type.replace('_', ' ').title()}
*Priority:* {priority.title()}
*Time:* {timestamp}

"""

        # Add type-specific content
        if notification_type == 'quality_summary':
            message += self._format_quality_slack(data)
        elif notification_type == 'drift_alert':
            message += self._format_drift_slack(data)
        elif notification_type == 'release_status':
            message += self._format_release_slack(data)
        elif notification_type == 'error_alert':
            message += self._format_error_slack(data)
        else:
            message += "*No specific formatting available for this notification type.*"

        message += "\n---\n*🤖 Automated by 254Carbon Meta*"

        return message

    def _format_quality_slack(self, data: Dict[str, Any]) -> str:
        """Format quality data for Slack."""
        avg_score = data.get('global', {}).get('avg_score', 0)
        total_services = data.get('metadata', {}).get('total_services', 0)

        return f"""📊 *Quality Summary*
• Average Score: {avg_score:.1f}/100
• Services: {total_services}
• Status: {'✅ Healthy' if avg_score >= 80 else '⚠️ Needs Attention' if avg_score >= 70 else '🚨 Critical'}

[View Full Report](https://github.com/254carbon/254carbon-meta)
"""

    def _format_drift_slack(self, data: Dict[str, Any]) -> str:
        """Format drift data for Slack."""
        total_issues = data.get('metadata', {}).get('total_issues', 0)
        high_issues = data.get('summary', {}).get('issues_by_severity', {}).get('high', 0)

        return f"""🔍 *Drift Detection*
• Total Issues: {total_issues}
• High Priority: {high_issues}
• Status: {'✅ Clean' if total_issues == 0 else '⚠️ Issues Found'}

[View Drift Report](https://github.com/254carbon/254carbon-meta)
"""

    def _format_release_slack(self, data: Dict[str, Any]) -> str:
        """Format release data for Slack."""
        train_name = data.get('train_name', 'Unknown')
        status = data.get('status', 'unknown')

        return f"""🚂 *Release Train: {train_name}*
• Status: {status.title()}
• Participants: {len(data.get('participants', []))}
• Duration: {data.get('execution_time', 'N/A')}

[View Release Report](https://github.com/254carbon/254carbon-meta)
"""

    def _format_error_slack(self, data: Dict[str, Any]) -> str:
        """Format error data for Slack."""
        error_type = data.get('error_type', 'Unknown')
        error_message = data.get('error_message', 'No details available')

        return f"""❌ *Error Alert*
• Type: {error_type}
• Message: {error_message}

[View Logs](https://github.com/254carbon/254carbon-meta/actions)
"""

    def _generate_discord_message(self, notification_type: str, priority: str, data: Dict[str, Any]) -> str:
        """Generate Discord-formatted message."""
        # Similar to Slack but adapted for Discord formatting
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        priority_emojis = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }

        emoji = priority_emojis.get(priority, 'ℹ️')

        message = f"""{emoji} **254Carbon Meta Notification**

**Type:** {notification_type.replace('_', ' ').title()}
**Priority:** {priority.title()}
**Time:** {timestamp}

"""

        # Add type-specific content (simplified for Discord)
        if notification_type == 'quality_summary':
            avg_score = data.get('global', {}).get('avg_score', 0)
            message += f"📊 **Quality Summary:** {avg_score:.1f}/100 average score"
        elif notification_type == 'drift_alert':
            total_issues = data.get('metadata', {}).get('total_issues', 0)
            message += f"🔍 **Drift Detection:** {total_issues} issues found"
        elif notification_type == 'release_status':
            train_name = data.get('train_name', 'Unknown')
            message += f"🚂 **Release Train:** {train_name}"
        elif notification_type == 'error_alert':
            error_type = data.get('error_type', 'Unknown')
            message += f"❌ **Error Alert:** {error_type}"

        message += "\n\n---\n🤖 Automated by 254Carbon Meta"

        return message

    def _generate_email_message(self, notification_type: str, priority: str, data: Dict[str, Any]) -> str:
        """Generate HTML email message."""
        # Generate HTML email with rich formatting
        html = f"""
<html>
<head>
    <title>254Carbon Meta - {notification_type.replace('_', ' ').title()}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .priority-high {{ color: #d32f2f; }}
        .priority-medium {{ color: #f57c00; }}
        .priority-low {{ color: #388e3c; }}
        .content {{ margin: 20px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>254Carbon Meta Notification</h2>
        <p><strong>Type:</strong> {notification_type.replace('_', ' ').title()}</p>
        <p><strong>Priority:</strong> <span class="priority-{priority}">{priority.title()}</span></p>
        <p><strong>Generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>

    <div class="content">
"""

        # Add type-specific content
        if notification_type == 'quality_summary':
            html += self._format_quality_email(data)
        elif notification_type == 'drift_alert':
            html += self._format_drift_email(data)
        elif notification_type == 'release_status':
            html += self._format_release_email(data)
        elif notification_type == 'error_alert':
            html += self._format_error_email(data)
        else:
            html += "<p>Detailed information not available for this notification type.</p>"

        html += """
    </div>

    <div class="footer">
        <p>This is an automated notification from the 254Carbon Meta platform governance system.</p>
        <p>For questions or issues, please contact the platform team.</p>
        <p><a href="https://github.com/254carbon/254carbon-meta">View Platform Dashboard</a></p>
    </div>
</body>
</html>
"""

        return html

    def _format_quality_email(self, data: Dict[str, Any]) -> str:
        """Format quality data for email."""
        avg_score = data.get('global', {}).get('avg_score', 0)
        total_services = data.get('metadata', {}).get('total_services', 0)
        grade_distribution = data.get('global', {}).get('grade_distribution', {})

        return f"""
        <h3>📊 Quality Summary</h3>
        <ul>
            <li><strong>Average Score:</strong> {avg_score:.1f}/100</li>
            <li><strong>Total Services:</strong> {total_services}</li>
            <li><strong>Grade Distribution:</strong> {', '.join([f"{grade}: {count}" for grade, count in grade_distribution.items()])}</li>
        </ul>
        <p><a href="https://github.com/254carbon/254carbon-meta">View Full Quality Report</a></p>
        """

    def _format_drift_email(self, data: Dict[str, Any]) -> str:
        """Format drift data for email."""
        total_issues = data.get('metadata', {}).get('total_issues', 0)
        high_issues = data.get('summary', {}).get('issues_by_severity', {}).get('high', 0)

        return f"""
        <h3>🔍 Drift Detection Results</h3>
        <ul>
            <li><strong>Total Issues:</strong> {total_issues}</li>
            <li><strong>High Priority Issues:</strong> {high_issues}</li>
        </ul>
        <p><a href="https://github.com/254carbon/254carbon-meta">View Drift Report</a></p>
        """

    def _format_release_email(self, data: Dict[str, Any]) -> str:
        """Format release data for email."""
        train_name = data.get('train_name', 'Unknown')
        status = data.get('status', 'unknown')

        return f"""
        <h3>🚂 Release Train: {train_name}</h3>
        <ul>
            <li><strong>Status:</strong> {status.title()}</li>
            <li><strong>Participants:</strong> {len(data.get('participants', []))}</li>
        </ul>
        <p><a href="https://github.com/254carbon/254carbon-meta">View Release Report</a></p>
        """

    def _format_error_email(self, data: Dict[str, Any]) -> str:
        """Format error data for email."""
        error_type = data.get('error_type', 'Unknown')
        error_message = data.get('error_message', 'No details available')

        return f"""
        <h3>❌ Error Alert</h3>
        <ul>
            <li><strong>Error Type:</strong> {error_type}</li>
            <li><strong>Message:</strong> {error_message}</li>
        </ul>
        <p><a href="https://github.com/254carbon/254carbon-meta/actions">View Logs</a></p>
        """


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Send unified notifications to multiple channels")
    parser.add_argument("--type", required=True, choices=['quality_summary', 'drift_alert', 'release_status', 'error_alert'],
                       help="Type of notification to send")
    parser.add_argument("--priority", choices=['low', 'medium', 'high'], default='medium',
                       help="Notification priority (default: medium)")
    parser.add_argument("--channel", choices=['slack', 'discord', 'email', 'all'], default='all',
                       help="Channel to send to (default: all)")
    parser.add_argument("--data-file", type=str, help="JSON file containing notification data")
    parser.add_argument("--custom-message", type=str, help="Custom message to send (overrides template)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without sending")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load notification data if provided
        data = {}
        if args.data_file:
            with open(args.data_file) as f:
                data = json.load(f)

        manager = NotificationManager()

        if args.dry_run:
            # Show what would be sent
            print("📨 Notification Preview:")
            print("=" * 50)

            if args.channel in ['slack', 'all']:
                print("\nSlack Message:")
                print("-" * 30)
                print(manager._generate_slack_message(args.type, args.priority, data))

            if args.channel in ['discord', 'all']:
                print("\nDiscord Message:")
                print("-" * 30)
                print(manager._generate_discord_message(args.type, args.priority, data))

            if args.channel in ['email', 'all']:
                print("\nEmail Content:")
                print("-" * 30)
                print(manager._generate_email_message(args.type, args.priority, data))
        else:
            # Send actual notifications
            success = manager.send_notification(args.type, args.priority, data, args.custom_message)

            if success:
                print("✅ Notifications sent successfully")
            else:
                print("❌ Failed to send notifications")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Notification sending failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
