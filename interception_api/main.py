import os
import uuid
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from memory_firewall import MemoryFirewall
from guardian import ExecutionGuardian
from models import ExecutionStep
from vault_store import VaultStore
from personal_memory_store import PersonalMemoryStore

# -------------------------------------------------------------
# Logging — JSON on Lambda, human-readable locally
# -------------------------------------------------------------
try:
    from aws.logging_config import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

log = logging.getLogger("interception_api")

# Initialize isolated stores
vault_db = VaultStore()
personal_db = PersonalMemoryStore()

# -------------------------------------------------------------
# Environment-aware wiring
# -------------------------------------------------------------
def _build_components():
    is_aws = "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    if is_aws:
        log.info("Running on AWS Lambda — using DynamoDB + SNS backends.")
        from aws.dynamo_store import DynamoStateStore
        from aws.dynamo_history_store import DynamoHistoryStore
        from aws.sns_alert_sink import SNSAlertSink

        store = DynamoStateStore()
        history = DynamoHistoryStore()
        alert_sink = SNSAlertSink()
    else:
        log.info("Running locally — using SQLite + in-memory backends.")
        from state_store import StateStore
        from memory_firewall.firewall import InMemoryHistoryStore

        store = StateStore()
        history = InMemoryHistoryStore()
        alert_sink = None

    fw = MemoryFirewall(history_store=history)
    gd = ExecutionGuardian(store=store, alert_sink=alert_sink)
    return fw, gd


app = FastAPI(title="Mem-Shield-AI Interception API & Vault")
firewall, guardian = _build_components()

# -------------------------------------------------------------
# Pydantic Request Models
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
    timestamp: float = 0.0

class PersonalMemoryUploadRequest(BaseModel):
    user_id: str = "user_default"
    category: str = "medical"  # "medical" | "preference" | "note" | "financial"
    title: str
    content: str

class CreateChatRequest(BaseModel):
    user_id: str = "user_default"
    title: str
    initial_messages: Optional[List[Dict[str, Any]]] = None
    password: Optional[str] = None

class LockChatRequest(BaseModel):
    chat_id: str
    password: str

class UnlockChatRequest(BaseModel):
    chat_id: str
    password: str

class AddChatMessageRequest(BaseModel):
    chat_id: str
    sender: str
    text: str
    password: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    chat_id: str
    recovery_key: str
    new_password: str

# -------------------------------------------------------------
# Core Interception API Endpoints
# -------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "healthy", "service": "mem-shield-ai"}

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

@app.post("/agent/step")
def post_step(req: AgentStepRequest):
    from dataclasses import asdict

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
        log.warning("Loop detected for agent=%s - cycles: %s", req.agent_id, audit_report["loops"])
    if audit_report["silent_failures"]:
        log.warning(
            "Silent failures for agent=%s - steps: %s",
            req.agent_id,
            [s.step_id for s in audit_report["silent_failures"]],
        )
    if audit_report["redundant_calls"]:
        log.warning(
            "Redundant calls for agent=%s - pairs: %s",
            req.agent_id,
            [(a.step_id, b.step_id) for a, b in audit_report["redundant_calls"]],
        )

    return {
        "loops": audit_report["loops"],
        "silent_failures": [asdict(s) for s in audit_report["silent_failures"]],
        "redundant_calls": [[asdict(a), asdict(b)] for a, b in audit_report["redundant_calls"]],
        "estimated_cost_leak": audit_report["estimated_cost_leak"],
    }

# -------------------------------------------------------------
# Personal & Medical Record Vault Endpoints (Firewall Protected)
# -------------------------------------------------------------
@app.post("/vault/personal/write")
def upload_personal_memory(req: PersonalMemoryUploadRequest):
    """Upload a medical or personal document. Passes through Memory Firewall first."""
    eval_key = f"{req.category}:{req.title}"
    eval_result = firewall.validate_write(req.user_id, eval_key, req.content)

    if not eval_result.accepted:
        log.warning(
            "Personal document rejected by firewall – user=%s category=%s title=%s score=%d",
            req.user_id, req.category, req.title, eval_result.score
        )
        raise HTTPException(
            status_code=400,
            detail={
                "accepted": False,
                "score": eval_result.score,
                "reasons": eval_result.reasons,
                "message": "Document contains malicious elements or severe security risk."
            }
        )

    mem_id = f"mem-{uuid.uuid4().hex[:8]}"
    saved = personal_db.save_memory(
        memory_id=mem_id,
        user_id=req.user_id,
        category=req.category,
        title=req.title,
        content=req.content,
        threat_score=eval_result.score,
        reasons=eval_result.reasons,
    )
    return {"accepted": True, "memory": saved}

@app.get("/vault/personal/list")
def list_personal_memories(user_id: str = "user_default", category: Optional[str] = None):
    memories = personal_db.list_memories(user_id, category)
    return {"user_id": user_id, "memories": memories}

# -------------------------------------------------------------
# Private Locked Chats & Vault Endpoints (Isolated DB)
# -------------------------------------------------------------
@app.post("/vault/chat/create")
def create_chat(req: CreateChatRequest):
    chat_id = f"chat-{uuid.uuid4().hex[:8]}"
    summary, recovery_key = vault_db.create_chat(
        chat_id=chat_id,
        user_id=req.user_id,
        title=req.title,
        initial_messages=req.initial_messages,
        password=req.password
    )
    return {
        "chat": summary,
        "recovery_key": recovery_key,
        "message": "Chat created successfully" + (" and locked with password." if recovery_key else ".")
    }

@app.post("/vault/chat/lock")
def lock_chat(req: LockChatRequest):
    recovery_key = vault_db.lock_existing_chat(req.chat_id, req.password)
    if not recovery_key:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {
        "chat_id": req.chat_id,
        "is_locked": True,
        "recovery_key": recovery_key,
        "message": "Chat locked successfully. Save your Emergency Recovery Key to reset password if forgotten."
    }

@app.post("/vault/chat/unlock")
def unlock_chat(req: UnlockChatRequest):
    success, messages, msg = vault_db.unlock_chat(req.chat_id, req.password)
    if not success:
        raise HTTPException(status_code=401, detail={"unlocked": False, "message": msg})
    return {
        "chat_id": req.chat_id,
        "unlocked": True,
        "messages": messages,
        "message": msg
    }

@app.post("/vault/chat/message")
def add_chat_message(req: AddChatMessageRequest):
    # Verify access first if chat is locked
    if req.password:
        success, _, msg = vault_db.unlock_chat(req.chat_id, req.password)
        if not success:
            raise HTTPException(status_code=401, detail={"message": "Authentication failed: " + msg})

    # Intercept text message with firewall
    eval_result = firewall.validate_write("chat_user", req.chat_id, req.text)
    if not eval_result.accepted:
        raise HTTPException(status_code=400, detail={"accepted": False, "message": "Message blocked by firewall: " + "; ".join(eval_result.reasons)})

    added = vault_db.add_message(req.chat_id, req.sender, req.text)
    if not added:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {"chat_id": req.chat_id, "added": True}

@app.post("/vault/chat/reset-password")
def reset_chat_password(req: ResetPasswordRequest):
    success, msg = vault_db.reset_password(req.chat_id, req.recovery_key, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail={"reset": False, "message": msg})
    return {"chat_id": req.chat_id, "reset": True, "message": msg}

@app.get("/vault/chat/all")
def list_chats(user_id: str = "user_default"):
    chats = vault_db.list_chats(user_id)
    return {"user_id": user_id, "chats": chats}

# -------------------------------------------------------------
# Static Frontend Serving
# -------------------------------------------------------------
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def read_root():
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Mem-Shield-AI API Running"}
