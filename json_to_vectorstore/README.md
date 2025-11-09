# JSON to Vector Store Pipeline

Extract BOQ items from JSON files, generate embeddings, and upload to Pinecone vector database.

## Overview

This pipeline processes hierarchical JSON BOQ files, extracts individual items, generates vector embeddings using OpenAI, and uploads them to Pinecone for semantic search.

## Features

- ✅ Extract items from hierarchical JSON
- ✅ Generate embeddings with OpenAI (text-embedding-3-small)
- ✅ Upload to Pinecone serverless vector database
- ✅ Batch processing with progress tracking
- ✅ ASCII-safe ID generation

## Directory Structure

```
json_to_vectorstore/
├── src/                      # Core modules
│   ├── json_processor.py     # JSON parsing & item extraction
│   ├── embeddings_generator.py # OpenAI embeddings
│   ├── pinecone_uploader.py  # Pinecone upload
│   ├── exporter.py           # JSONL export
│   ├── models.py             # Data models
│   └── pipeline.py           # Pipeline orchestration
├── input/                    # Place JSON files here
├── output/                   # Generated JSONL files
├── logs/                     # Log files
├── prepare_and_upload.py     # Main script
├── requirements.txt          # Dependencies
├── .env                      # API keys (not in git)
└── README.md                 # This file
```

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with API keys
cat > .env << EOF
OPENAI_API_KEY=your_openai_key_here
PINECONE_API_KEY=your_pinecone_key_here
EOF
```

## Usage

### First Time Setup

1. **Place JSON files** in the `input/` directory (from excel_to_json_pipeline)

2. **Configure environment:**
   - Set `OPENAI_API_KEY` in `.env`
   - Set `PINECONE_API_KEY` in `.env`

3. **Run the pipeline:**
   ```bash
   cd json_to_vectorstore
   python prepare_and_upload.py
   ```

4. **Output:**
   - JSONL file in `output/` directory (flattened items)
   - Vectors uploaded to Pinecone index "almabani"

### Adding New Data

To add new BOQ files to existing database:
```bash
# 1. Convert new Excel to JSON (in excel_to_json_pipeline)
# 2. Copy new JSON files to json_to_vectorstore/input/
# 3. Run prepare_and_upload.py (will ADD to existing data)
cd json_to_vectorstore
python prepare_and_upload.py
```

**Note:** This ADDS to existing data. If same items exist, they will be overwritten (same ID) or duplicated (different ID).

### Complete Refresh (Delete & Reprocess)

To delete everything and start fresh with all JSON files:
```bash
cd json_to_vectorstore
python delete_and_reprocess.py
```

This will:
1. Delete the entire Pinecone index
2. Find all JSON files from `excel_to_json_pipeline/output/`
3. Process all files from scratch
4. Upload to fresh index

### Delete Index Only

To just delete the Pinecone index without reprocessing:
```bash
cd json_to_vectorstore
python delete_index.py
```

## Input Format

JSON files from `excel_to_json_pipeline` with hierarchical structure:

```json
{
  "source_file": "example.xlsx",
  "source_sheet": "Sheet1",
  "hierarchy": [...]
}
```

## Output Format

JSONL file with one item per line:

```json
{"item_code": "1.1.1", "description": "Concrete C40", "unit": "m3", "rate": 450.0, "source_sheet": "Sheet1"}
{"item_code": "1.1.2", "description": "Steel reinforcement", "unit": "ton", "rate": 2500.0, "source_sheet": "Sheet1"}
```

## Vector Database

- **Provider:** Pinecone serverless
- **Index:** almabani
- **Dimensions:** 1536
- **Metric:** cosine similarity

Each vector includes metadata:
- `item_code`: Item code
- `description`: Full description
- `unit`: Unit of measurement
- `rate`: Unit rate
- `source_sheet`: Original Excel sheet name

## API Costs

- **OpenAI Embeddings:** ~$0.0001 per 1K tokens
- **Pinecone:** Free tier includes 100K vectors

## Requirements

- Python 3.8+
- openai
- pinecone-client
- pandas
- python-dotenv
- tqdm

## Notes

- Item IDs are sanitized to ASCII (non-ASCII characters converted)
- Batch size: 100 items for embeddings
- Progress bars show real-time status
- Logs saved in `logs/` directory

---

## Query the Vector Store

Test your vector database with text queries:

```bash
# Run from project root
.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "concrete foundation"
```

**Examples:**
```bash
# Search for excavation items (top 5 by default)
.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "excavation"

# Get top 10 results
.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "steel reinforcement" 10

# Search for specific work
.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "pumping station 80kw"
```

**Output shows:**
- Similarity score (0-1)
- Item description
- Unit
- Rate
- Item code
- Source project

```
