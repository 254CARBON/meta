#!/usr/bin/env python3
"""
254Carbon Meta Repository - Notification System

Multi-channel notification system supporting Slack, email, PagerDuty, and GitHub Issues.
Provides rich formatting, templating, and delivery tracking.

Usage:
    python scripts/send_notifications.py --channel slack --message "Service discovery complete"
    python scripts/send_notifications.py --config config/notifications.yaml --event quality_threshold_breach

Features:
- Slack integration with webhooks and rich formatting
- Email system with SMTP and templates
- PagerDuty integration for critical alerts
- GitHub Issues for automated issue creation
- Template-based message formatting
- Delivery tracking and retry logic
- Multi-channel routing based on event types
"""

import os
import sys
import json
import yaml
import argparse
import logging
import smtplib
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import time

from scripts.utils import audit_logger, monitor_execution

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/notifications.log')
    ]
)
logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Notification channel types."""
    SLACK = "slack"
    EMAIL = "email"
    PAGERDUTY = "pagerduty"
    GITHUB_ISSUE = "github_issue"


class NotificationSeverity(Enum):
    """Notification severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class NotificationMessage:
    """Represents a notification message."""
    title: str
    content: str
    severity: NotificationSeverity
    channel: NotificationChannel
    metadata: Dict[str, Any] = field(default_factory=dict)
    template: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class NotificationResult:
    """Result of notification delivery."""
    success: bool
    channel: NotificationChannel
    message_id: Optional[str] = None
    error: Optional[str] = None
    delivery_time: Optional[datetime] = None
    retry_count: int = 0


class NotificationSender:
    """Main notification sender class."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the notification sender."""
        self.config_path = config_path or 'config/notifications.yaml'
        self.config = self._load_config()
        self.templates_dir = Path('analysis/templates/notifications')
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize channel senders
        self.slack_sender = SlackNotificationSender(self.config.get('channels', {}).get('slack', {}))
        self.email_sender = EmailNotificationSender(self.config.get('channels', {}).get('email', {}))
        self.pagerduty_sender = PagerDutyNotificationSender(self.config.get('channels', {}).get('pagerduty', {}))
        self.github_sender = GitHubIssueNotificationSender(self.config.get('channels', {}).get('github', {}))
    
    def _load_config(self) -> Dict[str, Any]:
        """Load notification configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Notification config not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing notification config: {e}")
            return {}
    
    def send_notification(self, message: NotificationMessage) -> NotificationResult:
        """Send a notification message."""
        try:
            # Apply routing rules
            channels = self._get_routing_channels(message)
            
            results = []
            for channel in channels:
                result = self._send_to_channel(message, channel)
                results.append(result)
            
            # Return the first successful result or the first error
            for result in results:
                if result.success:
                    return result
            
            return results[0] if results else NotificationResult(
                success=False,
                channel=message.channel,
                error="No channels configured"
            )
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return NotificationResult(
                success=False,
                channel=message.channel,
                error=str(e)
            )
    
    def _get_routing_channels(self, message: NotificationMessage) -> List[NotificationChannel]:
        """Get channels to route the message to based on rules."""
        rules = self.config.get('rules', {})
        
        # Check for specific event routing
        if message.metadata.get('event_type') in rules:
            rule = rules[message.metadata['event_type']]
            channels = rule.get('channels', [])
            
            # Convert string channels to enum
            channel_enums = []
            for channel_str in channels:
                try:
                    channel_enums.append(NotificationChannel(channel_str))
                except ValueError:
                    logger.warning(f"Unknown channel: {channel_str}")
            
            if channel_enums:
                return channel_enums
        
        # Default routing based on severity
        if message.severity == NotificationSeverity.CRITICAL:
            return [NotificationChannel.SLACK, NotificationChannel.PAGERDUTY]
        elif message.severity == NotificationSeverity.HIGH:
            return [NotificationChannel.SLACK, NotificationChannel.EMAIL]
        elif message.severity == NotificationSeverity.MEDIUM:
            return [NotificationChannel.SLACK]
        else:
            return [NotificationChannel.EMAIL]
    
    def _send_to_channel(self, message: NotificationMessage, channel: NotificationChannel) -> NotificationResult:
        """Send message to specific channel."""
        try:
            if channel == NotificationChannel.SLACK:
                return self.slack_sender.send(message)
            elif channel == NotificationChannel.EMAIL:
                return self.email_sender.send(message)
            elif channel == NotificationChannel.PAGERDUTY:
                return self.pagerduty_sender.send(message)
            elif channel == NotificationChannel.GITHUB_ISSUE:
                return self.github_sender.send(message)
            else:
                return NotificationResult(
                    success=False,
                    channel=channel,
                    error=f"Unsupported channel: {channel}"
                )
        except Exception as e:
            logger.error(f"Error sending to {channel}: {e}")
            return NotificationResult(
                success=False,
                channel=channel,
                error=str(e)
            )


class SlackNotificationSender:
    """Slack notification sender."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Slack sender."""
        self.config = config
        self.webhooks = config.get('webhooks', {})
        self.default_webhook = config.get('default_webhook')
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send message to Slack."""
        try:
            # Determine webhook URL
            webhook_url = self._get_webhook_url(message)
            if not webhook_url:
                return NotificationResult(
                    success=False,
                    channel=NotificationChannel.SLACK,
                    error="No Slack webhook configured"
                )
            
            # Format message for Slack
            slack_message = self._format_slack_message(message)
            
            # Send to Slack
            response = requests.post(webhook_url, json=slack_message, timeout=30)
            response.raise_for_status()
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.SLACK,
                message_id=response.headers.get('X-Slack-Request-Timestamp'),
                delivery_time=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.SLACK,
                error=str(e)
            )
    
    def _get_webhook_url(self, message: NotificationMessage) -> Optional[str]:
        """Get webhook URL for message."""
        # Check for specific webhook based on severity or event type
        if message.severity == NotificationSeverity.CRITICAL:
            return self.webhooks.get('alerts') or self.default_webhook
        elif message.metadata.get('event_type') == 'quality_threshold_breach':
            return self.webhooks.get('reports') or self.default_webhook
        else:
            return self.default_webhook
    
    def _format_slack_message(self, message: NotificationMessage) -> Dict[str, Any]:
        """Format message for Slack."""
        # Color based on severity
        color_map = {
            NotificationSeverity.LOW: '#36a64f',      # Green
            NotificationSeverity.MEDIUM: '#ff9500',   # Orange
            NotificationSeverity.HIGH: '#ff0000',     # Red
            NotificationSeverity.CRITICAL: '#8b0000'   # Dark red
        }
        
        # Build Slack message
        slack_message = {
            'text': message.title,
            'attachments': [
                {
                    'color': color_map.get(message.severity, '#36a64f'),
                    'title': message.title,
                    'text': message.content,
                    'fields': self._build_slack_fields(message),
                    'footer': '254Carbon Meta',
                    'ts': int(datetime.now(timezone.utc).timestamp())
                }
            ]
        }
        
        # Add attachments if any
        if message.attachments:
            for attachment in message.attachments:
                slack_message['attachments'].append({
                    'title': attachment.get('title', 'Attachment'),
                    'text': attachment.get('content', ''),
                    'color': '#36a64f'
                })
        
        return slack_message
    
    def _build_slack_fields(self, message: NotificationMessage) -> List[Dict[str, Any]]:
        """Build Slack fields from message metadata."""
        fields = []
        
        # Add severity field
        fields.append({
            'title': 'Severity',
            'value': message.severity.value.upper(),
            'short': True
        })
        
        # Add timestamp field
        fields.append({
            'title': 'Time',
            'value': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'short': True
        })
        
        # Add event type if available
        if message.metadata.get('event_type'):
            fields.append({
                'title': 'Event Type',
                'value': message.metadata['event_type'],
                'short': True
            })
        
        # Add service name if available
        if message.metadata.get('service_name'):
            fields.append({
                'title': 'Service',
                'value': message.metadata['service_name'],
                'short': True
            })
        
        return fields


class EmailNotificationSender:
    """Email notification sender."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize email sender."""
        self.config = config
        self.smtp_host = config.get('smtp_host')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user')
        self.smtp_password = config.get('smtp_password')
        self.from_email = config.get('from_email', 'noreply@254carbon.com')
        self.templates_dir = Path(config.get('templates_dir', 'analysis/templates/notifications'))
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send message via email."""
        try:
            if not self.smtp_host:
                return NotificationResult(
                    success=False,
                    channel=NotificationChannel.EMAIL,
                    error="No SMTP host configured"
                )
            
            # Create email message
            email_msg = self._create_email_message(message)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                
                recipients = self._get_recipients(message)
                server.send_message(email_msg, to_addrs=recipients)
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.EMAIL,
                message_id=f"email_{int(datetime.now(timezone.utc).timestamp())}",
                delivery_time=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.EMAIL,
                error=str(e)
            )
    
    def _create_email_message(self, message: NotificationMessage) -> MIMEMultipart:
        """Create email message."""
        email_msg = MIMEMultipart('alternative')
        email_msg['From'] = self.from_email
        email_msg['Subject'] = f"[254Carbon Meta] {message.title}"
        
        # Create HTML content
        html_content = self._format_email_html(message)
        html_part = MIMEText(html_content, 'html')
        email_msg.attach(html_part)
        
        # Create plain text content
        text_content = self._format_email_text(message)
        text_part = MIMEText(text_content, 'plain')
        email_msg.attach(text_part)
        
        return email_msg
    
    def _format_email_html(self, message: NotificationMessage) -> str:
        """Format message as HTML email."""
        severity_colors = {
            NotificationSeverity.LOW: '#28a745',
            NotificationSeverity.MEDIUM: '#ffc107',
            NotificationSeverity.HIGH: '#fd7e14',
            NotificationSeverity.CRITICAL: '#dc3545'
        }
        
        color = severity_colors.get(message.severity, '#28a745')
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; border-radius: 5px; }}
                .content {{ padding: 20px; background-color: #f8f9fa; border-radius: 5px; margin-top: 10px; }}
                .metadata {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 10px; }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{message.title}</h1>
                <p>Severity: {message.severity.value.upper()}</p>
            </div>
            <div class="content">
                <p>{message.content}</p>
            </div>
            <div class="metadata">
                <h3>Metadata</h3>
                <ul>
                    <li><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
                    <li><strong>Event Type:</strong> {message.metadata.get('event_type', 'N/A')}</li>
                    <li><strong>Service:</strong> {message.metadata.get('service_name', 'N/A')}</li>
                </ul>
            </div>
            <div class="footer">
                <p>This notification was sent by 254Carbon Meta Repository</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_email_text(self, message: NotificationMessage) -> str:
        """Format message as plain text email."""
        text = f"""
254Carbon Meta Notification

Title: {message.title}
Severity: {message.severity.value.upper()}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

Content:
{message.content}

Metadata:
- Event Type: {message.metadata.get('event_type', 'N/A')}
- Service: {message.metadata.get('service_name', 'N/A')}

---
This notification was sent by 254Carbon Meta Repository
        """
        
        return text.strip()
    
    def _get_recipients(self, message: NotificationMessage) -> List[str]:
        """Get email recipients based on message."""
        # Get recipients from config
        recipients = self.config.get('recipients', [])
        
        # Add severity-based recipients
        if message.severity == NotificationSeverity.CRITICAL:
            critical_recipients = self.config.get('critical_recipients', [])
            recipients.extend(critical_recipients)
        
        # Add event-based recipients
        if message.metadata.get('event_type'):
            event_recipients = self.config.get('event_recipients', {}).get(
                message.metadata['event_type'], []
            )
            recipients.extend(event_recipients)
        
        # Remove duplicates
        return list(set(recipients))


class PagerDutyNotificationSender:
    """PagerDuty notification sender."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize PagerDuty sender."""
        self.config = config
        self.api_key = config.get('api_key')
        self.routing_key = config.get('routing_key')
        self.api_url = config.get('api_url', 'https://events.pagerduty.com/v2/enqueue')
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send message to PagerDuty."""
        try:
            if not self.routing_key:
                return NotificationResult(
                    success=False,
                    channel=NotificationChannel.PAGERDUTY,
                    error="No PagerDuty routing key configured"
                )
            
            # Format message for PagerDuty
            pagerduty_message = self._format_pagerduty_message(message)
            
            # Send to PagerDuty
            headers = {
                'Content-Type': 'application/json'
            }
            if self.api_key:
                headers['Authorization'] = f'Token token={self.api_key}'
            
            response = requests.post(
                self.api_url,
                json=pagerduty_message,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result_data = response.json()
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.PAGERDUTY,
                message_id=result_data.get('dedup_key'),
                delivery_time=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"PagerDuty notification failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.PAGERDUTY,
                error=str(e)
            )
    
    def _format_pagerduty_message(self, message: NotificationMessage) -> Dict[str, Any]:
        """Format message for PagerDuty."""
        # Determine severity
        severity_map = {
            NotificationSeverity.LOW: 'info',
            NotificationSeverity.MEDIUM: 'warning',
            NotificationSeverity.HIGH: 'error',
            NotificationSeverity.CRITICAL: 'critical'
        }
        
        pagerduty_message = {
            'routing_key': self.routing_key,
            'event_action': 'trigger',
            'dedup_key': f"254carbon-meta-{int(datetime.now(timezone.utc).timestamp())}",
            'payload': {
                'summary': message.title,
                'source': '254carbon-meta',
                'severity': severity_map.get(message.severity, 'info'),
                'component': message.metadata.get('service_name', 'meta'),
                'group': message.metadata.get('event_type', 'general'),
                'class': 'service_alert',
                'custom_details': {
                    'content': message.content,
                    'metadata': message.metadata
                }
            }
        }
        
        return pagerduty_message


class GitHubIssueNotificationSender:
    """GitHub issue notification sender."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize GitHub sender."""
        self.config = config
        self.token = config.get('token')
        self.owner = config.get('owner', '254carbon')
        self.repo = config.get('repo', '254carbon-meta')
        self.api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues"
    
    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send message as GitHub issue."""
        try:
            if not self.token:
                return NotificationResult(
                    success=False,
                    channel=NotificationChannel.GITHUB_ISSUE,
                    error="No GitHub token configured"
                )
            
            # Format message for GitHub
            github_message = self._format_github_message(message)
            
            # Send to GitHub
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.post(
                self.api_url,
                json=github_message,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result_data = response.json()
            
            return NotificationResult(
                success=True,
                channel=NotificationChannel.GITHUB_ISSUE,
                message_id=str(result_data.get('number')),
                delivery_time=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"GitHub issue notification failed: {e}")
            return NotificationResult(
                success=False,
                channel=NotificationChannel.GITHUB_ISSUE,
                error=str(e)
            )
    
    def _format_github_message(self, message: NotificationMessage) -> Dict[str, Any]:
        """Format message for GitHub issue."""
        # Determine labels
        labels = ['meta-notification']
        
        if message.severity == NotificationSeverity.CRITICAL:
            labels.append('critical')
        elif message.severity == NotificationSeverity.HIGH:
            labels.append('high')
        elif message.severity == NotificationSeverity.MEDIUM:
            labels.append('medium')
        else:
            labels.append('low')
        
        # Add event type label
        if message.metadata.get('event_type'):
            labels.append(message.metadata['event_type'])
        
        # Add service label
        if message.metadata.get('service_name'):
            labels.append(f"service:{message.metadata['service_name']}")
        
        github_message = {
            'title': f"[Meta] {message.title}",
            'body': f"""
## {message.title}

**Severity:** {message.severity.value.upper()}
**Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

### Description
{message.content}

### Metadata
- **Event Type:** {message.metadata.get('event_type', 'N/A')}
- **Service:** {message.metadata.get('service_name', 'N/A')}

---
*This issue was automatically created by 254Carbon Meta Repository*
            """.strip(),
            'labels': labels
        }
        
        return github_message


def main():
    """Main entry point for notification system."""
    parser = argparse.ArgumentParser(description='Send notifications via multiple channels')
    parser.add_argument('--config', default='config/notifications.yaml', help='Notification config file')
    parser.add_argument('--channel', choices=['slack', 'email', 'pagerduty', 'github_issue'], help='Specific channel to use')
    parser.add_argument('--message', help='Notification message')
    parser.add_argument('--title', help='Notification title')
    parser.add_argument('--severity', choices=['low', 'medium', 'high', 'critical'], default='medium', help='Severity level')
    parser.add_argument('--event-type', help='Event type for routing')
    parser.add_argument('--service-name', help='Service name')
    parser.add_argument('--metadata', help='Additional metadata as JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    # Parse metadata
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid metadata JSON: {e}")
            sys.exit(1)
    
    # Add command line metadata
    if args.event_type:
        metadata['event_type'] = args.event_type
    if args.service_name:
        metadata['service_name'] = args.service_name
    
    # Create notification message
    message = NotificationMessage(
        title=args.title or "254Carbon Meta Notification",
        content=args.message or "No message provided",
        severity=NotificationSeverity(args.severity),
        channel=NotificationChannel(args.channel) if args.channel else NotificationChannel.SLACK,
        metadata=metadata
    )
    
    # Send notification
    sender = NotificationSender(args.config)
    result = sender.send_notification(message)
    
    if result.success:
        print(f"Notification sent successfully via {result.channel.value}")
        if result.message_id:
            print(f"Message ID: {result.message_id}")
    else:
        print(f"Notification failed: {result.error}")
        sys.exit(1)


if __name__ == '__main__':
    main()