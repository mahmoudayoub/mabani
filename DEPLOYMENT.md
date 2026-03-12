# Almabani BOQ Management System — Deployment Guide

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Configuration](#2-environment-configuration)
3. [CDK Bootstrap (First Time Only)](#3-cdk-bootstrap-first-time-only)
4. [Deploy All Stacks](#4-deploy-all-stacks)
5. [Deploy Individual Stacks](#5-deploy-individual-stacks)
6. [Verify Deployment](#6-verify-deployment)
7. [Running Jobs](#7-running-jobs)
8. [Chat API Usage](#8-chat-api-usage)
9. [Deletion API Usage](#9-deletion-api-usage)
10. [Updating Secrets (No Redeployment)](#10-updating-secrets-no-redeployment)
11. [Updating Code (Redeployment Required)](#11-updating-code-redeployment-required)
12. [Monitoring & Logs](#12-monitoring--logs)
13. [Troubleshooting](#13-troubleshooting)
14. [Cost Model](#14-cost-model)

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `pyenv install 3.11` or system package manager |
| AWS CLI | v2 | `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install` |
| AWS CDK | v2 | `npm install -g aws-cdk` |
| Docker | 20+ | Required for building Fargate container images |
| Node.js | 18+ | Required by AWS CDK CLI |

**AWS Credentials** must be configured:

```bash
aws configure
# AWS Access Key ID: <your-key>
# AWS Secret Access Key: <your-secret>
# Default region name: eu-west-1
# Default output format: json
```

Verify access:

```bash
aws sts get-caller-identity
# Should show account 239146712026
```

---

## 2. Environment Configuration

The CDK app reads environment variables from `backend/env` (primary) or `.env` (fallback)
at the project root. These values are used to populate SSM parameters and Lambda env vars.

```bash
# Copy the example and fill in real values
cp backend/.env.example backend/env
```

**Required variables:**

```ini
# OpenAI API (REQUIRED)
OPENAI_API_KEY=sk-...your-actual-key...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-5-mini-2025-08-07
OPENAI_TEMPERATURE=1

# AWS S3 Vectors (REQUIRED)
S3_VECTORS_BUCKET=almabani-vectors
S3_VECTORS_INDEX_NAME=almabani
PRICECODE_INDEX_NAME=almabani-pricecode-vector

# Pipeline Settings
SIMILARITY_THRESHOLD=0.5
TOP_K=10
BATCH_SIZE=500
MAX_WORKERS=200
EMBEDDINGS_RPM=2000
CHAT_RPM=400

# Price Code Settings
PRICECODE_MAX_CONCURRENT=100
PRICECODE_MAX_CANDIDATES=1

# Logging
LOG_LEVEL=INFO
```

> **Important:** The `backend/env` file is loaded by `infra/app.py` using `python-dotenv`.
> The OPENAI_API_KEY is injected into SSM Parameter Store for Fargate stacks and as a
> Lambda environment variable for ChatStack. Do **not** commit this file to git.

---

## 3. CDK Bootstrap (First Time Only)

CDK bootstrap creates an S3 bucket and IAM roles that CDK uses to deploy assets (Docker images, Lambda code).

```bash
# Install CDK dependencies
cd infra
pip install -r requirements.txt
cd ..

# Bootstrap the target account/region
cdk bootstrap aws://239146712026/eu-west-1 --app "python3 infra/app.py"
```

This only needs to be run once per account/region.

---

## 4. Deploy All Stacks

```bash
# Deploy everything (will prompt for IAM changes)
cdk deploy --app "python3 infra/app.py" --all

# Deploy without prompts (CI/CD)
cdk deploy --app "python3 infra/app.py" --all --require-approval never
```

### What CDK Does

For each stack, CDK will:

1. **Build Docker images** locally (for Fargate stacks) and push to ECR
2. **Package Lambda code** and upload to S3
3. **Create/update CloudFormation stacks** with all resources
4. **Set up IAM roles** with least-privilege permissions
5. **Configure S3 event notifications** to trigger Lambdas
6. **Create SSM parameters** with OpenAI keys and config

### Deployment Order

CDK handles inter-stack dependencies automatically:

```
AlmabaniStack  ──┐
PriceCodeStack ──┼──▶ DeletionStack (receives bucket refs)
PriceCodeVectorStack ──┘
ChatStack (independent)
```

---

## 5. Deploy Individual Stacks

```bash
# Unit Rate pipeline
cdk deploy --app "python3 infra/app.py" AlmabaniStack

# Price Code Lexical pipeline
cdk deploy --app "python3 infra/app.py" PriceCodeStack

# Price Code Vector pipeline
cdk deploy --app "python3 infra/app.py" PriceCodeVectorStack

# Chat API
cdk deploy --app "python3 infra/app.py" ChatStack

# Deletion API (depends on the 3 pipeline stacks)
cdk deploy --app "python3 infra/app.py" DeletionStack
```

> **Note:** DeletionStack depends on AlmabaniStack, PriceCodeStack, and
> PriceCodeVectorStack for bucket references. Deploy those first.

---

## 6. Verify Deployment

After deployment, check the CloudFormation outputs:

```bash
# List all stack outputs
aws cloudformation describe-stacks --query "Stacks[].Outputs" --output table

# Or specific stacks
aws cloudformation describe-stacks --stack-name ChatStack --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name DeletionStack --query "Stacks[0].Outputs"
```

**Expected outputs:**

| Stack | Output | Description |
|-------|--------|-------------|
| AlmabaniStack | `S3BucketName` | S3 bucket for unit rate files |
| PriceCodeStack | `PriceCodeS3BucketName` | S3 bucket for price code files |
| PriceCodeVectorStack | `PriceCodeVectorBucketName` | S3 bucket for vector price code files |
| ChatStack | `ChatFunctionUrl` | Lambda Function URL (recommended, no timeout) |
| ChatStack | `ChatApiUrl` | API Gateway URL (29s timeout limit) |
| DeletionStack | `DeletionApiUrl` | Deletion API base URL |

Verify the Chat Lambda is working:

```bash
# Get the Function URL from outputs
CHAT_URL=$(aws cloudformation describe-stacks --stack-name ChatStack \
  --query "Stacks[0].Outputs[?OutputKey=='ChatFunctionUrl'].OutputValue" --output text)

# Warmup test
curl -s -X POST "$CHAT_URL" \
  -H "Content-Type: application/json" \
  -d '{"message": "warmup", "type": "unitrate"}' | python3 -m json.tool
```

---

## 7. Running Jobs

### Unit Rate Pipeline (AlmabaniStack)

| Job | Upload To | Result |
|-----|-----------|--------|
| **Parse** (Excel → JSON) | `s3://<bucket>/input/parse/myfile.xlsx` | `output/indexes/myfile.json` |
| **Fill** (rate matching) | `s3://<bucket>/input/fill/myfile.xlsx` | `output/fills/myfile_filled.xlsx` |

```bash
# Get the bucket name
BUCKET=$(aws cloudformation describe-stacks --stack-name AlmabaniStack \
  --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" --output text)

# Parse a BOQ file
aws s3 cp my_boq.xlsx s3://$BUCKET/input/parse/my_boq.xlsx

# Fill unit rates
aws s3 cp my_boq.xlsx s3://$BUCKET/input/fill/my_boq.xlsx

# Check output (after processing completes)
aws s3 ls s3://$BUCKET/output/indexes/
aws s3 ls s3://$BUCKET/output/fills/
```

### Price Code Lexical Pipeline (PriceCodeStack)

| Job | Upload To | Result |
|-----|-----------|--------|
| **Index** (build SQLite DB) | `s3://<bucket>/input/pricecode/index/catalog.xlsx` | SQLite DB in S3 |
| **Allocate** (match BOQ items) | `s3://<bucket>/input/pricecode/allocate/boq.xlsx` | `output/pricecode/boq_allocated.xlsx` |

```bash
PC_BUCKET=$(aws cloudformation describe-stacks --stack-name PriceCodeStack \
  --query "Stacks[0].Outputs[?OutputKey=='PriceCodeS3BucketName'].OutputValue" --output text)

# Index price codes
aws s3 cp catalog.xlsx s3://$PC_BUCKET/input/pricecode/index/catalog.xlsx

# Allocate price codes to BOQ
aws s3 cp boq.xlsx s3://$PC_BUCKET/input/pricecode/allocate/boq.xlsx
```

### Price Code Vector Pipeline (PriceCodeVectorStack)

| Job | Upload To | Result |
|-----|-----------|--------|
| **Index** (embed → S3 Vectors) | `s3://<bucket>/input/pricecode-vector/index/catalog.xlsx` | Embeddings in S3 Vectors |
| **Allocate** (similarity match) | `s3://<bucket>/input/pricecode-vector/allocate/boq.xlsx` | `output/pricecode-vector/boq_allocated.xlsx` |

```bash
PCV_BUCKET=$(aws cloudformation describe-stacks --stack-name PriceCodeVectorStack \
  --query "Stacks[0].Outputs[?OutputKey=='PriceCodeVectorBucketName'].OutputValue" --output text)

# Index price codes as embeddings
aws s3 cp catalog.xlsx s3://$PCV_BUCKET/input/pricecode-vector/index/catalog.xlsx

# Allocate using vector search
aws s3 cp boq.xlsx s3://$PCV_BUCKET/input/pricecode-vector/allocate/boq.xlsx
```

---

## 8. Chat API Usage

```bash
# Unit rate query
curl -X POST "$CHAT_URL" \
  -H "Content-Type: application/json" \
  -d '{"message": "HDPE pipe DN200 PN16 supply and install", "type": "unitrate"}'

# Price code query
curl -X POST "$CHAT_URL" \
  -H "Content-Type: application/json" \
  -d '{"message": "supply and install HDPE pipe DN200", "type": "pricecode"}'
```

**Response format:**

```json
{
  "status": "success",
  "message": "Found matching items",
  "matches": [
    {
      "code": "PC-1234",
      "description": "Supply and install HDPE pipe DN200 PN16",
      "reference": {
        "sheet_name": "Piping",
        "source_file": "catalog_v3.xlsx"
      }
    }
  ]
}
```

> **Tip:** Use the Function URL (`ChatFunctionUrl`) instead of API Gateway to avoid
> the 29-second timeout limit on complex queries.

---

## 9. Deletion API Usage

```bash
DEL_URL=$(aws cloudformation describe-stacks --stack-name DeletionStack \
  --query "Stacks[0].Outputs[?OutputKey=='DeletionApiUrl'].OutputValue" --output text)

# Delete a unit rate datasheet
curl -X DELETE "${DEL_URL}files/sheets/my_sheet_name"

# Delete a lexical price code set
curl -X DELETE "${DEL_URL}pricecode/sets/my_price_set"

# Delete a vector price code set
curl -X DELETE "${DEL_URL}pricecode-vector/sets/my_vector_set"

# Poll deletion status (returned in the 202 response)
curl "${DEL_URL}deletion-status/ds_1234567890_my_sheet_name"
```

All DELETE endpoints return `202 Accepted` with a `deletion_id` for status polling.

---

## 10. Updating Secrets (No Redeployment)

Fargate stacks read secrets from **SSM Parameter Store** at container start time.
You can update them without redeploying:

```bash
# Update OpenAI API key for unit rate pipeline
aws ssm put-parameter --name "/almabani/OPENAI_API_KEY" \
  --value "sk-new-key" --type String --overwrite

# Update for price code pipeline
aws ssm put-parameter --name "/pricecode/OPENAI_API_KEY" \
  --value "sk-new-key" --type String --overwrite

# Update for vector pipeline
aws ssm put-parameter --name "/pricecode-vector/OPENAI_API_KEY" \
  --value "sk-new-key" --type String --overwrite
```

**SSM Parameter paths:**

| Path | Parameters |
|------|------------|
| `/almabani/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |
| `/pricecode/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |
| `/pricecode-vector/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL` |

> **Note:** ChatStack and DeletionStack receive the API key as a Lambda env var.
> To update those, you must either redeploy or update the Lambda config directly:
>
> ```bash
> aws lambda update-function-configuration --function-name <ChatHandlerName> \
>   --environment "Variables={OPENAI_API_KEY=sk-new-key,...}"
> ```

---

## 11. Updating Code (Redeployment Required)

When you change Python code, workers, or Lambda handlers:

```bash
# Update backend/.env (or backend/env) if settings changed
# Then redeploy the affected stacks

# If you changed worker.py or almabani/ package:
cdk deploy --app "python3 infra/app.py" AlmabaniStack

# If you changed pricecode_worker.py:
cdk deploy --app "python3 infra/app.py" PriceCodeStack

# If you changed pricecode_vector_worker.py:
cdk deploy --app "python3 infra/app.py" PriceCodeVectorStack

# If you changed chat_handler.py or chat_deps layer:
cdk deploy --app "python3 infra/app.py" ChatStack

# If you changed delete_handler.py:
cdk deploy --app "python3 infra/app.py" DeletionStack
```

CDK automatically rebuilds Docker images and uploads new Lambda code.

---

## 12. Monitoring & Logs

All services log to **CloudWatch Logs**:

| Stack | Log Group | Content |
|-------|-----------|---------|
| AlmabaniStack | `/ecs/AlmabaniWorker` | Parse/fill progress, timing, errors |
| PriceCodeStack | `/ecs/PriceCodeWorker` | Index/allocate progress, LLM calls |
| PriceCodeVectorStack | `/ecs/PriceCodeVectorWorker` | Embedding/allocation progress |
| ChatStack | `/aws/lambda/ChatHandler` | Chat queries, matches, latency |
| DeletionStack | `/aws/lambda/...` | Dispatch/worker/status logs |

```bash
# Tail Fargate logs live
aws logs tail /ecs/AlmabaniWorker --follow

# View recent Chat Lambda logs
aws logs tail /aws/lambda/ChatStack-ChatHandler --since 1h
```

**Fargate task status:**

```bash
# List running tasks
aws ecs list-tasks --cluster AlmabaniCluster --desired-status RUNNING

# List stopped tasks (to check exit codes)
aws ecs list-tasks --cluster AlmabaniCluster --desired-status STOPPED
```

---

## 13. Troubleshooting

### Fargate task fails to start

```bash
# Check task stopped reason
TASK_ARN=$(aws ecs list-tasks --cluster AlmabaniCluster --desired-status STOPPED \
  --query "taskArns[0]" --output text)
aws ecs describe-tasks --cluster AlmabaniCluster --tasks $TASK_ARN \
  --query "tasks[0].{status:lastStatus,reason:stoppedReason,exitCode:containers[0].exitCode}"
```

**Common causes:**
- **CannotPullContainerError**: Docker image not found → redeploy to push new image
- **ResourceInitializationError**: Public IP not assigned → check subnet is public
- **Exit code 1**: Application error → check CloudWatch logs

### Lambda timeouts

- Chat Lambda: 120s limit. If queries time out, check OpenAI API latency
- Use the Function URL instead of API Gateway (avoids 29s limit)

### Permission errors

- `s3vectors:*` permission missing: Redeploy the affected stack
- `ecs:RunTask` denied: Trigger Lambda role needs `ecs:RunTask` + `iam:PassRole`

### S3 Vectors index not found

```bash
# List indices
aws s3vectors list-indexes --index-bucket almabani-vectors
```

If an index doesn't exist, run the corresponding indexing job first.

---

## 14. Cost Model

This architecture has **zero idle cost**:

| Component | Idle Cost | Per-Job Cost (~5 min) |
|-----------|----------|-----------------------|
| Fargate — AlmabaniStack (1 vCPU, 2 GB) | $0.00 | ~$0.004 |
| Fargate — PriceCodeStack (4 vCPU, 16 GB) | $0.00 | ~$0.030 |
| Fargate — PriceCodeVectorStack (2 vCPU, 8 GB) | $0.00 | ~$0.016 |
| Lambda (Chat, Deletion) | $0.00 | ~$0.0001 per call |
| NAT Gateway | $0.00 | N/A (public subnets only) |
| S3 + S3 Vectors | ~$0.02/GB/month | Minimal |

> All VPCs use **public subnets only** with 0 NAT Gateways.
> Fargate tasks get `assignPublicIp: ENABLED` for internet access.
