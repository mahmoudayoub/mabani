# Almabani BOQ Management System — Architecture

## Overview

Almabani is an AI-powered **Bill of Quantities (BOQ) Management System** built on a
**serverless, event-driven "Process & Die" architecture** on AWS. There are no persistent
servers — compute spins up on demand, processes the job, uploads results, and terminates.

The system is deployed as **5 independent AWS CDK stacks**, each self-contained with its
own compute, triggers, permissions, and API endpoints.

---

## AlmabaniStack — Unit Rate Processing

Parses Excel BOQ datasheets into structured JSON **and** fills missing unit rates
using AI-powered 3-stage matching (exact → close → approximation).

### Resources

| Resource | Type | Configuration |
|----------|------|---------------|
| VPC | `ec2.Vpc` | 2 AZs, public subnets only, 0 NAT Gateways |
| S3 Bucket | `s3.Bucket` | CORS enabled, auto-delete on stack destroy |
| ECS Cluster | `ecs.Cluster` | Fargate capacity provider |
| Fargate Task | `ecs.FargateTaskDefinition` | **1 vCPU, 2 GB RAM** |
| Docker Image | `Dockerfile` → `worker.py` | Python 3.11-slim, non-root |
| Lambda Trigger | `trigger.py` | Python 3.9, 30s timeout |
| SSM Params | `/almabani/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |

### S3 Path Routing

| Upload Path | JOB_MODE | Output |
|-------------|----------|--------|
| `input/parse/<file>.xlsx` | `PARSE` | `output/indexes/<file>.json` |
| `input/fill/<file>.xlsx` | `FILL` | `output/fills/<file>_filled.xlsx` |
| `estimates/<file>_estimate.json` | `FILL` | Progress/time estimate, written at job start, updated on completion |

### Flow Diagram

```mermaid
graph TB
    subgraph "Client"
        USER[Frontend / API Client]
    end

    subgraph "AlmabaniStack — eu-west-1"
        S3A[S3 Bucket<br/>AlmabaniData]
        LTA[Lambda Trigger<br/>trigger.py · 30s]
        ECSA[ECS Fargate<br/>1 vCPU · 2 GB<br/>worker.py]
    end

    subgraph "Dependencies"
        SSM[SSM Parameter Store<br/>/almabani/*]
        OAI[OpenAI API<br/>text-embedding-3-small<br/>+ gpt-5-mini-2025-08-07]
        S3VEC[S3 Vectors<br/>almabani-vectors<br/>index: almabani]
    end

    USER -->|Upload .xlsx| S3A
    S3A -->|OBJECT_CREATED<br/>input/parse/ · input/fill/| LTA
    LTA -->|ecs:RunTask<br/>PARSE or FILL| ECSA
    ECSA -->|Fetch secrets| SSM
    ECSA -->|Download input file| S3A

    ECSA -->|PARSE: Parse Excel → JSON<br/>then embed items| OAI
    ECSA -->|PARSE: Upsert vectors| S3VEC
    ECSA -->|PARSE: Upload output/indexes/| S3A

    ECSA -->|FILL: Embed unfilled items| OAI
    ECSA -->|FILL: Search almabani index| S3VEC
    ECSA -->|FILL: 3-stage LLM matching| OAI
    ECSA -->|FILL: Write estimate to S3| S3A
    ECSA -->|FILL: Upload output/fills/| S3A
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Fargate Task Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | AlmabaniData bucket |
| Fargate Task Role | `s3vectors:*` | `*` (S3 Vectors API) |
| Lambda Trigger | `ecs:RunTask` | Task Definition ARN |
| Lambda Trigger | `iam:PassRole` | Execution Role ARN, Task Role ARN |
| External Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | Bucket (dynamic: `{sls_service}-{sls_stage}-{region}-lambdaRole`) |

---

## PriceCodeStack — Lexical Price Code Allocation

Indexes price code reference catalogs into a SQLite TF-IDF lexical index, then
allocates price codes to BOQ items using lexical search + LLM reranking.

### Resources

| Resource | Type | Configuration |
|----------|------|---------------|
| VPC | `ec2.Vpc` | 2 AZs, public subnets only, 0 NAT Gateways |
| S3 Bucket | `s3.Bucket` | CORS enabled, auto-delete |
| ECS Cluster | `ecs.Cluster` | Fargate capacity provider |
| Fargate Task | `ecs.FargateTaskDefinition` | **4 vCPU, 16 GB RAM** |
| Docker Image | `Dockerfile.pricecode` → `pricecode_worker.py` | Python 3.11-slim |
| Lambda Trigger | `pricecode_trigger.py` | Python 3.9, 30s timeout |
| SSM Params | `/pricecode/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |

### S3 Path Routing

| Upload Path | JOB_MODE | Output |
|-------------|----------|--------|
| `input/pricecode/index/<file>.xlsx` | `INDEX` | SQLite DB stored in S3 |
| `input/pricecode/allocate/<file>.xlsx` | `ALLOCATE` | `output/pricecode/<file>_allocated.xlsx` |
| `estimates/pc_<file>_estimate.json` | `ALLOCATE` | Progress/time estimate, written at job start, updated on completion |
### Lexical Search Pipeline

```mermaid
graph LR
    subgraph "Allocation"
        A[BOQ Item] --> B[SQLite TF-IDF Search<br/>]
        B --> C[Local Rerank<br/>]
        C --> D[LLM Judge<br/>gpt-5-mini: judges each candidate]
        D --> E[Output<br/>Green=matched · Red=unmatched]
    end
```

**Key parameters:**
- `INITIAL_POOL_LIMIT` — Candidates fetched from SQLite (hardcoded: 5000)
- `PRICECODE_MAX_CANDIDATES` — Candidates passed to LLM (default: 1)
- `PRICECODE_MAX_CONCURRENT` — Max concurrent allocate jobs (default: 100)

### Flow Diagram

```mermaid
graph TB
    subgraph "Client"
        USER[Frontend / API Client]
    end

    subgraph "PriceCodeStack — eu-west-1"
        S3P[S3 Bucket<br/>PriceCodeData]
        LTP[Lambda Trigger<br/>pricecode_trigger.py · 30s]
        ECSP[ECS Fargate<br/>4 vCPU · 16 GB<br/>pricecode_worker.py]
        DB[SQLite TF-IDF Index<br/>stored in S3]
    end

    subgraph "Dependencies"
        SSM[SSM Parameter Store<br/>/pricecode/*]
        OAI[OpenAI API<br/>gpt-5-mini-2025-08-07<br/>LLM reranking — no embeddings]
    end

    USER -->|Upload .xlsx| S3P
    S3P -->|OBJECT_CREATED<br/>input/pricecode/| LTP
    LTP -->|ecs:RunTask<br/>INDEX or ALLOCATE| ECSP
    ECSP -->|Fetch secrets| SSM
    ECSP -->|Download input file| S3P

    ECSP -->|INDEX: Parse Excel → Extract items<br/>Build TF-IDF index| DB
    ECSP -->|INDEX: Upload SQLite DB| S3P

    ECSP -->|ALLOCATE: Download SQLite index| DB
    ECSP -->|ALLOCATE: Lexical search| DB
    ECSP -->|ALLOCATE: LLM reranking| OAI
    ECSP -->|ALLOCATE: Write estimate to S3| S3P
    ECSP -->|ALLOCATE: Upload allocated Excel| S3P
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Fargate Task Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | PriceCodeData bucket |
| Fargate Task Role | `s3vectors:*` | `*` (S3 Vectors API) |
| Lambda Trigger | `ecs:RunTask` | Task Definition ARN |
| Lambda Trigger | `iam:PassRole` | Execution Role ARN, Task Role ARN |
| External Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | Bucket (dynamic: `{sls_service}-{sls_stage}-{region}-lambdaRole`) |

---

## PriceCodeVectorStack — Embedding Price Code Allocation

Indexes price code catalogs into S3 Vectors using OpenAI embeddings, then allocates
codes using embedding similarity + LLM validation.

### Resources

| Resource | Type | Configuration |
|----------|------|---------------|
| VPC | `ec2.Vpc` | 2 AZs, public subnets only, 0 NAT Gateways |
| S3 Bucket | `s3.Bucket` | CORS enabled, auto-delete |
| ECS Cluster | `ecs.Cluster` | Fargate capacity provider |
| Fargate Task | `ecs.FargateTaskDefinition` | **2 vCPU, 8 GB RAM** |
| Docker Image | `Dockerfile.pricecode_vector` → `pricecode_vector_worker.py` | Python 3.11-slim |
| Lambda Trigger | `pricecode_vector_trigger.py` | Python 3.9, 30s timeout |
| SSM Params | `/pricecode-vector/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |
| S3 Vectors Index | `almabani-pricecode-vector` | 1536 dimensions |

### S3 Path Routing

| Upload Path | JOB_MODE | Output |
|-------------|----------|--------|
| `input/pricecode-vector/index/<file>.xlsx` | `INDEX` | Embeddings → S3 Vectors |
| `input/pricecode-vector/allocate/<file>.xlsx` | `ALLOCATE` | `output/pricecode-vector/<file>_allocated.xlsx` |
| `estimates/pcv_<file>_estimate.json` | `ALLOCATE` | Progress/time estimate, written at job start, updated on completion |
### Flow Diagram

```mermaid
graph TB
    subgraph "Client"
        USER[Frontend / API Client]
    end

    subgraph "PriceCodeVectorStack — eu-west-1"
        S3V[S3 Bucket<br/>PriceCodeVectorData]
        LTV[Lambda Trigger<br/>pricecode_vector_trigger.py · 30s]
        ECSV[ECS Fargate<br/>2 vCPU · 8 GB<br/>pricecode_vector_worker.py]
    end

    subgraph "Dependencies"
        SSM[SSM Parameter Store<br/>/pricecode-vector/*]
        OAI[OpenAI API<br/>text-embedding-3-small<br/>+ gpt-5-mini-2025-08-07]
        S3VEC[S3 Vectors<br/>almabani-vectors<br/>index: almabani-pricecode-vector]
    end

    USER -->|Upload .xlsx| S3V
    S3V -->|OBJECT_CREATED<br/>input/pricecode-vector/| LTV
    LTV -->|ecs:RunTask<br/>INDEX or ALLOCATE| ECSV
    ECSV -->|Fetch secrets| SSM
    ECSV -->|Download input file| S3V

    ECSV -->|INDEX: Parse Excel, extract items<br/>create embeddings| OAI
    ECSV -->|INDEX: Upsert vectors| S3VEC

    ECSV -->|ALLOCATE: Embed BOQ items| OAI
    ECSV -->|ALLOCATE: Similarity search| S3VEC
    ECSV -->|ALLOCATE: LLM judges candidates| OAI
    ECSV -->|ALLOCATE: Write estimate to S3| S3V
    ECSV -->|ALLOCATE: Upload allocated Excel| S3V
```

**Key parameters:**
- `PRICECODE_VECTOR_TOP_K` — Candidates per similarity query (default: 5)
- `PRICECODE_VECTOR_THRESHOLD` — Minimum cosine similarity (default: 0.40)
- `BATCH_SIZE` — Items per embedding batch (default: 500)
- `EMBEDDINGS_RPM` — Rate limit for OpenAI embeddings API (default: 3000)

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Fargate Task Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | PriceCodeVectorData bucket |
| Fargate Task Role | `s3vectors:*` | `*` (S3 Vectors API) |
| Lambda Trigger | `ecs:RunTask` | Task Definition ARN |
| Lambda Trigger | `iam:PassRole` | Execution Role ARN, Task Role ARN |
| External Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | Bucket (dynamic: `{sls_service}-{sls_stage}-{region}-lambdaRole`) |

---

## ChatStack — Natural Language Chat API

Provides a natural language interface for querying unit rates and price codes
via OpenAI embeddings + S3 Vectors + LLM matching.

### Resources

| Resource | Type | Configuration |
|----------|------|---------------|
| Lambda | `lambda.Function` | Python 3.11, **1 GB RAM, 120s timeout** |
| Lambda Layers | `ChatDepsLayer` | openai, httpx, multidict, frozenlist, yarl |
| Lambda Layers | `ChatAioDepsLayer` | aioboto3, aiobotocore, aiohttp |
| API Gateway | `apigw.RestApi` | POST `/chat`, CORS, 29s timeout |
| Function URL | `FunctionUrl` | No timeout limit (recommended) |

### Endpoints

| Method | Endpoint | Timeout | Notes |
|--------|----------|---------|-------|
| POST | `<ChatFunctionUrl>` | None (Lambda limit: 120s) | **Recommended** |
| POST | `<ChatApiUrl>/chat` | 29s (API Gateway limit) | Backup |

### Chat Flow

```mermaid
graph TB
    subgraph "Client"
        FE[Frontend / API Client]
    end

    subgraph "ChatStack — eu-west-1"
        APIGW[API Gateway<br/>POST /chat · 29s limit]
        FNURL[Lambda Function URL<br/>No timeout]
        CHAT[Lambda<br/>chat_handler.py<br/>Python 3.11 · 1 GB · 120s]
    end

    subgraph "Dependencies"
        OAI[OpenAI API<br/>text-embedding-3-small<br/>+ gpt-5-mini-2025-08-07]
        S3VEC[S3 Vectors<br/>almabani-vectors]
    end

    FE -->|POST /chat| APIGW
    FE -->|POST /chat| FNURL
    APIGW --> CHAT
    FNURL --> CHAT

    CHAT -->|1. Validate: construction-related?| OAI
    CHAT -->|2. Create embedding| OAI
    CHAT -->|3. Search by type<br/>unitrate → almabani · pricecode → almabani-pricecode-vector| S3VEC
    CHAT -->|4. unitrate: 3-stage match · pricecode: strict LLM judge| OAI
    CHAT -->|HTTP response| APIGW
    CHAT -->|HTTP response| FNURL
    APIGW -->|result or rejection| FE
    FNURL -->|result or rejection| FE
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Chat Lambda | `s3vectors:*` | `*` (S3 Vectors API) |

> **Note:** OpenAI API key is passed as a Lambda environment variable at deploy time.

---

## DeletionStack — Data Management API

Async deletion of datasheets and price code sets. Uses a dispatcher/worker
pattern: dispatcher returns 202 immediately, worker runs in the background.

### Resources

| Resource | Type | Configuration |
|----------|------|---------------|
| Dispatcher Lambdas (×3) | `lambda.Function` | Python 3.11, 10s timeout |
| Worker Lambdas (×3) | `lambda.Function` | Python 3.11, 120s–15 min timeout |
| Status Lambda (×1) | `lambda.Function` | Python 3.11, 10s timeout |
| Lambda Layer | `DeletionDependenciesLayer` | aioboto3, aiobotocore, aiohttp |
| API Gateway | `apigw.RestApi` | DELETE + GET, full CORS |

### API Endpoints

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| DELETE | `/files/sheets/{sheet_name}` | Dispatcher → Worker | Delete unit rate datasheet + vectors |
| DELETE | `/pricecode/sets/{set_name}` | Dispatcher → Worker | Delete lexical price code set |
| DELETE | `/pricecode-vector/sets/{set_name}` | Dispatcher → Worker | Delete vector price code set |
| GET | `/deletion-status/{deletion_id}` | Status Lambda | Poll status (auto-cleanup on read) |

### Async Deletion Flow

```mermaid
graph TB
    subgraph "Client"
        FE[Frontend / API Client]
    end

    subgraph "DeletionStack — eu-west-1"
        APIGW[API Gateway<br/>DELETE + GET endpoints]
        DISP[Dispatcher Lambdas ×3<br/>10s timeout]
        WORK[Worker Lambdas ×3<br/>up to 15 min]
        STAT[Status Lambda<br/>10s timeout]
    end

    subgraph "Data Stores"
        S3A[S3 Bucket<br/>AlmabaniData]
        S3P[S3 Bucket<br/>PriceCodeData]
        S3PV[S3 Bucket<br/>PriceCodeVectorData]
        S3VEC[S3 Vectors<br/>almabani-vectors]
    end

    FE -->|DELETE requests<br/>GET deletion-status| APIGW
    APIGW --> DISP
    APIGW --> STAT

    DISP -->|Write status: pending| S3A
    DISP -->|lambda:InvokeFunction async| WORK
    DISP -->|HTTP 202 Accepted| APIGW

    WORK -->|Delete vectors| S3VEC
    WORK -->|Delete objects + update registry| S3A
    WORK -->|Delete objects + update registry| S3P
    WORK -->|Delete objects + update registry| S3PV
    WORK -->|Write status: complete| S3A

    STAT -->|Read status file| S3A
    STAT -->|HTTP 200 status| APIGW
    APIGW -->|response| FE
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Worker (Datasheet) | `s3:*` on bucket | AlmabaniData bucket |
| Worker (Datasheet) | `s3vectors:*` | `*` |
| Worker (PriceCode) | `s3:*` on bucket | PriceCodeData bucket |
| Worker (PriceCode) | `s3vectors:*` | `*` |
| Worker (PCV) | `s3:*` on bucket | PriceCodeVectorData bucket |
| Worker (PCV) | `s3vectors:*` | `*` |
| Dispatcher | `lambda:InvokeFunction` | Corresponding Worker ARN |
| Dispatcher | `s3:PutObject` | Respective bucket (status markers) |
| Status Lambda | `s3:GetObject` | All 3 buckets |

---

## Shared Infrastructure

### S3 Vectors (Managed Vector Search)

All embeddings are stored in **AWS S3 Vectors** — a managed vector search service on S3.

| Index Name | Used By | Content | Model | Dimensions |
|------------|---------|---------|-------|------------|
| `almabani` | AlmabaniStack, ChatStack | Unit rate items from BOQ datasheets | `text-embedding-3-small` | 1536 |
| `almabani-pricecode-vector` | PriceCodeVectorStack, ChatStack | Price code catalog items | `text-embedding-3-small` | 1536 |

**Bucket:** `almabani-vectors`

### SSM Parameter Store (Secrets)

| Path Prefix | Stack | Parameters |
|-------------|-------|------------|
| `/almabani/*` | AlmabaniStack | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |
| `/pricecode/*` | PriceCodeStack | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |
| `/pricecode-vector/*` | PriceCodeVectorStack | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_CHAT_MODEL` |

Fargate containers receive secrets via `ecs.Secret.from_ssm_parameter()` — injected at
container start time. SSM parameters are **created and overwritten by CDK** from `boq-backend/env`
on every `cdk deploy`. To permanently update a secret, edit `boq-backend/env` and redeploy
the affected stack.

ChatStack receives the OpenAI API key as a Lambda environment variable
(set at `cdk deploy` time from `boq-backend/env`). DeletionStack does not use OpenAI.

### Docker Images

| Dockerfile | Entrypoint | Stack |
|------------|-----------|-------|
| `boq-backend/Dockerfile` | `python3 worker.py` | AlmabaniStack |
| `boq-backend/Dockerfile.pricecode` | `python3 pricecode_worker.py` | PriceCodeStack |
| `boq-backend/Dockerfile.pricecode_vector` | `python3 pricecode_vector_worker.py` | PriceCodeVectorStack |

All images: Python 3.11-slim, non-root `appuser`, package installed in editable mode.

---

## Cross-Stack Dependency Structure

**DeletionStack** depends on the three pipeline stacks (AlmabaniStack, PriceCodeStack, PriceCodeVectorStack). During CDK deployment, the CDK app passes each pipeline stack's S3 bucket reference to the DeletionStack. This allows the deletion workers to assume cross-account-like permissions for cleanup:
- Datasheet worker deletes from **AlmabaniStack bucket** + **S3 Vectors**  
- PriceCode worker deletes from **PriceCodeStack bucket**  
- PriceCodeVector worker deletes from **PriceCodeVectorStack bucket** + **S3 Vectors**  

**ChatStack** is completely standalone — it doesn't need bucket references. Instead, it uses broad `s3vectors:*` IAM permissions to query both the `almabani` and `almabani-pricecode-vector` indices stored in the shared `almabani-vectors` S3 Vectors bucket.

**Deployment order:**
1. AlmabaniStack, PriceCodeStack, PriceCodeVectorStack (any order)
2. ChatStack (can be parallel)
3. DeletionStack last (requires bucket refs from steps 1–2)

---

## Cost Model (Zero Idle Cost)

| Component | Idle Cost | Per-Job Cost (~5 min) |
|-----------|----------|-----------------------|
| Fargate — AlmabaniStack (1 vCPU, 2 GB) | $0.00 | ~$0.004 |
| Fargate — PriceCodeStack (4 vCPU, 16 GB) | $0.00 | ~$0.030 |
| Fargate — PriceCodeVectorStack (2 vCPU, 8 GB) | $0.00 | ~$0.016 |
| Lambda (Chat, Deletion) | $0.00 | ~$0.0001 per invocation |
| NAT Gateway | $0.00 | N/A (public subnets only) |
| S3 + S3 Vectors | ~$0.02/GB/month | Minimal |

> All VPCs use **public subnets only with 0 NAT Gateways**. Fargate tasks get
> `assignPublicIp: ENABLED` for internet access (OpenAI, S3, SSM).
