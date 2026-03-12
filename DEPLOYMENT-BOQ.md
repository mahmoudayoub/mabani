# Almabani BOQ Management System — Deployment Guide

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Configuration](#2-environment-configuration)
3. [CDK Bootstrap (First Time Only)](#3-cdk-bootstrap-first-time-only)
4. [Deploy All Stacks](#4-deploy-all-stacks)
5. [Deploy Individual Stacks](#5-deploy-individual-stacks)
6. [Verify Deployment](#6-verify-deployment)
7. [Updating Code (Redeployment Required)](#7-updating-code-redeployment-required)
8. [Monitoring & Logs](#8-monitoring--logs)
9. [Troubleshooting](#9-troubleshooting)
10. [Cost Model](#10-cost-model)

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
# Should show your AWS account ID
```

---

## 2. Environment Configuration

The CDK app reads environment variables from `boq-backend/env` (primary) or `.env` (fallback)
at the project root. These values are used to populate SSM parameters and Lambda env vars.

```bash
# Copy the example and fill in real values
cp boq-backend/.env.example boq-backend/env
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

> **Important:** The `boq-backend/env` file is loaded by `infra/app.py` using `python-dotenv`.
> The OPENAI_API_KEY is injected into SSM Parameter Store for Fargate stacks and as a
> Lambda environment variable for ChatStack. Do **not** commit this file to git.

### Cross-Service Bucket Access 

The CDK stacks automatically grant the main Serverless backend (`taskflow-backend`) Lambda
role read/write access to all 3 BOQ S3 buckets. The role name is constructed dynamically:

```
{SERVERLESS_SERVICE_NAME}-{SERVERLESS_STAGE}-{region}-lambdaRole
```

Defaults: `taskflow-backend-dev-eu-west-1-lambdaRole`. Override via `boq-backend/env`:

```ini
SERVERLESS_SERVICE_NAME=taskflow-backend
SERVERLESS_STAGE=dev
```

### Frontend Environment Variables

The React/Vite frontend uses these env vars (in `frontend/.env.local`) to reach the BOQ APIs:

| Variable | Value (from CloudFormation outputs) |
|----------|-------------------------------------|
| `VITE_BOQ_DELETION_API_URL` | `DeletionStack` → `DeletionApiUrl` |
| `VITE_BOQ_CHAT_API_URL` | `ChatStack` → `ChatFunctionUrl` |

---

## 3. CDK Bootstrap (First Time Only)

CDK bootstrap creates an S3 bucket and IAM roles that CDK uses to deploy assets (Docker images, Lambda code).

```bash
# Install CDK dependencies
cd infra
pip install -r requirements.txt
cd ..

# Bootstrap the target account/region
cdk bootstrap aws://<YOUR_ACCOUNT_ID>/eu-west-1 --app "python3 infra/app.py"
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
aws cloudformation describe-stacks --query "Stacks[].Outputs[].[OutputKey,OutputValue,Description]" --output table

# Or specific stacks
aws cloudformation describe-stacks --stack-name ChatStack \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue,Description]" --output table
aws cloudformation describe-stacks --stack-name DeletionStack \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue,Description]" --output table
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
 

---

## 7. Updating Code (Redeployment Required)

When you change Python code, workers, or Lambda handlers:

```bash
# Update boq-backend/env if settings changed
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

## 8. Monitoring & Logs

All services log to **CloudWatch Logs**. Open **AWS Console → CloudWatch → Log groups** and filter by stack name.

| Stack | Filter by | Content |
|-------|-----------|---------|
| AlmabaniStack (Fargate) | `AlmabaniStack` + `ecs` | Parse/fill progress and errors |
| PriceCodeStack (Fargate) | `PriceCodeStack` + `ecs` | Index/allocate progress and errors |
| PriceCodeVectorStack (Fargate) | `PriceCodeVectorStack` + `ecs` | Vector index/allocate progress |
| ChatStack (Lambda) | `ChatStack` | Chat queries, matches, latency |
| DeletionStack (Lambda) | `DeletionStack` | Dispatch/worker/status logs |

**Fargate task status:** AWS Console → **ECS → Clusters** → select the cluster (find it under **CloudFormation → [Stack] → Resources**) → **Tasks** → filter by `RUNNING` or `STOPPED`. Stopped tasks show exit code and stop reason in the task detail view.

---

## 9. Troubleshooting

### Fargate task fails to start

Open **ECS → Clusters → [cluster] → Tasks → Stopped**, click the task, and read the **Stopped reason** and **Exit code** in the detail panel.

- **CannotPullContainerError** — Docker image missing; redeploy the stack to push a fresh image
- **ResourceInitializationError** — Public IP not assigned; verify the subnet has *Auto-assign public IPv4* enabled
- **Exit code 1** — Application error; open the linked CloudWatch log stream for details

### Lambda timeouts

- Chat Lambda has a 120s limit. Check OpenAI API latency in the **CloudWatch → ChatStack** log group.
- Always use the **Function URL** (`ChatFunctionUrl`) instead of API Gateway to avoid the 29s limit.

### Permission errors

- Missing `s3vectors:*` — redeploy the affected stack to re-apply IAM policies
- `ecs:RunTask` denied — the trigger Lambda role needs `ecs:RunTask` + `iam:PassRole`; redeploy

### S3 Vectors index not found

Open **AWS Console → S3 → [bucket] → Vector indexes** (or **S3 Vectors** service if available in the console). If an index is missing, run the corresponding indexing job first.

---

## 10. Cost Model

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
