# Almabani BOQ Management System

AI-powered construction Bill of Quantities (BOQ) processing platform. Parses Excel BOQ datasheets, indexes them into vector databases, and uses AI to match unit rates and allocate price codes — either through batch processing (cloud) or a natural language chat interface.

## Features

### Unit Rate Pipeline
- **Parse** — Extract structured items from Excel BOQ datasheets into JSON
- **Index** — Embed items with OpenAI and store in S3 Vectors
- **Fill** — AI-powered rate matching: finds similar items and fills missing rates using 3-stage matching (exact → close → approximation)

### Price Code Pipeline (Lexical)
- **Index** — Build SQLite TF-IDF index from reference Excel catalogs
- **Allocate** — Match BOQ items to price codes using domain-aware lexical search + LLM validation

### Price Code Pipeline (Vector)
- **Index** — Embed price code catalogs with OpenAI and store in S3 Vectors
- **Allocate** — Match BOQ items to price codes using embedding similarity + LLM validation

### Chat Interface
- Natural language queries against both unit rate and price code indexes
- Input validation (construction-domain only), vector search, and LLM-powered matching
- Deployed as Lambda with Function URL (no timeout) + API Gateway (29s limit, backward compat)

### Deletion API
- Delete individual datasheets or price code sets from S3 Vectors and S3 registry
- Async dispatcher/worker pattern with status polling
- REST API: `DELETE /files/sheets/{name}`, `DELETE /pricecode/sets/{name}`, `DELETE /pricecode-vector/sets/{name}`

---

## Architecture

**Event-driven "Process & Die"** — no persistent servers. Files uploaded to S3 trigger Lambda functions which launch Fargate containers. Containers process the file, upload results, and exit.

| Stack | Compute | Purpose | Trigger Paths |
|-------|---------|---------|---------------|
| **AlmabaniStack** | Fargate (1 vCPU, 2 GB) | Unit rate parse + fill | `input/parse/`, `input/fill/` |
| **PriceCodeStack** | Fargate (2 vCPU, 16 GB) | Price code lexical index + allocate | `input/pricecode/index/`, `input/pricecode/allocate/` |
| **PriceCodeVectorStack** | Fargate (2 vCPU, 8 GB) | Price code vector index + allocate | `input/pricecode-vector/index/`, `input/pricecode-vector/allocate/` |
| **ChatStack** | Lambda (1 GB, 120s) | Natural language chat API | POST `/chat` or Function URL |
| **DeletionStack** | Lambda (30s-120s) | Async deletion API | DELETE endpoints |

**AI Stack**: OpenAI (GPT-5-mini, text-embedding-3-small) + S3 Vectors (cosine similarity, 1536 dims)

**Secrets**: AWS SSM Parameter Store (`/almabani/*`, `/pricecode/*`)

---

## Directory Structure

```
boq-backend/
├── almabani/                  # Python package (pip install -e .)
│   ├── parsers/               # Excel → JSON parsing pipeline
│   ├── rate_matcher/          # Unit rate AI matching (3-stage)
│   ├── pricecode/             # Price code allocation (lexical TF-IDF)
│   ├── pricecode_vector/      # Price code allocation (embedding-based)
│   ├── vectorstore/           # S3 Vectors indexing
│   ├── core/                  # Shared utilities (embeddings, storage, models)
│   ├── config/                # Pydantic settings + logging
│   └── cli/                   # Typer CLI tool
├── worker.py                  # Fargate worker (unit rate: parse + fill)
├── pricecode_worker.py        # Fargate worker (pricecode lexical: index + allocate)
├── pricecode_vector_worker.py # Fargate worker (pricecode vector: index + allocate)
├── chat_handler.py            # Lambda handler (chat API)
├── delete_handler.py          # Lambda handler (deletion API)
├── Dockerfile                 # Unit rate worker image
├── Dockerfile.pricecode       # Pricecode lexical worker image
├── Dockerfile.pricecode_vector # Pricecode vector worker image
├── layers/                    # Lambda layer dependencies
├── requirements.txt           # Python dependencies
└── pyproject.toml             # Package configuration
infra/                         # AWS CDK (Python)
├── app.py                     # CDK app entry point (5 stacks)
├── almabani_stack.py          # Unit rate stack
├── pricecode_stack.py         # Pricecode lexical stack
├── pricecode_vector_stack.py  # Pricecode vector stack
├── chat_stack.py              # Chat API stack
├── deletion_stack.py          # Deletion API stack
└── lambdas/                   # Lambda trigger functions
docs/                          # Architecture & backend documentation
DEPLOYMENT.md                  # Cloud deployment guide
README-BOQ.md                  # This file
```

---

## Quick Start

### Cloud Deployment

```bash
# 1. Install CDK dependencies
pip install -r infra/requirements.txt

# 2. Bootstrap (first time only)
cdk bootstrap aws://<YOUR_ACCOUNT_ID>/eu-west-1

# 3. Deploy all stacks
cdk deploy --app "python3 infra/app.py" --all

# Or deploy individual stacks
cdk deploy --app "python3 infra/app.py" AlmabaniStack
cdk deploy --app "python3 infra/app.py" PriceCodeStack
cdk deploy --app "python3 infra/app.py" PriceCodeVectorStack
cdk deploy --app "python3 infra/app.py" ChatStack
cdk deploy --app "python3 infra/app.py" DeletionStack
```

### Running a Job (Cloud)

Upload a file to S3 and the pipeline runs automatically:

| Job | Upload to | Result at |
|-----|-----------|-----------|
| Parse Excel → JSON | `input/parse/myfile.xlsx` | `output/indexes/myfile.json` |
| Fill Rates | `input/fill/myfile.xlsx` | `output/fills/myfile_filled.xlsx` |
| Index Price Codes (Lexical) | `input/pricecode/index/catalog.xlsx` | SQLite index in S3 |
| Allocate Price Codes (Lexical) | `input/pricecode/allocate/boq.xlsx` | `output/pricecode/boq_allocated.xlsx` |
| Index Price Codes (Vector) | `input/pricecode-vector/index/catalog.xlsx` | Embeddings in S3 Vectors |
| Allocate Price Codes (Vector) | `input/pricecode-vector/allocate/boq.xlsx` | `output/pricecode-vector/boq_allocated.xlsx` |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| AI Models | OpenAI GPT-5-mini (chat), text-embedding-3-small (embeddings) |
| Vector DB | AWS S3 Vectors (1536 dims, cosine similarity) |
| Infrastructure | AWS CDK (Python) |
| Compute | ECS Fargate (batch), Lambda (APIs) |
| Storage | S3 (files), SSM Parameter Store (secrets) |
| Config | Pydantic Settings |
| CLI | Typer + Rich |
| Containers | Docker (python:3.11-slim) |
