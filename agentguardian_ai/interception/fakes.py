from agentguardian_ai.models import TrustScoreResult, Decision, MemoryWrite, ToolCall


class FakeMemoryFirewall:
    def intercept_write(self, write: MemoryWrite) -> TrustScoreResult:
        if "ignore previous instructions" in write.content.lower():
            return TrustScoreResult(score=10, decision=Decision.BLOCK, reasons=["fake_injection_marker"])
        return TrustScoreResult(score=100, decision=Decision.ALLOW, reasons=[])


class FakeExecutionGuardian:
    def __init__(self):
        self._call_counts: dict[str, int] = {}

    def check(self, call: ToolCall) -> TrustScoreResult:
        key = f"{call.session_id}:{call.tool_name}"
        self._call_counts[key] = self._call_counts.get(key, 0) + 1
        if self._call_counts[key] > 3:
            return TrustScoreResult(score=20, decision=Decision.BLOCK, reasons=["fake_repeated_call_loop"])
        return TrustScoreResult(score=100, decision=Decision.ALLOW, reasons=[])
