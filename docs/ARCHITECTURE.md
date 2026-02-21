# Architecture

## Overview

Almabani uses an **event-driven serverless architecture** on AWS. There are no persistent servers — compute resources spin up on demand and terminate after processing.

The system is split into **4 independent CDK stacks**, each with its own compute, triggers, and API endpoints.

---

## CDK Stacks

### 1. AlmabaniStack (Unit Rate Processing)

**Purpose**: Parse Excel BOQs and fill unit rates using AI matching.

| Resource | Configuration |
|----------|--------------|
| VPC | Public subnets only (no NAT Gateway) |
| S3 Bucket | `AlmabaniData` — versioning off, CORS enabled, auto-delete |
| ECS Cluster | `AlmabaniCluster` — Fargate capacity provider |
| Fargate Task | 1 vCPU, 2 GB RAM, Docker image from `Dockerfile` |
| Lambda Trigger | Python 3.9, `trigger.py`, 30s timeout |
| SSM Parameters | `/almabani/OPENAI_API_KEY`, `/almabani/PINECONE_API_KEY`, etc. |

**S3 Path Routing** (handled by `trigger.py`):
- `input/parse/*.xlsx` → `JOB_MODE=PARSE` → `worker.py` → `output/indexes/*.json`
- `input/fill/*.xlsx` → `JOB_MODE=FILL` → `worker.py` → `output/fills/*_filled.xlsx`

---

### 2. PriceCodeStack (Price Code Allocation)

**Purpose**: Index price code catalogs and allocate codes to BOQ items.

| Resource | Configuration |
|----------|--------------|
| VPC | Own VPC (standalone mode) or shared from AlmabaniStack |
| S3 Bucket | Own bucket (standalone) or shared |
| ECS Cluster | `PriceCodeCluster` |
| Fargate Task | **2 vCPU, 8 GB RAM** (large Excel files), Docker image from `Dockerfile.pricecode` |
| Lambda Trigger | Python 3.9, `pricecode_trigger.py`, 30s timeout |
| SSM Parameters | `/pricecode/OPENAI_API_KEY`, `/pricecode/PINECONE_API_KEY`, etc. |

**S3 Path Routing** (handled by `pricecode_trigger.py`):
- `input/pricecode/index/*.xlsx` → `JOB_MODE=INDEX` → `pricecode_worker.py` → Pinecone index
- `input/pricecode/allocate/*.xlsx` → `JOB_MODE=ALLOCATE` → `pricecode_worker.py` → `output/pricecode/*_allocated.xlsx`

---

### 3. ChatStack (Natural Language API)

**Purpose**: Chat interface for querying unit rates and price codes in natural language.

| Resource | Configuration |
|----------|--------------|
| Lambda | Python 3.11, `chat_handler.handler`, 1024 MB, **120s timeout** |
| Lambda Layer | `ChatDepsLayer` — openai, pinecone dependencies |
| API Gateway | REST API `Almabani Chat API`, POST `/chat`, CORS enabled |
| Function URL | **No timeout limit** — recommended for long LLM calls |

**Two access methods**:
1. **API Gateway** (`ChatApiUrl`): `POST /chat` — has 29-second timeout
2. **Function URL** (`ChatFunctionUrl`): Direct Lambda invocation — **no timeout** (recommended)

**Chat flow**:
1. Validate input is construction-related (LLM classification)
2. Create embedding with OpenAI
3. Search Pinecone index (unit rate or price code based on `chat_type`)
4. LLM matching with domain-specific prompts
5. Return structured results with confidence scores

---

### 4. DeletionStack (Data Management API)

**Purpose**: Delete datasheets and price code sets from Pinecone and S3.

| Resource | Configuration |
|----------|--------------|
| Lambda (Datasheet) | Python 3.11, `delete_handler.delete_datasheet`, 30s timeout |
| Lambda (Price Code) | Python 3.11, `delete_handler.delete_price_code_set`, 30s timeout |
| Lambda Layer | `DeletionDependenciesLayer` — pinecone-client, boto3 |
| API Gateway | REST API `Almabani Sheet Deletion`, CORS enabled |
| Shared Buckets | References `AlmabaniStack.bucket` + `PriceCodeStack.bucket` |

**API Endpoints**:
- `DELETE /files/sheets/{sheet_name}` — Remove a datasheet from Pinecone and S3 registry
- `DELETE /pricecode/sets/{set_name}` — Remove a price code set from Pinecone index

---

## Event-Driven Flow

```
┌─────────┐     ┌──────────────────┐     ┌─────────────┐     ┌───────────────┐
│  Upload  │────▶│  S3 Notification │────▶│   Lambda     │────▶│  Fargate Task │
│  to S3   │     │  (OBJECT_CREATED)│     │  (trigger)   │     │  (worker.py)  │
└─────────┘     └──────────────────┘     └─────────────┘     └───────┬───────┘
                                                                      │
                                                          ┌───────────┼───────────┐
                                                          │           │           │
                                                    ┌─────▼──┐  ┌────▼───┐  ┌────▼────┐
                                                    │Download │  │Process │  │ Upload  │
                                                    │from S3  │  │  file  │  │to S3 +  │
                                                    │         │  │(AI/ML) │  │  EXIT   │
                                                    └────────┘  └────────┘  └─────────┘
```

**Key points**:
- Lambda only determines mode and launches Fargate — it does no processing
- Fargate container fetches secrets from SSM Parameter Store at startup
- Container runs in public subnet with public IP (no NAT Gateway = zero idle cost)
- Container exits immediately after uploading results

---

## Secrets Management

All API keys and configuration are stored in **AWS SSM Parameter Store**:

| Path | Used By | Parameters |
|------|---------|------------|
| `/almabani/*` | AlmabaniStack | `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL`, `PINECONE_ENVIRONMENT` |
| `/pricecode/*` | PriceCodeStack | Same set of parameters, separate values |

ChatStack and DeletionStack receive API keys directly as Lambda environment variables (set at deploy time from local env).

**Updating secrets** does not require redeployment — the next Fargate task will fetch the latest values from SSM.

---

## Pinecone Indexes

| Index | Used For | Queried By |
|-------|----------|------------|
| `almabani-1` | Unit rate items from BOQ datasheets | Rate filler pipeline, Chat API (unitrate mode) |
| `almabani-pricecode` | Price code catalog items | Price code allocator, Chat API (pricecode mode) |

Both use `text-embedding-3-small` (1536 dimensions, cosine similarity).

---

## Cost Model

| Component | Idle Cost | Per-Job Cost |
|-----------|----------|-------------|
| Fargate (AlmabaniStack) | $0.00 | ~$0.004 (5 min job) |
| Fargate (PriceCodeStack) | $0.00 | ~$0.016 (5 min, 2vCPU/8GB) |
| Lambda (Chat/Deletion) | $0.00 | ~$0.0001 per invocation |
| NAT Gateway | $0.00 | N/A (public subnets only) |
| S3 | ~$0.02/GB/month | Minimal |
| Pinecone | Per plan | Per plan |
