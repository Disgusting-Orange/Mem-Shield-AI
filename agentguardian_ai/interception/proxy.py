from fastapi import FastAPI
from agentguardian_ai.models import MemoryWrite, ToolCall, Alert, Decision
from agentguardian_ai.interception.alert_sink import LocalAlertSink
from agentguardian_ai.interception.fakes import FakeMemoryFirewall, FakeExecutionGuardian

app = FastAPI(title="Mem-Shield-AI Interception Proxy")

memory_firewall = FakeMemoryFirewall()
execution_guardian = FakeExecutionGuardian()
alert_sink = LocalAlertSink()

_session_state: dict[str, str] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/intercept/memory-write")
def intercept_memory_write(write: MemoryWrite):
    result = memory_firewall.intercept_write(write)
    _session_state[write.session_id] = result.decision.value
    if result.decision != Decision.ALLOW:
        alert_sink.notify(Alert(
            severity="critical" if result.decision == Decision.BLOCK else "warning",
            source_module="memory_firewall",
            message=f"Memory write {result.decision.value}",
            context={"agent_id": write.agent_id, "session_id": write.session_id,
                     "score": result.score, "reasons": result.reasons},
        ))
    return {"decision": result.decision, "score": result.score, "reasons": result.reasons}


@app.post("/intercept/tool-call")
def intercept_tool_call(call: ToolCall):
    result = execution_guardian.check(call)
    _session_state[call.session_id] = result.decision.value
    if result.decision != Decision.ALLOW:
        alert_sink.notify(Alert(
            severity="critical",
            source_module="execution_guardian",
            message=f"Tool call {result.decision.value}: {call.tool_name}",
            context={"agent_id": call.agent_id, "session_id": call.session_id, "reasons": result.reasons},
        ))
    return {"decision": result.decision, "score": result.score, "reasons": result.reasons}


@app.post("/admin/override/{session_id}")
def override_decision(session_id: str, new_decision: Decision):
    old = _session_state.get(session_id, "unknown")
    _session_state[session_id] = new_decision.value
    alert_sink.notify(Alert(
        severity="info",
        source_module="admin",
        message=f"Manual override: {old} -> {new_decision.value}",
        context={"session_id": session_id},
    ))
    return {"status": "overridden", "session_id": session_id, "previous": old, "new": new_decision.value}


@app.get("/admin/audit-trail")
def get_audit_trail():
    return alert_sink.read_audit_trail()
