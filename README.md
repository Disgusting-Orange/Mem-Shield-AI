# 🛡️ Mem-Shield-AI

**Zero-Trust Memory Firewall & Execution Runtime Guardian for Autonomous AI Agents**

> Built at [Frontier Hackathon](https://github.com/Disgusting-Orange/Mem-Shield-AI) — 30–31 July 2026

---

## 🧠 What It Does

Autonomous AI agents can misbehave in subtle, dangerous ways — silently failing, looping endlessly, leaking cost, or getting their memory poisoned by adversarial inputs. **Mem-Shield-AI** acts as a **real-time safety layer** that intercepts, audits, and secures every step and memory write an agent takes.

### Two Core Engines

| Engine | Purpose |
|--------|---------|
| **Memory Firewall** | Validates every memory write using **Groq LLM trust scoring** + **semantic drift detection** (sentence-transformers / ONNX). Rejects memory poisoning & prompt injection attempts before they persist. |
| **Execution Guardian** | Tracks agent execution as a **directed graph (NetworkX)**, detecting **reasoning loops**, **silent failures**, **redundant API calls**, and estimating **cost leaks** in real time. |

---

## 🏗️ System Architecture

```
                               ┌───────────────────────────────────┐
                               │       Autonomous AI Agent         │
                               └─────────────────┬─────────────────┘
                                                 │
                                                 │ HTTP POST
                                                 ▼
                               ┌───────────────────────────────────┐
                               │     FastAPI Interception API      │
                               │   (/memory/write & /agent/step)   │
                               └─────────────────┬─────────────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        ▼                                                 ▼
         ┌──────────────────────────────┐                 ┌──────────────────────────────┐
         │       Memory Firewall        │                 │  Execution Runtime Guardian  │
         │  (Pre-Persistence Defense)   │                 │     (Live Graph Auditor)     │
         ├──────────────────────────────┤                 ├──────────────────────────────┤
         │ • Groq LLM (Llama 3.3 70B)   │                 │ • Directed Graph (NetworkX)  │
         │   Intent Trust Scoring       │                 │ • Graph Loop/Cycle Detection │
         │ • Semantic Drift Detection   │                 │ • Silent Failure Detection   │
         │   (Sentence Embeddings)      │                 │ • Redundant Call Detection   │
         │ • Weighted Blended Score     │                 │ • Real-time Cost Leak Math   │
         └──────────────┬───────────────┘                 └──────────────┬───────────────┘
                        │                                                │
                        ▼                                                ▼
         ┌──────────────────────────────┐                 ┌──────────────────────────────┐
         │     ACCEPT / REJECT Write    │                 │   Audit Report + SNS Alert   │
         └──────────────────────────────┘                 └──────────────┴───────────────┘
```

---

## 🔍 Detection Capabilities

| Detection | How It Works |
|-----------|--------------|
| **Memory Poisoning** | Groq LLM scores trust (0–100). Semantic embeddings compare against historical writes. Combined score below threshold (40) → **rejected**. |
| **Reasoning Loops** | Execution graph analyzed with NetworkX cycle detection (Johnson's algorithm) to catch loops (`A → B → C → A`). |
| **Silent Failures** | Cross-checks step `status == "success"` against error signatures in the payload (`"error"`, `"timeout"`, `"traceback"`). |
| **Redundant Calls** | Flags identical `(action, params)` pairs executed within a 30-second window. |
| **Cost Leaks** | Sum of estimated costs for all redundant + loop cycle steps. |

---

## ☁️ Dual Execution Modes: Local vs AWS ($0.00 Free Tier)

Mem-Shield-AI uses abstract interfaces (`interfaces.py`) to auto-wire local or cloud backends based on the runtime environment:

| Service | Local Mode | AWS Cloud Mode (100% Free Tier) |
| :--- | :--- | :--- |
| **Compute** | Uvicorn (`localhost:8000`) | **AWS Lambda** (Container) + **Lambda Function URL** (1M req/mo free) |
| **Step Storage** | SQLite (`agentguardian.db`) | **Amazon DynamoDB** (`mem-shield-steps`, 25 GB free) |
| **Firewall Memory** | In-Memory `dict` | **Amazon DynamoDB** (`mem-shield-write-history`, 25 GB free) |
| **Alerting** | Console Logging | **Amazon SNS** (`mem-shield-alerts` → Instant Email Notifications) |
| **Logging** | Human-readable stdout | **AWS CloudWatch Logs** (Structured JSON, 5 GB/mo free) |
| **Secrets** | Local `.env` file | **AWS SSM Parameter Store** (SecureString, Always Free) |
| **Registry** | N/A | **Amazon ECR** (500 MB free allowance) |

---

## 🚀 Quick Start

### Option A: Local Development

#### 1. Setup Environment
```bash
git clone https://github.com/Disgusting-Orange/Mem-Shield-AI.git
cd Mem-Shield-AI

python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

#### 2. Configure Groq API Key
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_groq_api_key_here
MEMORY_TRUST_THRESHOLD=40
```

#### 3. Run full pipeline demo
```bash
python demo/full_pipeline_demo.py
```

---

### Option B: Deploy to AWS ($0.00 Free Tier)

Prerequisites: AWS CLI installed and configured (`aws configure`).

#### Deploy on Windows PowerShell:
```powershell
$env:ALERT_EMAIL="your_email@domain.com"
.\aws\deploy.ps1
```

#### Deploy on Linux / macOS / Git Bash:
```bash
ALERT_EMAIL="your_email@domain.com" ./aws/deploy.sh
```

*The script automatically builds the Docker container, pushes to ECR, sets up DynamoDB tables, SNS topics, SSM parameters, and outputs your public Lambda Function URL!*

---

## 📡 API Endpoints

### 1. `POST /memory/write`
Validates a proposed memory write before persisting it.

**Request:**
```json
{
  "agent_id": "agent-1",
  "key": "user_preferences",
  "value": "{\"color\": \"blue\"}"
}
```

**Response (accepted — 200):**
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
    "score": 12,
    "reasons": [
      "Malicious override attempt detected",
      "Semantic similarity to prior writes: 15%"
    ]
  }
}
```

---

### 2. `POST /agent/step`
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
  "redundant_calls": [],
  "estimated_cost_leak": 0.0
}
```

---

### 3. `GET /health`
Health check endpoint for Lambda Function URLs and load balancers.

**Response:**
```json
{
  "status": "healthy",
  "service": "mem-shield-ai"
}
```

---

## 📁 Project Structure

```
Mem-Shield-AI/
├── memory_firewall/
│   ├── __init__.py
│   ├── config.py              # SSM-first & .env config loader
│   ├── firewall.py            # MemoryFirewall (LLM + Embeddings)
│   └── models.py              # TrustScoreResult dataclass
├── interception_api/
│   ├── __init__.py
│   └── main.py                # FastAPI app & environment auto-wiring
├── aws/
│   ├── deploy.ps1             # PowerShell one-click AWS deploy script
│   ├── deploy.sh              # Bash one-click AWS deploy script
│   ├── dynamo_store.py        # DynamoDB step storage
│   ├── dynamo_history_store.py# DynamoDB memory history storage
│   ├── sns_alert_sink.py      # SNS email alert sink
│   ├── logging_config.py      # CloudWatch JSON logger
│   ├── lambda_handler.py      # Mangum ASGI Lambda adapter
│   ├── iam_policy.json        # IAM permissions
│   └── trust_policy.json      # IAM trust policy
├── demo/
│   └── full_pipeline_demo.py  # End-to-end 5-attack simulation
├── guardian.py                # ExecutionGuardian engine (NetworkX graph)
├── interfaces.py              # Abstract Base Classes (Repository pattern)
├── models.py                  # ExecutionStep dataclass
├── state_store.py             # SQLite step storage
├── config.py                  # Guardian detection parameters
├── Dockerfile                 # Multi-stage CPU-optimized build
├── .dockerignore              # Container exclusions
├── requirements.txt           # Python package dependencies
└── README.md
```

---

## 🛠️ Tech Stack

- **Python 3.11+**
- **FastAPI** + **Uvicorn** / **Mangum** — ASGI web framework & Lambda adapter
- **Groq API** (Llama 3.3 70B) — LLM trust scoring
- **sentence-transformers** / **ONNX** — Vector embeddings (`all-MiniLM-L6-v2`)
- **NetworkX** — Graph theory cycle detection
- **Amazon Web Services (AWS)** — Lambda, DynamoDB, SNS, SSM, CloudWatch, ECR
- **SQLite** — Local persistent storage
- **Pydantic v2** — Data validation

---

## 👥 Team
Frontier Hackathon 2026

- **Kamalesh N**
- **S Priyankaa**
- **Sai Abhishek D**

---

## 📄 License
MIT License
