# Architecture

## Overview

Almabani uses an **event-driven serverless architecture** on AWS. There are no persistent servers — compute resources spin up on demand and terminate after processing.

The system is split into **5 independent CDK stacks**, each with its own compute, triggers, and API endpoints.

---

## CDK Stacks

### 1. AlmabaniStack (Unit Rate Processing)

**Purpose**: Parse Excel BOQs and fill unit rates using AI matching.

| Resource | Configuration |
|----------|--------------|
| VPC | Public subnets only (no NAT Gateway) |
| S3 Bucket | `AlmabaniData` — CORS enabled, auto-delete |
| ECS Cluster | `AlmabaniCluster` — Fargate capacity provider |
| Fargate Task | 1 vCPU, 2 GB RAM |
| Lambda Trigger | `trigger.py` — routes S3 events to Fargate |
| SSM Parameters | `/almabani/*` (OpenAI keys, S3 Vectors config) |

**S3 Path Routing**:
- `input/parse/*.xlsx` → `JOB_MODE=PARSE` → JSON output
- `input/fill/*.xlsx` → `JOB_MODE=FILL` → Filled Excel output

---

### 2. PriceCodeStack (Lexical Price Code Allocation)

**Purpose**: Index price code catalogs into SQLite and allocate codes using TF-IDF lexical search + LLM.

| Resource | Configuration |
|----------|--------------|
| VPC | Standalone VPC |
| S3 Bucket | `PriceCodeData` — CORS enabled, auto-delete |
| ECS Cluster | `PriceCodeCluster` |
| Fargate Task | **2 vCPU, 16 GB RAM** (large Excel files) |
| Lambda Trigger | `pricecode_trigger.py` |
| SSM Parameters | `/pricecode/*` |

**S3 Path Routing**:
- `input/pricecode/index/*.xlsx` → `JOB_MODE=INDEX` → Build SQLite TF-IDF index
- `input/pricecode/allocate/*.xlsx` → `JOB_MODE=ALLOCATE` → Color-coded Excel output

---

### 3. PriceCodeVectorStack (Embedding-Based Price Code Allocation)

**Purpose**: Index price code catalogs into S3 Vectors and allocate codes using embedding similarity + LLM.

| Resource | Configuration |
|----------|--------------|
| VPC | Standalone VPC |
| S3 Bucket | Shared or standalone |
| ECS Cluster | `PriceCodeVectorCluster` |
| Fargate Task | **2 vCPU, 8 GB RAM** |
| Lambda Trigger | `pricecode_vector_trigger.py` |
| S3 Vectors Index | `almabani-pricecode-vector` |

**S3 Path Routing**:
- `input/pricecode-vector/index/*.xlsx` → `JOB_MODE=INDEX` → Embed to S3 Vectors
- `input/pricecode-vector/allocate/*.xlsx` → `JOB_MODE=ALLOCATE` → Allocated Excel output

---

### 4. ChatStack (Natural Language API)

**Purpose**: Chat interface for querying unit rates and price codes in natural language.

| Resource | Configuration |
|----------|--------------|
| Lambda | Python 3.11, 1024 MB, **120s timeout** |
| Lambda Layers | ChatDepsLayer (openai, boto3), ChatAioDepsLayer (aioboto3, aiohttp) |
| API Gateway | REST API, POST `/chat`, CORS enabled |
| Function URL | No timeout limit — recommended for long LLM calls |

**Chat flow**:
1. Validate input is construction-related (LLM classification)
2. Create embedding with OpenAI
3. Search S3 Vectors index (unit rate or price code based on `type`)
4. LLM matching with domain-specific prompts
5. Return structured results with confidence scores

---

### 5. DeletionStack (Data Management API)

**Purpose**: Async deletion of datasheets and price code sets.

| Resource | Configuration |
|----------|--------------|
| Dispatcher Lambdas (3) | Python 3.11, 10s timeout — return 202 immediately |
| Worker Lambdas (3) | Python 3.11, 30-120s timeout — do actual deletion |
| Status Lambda | Python 3.11, 10s timeout — poll & auto-cleanup |
| API Gateway | REST API, DELETE + GET endpoints |
| Lambda Layer | DeletionDependenciesLayer (aioboto3, aiohttp, boto3) |

**API Endpoints**:
- `DELETE /files/sheets/{sheet_name}` — Delete from S3 Vectors + S3 registry
- `DELETE /pricecode/sets/{set_name}` — Delete from price code index
- `DELETE /pricecode-vector/sets/{set_name}` — Delete from S3 Vectors index
- `GET /deletion-status/{deletion_id}` — Poll status (auto-cleanup on read)

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
| `/almabani/*` | AlmabaniStack | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL`, `S3_VECTORS_BUCKET`, `S3_VECTORS_INDEX` |
| `/pricecode/*` | PriceCodeStack | `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` |

ChatStack and DeletionStack receive API keys as Lambda environment variables (set at deploy time).

**Updating secrets** does not require redeployment — the next Fargate task will fetch the latest values.

---

## Vector Storage

All vector data is stored in **AWS S3 Vectors** (managed vector search on S3):

| Index | Used For | Embedding Model |
|-------|----------|----------------|
| `almabani` | Unit rate items from BOQ datasheets | text-embedding-3-small (1536 dims) |
| `almabani-pricecode-vector` | Price code catalog items (chat + vector pipeline) | text-embedding-3-small (1536 dims) |

---

## Cost Model

| Component | Idle Cost | Per-Job Cost |
|-----------|----------|-------------|
| Fargate (1 vCPU, 2 GB) | $0.00 | ~$0.004 (5 min job) |
| Fargate (2 vCPU, 16 GB) | $0.00 | ~$0.030 (5 min job) |
| Fargate (2 vCPU, 8 GB) | $0.00 | ~$0.016 (5 min job) |
| Lambda | $0.00 | ~$0.0001 per invocation |
| NAT Gateway | $0.00 | N/A (public subnets only) |
| S3 + S3 Vectors | ~$0.02/GB/month | Minimal |
