# memory_firewall configuration
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Default threshold (0-100). Can be overridden via env var.
MEMORY_TRUST_THRESHOLD = int(os.getenv("MEMORY_TRUST_THRESHOLD", "40"))
