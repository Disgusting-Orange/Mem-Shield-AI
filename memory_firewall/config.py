# memory_firewall configuration
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_param(ssm_name: str, env_fallback: str, default: str = "") -> str:
    """Try AWS SSM Parameter Store first, fall back to env var for local dev.

    SSM Parameter Store Standard is always free (up to 10,000 parameters).
    """
    # Only try SSM if we're in an AWS environment
    if "AWS_LAMBDA_FUNCTION_NAME" in os.environ or os.environ.get("USE_SSM") == "1":
        try:
            import boto3
            ssm = boto3.client("ssm")
            resp = ssm.get_parameter(Name=ssm_name, WithDecryption=True)
            logger.info("Loaded %s from SSM Parameter Store.", ssm_name)
            return resp["Parameter"]["Value"]
        except Exception as exc:
            logger.warning("SSM lookup failed for %s: %s. Falling back to env var.", ssm_name, exc)

    return os.getenv(env_fallback, default)


GROQ_API_KEY = _get_param("/mem-shield-ai/groq-api-key", "GROQ_API_KEY")

# Default threshold (0-100). Can be overridden via env var.
MEMORY_TRUST_THRESHOLD = int(
    _get_param("/mem-shield-ai/trust-threshold", "MEMORY_TRUST_THRESHOLD", "40")
)
