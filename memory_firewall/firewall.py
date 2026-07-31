import os
import json
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple

import requests

from .config import GROQ_API_KEY, MEMORY_TRUST_THRESHOLD
from .models import TrustScoreResult

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from interfaces import BaseHistoryStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding helper — tries ONNX first (lightweight), falls back to
# sentence-transformers + torch (heavier but works everywhere).
# ---------------------------------------------------------------------------
def _load_embedder():
    """Load the best available embedding backend."""
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer

        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        cache_dir = os.environ.get("MODEL_CACHE_DIR", None)
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
        model = ORTModelForFeatureExtraction.from_pretrained(
            model_name, export=True, cache_dir=cache_dir
        )
        logger.info("Loaded ONNX embedding backend (lightweight).")
        return ("onnx", tokenizer, model)
    except ImportError:
        pass

    # Fallback: sentence-transformers + torch (local dev)
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformers embedding backend (torch).")
        return ("st", None, model)
    except ImportError:
        logger.warning("No embedding backend available. Semantic drift detection disabled.")
        return ("none", None, None)


def _embed(backend_tuple, texts: List[str]) -> np.ndarray:
    """Encode a list of texts into embeddings using whichever backend is loaded."""
    kind, tokenizer, model = backend_tuple
    if kind == "onnx":
        inputs = tokenizer(texts, return_tensors="np", padding=True, truncation=True)
        outputs = model(**inputs)
        # Mean pooling over token embeddings
        embeddings = outputs.last_hidden_state.mean(axis=1)
        return np.array(embeddings)
    elif kind == "st":
        return model.encode(texts, convert_to_numpy=True)
    else:
        return np.array([])


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity between a single vector `a` and a matrix `b`."""
    a_norm = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=-1, keepdims=True) + 1e-9)
    return (a_norm @ b_norm.T).flatten()


# ---------------------------------------------------------------------------
# In-memory history store (local dev default)
# ---------------------------------------------------------------------------
class InMemoryHistoryStore(BaseHistoryStore):
    """Simple dict-backed history — used when no DynamoDB is configured."""

    def __init__(self):
        self._data: Dict[str, List[Dict[str, str]]] = {}

    def load_history(self, agent_id: str) -> List[Dict[str, str]]:
        return self._data.get(agent_id, [])

    def append_write(self, agent_id: str, key: str, value: str) -> None:
        self._data.setdefault(agent_id, []).append({"key": key, "value": value})


# ---------------------------------------------------------------------------
# MemoryFirewall
# ---------------------------------------------------------------------------
class MemoryFirewall:
    """Zero-Trust firewall that validates a memory write before it is persisted.

    The firewall combines two independent signals:
    1. **LLM trust scoring** – a lightweight Groq LLM call evaluates how "trustworthy"
       the candidate write looks (e.g., does it contain malicious instructions?).
    2. **Semantic drift detection** – the write is embedded with
       ``all-MiniLM-L6-v2`` and compared to the agent's
       historical writes. Large semantic distance may indicate a poisoning attempt.

    Both signals are normalised to a 0-100 range and blended (60 % LLM, 40 % semantic).
    If the combined score falls below :data:`MEMORY_TRUST_THRESHOLD` the write is
    rejected and a :class:`TrustScoreResult` with ``accepted=False`` is returned.
    """

    def __init__(self, history_store: Optional[BaseHistoryStore] = None) -> None:
        self._history_store = history_store or InMemoryHistoryStore()
        # Load embedding model once (ONNX on Lambda, torch locally)
        self._embedder = _load_embedder()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def validate_write(self, agent_id: str, key: str, value: str) -> TrustScoreResult:
        """Validate a proposed memory write.

        Parameters
        ----------
        agent_id: str
            Identifier of the agent performing the write.
        key: str
            Memory key (e.g., ``"user_preferences"``).
        value: str
            JSON-serialisable payload that will be stored.

        Returns
        -------
        TrustScoreResult
            Contains the combined score, the list of reasons, and a boolean flag
            indicating whether the write is accepted.
        """
        # -----------------------------------------------------------------
        # 1️⃣ LLM based trust scoring via Groq
        # -----------------------------------------------------------------
        try:
            groq_score, groq_reason = self._score_with_groq(key, value)
        except Exception as exc:
            # If the LLM call fails we fall back to a safe low score but continue.
            logger.warning("Groq scoring failed: %s. Falling back to score 30.", exc)
            groq_score = 30
            groq_reason = f"Groq call error: {exc}"

        # -----------------------------------------------------------------
        # 2️⃣ Semantic similarity / drift check
        # -----------------------------------------------------------------
        semantic_score, semantic_reason = self._semantic_drift_score(agent_id, value)

        # -----------------------------------------------------------------
        # 3️⃣ Combine scores (weights can be tuned via env if needed)
        # -----------------------------------------------------------------
        combined = int(groq_score * 0.6 + semantic_score * 0.4)
        accepted = combined >= MEMORY_TRUST_THRESHOLD

        reasons: List[str] = [groq_reason, semantic_reason]
        result = TrustScoreResult(score=combined, reasons=reasons, accepted=accepted)

        # Record the write if it is accepted – it becomes part of the drift history.
        if accepted:
            self._history_store.append_write(agent_id, key, value)
        else:
            logger.warning(
                "Memory write rejected (agent=%s, key=%s, score=%s). Reasons: %s",
                agent_id,
                key,
                combined,
                "; ".join(reasons),
            )

        return result

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _score_with_groq(self, key: str, value: str) -> Tuple[int, str]:
        """Call Groq LLM to obtain a trust score (0-100).

        The prompt asks the model to output a plain integer and a short rationale.
        """
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not set in environment")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        system_prompt = (
            "You are a security evaluator. Given a memory key and its value, "
            "output a trust score between 0 and 100 (higher is more trustworthy) "
            "and a concise reason. Respond strictly in the format: <score> - <reason>."
        )
        user_prompt = f"Key: {key}\nValue: {value}"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Expected "<score> - <reason>"
        try:
            score_part, reason_part = content.split("-", 1)
            score = int(score_part.strip())
            reason = reason_part.strip()
        except Exception:
            # Fallback parsing – extract first integer we find.
            import re

            match = re.search(r"(\d{1,3})", content)
            score = int(match.group(1)) if match else 0
            reason = content
        # Clamp score to 0-100
        score = max(0, min(100, score))
        return score, reason

    def _semantic_drift_score(self, agent_id: str, new_value: str) -> Tuple[int, str]:
        """Compute similarity of ``new_value`` to the agent's previous writes.

        Returns a score 0-100 where 100 means *very similar* to past memory.
        If there is no history, we assume maximum similarity (100).
        """
        # If no embedding backend is available, skip drift detection
        if self._embedder[0] == "none":
            return 100, "Semantic drift detection unavailable (no embedding backend)"

        history = self._history_store.load_history(agent_id)
        if not history:
            return 100, "No prior writes – assuming safe"

        # Embed the new value.
        new_emb = _embed(self._embedder, [new_value])
        # Embed all historic values.
        past_vals = [entry["value"] for entry in history]
        past_emb = _embed(self._embedder, past_vals)

        # Compute cosine similarity with each past entry, take the maximum.
        sims = _cosine_similarity(new_emb, past_emb)
        max_sim = float(sims.max())  # between -1 and 1 (should be >=0 for our model)

        # Normalise to 0-100.
        score = int(max(0.0, min(1.0, max_sim)) * 100)
        reason = f"Semantic similarity to prior writes: {score}%"
        return score, reason
