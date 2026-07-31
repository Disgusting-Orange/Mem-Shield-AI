"""
interfaces.py
--------------
Abstract base classes that decouple core logic (guardian, firewall) from
their storage and alerting backends.

Local dev  → SQLite StateStore, in-memory history, console logging
AWS deploy → DynamoDB StateStore, DynamoDB history, SNS alerts

Swap implementations without touching detection logic.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from models import ExecutionStep


class BaseStateStore(ABC):
    """Durable log of every execution step an agent takes."""

    @abstractmethod
    def save(self, step: ExecutionStep) -> None:
        """Persist a single execution step."""
        ...

    @abstractmethod
    def get_steps(self, agent_id: str) -> List[ExecutionStep]:
        """Retrieve all stored steps for a given agent."""
        ...


class BaseAlertSink(ABC):
    """Push-notification channel for security/audit alerts."""

    @abstractmethod
    def send_alert(self, agent_id: str, alert_type: str, details: Dict[str, Any]) -> None:
        """
        Fire an alert.

        Parameters
        ----------
        agent_id : str
            Which agent triggered the alert.
        alert_type : str
            One of: "loop_detected", "silent_failure", "redundant_calls",
            "memory_rejected", "cost_leak".
        details : dict
            Arbitrary context (step IDs, scores, reasons, etc.).
        """
        ...


class BaseHistoryStore(ABC):
    """Persistence for the Memory Firewall's semantic-drift history."""

    @abstractmethod
    def load_history(self, agent_id: str) -> List[Dict[str, str]]:
        """Return all prior accepted writes for an agent as [{"key": ..., "value": ...}, ...]."""
        ...

    @abstractmethod
    def append_write(self, agent_id: str, key: str, value: str) -> None:
        """Record a newly accepted memory write."""
        ...
