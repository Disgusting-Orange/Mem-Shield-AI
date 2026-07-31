"""
aws/lambda_handler.py
----------------------
Mangum adapter — translates AWS Lambda events into ASGI (FastAPI) requests.
Your existing FastAPI app needs ZERO changes.

This file is the Lambda entrypoint: CMD ["aws.lambda_handler.handler"]
"""

from mangum import Mangum
from interception_api.main import app

handler = Mangum(app, lifespan="off")
