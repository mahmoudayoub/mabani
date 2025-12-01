# Almabani BOQ Management System

AI-assisted toolkit for parsing BOQ Excel files, indexing them for semantic search, and auto-filling missing rates with a 3-stage LLM workflow.

## Overview
- **Parse**: Detect headers/columns in Excel and export hierarchical JSON per sheet.
- **Index**: Turn JSON into embeddings and push to Pinecone (ASCII-safe IDs, metadata preserved).
- **Fill**: Search the vector store and run Matcher → Expert → Estimator stages to fill rates; writes back to Excel with color coding and reasoning.
- **CLI**: Single entrypoint `almabani` built with Typer.

## Quick Start
```bash
python -m pip install -e .
```

Create `.env` in the repo root (defaults shown come from `almabani/config/settings.py`):
```
OPENAI_API_KEY=...
PINECONE_API_KEY=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
PINECONE_ENVIRONMENT=us-east-1
PINECONE_INDEX_NAME=almabani
SIMILARITY_THRESHOLD=0.5
TOP_K=6
BATCH_SIZE=500
PINECONE_BATCH_SIZE=300
MAX_WORKERS=5
```

### Build the vector database
```bash
# 1) Parse Excel → JSON (one file per sheet by default)
almabani parse data/input/Master_BOQ.xlsx --output data/output

# 2) Index JSON → Pinecone
almabani index data/output --create
```

### Fill a new BOQ
```bash
almabani fill data/input/New_Project.xlsx "Sheet Name" --output data/output
```
Outputs a filled Excel file (timestamped if `--output` is a directory) and logs the processing stats.

## CLI Reference
- `almabani parse INPUT_FILE [--output PATH] [--mode single|multiple] [--sheets a,b,c] [--log PATH]`
- `almabani index INPUT_PATH [--namespace NS] [--batch-size N] [--create] [--log PATH]` (defaults pulled from .env if flags omitted)
- `almabani fill INPUT_FILE SHEET_NAME [--output PATH] [--namespace NS] [--threshold FLOAT] [--top-k N] [--workers N] [--log PATH]` (defaults pulled from .env if flags omitted)
- `almabani query "text to search" [--namespace NS] [--top-k N] [--threshold FLOAT]` (defaults pulled from .env if flags omitted)
- `almabani delete-index [--force]`
- `almabani delete-sheet SHEET_NAME [--force]`
- `almabani version`

## What the Pipelines Do
### Parsing (`almabani.parsers`)
- `ExcelIO` auto-detects the header row (scans first 10 rows for Level/Item/Description/Unit/Rate) and renames duplicate columns.
- Required columns are inferred by name; optional ones include `trade`, `code`, `full_description`, `reference`, `reasoning`.
- Rows after the header become `HierarchyItem`s. Level handling:
  - Numeric `level` → tree depth.
  - Subcategory indicator `c` → sub-level tracking (consecutive `c` rows nest).
  - Items with empty Level but an Item code/description are treated as leaf items.
- `HierarchyProcessor` attaches children based on numeric levels and `c`-level stacks.
- `JsonExporter` writes either one workbook JSON or one JSON per sheet (`<workbook>_<sheet>.json`).

### Vector indexing (`almabani.vectorstore`)
- `JSONProcessor` walks each sheet’s hierarchy; embedding text looks like `Category: A > B. <description>. Unit: <unit>`.
- Metadata includes `category_path`, `sheet_name`, `parent`, `grandparent`, `row_number`, and optional fields (`trade`, `code`, `full_description`).
- `EmbeddingsService` (OpenAI) batches requests; `VectorStoreService` sanitizes IDs to ASCII and upserts in batches.

### Rate filling (`almabani.rate_matcher`)
- `RateMatcher.find_match`:
  1) Embed `[grandparent] / [parent] / description` and search Pinecone (top_k, threshold).
  2) Stage 1: Matcher (expects `status: exact_match`).
  3) Stage 2: Expert (expects `status: close_match` with confidences).
  4) Stage 3: Estimator (expects `status: approximated`; note the prompt text currently says `"approximation"`, so keep them in sync).
- `RateFillerPipeline` targets rows where **Level is empty** and **Item is present**. Parents/grandparents are tracked from numeric and `c` levels above the row.
- Excel output (`ExcelIO.write_filled_excel`):
  - Creates `AutoRate Reference` and `AutoRate Reasoning` columns if missing.
  - Colors: Green (exact), Yellow (close), Orange (approximation), Red (not filled).
  - Writes filled unit/rate, reference (with confidence for close/approx), and reasoning text.

## Configuration Notes
- `Settings` loads from `.env` in the repo root; computed paths `input/`, `output/`, `logs/` live under the project root by default.
- Pinecone index creation only happens when `almabani index --create` is run; `fill`/`query` assume the index already exists.
- Embedding dimensions default to 1536 (`text-embedding-3-small`); adjust `PINECONE_DIMENSION` if you switch models.

## Troubleshooting
- **Estimator never triggers**: Ensure the Estimator prompt returns `status: "approximated"` to match `RateMatcher`.
- **Empty results**: Verify the index exists and your namespace matches; lower `--threshold` (e.g., 0.5) or increase `--top-k`.
- **Missing API keys**: Settings creation will fail if `OPENAI_API_KEY` or `PINECONE_API_KEY` are absent.
- **Wrong columns detected**: Check header row placement; the detector scans only the first 10 rows.
