# ============================================================
# Mem-Shield-AI — AWS Free-Tier Deployment Script (PowerShell)
# ============================================================

$ErrorActionPreference = "Continue"
$env:AWS_PAGER = ""  # Disable CLI interactive pager
$env:BUILDX_NO_DEFAULT_ATTESTATIONS = "1"

$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }
$FunctionName = "mem-shield-ai"
$EcrRepo = "mem-shield-ai"
$AlertEmail = $env:ALERT_EMAIL

Write-Host "Mem-Shield-AI Deployment" -ForegroundColor Cyan
Write-Host "Region: $Region"

# ---------------------------------------------------------
# Get AWS Account ID
# ---------------------------------------------------------
$AccountId = (aws sts get-caller-identity --query Account --output text --no-cli-pager).Trim()
$EcrUri = "$AccountId.dkr.ecr.$Region.amazonaws.com"
Write-Host "Account: $AccountId`n"

# ---------------------------------------------------------
# 1. Create ECR Repository
# ---------------------------------------------------------
Write-Host "Step 1/7: Creating ECR repository..." -ForegroundColor Yellow
$ecrCheck = aws ecr describe-repositories --repository-names $EcrRepo --region $Region --no-cli-pager 2>$null
if (-not $ecrCheck) {
    aws ecr create-repository --repository-name $EcrRepo --region $Region --no-cli-pager
} else {
    Write-Host "   -> ECR Repository already exists."
}

# ---------------------------------------------------------
# 2. Build and Push Docker Image
# ---------------------------------------------------------
Write-Host "`nStep 2/7: Building Docker image..." -ForegroundColor Yellow
# Disable Buildx attestations so Docker generates standard OCI/Docker V2 manifest for AWS Lambda
docker build --provenance=false -t $FunctionName .

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker build failed! Aborting." -ForegroundColor Red
    exit 1
}

Write-Host "   Tagging and pushing to ECR..."
docker tag "${FunctionName}:latest" "${EcrUri}/${EcrRepo}:latest"

$dockerPassword = aws ecr get-login-password --region $Region --no-cli-pager
$dockerPassword | docker login --username AWS --password-stdin $EcrUri
docker push "${EcrUri}/${EcrRepo}:latest"

# ---------------------------------------------------------
# 3. Create DynamoDB Tables
# ---------------------------------------------------------
Write-Host "`nStep 3/7: Creating DynamoDB tables..." -ForegroundColor Yellow
$tbl1 = aws dynamodb describe-table --table-name mem-shield-steps --region $Region --no-cli-pager 2>$null
if (-not $tbl1) {
    aws dynamodb create-table `
      --table-name mem-shield-steps `
      --attribute-definitions AttributeName=agent_id,AttributeType=S AttributeName=timestamp,AttributeType=N `
      --key-schema AttributeName=agent_id,KeyType=HASH AttributeName=timestamp,KeyType=RANGE `
      --billing-mode PAY_PER_REQUEST `
      --region $Region --no-cli-pager
} else {
    Write-Host "   -> Table mem-shield-steps already exists."
}

$tbl2 = aws dynamodb describe-table --table-name mem-shield-write-history --region $Region --no-cli-pager 2>$null
if (-not $tbl2) {
    aws dynamodb create-table `
      --table-name mem-shield-write-history `
      --attribute-definitions AttributeName=agent_id,AttributeType=S AttributeName=write_ts,AttributeType=N `
      --key-schema AttributeName=agent_id,KeyType=HASH AttributeName=write_ts,KeyType=RANGE `
      --billing-mode PAY_PER_REQUEST `
      --region $Region --no-cli-pager
} else {
    Write-Host "   -> Table mem-shield-write-history already exists."
}

# ---------------------------------------------------------
# 4. Create SNS Topic
# ---------------------------------------------------------
Write-Host "`nStep 4/7: Creating SNS topic..." -ForegroundColor Yellow
$TopicArn = (aws sns create-topic --name mem-shield-alerts --region $Region --query TopicArn --output text --no-cli-pager).Trim()
Write-Host "   Topic ARN: $TopicArn"

if ($AlertEmail) {
    Write-Host "   Subscribing $AlertEmail..."
    aws sns subscribe --topic-arn $TopicArn --protocol email --notification-endpoint $AlertEmail --region $Region --no-cli-pager
} else {
    Write-Host "   Set `$env:ALERT_EMAIL='you@domain.com' to auto-subscribe to email alerts."
}

# ---------------------------------------------------------
# 5. Store Groq API Key in SSM
# ---------------------------------------------------------
Write-Host "`nStep 5/7: Storing secrets in SSM Parameter Store..." -ForegroundColor Yellow
if (Test-Path .env) {
    $groqLine = Get-Content .env | Where-Object { $_ -match "^GROQ_API_KEY=" }
    if ($groqLine) {
        $GroqKey = ($groqLine -split "=", 2)[1].Trim()
        if ($GroqKey) {
            aws ssm put-parameter --name "/mem-shield-ai/groq-api-key" --value $GroqKey --type SecureString --overwrite --region $Region --no-cli-pager
            Write-Host "   -> Groq API key stored in SSM."
        }
    }
} else {
    Write-Host "   No .env file found."
}

# ---------------------------------------------------------
# 6. Create IAM Role + Lambda Function
# ---------------------------------------------------------
Write-Host "`nStep 6/7: Creating Lambda function..." -ForegroundColor Yellow
$RoleName = "mem-shield-lambda-role"

$roleCheck = aws iam get-role --role-name $RoleName --no-cli-pager 2>$null
if (-not $roleCheck) {
    aws iam create-role --role-name $RoleName --assume-role-policy-document file://aws/trust_policy.json --no-cli-pager
} else {
    Write-Host "   -> IAM Role already exists."
}

aws iam attach-role-policy --role-name $RoleName --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --no-cli-pager 2>$null

if (Test-Path aws/iam_policy.json) {
    aws iam put-role-policy --role-name $RoleName --policy-name mem-shield-permissions --policy-document file://aws/iam_policy.json --no-cli-pager 2>$null
}

Write-Host "   Waiting 10s for IAM role propagation..."
Start-Sleep -Seconds 10

$RoleArn = "arn:aws:iam::${AccountId}:role/${RoleName}"

$fnCheck = aws lambda get-function --function-name $FunctionName --region $Region --no-cli-pager 2>$null
if (-not $fnCheck) {
    aws lambda create-function `
      --function-name $FunctionName `
      --package-type Image `
      --code ImageUri="${EcrUri}/${EcrRepo}:latest" `
      --role $RoleArn `
      --timeout 30 `
      --memory-size 1024 `
      --environment "Variables={SNS_TOPIC_ARN=$TopicArn,DYNAMO_STEPS_TABLE=mem-shield-steps,DYNAMO_HISTORY_TABLE=mem-shield-write-history}" `
      --region $Region --no-cli-pager
} else {
    Write-Host "   Updating existing Lambda code..."
    aws lambda update-function-code `
      --function-name $FunctionName `
      --image-uri "${EcrUri}/${EcrRepo}:latest" `
      --region $Region --no-cli-pager
}

# ---------------------------------------------------------
# 7. Create Function URL
# ---------------------------------------------------------
Write-Host "`nStep 7/7: Creating Function URL..." -ForegroundColor Yellow
$urlCheck = aws lambda get-function-url-config --function-name $FunctionName --region $Region --no-cli-pager 2>$null
if (-not $urlCheck) {
    aws lambda create-function-url-config --function-name $FunctionName --auth-type NONE --region $Region --no-cli-pager 2>$null
}

$FuncUrlObj = aws lambda get-function-url-config --function-name $FunctionName --region $Region --query FunctionUrl --output text --no-cli-pager 2>$null
if ($FuncUrlObj) {
    $FuncUrl = $FuncUrlObj.Trim()
} else {
    $FuncUrl = "Failed to retrieve URL"
}

aws lambda add-permission `
  --function-name $FunctionName `
  --statement-id FunctionURLAllowPublicAccess `
  --action lambda:InvokeFunctionUrl `
  --principal "*" `
  --function-url-auth-type NONE `
  --region $Region --no-cli-pager 2>$null

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "   API URL: $FuncUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Test it:"
Write-Host "   curl ${FuncUrl}health"
Write-Host ""
Write-Host "   Monthly cost: `$0.00 (100% free tier)" -ForegroundColor Green
Write-Host "============================================================"
