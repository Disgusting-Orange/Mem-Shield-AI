import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from memory_firewall import MemoryFirewall
from execution_guardian import ExecutionGuardian, ExecutionStep

# -------------------------------------------------------------
# Logging – mimics CloudWatch (INFO for normal, WARNING for issues)
# -------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("interception_api")

app = FastAPI(title="Mem-Shield-AI Interception API")
firewall = MemoryFirewall()
guardian = ExecutionGuardian()

# -------------------------------------------------------------
# Pydantic request models (kept simple as you requested)
# -------------------------------------------------------------
class MemoryWriteRequest(BaseModel):
    agent_id: str
    key: str
    value: str

class AgentStepRequest(BaseModel):
    agent_id: str
    step_id: str
    action: str
    params: Dict[str, Any] = {}
    status: str = "success"
    result_payload: str = ""
    cost_estimate: float = 0.0
    timestamp: float = 0.0   # optional, can be omitted

# -------------------------------------------------------------
# Endpoint: /memory/write
# -------------------------------------------------------------
@app.post("/memory/write")
def write_memory(req: MemoryWriteRequest):
    result = firewall.validate_write(req.agent_id, req.key, req.value)
    if not result.accepted:
        log.warning(
            "Memory write REJECTED – agent=%s key=%s score=%d reasons=%s",
            req.agent_id,
            req.key,
            result.score,
            "; ".join(result.reasons),
        )
        raise HTTPException(
            status_code=400,
            detail={"accepted": False, "score": result.score, "reasons": result.reasons},
        )
    log.info(
        "Memory write ACCEPTED – agent=%s key=%s score=%d",
        req.agent_id,
        req.key,
        result.score,
    )
    return {"accepted": True, "score": result.score, "reasons": result.reasons}

# -------------------------------------------------------------
# Endpoint: /agent/step
# -------------------------------------------------------------
@app.post("/agent/step")
def post_step(req: AgentStepRequest):
    step = ExecutionStep(
        agent_id=req.agent_id,
        step_id=req.step_id,
        action=req.action,
        params=req.params,
        status=req.status,
        result_payload=req.result_payload,
        cost_estimate=req.cost_estimate,
        timestamp=req.timestamp,
    )
    guardian.record_step(step)
    audit_report = guardian.audit(req.agent_id)

    if audit_report["loops"]:
        log.warning("Loop detected for agent=%s – cycles: %s", req.agent_id, audit_report["loops"])
    if audit_report["silent_failures"]:
        log.warning(
            "Silent failures for agent=%s – steps: %s",
            req.agent_id,
            [s.step_id for s in audit_report["silent_failures"]],
        )
    if audit_report["redundant_calls"]:
        log.warning(
            "Redundant calls for agent=%s – pairs: %s",
            req.agent_id,
            [(a.step_id, b.step_id) for a, b in audit_report["redundant_calls"]],
        )
    return audit_report
