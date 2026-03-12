# Almabani BOQ Management System — Architecture

## Overview

Almabani is an AI-powered **Bill of Quantities (BOQ) Management System** built on a
**serverless, event-driven "Process & Die" architecture** on AWS. There are no persistent
servers — compute spins up on demand, processes the job, uploads results, and terminates.

The system is deployed as **5 independent AWS CDK stacks**, each self-contained with its
own compute, triggers, permissions, and API endpoints.

---

## System Overview Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        FE[Frontend / API Client]
    end

    subgraph "AWS Cloud — eu-west-1"
        subgraph "AlmabaniStack"
            S3A[S3 Bucket<br/>AlmabaniData]
            LTA[Lambda Trigger<br/>trigger.py]
            ECSA[ECS Fargate<br/>1 vCPU · 2 GB<br/>worker.py]
        end

        subgraph "PriceCodeStack"
            S3P[S3 Bucket<br/>PriceCodeData]
            LTP[Lambda Trigger<br/>pricecode_trigger.py]
            ECSP[ECS Fargate<br/>4 vCPU · 16 GB<br/>pricecode_worker.py]
        end

        subgraph "PriceCodeVectorStack"
            S3V[S3 Bucket<br/>PriceCodeVectorData]
            LTV[Lambda Trigger<br/>pricecode_vector_trigger.py]
            ECSV[ECS Fargate<br/>2 vCPU · 8 GB<br/>pricecode_vector_worker.py]
        end

        subgraph "ChatStack"
            APIGW_C[API Gateway<br/>POST /chat]
            FNURL[Lambda Function URL<br/>No timeout]
            CHAT[Lambda<br/>chat_handler.py<br/>Python 3.11 · 1 GB · 120s]
        end

        subgraph "DeletionStack"
            APIGW_D[API Gateway<br/>DELETE + GET endpoints]
            DISP[Dispatcher Lambdas ×3<br/>10s timeout]
            WORK[Worker Lambdas ×3<br/>up to 15 min]
            STAT[Status Lambda<br/>10s timeout]
        end

        subgraph "Shared Services"
            SSM[SSM Parameter Store<br/>Secrets &amp; Config]
            S3VEC[S3 Vectors<br/>almabani-vectors]
        end
    end

    FE -->|Upload .xlsx| S3A
    FE -->|Upload .xlsx| S3P
    FE -->|Upload .xlsx| S3V
    FE -->|POST /chat| APIGW_C
    FE -->|POST /chat| FNURL
    FE -->|DELETE / GET| APIGW_D

    S3A -->|OBJECT_CREATED<br/>input/parse/ · input/fill/| LTA
    S3P -->|OBJECT_CREATED<br/>input/pricecode/| LTP
    S3V -->|OBJECT_CREATED<br/>input/pricecode-vector/| LTV

    LTA -->|ecs:RunTask| ECSA
    LTP -->|ecs:RunTask| ECSP
    LTV -->|ecs:RunTask| ECSV

    ECSA -->|Read/Write| S3A
    ECSA -->|Upsert/Search| S3VEC
    ECSA -->|Fetch secrets| SSM

    ECSP -->|Read/Write| S3P
    ECSP -->|Fetch secrets| SSM

    ECSV -->|Read/Write| S3V
    ECSV -->|Upsert/Search| S3VEC
    ECSV -->|Fetch secrets| SSM

    APIGW_C --> CHAT
    FNURL --> CHAT
    CHAT -->|Search| S3VEC

    APIGW_D --> DISP
    APIGW_D --> STAT
    DISP -->|Async Invoke| WORK
    WORK -->|Delete vectors| S3VEC
    WORK -->|Delete objects| S3A
    WORK -->|Delete objects| S3P
    WORK -->|Delete objects| S3V
```

---

## Service 1 — AlmabaniStack (Unit Rate Processing)

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

### Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant S3 as S3 (AlmabaniData)
    participant Lambda as Lambda Trigger
    participant Fargate as Fargate (worker.py)
    participant SSM as SSM Params
    participant OpenAI as OpenAI API
    participant S3V as S3 Vectors

    User->>S3: Upload .xlsx to input/parse/ or input/fill/
    S3->>Lambda: S3 OBJECT_CREATED event
    Lambda->>Lambda: Determine JOB_MODE from path
    Lambda->>Fargate: ecs:RunTask (PARSE or FILL)

    Fargate->>SSM: Fetch OPENAI_API_KEY, models
    Fargate->>S3: Download input file

    alt PARSE mode
        Fargate->>Fargate: Parse Excel → JSON
        Fargate->>OpenAI: Create embeddings (text-embedding-3-small)
        Fargate->>S3V: Upsert vectors to "almabani" index
        Fargate->>S3: Upload output/indexes/<file>.json
    else FILL mode
        Fargate->>OpenAI: Embed unfilled items
        Fargate->>S3V: Search "almabani" index for matches
        Fargate->>OpenAI: 3-stage LLM matching
        Fargate->>S3: Upload output/fills/<file>_filled.xlsx
    end

    Fargate->>Fargate: Exit (container dies)
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Fargate Task Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | AlmabaniData bucket |
| Fargate Task Role | `s3vectors:*` | `*` (S3 Vectors API) |
| Lambda Trigger | `ecs:RunTask` | Task Definition ARN |
| Lambda Trigger | `iam:PassRole` | Execution Role ARN, Task Role ARN |

---

## Service 2 — PriceCodeStack (Lexical Price Code Allocation)

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

### Lexical Search Pipeline

```mermaid
flowchart LR
    A[BOQ Item] --> B[TF-IDF Lexical Search<br/>Initial Pool = TOP_K candidates]
    B --> C[LLM Reranking<br/>Domain-Aware Judge]
    C --> D[Top MAX_CANDIDATES<br/>Final Match]
    D --> E[Color-Coded Excel Output<br/>Green=matched · Red=unmatched]
```

**Key parameters:**
- `PRICECODE_MAX_CONCURRENT` — Max concurrent DB queries (default: 200)
- `PRICECODE_MAX_CANDIDATES` — Final candidates after reranking (default: 1)
- `PRICECODE_BATCH_SIZE` — Items per processing batch (default: 100)

### Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant S3 as S3 (PriceCodeData)
    participant Lambda as Lambda Trigger
    participant Fargate as Fargate (pricecode_worker.py)
    participant SSM as SSM Params
    participant SQLite as SQLite TF-IDF Index
    participant OpenAI as OpenAI API

    User->>S3: Upload .xlsx to input/pricecode/index/ or allocate/
    S3->>Lambda: S3 OBJECT_CREATED event
    Lambda->>Fargate: ecs:RunTask (INDEX or ALLOCATE)

    Fargate->>SSM: Fetch secrets
    Fargate->>S3: Download input file

    alt INDEX mode
        Fargate->>Fargate: Parse Excel → Extract price code items
        Fargate->>SQLite: Build TF-IDF index with domain tokens
        Fargate->>S3: Upload SQLite DB to S3
    else ALLOCATE mode
        Fargate->>S3: Download SQLite index
        Fargate->>SQLite: Lexical search (initial pool per item)
        Fargate->>OpenAI: LLM reranking (judge best match)
        Fargate->>S3: Upload color-coded allocated Excel
    end

    Fargate->>Fargate: Exit
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Fargate Task Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | PriceCodeData bucket |
| Fargate Task Role | `s3vectors:*` | `*` (S3 Vectors API) |
| Lambda Trigger | `ecs:RunTask` | Task Definition ARN |
| Lambda Trigger | `iam:PassRole` | Execution Role ARN, Task Role ARN |

---

## Service 3 — PriceCodeVectorStack (Embedding Price Code Allocation)

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
| SSM Params | `/pricecode-vector/*` | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL` |
| S3 Vectors Index | `almabani-pricecode-vector` | 1536 dimensions |

### S3 Path Routing

| Upload Path | JOB_MODE | Output |
|-------------|----------|--------|
| `input/pricecode-vector/index/<file>.xlsx` | `INDEX` | Embeddings → S3 Vectors |
| `input/pricecode-vector/allocate/<file>.xlsx` | `ALLOCATE` | `output/pricecode-vector/<file>_allocated.xlsx` |

### Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant S3 as S3 (PriceCodeVectorData)
    participant Lambda as Lambda Trigger
    participant Fargate as Fargate (pricecode_vector_worker.py)
    participant SSM as SSM Params
    participant OpenAI as OpenAI API
    participant S3V as S3 Vectors

    User->>S3: Upload .xlsx to input/pricecode-vector/index/ or allocate/
    S3->>Lambda: S3 OBJECT_CREATED event
    Lambda->>Fargate: ecs:RunTask (INDEX or ALLOCATE)

    Fargate->>SSM: Fetch secrets
    Fargate->>S3: Download input file

    alt INDEX mode
        Fargate->>Fargate: Parse Excel → Extract price code items
        Fargate->>OpenAI: Create embeddings (batched, rate-limited)
        Fargate->>S3V: Upsert vectors to "almabani-pricecode-vector"
    else ALLOCATE mode
        Fargate->>OpenAI: Embed BOQ items
        Fargate->>S3V: Similarity search (top_k=5, threshold=0.40)
        Fargate->>OpenAI: LLM one-shot matching
        Fargate->>S3: Upload allocated Excel
    end

    Fargate->>Fargate: Exit
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
| External Role | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` | Bucket (for `taskflow-backend-dev` Lambda) |

---

## Service 4 — ChatStack (Natural Language Chat API)

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
sequenceDiagram
    participant Client
    participant Lambda as Chat Lambda
    participant OpenAI as OpenAI API
    participant S3V as S3 Vectors

    Client->>Lambda: POST {"message": "...", "type": "unitrate|pricecode"}
    Lambda->>OpenAI: Classify query (construction-related?)

    alt Not construction-related
        Lambda->>Client: 200 {"status": "rejected", "message": "..."}
    else Construction-related
        Lambda->>OpenAI: Create embedding (text-embedding-3-small)

        alt type = "unitrate"
            Lambda->>S3V: Search "almabani" index (top_k=10)
        else type = "pricecode"
            Lambda->>S3V: Search "almabani-pricecode-vector" index (top_k=10)
        end

        Lambda->>OpenAI: 3-stage LLM matching (exact → close → approx)
        Lambda->>Client: 200 {"status": "success", "matches": [...]}
    end
```

### IAM Permissions

| Principal | Action | Resource |
|-----------|--------|----------|
| Chat Lambda | `s3vectors:*` | `*` (S3 Vectors API) |

> **Note:** OpenAI API key is passed as a Lambda environment variable at deploy time.

---

## Service 5 — DeletionStack (Data Management API)

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
sequenceDiagram
    participant Client
    participant APIGW as API Gateway
    participant Disp as Dispatcher Lambda (10s)
    participant S3 as S3 Bucket
    participant Worker as Worker Lambda (120s)
    participant S3V as S3 Vectors

    Client->>APIGW: DELETE /files/sheets/my_sheet
    APIGW->>Disp: Route request
    Disp->>S3: Write status "pending"
    Disp->>Worker: lambda:InvokeFunction (async)
    Disp->>Client: 202 {"deletion_id": "ds_...", "message": "Delete started"}

    Worker->>S3V: Delete vectors from "almabani" index
    Worker->>S3: Delete objects under sheet prefix
    Worker->>S3: Update available_sheets.json registry
    Worker->>S3: Write status "complete"

    Client->>APIGW: GET /deletion-status/ds_...
    APIGW->>S3: Read status file
    S3->>Client: {"status": "complete"}
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
| `/pricecode-vector/*` | PriceCodeVectorStack | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL` |

Fargate containers receive secrets via `ecs.Secret.from_ssm_parameter()` — injected at
container start time. **Updating an SSM parameter does NOT require redeployment.**

ChatStack and DeletionStack receive the OpenAI API key as a Lambda environment variable
(set at `cdk deploy` time from the local `.env` file).

### Docker Images

| Dockerfile | Entrypoint | Stack |
|------------|-----------|-------|
| `backend/Dockerfile` | `python3 worker.py` | AlmabaniStack |
| `backend/Dockerfile.pricecode` | `python3 pricecode_worker.py` | PriceCodeStack |
| `backend/Dockerfile.pricecode_vector` | `python3 pricecode_vector_worker.py` | PriceCodeVectorStack |

All images: Python 3.11-slim, non-root `appuser`, package installed in editable mode.

---

## Cross-Stack Dependency Map

```mermaid
graph LR
    subgraph "infra/app.py"
        APP((CDK App))
    end

    APP --> AS[AlmabaniStack]
    APP --> PS[PriceCodeStack]
    APP --> PVS[PriceCodeVectorStack]
    APP --> CS[ChatStack]
    APP --> DS[DeletionStack]

    AS -->|bucket| DS
    PS -->|bucket| DS
    PVS -->|bucket| DS

    AS -.->|S3 Vectors: almabani| CS
    PVS -.->|S3 Vectors: almabani-pricecode-vector| CS
```

**DeletionStack** receives bucket references from the 3 pipeline stacks so its worker
Lambdas can delete objects from those buckets. **ChatStack** is standalone — it accesses
S3 Vectors directly via the `s3vectors:*` IAM policy.

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
