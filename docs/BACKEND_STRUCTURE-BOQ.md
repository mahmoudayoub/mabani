# Backend Structure

## Overview

The backend is a Python 3.11 application structured as an installable package (`almabani` v2.0.0). It runs in two modes:

1. **Fargate workers** — batch processing triggered by S3 uploads
2. **Lambda handlers** — serverless APIs (chat, deletion)

---

## Entrypoints

| File | Runs As | Purpose |
|------|---------|---------|
| `worker.py` | Fargate (AlmabaniStack) | Unit rate parsing & filling |
| `pricecode_worker.py` | Fargate (PriceCodeStack) | Lexical price code index & allocation |
| `pricecode_vector_worker.py` | Fargate (PriceCodeVectorStack) | Embedding price code index & allocation |
| `chat_handler.py` | Lambda (ChatStack) | Natural language chat API |
| `delete_handler.py` | Lambda (DeletionStack) | Async deletion dispatchers + workers |

---

## `almabani/` Package

The core logic is organized into sub-modules:

### `parsers/` — Excel to JSON

Extracts structured BOQ items from Excel datasheets.

| File | Purpose |
|------|---------|
| `excel_parser.py` | Reads Excel files, detects headers and data columns |
| `hierarchy_processor.py` | Builds item hierarchy (section → subsection → item) |
| `json_exporter.py` | Formats parsed data as JSON output |
| `pipeline.py` | Orchestrates the full parse pipeline |

### `rate_matcher/` — AI Rate Matching

Fills missing unit rates by finding similar items in the vector database.

| File | Purpose |
|------|---------|
| `matcher.py` | 3-stage matching engine (exact → close → approximation) |
| `pipeline.py` | Rate filler pipeline — batch processing with concurrency control |
| `prompts.py` | LLM prompts for construction-domain matching |

### `pricecode/` — Price Code Allocation (Lexical)

Matches BOQ items to price codes using TF-IDF lexical search + LLM validation.

| File | Purpose |
|------|---------|
| `lexical_search.py` | TF-IDF/BM25 lexical engine with domain-aware tokenization, synonym normalization, spec extraction |
| `indexer.py` | Builds SQLite index from reference Excel files |
| `matcher.py` | Lexical search → LLM judge (match or reject) |
| `pipeline.py` | Full allocation pipeline (parse → search → match → color-coded Excel) |
| `prompts.py` | LLM prompts for price code matching |

### `pricecode_vector/` — Price Code Allocation (Embedding-Based)

Matches BOQ items to price codes using OpenAI embeddings + S3 Vectors + LLM validation.

| File | Purpose |
|------|---------|
| `indexer.py` | Embed price code Excel files → store in S3 Vectors |
| `matcher.py` | Embedding similarity + LLM one-shot matching |
| `pipeline.py` | Full allocation pipeline using embeddings |
| `prompts.py` | LLM prompts for embedding-based matching |

### `vectorstore/` — S3 Vectors Indexing

| File | Purpose |
|------|---------|
| `indexer.py` | Process JSON files → OpenAI embeddings → S3 Vectors upsert |

### `core/` — Shared Utilities

| File | Purpose |
|------|---------|
| `embeddings.py` | OpenAI embedding creation with batching and rate limiting |
| `models.py` | Pydantic data models for BOQ items, matches, results |
| `excel.py` | Excel read/write utilities (openpyxl) |
| `storage.py` | Storage abstraction — local filesystem or S3 |
| `vector_store.py` | S3 Vectors client wrapper (index management, upsert, search, delete) |
| `async_vector_store.py` | Async S3 Vectors client (used by chat Lambda) |
| `rate_limits.py` | API rate limiter (RPM-based) |

### `config/` — Configuration

| File | Purpose |
|------|---------|
| `settings.py` | Pydantic-based settings — all env vars mapped to typed fields |
| `logging_config.py` | Structured logging setup |

---

## Key Settings (from `settings.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `openai_chat_model` | `gpt-5-mini-2025-08-07` | LLM for matching/chat |
| `openai_embedding_model` | `text-embedding-3-small` | Embedding model |
| `s3_vectors_bucket` | `almabani-vectors` | S3 Vectors bucket |
| `s3_vectors_index_name` | `almabani` | Unit rate S3 Vectors index |
| `pricecode_index_name` | `almabani-pricecode-vector` | Price code S3 Vectors index (chat + vector pipeline) |
| `similarity_threshold` | `0.5` | Minimum cosine similarity (unit rate) |
| `top_k` | `10` | Candidates per query (unit rate fill) |
| `pricecode_max_candidates` | `1` | Lexical candidates sent to LLM per item |
| `pricecode_max_concurrent` | `200` | Max concurrent DB queries (lexical pipeline) |
| `pricecode_vector_top_k` | `5` | Candidates per query (vector price code) |
| `pricecode_vector_threshold` | `0.40` | Minimum cosine similarity (vector price code) |
| `batch_size` | `500` | Items per processing batch |
| `max_workers` | `200` | Max concurrent embedding tasks |
| `embeddings_rpm` | `3000` | OpenAI embeddings rate limit |
| `chat_rpm` | `5000` | OpenAI chat rate limit |

---

## Workers

### `worker.py` (Unit Rate Pipeline)

Fargate entrypoint for the AlmabaniStack. Determines job mode from environment variables.

**Modes**:
- `PARSE` — Downloads Excel from S3, runs parse pipeline, uploads JSON to `output/indexes/`, indexes into S3 Vectors
- `FILL` — Downloads Excel from S3, runs rate filler pipeline, uploads filled Excel to `output/fills/`

### `pricecode_worker.py` (Price Code Lexical Pipeline)

Fargate entrypoint for the PriceCodeStack.

**Modes**:
- `INDEX` — Index price codes from Excel into SQLite TF-IDF database, upload to S3
- `ALLOCATE` — Download SQLite index from S3, match BOQ items using lexical search + LLM, output color-coded Excel

### `pricecode_vector_worker.py` (Price Code Vector Pipeline)

Fargate entrypoint for the PriceCodeVectorStack.

**Modes**:
- `INDEX` — Embed price code items from Excel into S3 Vectors index
- `ALLOCATE` — Query S3 Vectors for similar items, match via LLM, output allocated Excel

---

## Lambda Handlers

### `chat_handler.py` (Chat API)

Natural language interface for querying both unit rates and price codes.

**Request body**:
```json
{
  "message": "HDPE pipe DN200 PN16 supply and install",
  "type": "unitrate"
}
```

**Flow**:
1. `validate_construction_query()` — LLM validates input is construction-related
2. `search_vectors()` — Embed query, search S3 Vectors for candidates
3. `match_unitrate()` or `match_pricecode()` — LLM matching with domain prompts
4. Return structured results with confidence scores

### `delete_handler.py` (Deletion API)

Dispatcher/worker Lambda handlers for async deletion:

| Handler | Endpoint | Action |
|---------|----------|--------|
| `dispatch_delete_datasheet` | `DELETE /files/sheets/{name}` | 202 → async delete from S3 Vectors + registry |
| `dispatch_delete_price_code_set` | `DELETE /pricecode/sets/{name}` | 202 → async delete from index |
| `dispatch_delete_pricecode_vector_set` | `DELETE /pricecode-vector/sets/{name}` | 202 → async delete from S3 Vectors |
| `get_deletion_status` | `GET /deletion-status/{id}` | Poll status (auto-cleanup) |

---

## Docker

| File | Purpose | Entrypoint |
|------|---------|-----------|
| `Dockerfile` | Unit rate worker | `python worker.py` |
| `Dockerfile.pricecode` | Pricecode lexical worker | `python pricecode_worker.py` |
| `Dockerfile.pricecode_vector` | Pricecode vector worker | `python pricecode_vector_worker.py` |

All images use `python:3.11-slim`, run as non-root `appuser`, and install the `almabani` package in editable mode.
