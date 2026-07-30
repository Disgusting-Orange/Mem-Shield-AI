"""
models.py
---------
Data model for a single execution step taken by an autonomous agent.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionStep:
    agent_id: str
    step_id: str
    action: str              # e.g. "call_api:get_weather"
    params: dict = field(default_factory=dict)
    status: str = "pending"  # "pending" | "success" | "failure"
    timestamp: float = field(default_factory=time.time)
    cost_estimate: float = 0.0  # in your chosen unit (rupees, tokens, etc.)
    # A step "reports" success but its result payload can still carry a
    # failure signature (e.g. an error string) -- that's what makes a
    # failure "silent": the agent thinks it succeeded.
    result_payload: Optional[str] = None
