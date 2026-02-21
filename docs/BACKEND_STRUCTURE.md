# Backend Structure

## Overview

The backend is a Python 3.11 application structured as an installable package (`almabani` v2.0.0). It runs in three modes:

1. **Fargate workers** — batch processing triggered by S3 uploads
2. **Lambda handlers** — serverless APIs (chat, deletion)
3. **Flask web GUI** — local development interface

---

## `almabani/` Package

The core logic is organized into 7 sub-modules:

### `parsers/` — Excel → JSON

Extracts structured BOQ items from Excel datasheets.

| File | Purpose |
|------|---------|
| `excel_parser.py` | Reads Excel files, detects headers and data columns |
| `hierarchy_processor.py` | Builds item hierarchy (section → subsection → item) |
| `json_exporter.py` | Formats parsed data as JSON output |
| `pipeline.py` | Orchestrates the full parse pipeline |

### `rate_matcher/` — AI Rate Matching

Fills missing unit rates by finding similar items in the vector database.

| File | Size | Purpose |
|------|------|---------|
| `matcher.py` | 30 KB | 3-stage matching engine (exact → close → approximation) |
| `pipeline.py` | 17 KB | Rate filler pipeline — batch processing with concurrency control |
| `prompts.py` | 31 KB | LLM prompts for construction-domain matching |

### `pricecode/` — Price Code Allocation

Matches BOQ items to price codes from indexed catalogs.

| File | Purpose |
|------|---------|
| `indexer.py` | Indexes price code Excel files into Pinecone |
| `matcher.py` | Price code matching with unit and specificity checks |
| `pipeline.py` | Full allocation pipeline (26 KB — the largest module) |
| `prompts.py` | LLM prompts for price code matching |

### `vectorstore/` — Vector DB Integration

| File | Purpose |
|------|---------|
| `indexer.py` | Processes JSON files → OpenAI embeddings → Pinecone upsert |

### `core/` — Shared Utilities

| File | Purpose |
|------|---------|
| `embeddings.py` | OpenAI embedding creation with batching and rate limiting |
| `models.py` | Pydantic data models for BOQ items, matches, results |
| `excel.py` | Excel read/write utilities (openpyxl) |
| `storage.py` | Storage abstraction — local filesystem or S3 |
| `vector_store.py` | Pinecone client wrapper (sync) |
| `async_vector_store.py` | Pinecone async operations |
| `rate_limits.py` | API rate limiter (RPM-based) |

### `config/` — Configuration

| File | Purpose |
|------|---------|
| `settings.py` | Pydantic-based settings — all env vars mapped to typed fields |
| `logging_config.py` | Structured logging setup |

**Key settings** (from `settings.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `openai_chat_model` | `gpt-5-mini-2025-08-07` | LLM for matching/chat |
| `openai_embedding_model` | `text-embedding-3-small` | Embedding model |
| `pinecone_index_name` | `almabani` | Unit rate index |
| `pricecode_index_name` | `almabani-pricecode` | Price code index |
| `similarity_threshold` | `0.5` | Minimum cosine similarity |
| `top_k` | `10` | Candidates per query (rate filler) |
| `pricecode_top_k` | `150` | Candidates per query (price code) |
| `batch_size` | `500` | Items per processing batch |
| `max_workers` | `200` | Max concurrent embedding tasks |
| `embeddings_rpm` | `3000` | OpenAI embeddings rate limit |
| `chat_rpm` | `5000` | OpenAI chat rate limit |

### `cli/` — Command-Line Interface

| File | Purpose |
|------|---------|
| `main.py` | Typer-based CLI for running pipelines from the command line |

---

## Workers

### `worker.py` (Unit Rate Pipeline)

Fargate entrypoint for the AlmabaniStack. Determines job mode from environment variables and runs the appropriate pipeline.

**Modes**:
- `PARSE` — Downloads Excel from S3, runs parse pipeline, uploads JSON to `output/indexes/`
- `FILL` — Downloads Excel from S3, runs rate filler pipeline, uploads filled Excel to `output/fills/`

**Key functions**:
- `process_parse()` — Parse pipeline orchestration
- `process_fill()` — Rate filler with Pinecone search and LLM matching
- `register_sheet_name()` — Maintains an S3 registry of available sheets

### `pricecode_worker.py` (Price Code Pipeline)

Fargate entrypoint for the PriceCodeStack.

**Modes**:
- `INDEX` — Index price codes from Excel into Pinecone (`almabani-pricecode`)
- `ALLOCATE` — Allocate price codes to BOQ items, output filled Excel

**Key functions**:
- `process_index()` — Parse Excel, create embeddings, upsert to Pinecone
- `process_allocate()` — Download Excel, match against Pinecone index, write allocated Excel

---

## Lambda Handlers

### `chat_handler.py` (Chat API)

Natural language interface for querying both unit rates and price codes.

**Handler**: `chat_handler.handler`

**Request body**:
```json
{
  "message": "HDPE pipe DN200 PN16 supply and install",
  "chat_type": "unitrate"  // or "pricecode"
}
```

**Flow**:
1. `validate_construction_query()` — LLM validates input is construction-related
2. `search_pinecone()` — Vector search for candidates
3. `match_unitrate()` or `match_pricecode()` — LLM matching with domain prompts
4. Return structured results with confidence scores

### `delete_handler.py` (Deletion API)

Two Lambda handlers in one file:

| Handler | Endpoint | Action |
|---------|----------|--------|
| `delete_datasheet` | `DELETE /files/sheets/{sheet_name}` | Remove from Pinecone + S3 registry |
| `delete_price_code_set` | `DELETE /pricecode/sets/{set_name}` | Remove from price code Pinecone index |

---

## Flask Web GUI

**File**: `app/main.py` (628 lines)

Local development interface with these pages:

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Home page with overview |
| `/parse` | GET | Parse page UI |
| `/api/parse` | POST | Upload Excel, get JSON |
| `/index` | GET | Index page UI (list available JSONs) |
| `/api/index` | POST | Index JSON into Pinecone |
| `/fill` | GET | Fill page UI |
| `/api/fill` | POST | Upload Excel, get rate-filled Excel |
| `/query` | GET | Query page UI |
| `/api/query` | POST | Search vector store |
| `/settings` | GET | View current configuration |
| `/files` | GET | Files management page |
| `/api/files/delete` | POST | Delete a file |
| `/api/files/delete_all` | POST | Delete all files in a folder |
| `/download/<key>` | GET | Download file (S3 presigned URL redirect) |

**Storage mode**: Configurable via `STORAGE_TYPE` env var (`local` or `s3`).

---

## Docker

### `Dockerfile` (Unit Rate Worker)

- Base: `python:3.11-slim`
- Non-root user (`appuser`)
- Installs `almabani` package in editable mode
- Entrypoint: `python worker.py`

### `Dockerfile.pricecode` (Price Code Worker)

- Base: `python:3.11-slim`
- Same structure, different entrypoint: `python pricecode_worker.py`

### `docker-compose.yml` (Local Dev)

- Runs Flask web GUI on port 8080
- Mounts persistent volumes for uploads, fills, indexes, and logs
- Health check on `http://localhost:8080/`

---

## Dependencies

**Core**: pandas, openpyxl, pydantic, pydantic-settings, pyyaml

**AI**: openai, pinecone (gRPC + async)

**Web**: Flask, Jinja2, FastAPI, uvicorn

**CLI**: typer, rich, tqdm

**AWS**: boto3, serverless-wsgi
