import json
import logging
from abc import ABC, abstractmethod

from agentguardian_ai.models import Alert


class AlertSink(ABC):
    @abstractmethod
    def notify(self, alert: Alert) -> None:
        ...


class LocalAlertSink(AlertSink):
    def __init__(self, log_path: str = "audit_trail.jsonl"):
        self.logger = logging.getLogger("agent_guardrails")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        self.log_path = log_path

    def notify(self, alert: Alert) -> None:
        record = {
            "severity": alert.severity,
            "source": alert.source_module,
            "message": alert.message,
            "context": alert.context,
            "timestamp": alert.timestamp.isoformat(),
        }
        log_fn = {
            "info": self.logger.info,
            "warning": self.logger.warning,
            "critical": self.logger.critical,
        }.get(alert.severity, self.logger.info)
        log_fn(f"[{alert.source_module}] {alert.message} | context={alert.context}")
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def read_audit_trail(self) -> list[dict]:
        try:
            with open(self.log_path, "r") as f:
                return [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []
