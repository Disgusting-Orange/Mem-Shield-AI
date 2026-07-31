"""
aws/logging_config.py
----------------------
Structured JSON logging for CloudWatch.

On Lambda, stdout is automatically shipped to CloudWatch Logs via the
awslogs driver — no extra agent or config needed. We just need to format
logs as JSON so CloudWatch can parse structured fields.
"""

import logging
import os
import sys

try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the current environment.

    - On AWS Lambda (or when LOG_FORMAT=json): structured JSON output
    - Locally: standard human-readable format
    """
    root = logging.getLogger()
    # Remove any existing handlers (Lambda adds one by default)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    log_format = os.environ.get("LOG_FORMAT", "")
    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    if (is_lambda or log_format == "json") and HAS_JSON_LOGGER:
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)

    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
