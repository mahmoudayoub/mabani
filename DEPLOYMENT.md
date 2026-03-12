# Almabani Deployment Guide

## 1. Architecture: Event-Driven Batch Processing

This deployment implements a **"Process & Die"** architecture using AWS Fargate and S3 Events. There is **no persistent server** running. The system only wakes up when a file is uploaded, processes it, and then terminates.

### Workflow
1. **Frontend/User** uploads a file to S3 in the `input/` folder.
2. **S3 Event Notification** triggers a **Lambda** function.
3. **Lambda** inspects the file path and launches a **Fargate Task**.
4. **Fargate Container** downloads the file, fetches secrets from SSM, runs the worker, uploads results, and **exits**.

### CDK Stacks

| Stack | Compute | Resources |
|-------|---------|-----------|
| **AlmabaniStack** | Fargate (1 vCPU, 2 GB) | VPC, S3, ECS, Lambda trigger, SSM params |
| **PriceCodeStack** | Fargate (2 vCPU, 16 GB) | VPC, S3, ECS, Lambda trigger, SSM params |
| **PriceCodeVectorStack** | Fargate (2 vCPU, 8 GB) | VPC, S3, ECS, Lambda trigger |
| **ChatStack** | Lambda (1 GB, 120s) | API Gateway, Function URL, Lambda layers |
| **DeletionStack** | Lambda (30s-120s) | API Gateway, dispatchers + workers |

---

## 2. Configuration & Secrets (AWS SSM)

Secrets are stored in **AWS Systems Manager (SSM) Parameter Store**. You do **not** need to redeploy to change them.

### Managed Parameters

| Path | Parameters |
|------|------------|
| `/almabani/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL`, `S3_VECTORS_BUCKET`, `S3_VECTORS_INDEX` |
| `/pricecode/*` | `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `S3_VECTORS_BUCKET`, `S3_VECTORS_INDEX` |

### How to Update
1. Navigate to **AWS Console** → **Systems Manager** → **Parameter Store**
2. Edit the parameter value and save
3. The next Fargate task or Lambda invocation will use the new value

---

## 3. Cost Analysis (Zero Idle Cost)

| Component | Idle Cost | Per-Job Cost |
|-----------|----------|-------------|
| Fargate (AlmabaniStack, 1 vCPU/2 GB) | $0.00 | ~$0.004 (5 min job) |
| Fargate (PriceCodeStack, 2 vCPU/16 GB) | $0.00 | ~$0.030 (5 min job) |
| Fargate (PriceCodeVectorStack, 2 vCPU/8 GB) | $0.00 | ~$0.016 (5 min job) |
| Lambda (Chat/Deletion) | $0.00 | ~$0.0001 per invocation |
| NAT Gateway | $0.00 | N/A (public subnets only) |
| S3 | ~$0.02/GB/month | Minimal |

---

## 4. Deployment

```bash
# Install CDK dependencies
pip install -r infra/requirements.txt

# Bootstrap (first time only)
cdk bootstrap aws://239146712026/eu-west-1

# Deploy all stacks
cdk deploy --app "python3 infra/app.py" --all

# Deploy individual stacks
cdk deploy --app "python3 infra/app.py" AlmabaniStack
cdk deploy --app "python3 infra/app.py" PriceCodeStack
cdk deploy --app "python3 infra/app.py" PriceCodeVectorStack
cdk deploy --app "python3 infra/app.py" ChatStack
cdk deploy --app "python3 infra/app.py" DeletionStack
```

---

## 5. Running Jobs

### Unit Rate Pipeline (AlmabaniStack)

| Job | Upload to | Result |
|-----|-----------|--------|
| **Parse** (Excel → JSON) | `s3://<bucket>/input/parse/myfile.xlsx` | `output/indexes/myfile.json` |
| **Fill** (rate matching) | `s3://<bucket>/input/fill/myfile.xlsx` | `output/fills/myfile_filled.xlsx` |

### Price Code Pipeline — Lexical (PriceCodeStack)

| Job | Upload to | Result |
|-----|-----------|--------|
| **Index** (build SQLite index) | `s3://<bucket>/input/pricecode/index/catalog.xlsx` | SQLite index stored in S3 |
| **Allocate** (match BOQ items) | `s3://<bucket>/input/pricecode/allocate/boq.xlsx` | `output/pricecode/boq_allocated.xlsx` |

### Price Code Pipeline — Vector (PriceCodeVectorStack)

| Job | Upload to | Result |
|-----|-----------|--------|
| **Index** (embed to S3 Vectors) | `s3://<bucket>/input/pricecode-vector/index/catalog.xlsx` | Embeddings in S3 Vectors |
| **Allocate** (match BOQ items) | `s3://<bucket>/input/pricecode-vector/allocate/boq.xlsx` | `output/pricecode-vector/boq_allocated.xlsx` |

---

## 6. Chat API (ChatStack)

Natural language queries for unit rates and price codes.

**Endpoints** (check CloudFormation outputs for URLs):
- **Function URL**: `POST <ChatFunctionUrl>` — no timeout (recommended)
- **API Gateway**: `POST <ChatApiUrl>/chat` — 29-second timeout

**Example**:
```bash
# Unit rate query
curl -X POST <ChatFunctionUrl> \
  -H "Content-Type: application/json" \
  -d '{"message": "HDPE pipe DN200 PN16", "type": "unitrate"}'

# Price code query
curl -X POST <ChatFunctionUrl> \
  -H "Content-Type: application/json" \
  -d '{"message": "supply and install HDPE pipe DN200", "type": "pricecode"}'
```

---

## 7. Deletion API (DeletionStack)

Async deletion with status polling.

**Endpoints** (check CloudFormation output `DeletionApiUrl`):
- `DELETE <url>/files/sheets/{sheet_name}` — Delete a unit rate datasheet
- `DELETE <url>/pricecode/sets/{set_name}` — Delete a price code set (lexical)
- `DELETE <url>/pricecode-vector/sets/{set_name}` — Delete a price code set (vector)
- `GET <url>/deletion-status/{deletion_id}` — Poll deletion status

All DELETE endpoints return `202 Accepted` with a `deletion_id` for polling.

---

## 8. Monitoring

| Stack | CloudWatch Log Group |
|-------|---------------------|
| AlmabaniStack | Fargate container logs (unit rate worker) |
| PriceCodeStack | Fargate container logs (pricecode worker) |
| PriceCodeVectorStack | Fargate container logs (pricecode vector worker) |
| ChatStack | Lambda `ChatHandler` logs |
| DeletionStack | Lambda logs per deletion handler |
