#!/bin/bash
# ============================================================
# Mem-Shield-AI — AWS Free-Tier Deployment Script
# ============================================================
# Prerequisites:
#   1. AWS CLI installed and configured (aws configure)
#   2. Docker installed and running
#   3. Run from the project root directory
#
# Usage:
#   chmod +x aws/deploy.sh
#   ./aws/deploy.sh
# ============================================================

set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
FUNCTION_NAME="mem-shield-ai"
ECR_REPO="mem-shield-ai"
ALERT_EMAIL="${ALERT_EMAIL:-}"

echo "🛡️  Mem-Shield-AI Deployment"
echo "   Region: $REGION"
echo ""

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
echo "   Account: $ACCOUNT_ID"
echo ""

# ---------------------------------------------------------
# 1. Create ECR Repository
# ---------------------------------------------------------
echo "📦 Step 1/7: Creating ECR repository..."
aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --region "$REGION" 2>/dev/null || echo "   (already exists)"

# ---------------------------------------------------------
# 2. Build and Push Docker Image
# ---------------------------------------------------------
echo "🐳 Step 2/7: Building Docker image (this may take a few minutes)..."
docker build -t "$FUNCTION_NAME" .

echo "   Tagging and pushing to ECR..."
docker tag "$FUNCTION_NAME:latest" "$ECR_URI/$ECR_REPO:latest"
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_URI"
docker push "$ECR_URI/$ECR_REPO:latest"

# ---------------------------------------------------------
# 3. Create DynamoDB Tables
# ---------------------------------------------------------
echo "🗄️  Step 3/7: Creating DynamoDB tables..."
aws dynamodb create-table \
  --table-name mem-shield-steps \
  --attribute-definitions \
    AttributeName=agent_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
  --key-schema \
    AttributeName=agent_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || echo "   (mem-shield-steps already exists)"

aws dynamodb create-table \
  --table-name mem-shield-write-history \
  --attribute-definitions \
    AttributeName=agent_id,AttributeType=S \
    AttributeName=write_ts,AttributeType=N \
  --key-schema \
    AttributeName=agent_id,KeyType=HASH \
    AttributeName=write_ts,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || echo "   (mem-shield-write-history already exists)"

# ---------------------------------------------------------
# 4. Create SNS Topic
# ---------------------------------------------------------
echo "📢 Step 4/7: Creating SNS topic..."
TOPIC_ARN=$(aws sns create-topic \
  --name mem-shield-alerts \
  --region "$REGION" \
  --query TopicArn --output text)
echo "   Topic ARN: $TOPIC_ARN"

if [ -n "$ALERT_EMAIL" ]; then
  echo "   Subscribing $ALERT_EMAIL (check inbox to confirm)..."
  aws sns subscribe \
    --topic-arn "$TOPIC_ARN" \
    --protocol email \
    --notification-endpoint "$ALERT_EMAIL" \
    --region "$REGION"
else
  echo "   ⚠️  Set ALERT_EMAIL env var to auto-subscribe. Example:"
  echo "      ALERT_EMAIL=you@example.com ./aws/deploy.sh"
fi

# ---------------------------------------------------------
# 5. Store Groq API Key in SSM
# ---------------------------------------------------------
echo "🔑 Step 5/7: Storing secrets in SSM Parameter Store..."
if [ -f .env ]; then
  GROQ_KEY=$(grep GROQ_API_KEY .env | cut -d= -f2)
  if [ -n "$GROQ_KEY" ]; then
    aws ssm put-parameter \
      --name "/mem-shield-ai/groq-api-key" \
      --value "$GROQ_KEY" \
      --type SecureString \
      --overwrite \
      --region "$REGION"
    echo "   ✅ Groq API key stored in SSM."
  fi
else
  echo "   ⚠️  No .env file found. Set the SSM parameter manually:"
  echo "      aws ssm put-parameter --name /mem-shield-ai/groq-api-key --value YOUR_KEY --type SecureString"
fi

# ---------------------------------------------------------
# 6. Create IAM Role + Lambda Function
# ---------------------------------------------------------
echo "⚙️  Step 6/7: Creating Lambda function..."
ROLE_NAME="mem-shield-lambda-role"

# Create role (ignore if exists)
aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' 2>/dev/null || echo "   (role already exists)"

# Attach basic Lambda execution policy (CloudWatch Logs)
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

# Attach our custom policy (DynamoDB, SNS, SSM)
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name mem-shield-permissions \
  --policy-document file://aws/iam_policy.json

# Wait for role to propagate
echo "   Waiting 10s for IAM role to propagate..."
sleep 10

ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"

# Create or update Lambda function
aws lambda create-function \
  --function-name "$FUNCTION_NAME" \
  --package-type Image \
  --code "ImageUri=$ECR_URI/$ECR_REPO:latest" \
  --role "$ROLE_ARN" \
  --timeout 30 \
  --memory-size 1024 \
  --environment "Variables={SNS_TOPIC_ARN=$TOPIC_ARN,DYNAMO_STEPS_TABLE=mem-shield-steps,DYNAMO_HISTORY_TABLE=mem-shield-write-history}" \
  --region "$REGION" 2>/dev/null || \
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --image-uri "$ECR_URI/$ECR_REPO:latest" \
  --region "$REGION"

# ---------------------------------------------------------
# 7. Create Function URL (free HTTPS endpoint)
# ---------------------------------------------------------
echo "🌐 Step 7/7: Creating Function URL..."
FUNC_URL=$(aws lambda create-function-url-config \
  --function-name "$FUNCTION_NAME" \
  --auth-type NONE \
  --region "$REGION" \
  --query FunctionUrl --output text 2>/dev/null || \
aws lambda get-function-url-config \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query FunctionUrl --output text)

# Grant public access to the Function URL
aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --region "$REGION" 2>/dev/null || true

echo ""
echo "============================================================"
echo "🎉 Deployment complete!"
echo ""
echo "   🌐 API URL: $FUNC_URL"
echo ""
echo "   Test it:"
echo "   curl ${FUNC_URL}health"
echo "   curl -X POST ${FUNC_URL}memory/write \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"agent_id\":\"test\",\"key\":\"greeting\",\"value\":\"hello world\"}'"
echo ""
echo "   💰 Monthly cost: \$0.00 (all free tier)"
echo "============================================================"
