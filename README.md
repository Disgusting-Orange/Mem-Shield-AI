# 🛡️ Mem-Shield-AI

**Zero-Trust Memory Firewall & Execution Runtime Guardian for Autonomous AI Agents**

> Built at [Frontier Hackathon](https://github.com/Disgusting-Orange/Mem-Shield-AI) — 30–31 July 2026

---

## 🧠 What It Does

Autonomous AI agents can misbehave in subtle, dangerous ways — silently failing, looping endlessly, leaking cost, or getting their memory poisoned by adversarial inputs. **Mem-Shield-AI** acts as a **real-time safety layer** that intercepts and audits every action an agent takes.

### Two Core Modules

| Module | Purpose |
|--------|---------|
| **Memory Firewall** | Validates every memory write using **Groq LLM trust scoring** + **semantic drift detection** (sentence-transformers). Rejects poisoning attempts before they persist. |
| **Execution Guardian** | Tracks agent execution as a **directed graph**, detecting **reasoning loops**, **silent failures**, **redundant API calls**, and estimating **cost leaks** in real time. |

---

## 🏗️ Architecture

```
Agent Action
    │
    ▼
┌──────────────────────────┐
│   FastAPI Interception    │  ← /memory/write  &  /agent/step
│         API               │
└────────┬─────────────────┘
         │
    ┌────┴─────┐
    ▼          ▼
┌────────┐ ┌────────────┐
│ Memory │ │ Execution  │
│Firewall│ │  Guardian  │
│        │ │            │
│• Groq  │ │• Loop det. │
│  LLM   │ │• Silent    │
│• Sem.  │ │  failures  │
│  drift │ │• Redundant │
│        │ │  calls     │
│        │ │• Cost leak │
└────────┘ └────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/Disgusting-Orange/Mem-Shield-AI.git
cd Mem-Shield-AI
git checkout execution-guardian

python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Run the Demo

```bash
python demo/full_pipeline_demo.py
```

> ⏳ First run takes ~30–40 seconds to download the sentence-transformers model. Subsequent runs are faster.

---

## 📡 API Endpoints

### `POST /memory/write`

Validates a proposed memory write before persisting it.

**Request:**
```json
{
  "agent_id": "agent-1",
  "key": "user_preferences",
  "value": "{\"color\": \"blue\"}"
}
```

**Response (accepted):**
```json
{
  "accepted": true,
  "score": 88,
  "reasons": [
    "Low-risk user preference data",
    "No prior writes - assuming safe"
  ]
}
```

**Response (rejected — 400):**
```json
{
  "detail": {
    "accepted": false,
    "score": 0,
    "reasons": [
      "Malicious intent explicitly stated",
      "Semantic similarity to prior writes: 0%"
    ]
  }
}
```

### `POST /agent/step`

Records an execution step and returns a real-time audit report.

**Request:**
```json
{
  "agent_id": "agent-1",
  "step_id": "step-001",
  "action": "search",
  "params": {"query": "best coffee shops"},
  "status": "success",
  "result_payload": "list of shops",
  "cost_estimate": 0.001,
  "timestamp": 1785407685.45
}
```

**Response:**
```json
{
  "loops": [],
  "silent_failures": [],
  "redundant_calls": [["step-001 (dup)", "step-001 (dup)"]],
  "estimated_cost_leak": 0.001
}
```

---

## 🔍 What Gets Detected

| Detection | How It Works |
|-----------|--------------|
| **Memory Poisoning** | Groq LLM scores trust (0–100). Semantic embeddings compare against historical writes. Combined score below threshold → **rejected**. |
| **Silent Failures** | Agent says `status: "success"` but payload contains `"error"`, `"timeout"`, `"traceback"`, etc. |
| **Redundant Calls** | Same `(action, params)` within a 30-second window → flagged as wasteful. |
| **Reasoning Loops** | Execution graph analyzed with NetworkX cycle detection. |
| **Cost Leaks** | Sum of `cost_estimate` for all redundant + looped steps. |

---

## 📁 Project Structure

```
Mem-Shield-AI/
├── memory_firewall/
│   ├── __init__.py
│   ├── config.py          # Groq API key, trust threshold
│   ├── firewall.py         # MemoryFirewall class
│   └── models.py           # TrustScoreResult dataclass
├── interception_api/
│   ├── __init__.py
│   └── main.py             # FastAPI app (/memory/write, /agent/step)
├── demo/
│   └── full_pipeline_demo.py  # End-to-end demo script
├── guardian.py              # ExecutionGuardian class
├── models.py                # ExecutionStep dataclass
├── state_store.py           # SQLite-backed step log
├── config.py                # Detection thresholds
├── requirements.txt
├── .env                     # (not tracked) Groq API key
└── README.md
```

---

## 🛠️ Tech Stack

- **Python 3.11+**
- **FastAPI** + **Uvicorn** — async HTTP interception layer
- **Groq API** (Llama 3.3 70B) — LLM-based trust scoring
- **sentence-transformers** (all-MiniLM-L6-v2) — semantic drift detection
- **NetworkX** — execution graph & cycle detection
- **SQLite** — lightweight persistent step log
- **Pydantic** — request validation

---

## 👥 Team

**Disgusting Orange** — Frontier Hackathon 2026

---

## 📄 License

MIT
