FROM public.ecr.aws/lambda/python:3.11 AS builder

# Install CPU-only torch FIRST (200MB instead of 2GB)
RUN pip install --no-cache-dir --prefer-binary torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies with --prefer-binary to ensure binary wheels are used
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Pre-download the embedding model at build time (avoids cold-start download)
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

# --- Final stage (copy only what we need) ---
FROM public.ecr.aws/lambda/python:3.11

# Copy installed packages
COPY --from=builder /var/lang/lib/python3.11/site-packages /var/lang/lib/python3.11/site-packages

# Copy cached model
COPY --from=builder /root/.cache /root/.cache

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}

# Lambda handler entrypoint
CMD ["aws.lambda_handler.handler"]
