# Almabani BOQ Management System

AI-powered construction Bill of Quantities (BOQ) processing platform. Parses Excel BOQ datasheets, indexes them into a vector database, and uses AI to match unit rates and allocate price codes — either through batch processing (cloud) or a natural language chat interface.

## Features

### Unit Rate Pipeline
- **Parse** — Extract structured items from Excel BOQ datasheets into JSON
- **Index** — Embed items with OpenAI and store in Pinecone vector database
- **Fill** — AI-powered rate matching: finds similar items and fills missing rates using 3-stage matching (exact → close → approximation)

### Price Code Pipeline
- **Index** — Index price code catalogs into a dedicated Pinecone index (`almabani-pricecode`)
- **Allocate** — Match BOQ items to price codes with unit compatibility and specificity checks

### Chat Interface
- Natural language queries against both unit rate and price code indexes
- Input validation (construction-domain only), vector search, and LLM-powered matching
- Deployed as Lambda with Function URL (no timeout) + API Gateway (29s limit, backward compat)

### Deletion API
- Delete individual datasheets or price code sets from Pinecone and S3 registry
- REST API: `DELETE /files/sheets/{sheet_name}` and `DELETE /pricecode/sets/{set_name}`

### Web GUI (Local Dev)
- Flask-based interface at `http://localhost:5000`
- Pages for Parse, Index, Fill, Query, Files management, and Settings
- Supports both local filesystem and S3 storage backends

---

## Architecture

**Event-driven "Process & Die"** — no persistent servers. Files uploaded to S3 trigger Lambda functions which launch Fargate containers. Containers process the file, upload results, and exit.

| Stack | Compute | Resources | Trigger |
|-------|---------|-----------|---------|
| **AlmabaniStack** | Fargate (1 vCPU, 2 GB) | VPC, S3, ECS, Lambda, SSM | `input/parse/`, `input/fill/` |
| **PriceCodeStack** | Fargate (2 vCPU, 8 GB) | VPC, S3, ECS, Lambda, SSM | `input/pricecode/index/`, `input/pricecode/allocate/` |
| **ChatStack** | Lambda (1 GB, 120s) | API Gateway, Function URL | POST `/chat` |
| **DeletionStack** | Lambda (30s) | API Gateway | DELETE endpoints |

**AI Stack**: OpenAI (GPT-5-mini, text-embedding-3-small) + Pinecone (2 indexes: `almabani-1`, `almabani-pricecode`)

**Secrets**: AWS SSM Parameter Store (`/almabani/*`, `/pricecode/*`)

---

## Directory Structure

```
Almabani/
├── backend/
│   ├── almabani/                  # Python package (pip install -e .)
│   │   ├── parsers/               # Excel → JSON parsing pipeline
│   │   │   ├── excel_parser.py    # BOQ Excel reader
│   │   │   ├── hierarchy_processor.py  # Item hierarchy builder
│   │   │   ├── json_exporter.py   # JSON output formatter
│   │   │   └── pipeline.py        # Parse pipeline orchestrator
│   │   ├── rate_matcher/          # Unit rate AI matching
│   │   │   ├── matcher.py         # 3-stage matching engine
│   │   │   ├── pipeline.py        # Rate filler pipeline
│   │   │   └── prompts.py         # LLM prompts for matching
│   │   ├── pricecode/             # Price code allocation
│   │   │   ├── indexer.py         # Price code indexing
│   │   │   ├── matcher.py         # Price code matching
│   │   │   ├── pipeline.py        # Allocation pipeline
│   │   │   └── prompts.py         # LLM prompts for allocation
│   │   ├── vectorstore/           # Pinecone vector DB integration
│   │   │   └── indexer.py         # JSON → embeddings → Pinecone
│   │   ├── core/                  # Shared utilities
│   │   │   ├── embeddings.py      # OpenAI embedding helpers
│   │   │   ├── models.py          # Data models
│   │   │   ├── excel.py           # Excel I/O utilities
│   │   │   ├── storage.py         # Local/S3 storage abstraction
│   │   │   ├── vector_store.py    # Pinecone client wrapper
│   │   │   ├── async_vector_store.py  # Async Pinecone operations
│   │   │   └── rate_limits.py     # API rate limiting
│   │   ├── config/                # Configuration
│   │   │   ├── settings.py        # Pydantic-based settings
│   │   │   └── logging_config.py  # Logging setup
│   │   └── cli/                   # CLI tool (typer)
│   │       └── main.py            # Command-line interface
│   ├── app/                       # Flask web GUI
│   │   ├── main.py                # Routes and API endpoints
│   │   ├── templates/             # Jinja2 HTML templates
│   │   └── static/                # CSS/JS assets
│   ├── worker.py                  # Fargate worker (parse + fill)
│   ├── pricecode_worker.py        # Fargate worker (index + allocate)
│   ├── chat_handler.py            # Lambda handler (NL chat API)
│   ├── delete_handler.py          # Lambda handler (deletion API)
│   ├── Dockerfile                 # Worker container image
│   ├── Dockerfile.pricecode       # Price code worker container image
│   ├── docker-compose.yml         # Local Docker dev setup
│   └── requirements.txt           # Python dependencies
├── infra/                         # AWS CDK (Python)
│   ├── app.py                     # CDK app entry point (4 stacks)
│   ├── almabani_stack.py          # Main stack (VPC, S3, ECS, Lambda)
│   ├── pricecode_stack.py         # Price code stack (ECS, Lambda)
│   ├── chat_stack.py              # Chat API stack (Lambda, API GW)
│   ├── deletion_stack.py          # Deletion API stack (Lambda, API GW)
│   └── lambdas/                   # Lambda trigger functions
│       ├── trigger.py             # S3 → Fargate (parse/fill)
│       └── pricecode_trigger.py   # S3 → Fargate (index/allocate)
├── data/                          # Sample data files
├── scripts/                       # Utility scripts
├── DEPLOYMENT.md                  # Cloud deployment guide
└── LOCAL_DEV.md                   # Local development guide
```

---

## Quick Start

### Local Development

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt
pip install -e .

# 2. Configure environment
cp .env.example .env
# Edit .env with your OpenAI and Pinecone API keys

# 3. Run the web GUI
python app/main.py
# Open http://localhost:5000
```

### Cloud Deployment

```bash
# 1. Install CDK dependencies
pip install -r infra/requirements.txt

# 2. Bootstrap (first time only)
cdk bootstrap aws://239146712026/eu-west-1

# 3. Deploy all stacks
cdk deploy --app "python3 infra/app.py" --all
```

### Running a Job (Cloud)

Upload a file to S3 and the pipeline runs automatically:

| Job | Upload to | Result at |
|-----|-----------|-----------|
| Parse Excel → JSON | `input/parse/myfile.xlsx` | `output/indexes/myfile.json` |
| Fill Rates | `input/fill/myfile.xlsx` | `output/fills/myfile_filled.xlsx` |
| Index Price Codes | `input/pricecode/index/catalog.xlsx` | Vectors stored in Pinecone |
| Allocate Price Codes | `input/pricecode/allocate/boq.xlsx` | `output/pricecode/boq_allocated.xlsx` |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| AI Models | OpenAI GPT-5-mini (chat), text-embedding-3-small (embeddings) |
| Vector DB | Pinecone (gRPC + async) |
| Infrastructure | AWS CDK (Python) |
| Compute | ECS Fargate (batch), Lambda (APIs) |
| Storage | S3 (files), SSM Parameter Store (secrets) |
| Web GUI | Flask + Jinja2 |
| Config | Pydantic Settings |
| CLI | Typer + Rich |
| Containers | Docker (python:3.11-slim) |
