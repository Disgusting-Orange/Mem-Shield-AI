"""
aws/sns_alert_sink.py
----------------------
SNS-backed alert sink — pushes notifications on security events.
Free tier: 1M publishes + 1,000 email notifications per month.

Subscribe your email to the topic to get instant alerts:
  aws sns subscribe --topic-arn <ARN> --protocol email --notification-endpoint you@email.com
"""

import json
import os
import time
import logging
from typing import Dict, Any

import boto3

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from interfaces import BaseAlertSink

logger = logging.getLogger(__name__)

TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")


class SNSAlertSink(BaseAlertSink):
    """Publishes security alerts to an SNS topic."""

    def __init__(self, topic_arn: str = TOPIC_ARN):
        self._sns = boto3.client("sns")
        self._topic_arn = topic_arn
        if not self._topic_arn:
            logger.warning("SNS_TOPIC_ARN not set — alerts will be logged but not published.")

    def send_alert(self, agent_id: str, alert_type: str, details: Dict[str, Any]) -> None:
        message = {
            "agent_id": agent_id,
            "alert_type": alert_type,
            "details": details,
            "timestamp": time.time(),
        }

        # Always log the alert
        logger.warning(
            "🚨 ALERT [%s] agent=%s: %s",
            alert_type, agent_id, json.dumps(details, default=str),
        )

        # Publish to SNS if configured
        if self._topic_arn:
            try:
                subject = f"Mem-Shield-AI Alert: {alert_type} (agent: {agent_id})"
                # SNS subject max 100 chars
                subject = subject[:100]
                self._sns.publish(
                    TopicArn=self._topic_arn,
                    Subject=subject,
                    Message=json.dumps(message, indent=2, default=str),
                )
            except Exception as exc:
                logger.error("Failed to publish SNS alert: %s", exc)
