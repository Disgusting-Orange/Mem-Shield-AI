from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"


@dataclass
class MemoryWrite:
    agent_id: str
    session_id: str
    content: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class TrustScoreResult:
    score: int
    decision: Decision
    reasons: list[str]


@dataclass
class ToolCall:
    agent_id: str
    session_id: str
    tool_name: str
    args: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExecutionStep:
    agent_id: str
    session_id: str
    step_id: str
    parent_step_id: Optional[str]
    tool_name: Optional[str]
    reasoning_snippet: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Alert:
    severity: str
    source_module: str
    message: str
    context: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
