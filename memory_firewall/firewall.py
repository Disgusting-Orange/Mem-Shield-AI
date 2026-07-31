import os
import json
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple, Any

import requests

from .config import GROQ_API_KEY, MEMORY_TRUST_THRESHOLD
from .models import TrustScoreResult

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from interfaces import BaseHistoryStore

logger = logging.getLogger(__name__)

# Medical keywords & terms for fast local heuristic detection
MEDICAL_KEYWORDS = [
    "blood test", "symptom", "fever", "doctor", "prescription", "diagnosis",
    "patient", "hospital", "dosage", "clinic", "mg", "ml", "bp", "pulse",
    "hemoglobin", "cholesterol", "allergy", "infection", "treatment", "pain",
    "medicine", "tablet", "capsule", "disease", "vaccine", "ct scan", "mri",
    "x-ray", "lab report", "clinical", "physician", "heart rate", "glucose"
]


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

    Also provides automatic AI medical & personal health classification.
    """

    def __init__(self, history_store: Optional[BaseHistoryStore] = None) -> None:
        self._history_store = history_store or InMemoryHistoryStore()
        # Load embedding model once (ONNX on Lambda, torch locally)
        self._embedder = _load_embedder()

    def classify_content(self, text: str) -> Dict[str, Any]:
        """Automatically classify whether text is medical/personal health data."""
        text_lower = text.lower()
        matched_terms = [term for term in MEDICAL_KEYWORDS if term in text_lower]

        is_medical = len(matched_terms) > 0

        # Optional Groq LLM validation for edge cases
        reason = f"Matched medical terms: {', '.join(matched_terms[:3])}" if is_medical else "General conversation context"

        return {
            "is_medical": is_medical,
            "category": "medical" if is_medical else "general",
            "matched_terms": matched_terms,
            "reason": reason
        }

    def validate_write(self, agent_id: str, key: str, value: str) -> TrustScoreResult:
        """Validate a proposed memory write.

        Returns TrustScoreResult with score (0-100), reasons, and accepted flag.
        """
        # 1️⃣ LLM based trust scoring via Groq
        try:
            groq_score, groq_reason = self._score_with_groq(key, value)
        except Exception as exc:
            logger.warning("Groq scoring failed: %s. Falling back to score 30.", exc)
            groq_score = 30
            groq_reason = f"Groq call error: {exc}"

        # 2️⃣ Semantic similarity / drift check
        semantic_score, semantic_reason = self._semantic_drift_score(agent_id, value)

        # 3️⃣ Combine scores
        combined = int(groq_score * 0.6 + semantic_score * 0.4)
        accepted = combined >= MEMORY_TRUST_THRESHOLD

        reasons: List[str] = [groq_reason, semantic_reason]
        result = TrustScoreResult(score=combined, reasons=reasons, accepted=accepted)

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

    def _score_with_groq(self, key: str, value: str) -> Tuple[int, str]:
        """Call Groq LLM to obtain a trust score (0-100)."""
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

        try:
            score_part, reason_part = content.split("-", 1)
            score = int(score_part.strip())
            reason = reason_part.strip()
        except Exception:
            import re
            match = re.search(r"(\d{1,3})", content)
            score = int(match.group(1)) if match else 0
            reason = content

        score = max(0, min(100, score))
        return score, reason

    def _semantic_drift_score(self, agent_id: str, new_value: str) -> Tuple[int, str]:
        """Compute similarity of ``new_value`` to the agent's previous writes."""
        if self._embedder[0] == "none":
            return 100, "Semantic drift detection unavailable (no embedding backend)"

        history = self._history_store.load_history(agent_id)
        if not history:
            return 100, "No prior writes – assuming safe"

        new_emb = _embed(self._embedder, [new_value])
        past_vals = [entry["value"] for entry in history]
        past_emb = _embed(self._embedder, past_vals)

        sims = _cosine_similarity(new_emb, past_emb)
        max_sim = float(sims.max())

        score = int(max(0.0, min(1.0, max_sim)) * 100)
        reason = f"Semantic similarity to prior writes: {score}%"
        return score, reason
