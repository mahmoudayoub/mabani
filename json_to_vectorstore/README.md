# JSON to Vector Store Pipeline# JSON to Vector Store Pipeline



Extract items from JSON BOQ files, generate enriched embeddings, and upload to Pinecone vector database.Extract BOQ items from JSON files, generate embeddings, and upload to Pinecone vector database.



## Overview## Overview



This pipeline processes JSON files from the `excel_to_json_pipeline`, extracts items with hierarchical context, generates OpenAI embeddings with enriched text (grandparent | parent | description), and uploads them to Pinecone for semantic search.This pipeline processes hierarchical JSON BOQ files, extracts individual items, generates vector embeddings using OpenAI, and uploads them to Pinecone for semantic search.



## Features## Features



- ✅ **Hierarchical Context**: Embeddings include grandparent, parent, and item description- ✅ Extract items from hierarchical JSON

- ✅ **Batch Processing**: Efficient embedding generation with rate limiting- ✅ Generate embeddings with OpenAI (text-embedding-3-small)

- ✅ **Metadata Storage**: Full item details stored in Pinecone for retrieval- ✅ Upload to Pinecone serverless vector database

- ✅ **Progress Tracking**: Real-time progress bars with tqdm- ✅ Batch processing with progress tracking

- ✅ **Error Handling**: Robust error handling with retry logic- ✅ ASCII-safe ID generation

- ✅ **Export Support**: Generates JSONL files for backup/analysis

## Directory Structure

## Directory Structure

```

```json_to_vectorstore/

json_to_vectorstore/├── src/                      # Core modules

├── src/│   ├── json_processor.py     # JSON parsing & item extraction

│   ├── json_processor.py         # Extract & enrich items from JSON│   ├── embeddings_generator.py # OpenAI embeddings

│   ├── embeddings_generator.py   # Generate OpenAI embeddings│   ├── pinecone_uploader.py  # Pinecone upload

│   ├── pinecone_uploader.py      # Upload to Pinecone│   ├── exporter.py           # JSONL export

│   ├── exporter.py               # Export to JSONL│   ├── models.py             # Data models

│   ├── models.py                 # Data models│   └── pipeline.py           # Pipeline orchestration

│   └── pipeline.py               # Main orchestration├── input/                    # Place JSON files here

├── input/                        # (not used - reads from excel_to_json_pipeline/output)├── output/                   # Generated JSONL files

├── output/                       # JSONL exports├── logs/                     # Log files

├── logs/                         # Processing logs├── prepare_and_upload.py     # Main script

├── process_json_to_vectorstore.py # Main entry point├── requirements.txt          # Dependencies

├── delete_index.py               # Utility to delete Pinecone index├── .env                      # API keys (not in git)

├── query_vectorstore.py          # Utility to test queries└── README.md                 # This file

└── requirements.txt              # Dependencies```

```

## Installation

## Installation

```bash

```bash# Install dependencies

# From project rootpip install -r requirements.txt

pip install -r requirements.txt

```# Create .env file with API keys

cat > .env << EOF

## ConfigurationOPENAI_API_KEY=your_openai_key_here

PINECONE_API_KEY=your_pinecone_key_here

Create `.env` file in `json_to_vectorstore/` directory:EOF

```

```bash

# OpenAI API Key## Usage

OPENAI_API_KEY=sk-...

### First Time Setup

# Pinecone API Key

PINECONE_API_KEY=pc-...1. **Place JSON files** in the `input/` directory (from excel_to_json_pipeline)

```

2. **Configure environment:**

## Usage   - Set `OPENAI_API_KEY` in `.env`

   - Set `PINECONE_API_KEY` in `.env`

### Process All JSON Files

3. **Run the pipeline:**

```bash   ```bash

# Pipeline automatically reads from excel_to_json_pipeline/output   cd json_to_vectorstore

cd json_to_vectorstore   python prepare_and_upload.py

python process_json_to_vectorstore.py   ```

```

4. **Output:**

This will:   - JSONL file in `output/` directory (flattened items)

1. Load all JSON files from `../excel_to_json_pipeline/output/`   - Vectors uploaded to Pinecone index "almabani"

2. Extract items with hierarchy (grandparent, parent, description)

3. Generate embeddings: `[grandparent] | [parent] | [description]`### Adding New Data

4. Upload to Pinecone index `almabani`

5. Export to JSONL in `output/`To add new BOQ files to existing database:

```bash

### Delete and Rebuild Index# 1. Convert new Excel to JSON (in excel_to_json_pipeline)

# 2. Copy new JSON files to json_to_vectorstore/input/

```bash# 3. Run prepare_and_upload.py (will ADD to existing data)

# Delete existing indexcd json_to_vectorstore

python delete_index.pypython prepare_and_upload.py

```

# Rebuild from scratch

python process_json_to_vectorstore.py**Note:** This ADDS to existing data. If same items exist, they will be overwritten (same ID) or duplicated (different ID).

```

### Complete Refresh (Delete & Reprocess)

### Query Vector Store

To delete everything and start fresh with all JSON files:

```bash```bash

# Test a querycd json_to_vectorstore

python query_vectorstore.py "cement treated base course"python delete_and_reprocess.py

``````



## Embedding FormatThis will:

1. Delete the entire Pinecone index

**Enriched Text Format:**2. Find all JSON files from `excel_to_json_pipeline/output/`

```3. Process all files from scratch

[grandparent] | [parent] | [description]4. Upload to fresh index

```

### Delete Index Only

**Example:**

```To just delete the Pinecone index without reprocessing:

4.1 - Granular Base & Sub base | 4.2 - Cement Treated Base | Cement treated base course to PCC apron, thickness 150mm```bash

```cd json_to_vectorstore

python delete_index.py

**Key Changes (Nov 2025):**```

- ❌ Removed labels: `Context:`, `Parent:`, `Item:`

- ✅ Clean format: just values separated by `|`## Input Format

- ✅ Better alignment with query format in rate_filler_pipeline

JSON files from `excel_to_json_pipeline` with hierarchical structure:

## Metadata Stored in Pinecone

```json

Each vector includes metadata:{

```json  "source_file": "example.xlsx",

{  "source_sheet": "Sheet1",

  "description": "Cement treated base course...",  "hierarchy": [...]

  "unit": "m2",}

  "rate": 137.4,```

  "grandparent_description": "4.1 - Granular Base & Sub base",

  "parent_description": "4.2 - Cement Treated Base",## Output Format

  "item_code": "4.2.01",

  "trade": "C",JSONL file with one item per line:

  "code": "C0300411",

  "full_description": "Rigid Pavement P304...",```json

  "source_file": "Book_2.xlsx",{"item_code": "1.1.1", "description": "Concrete C40", "unit": "m3", "rate": 450.0, "source_sheet": "Sheet1"}

  "sheet_name": "9-PA"{"item_code": "1.1.2", "description": "Steel reinforcement", "unit": "ton", "rate": 2500.0, "source_sheet": "Sheet1"}

}```

```

## Vector Database

## Output Files

- **Provider:** Pinecone serverless

### JSONL Export- **Index:** almabani

- **Dimensions:** 1536

Saved to `output/vectorstore_items_YYYYMMDD_HHMMSS.jsonl`- **Metric:** cosine similarity



```jsonlEach vector includes metadata:

{"description": "...", "embedding": [...], "metadata": {...}}- `item_code`: Item code

{"description": "...", "embedding": [...], "metadata": {...}}- `description`: Full description

```- `unit`: Unit of measurement

- `rate`: Unit rate

## Pinecone Index Configuration- `source_sheet`: Original Excel sheet name



- **Index Name:** `almabani`## API Costs

- **Dimension:** 1536 (OpenAI text-embedding-3-small)

- **Metric:** cosine- **OpenAI Embeddings:** ~$0.0001 per 1K tokens

- **Cloud:** AWS- **Pinecone:** Free tier includes 100K vectors

- **Region:** us-east-1

## Requirements

## Processing Stats

- Python 3.8+

Typical processing for ~30,000 items:- openai

- **Embedding Generation:** ~5-10 minutes- pinecone-client

- **Pinecone Upload:** ~2-3 minutes (batches of 100)- pandas

- **Total Time:** ~10-15 minutes- python-dotenv

- tqdm

## Utilities

## Notes

### delete_index.py

- Item IDs are sanitized to ASCII (non-ASCII characters converted)

Safely delete the Pinecone index with confirmation prompt.- Batch size: 100 items for embeddings

- Progress bars show real-time status

```bash- Logs saved in `logs/` directory

python delete_index.py

# Prompts: Delete index 'almabani'? (yes/no):---

```

## Query the Vector Store

### query_vectorstore.py

Test your vector database with text queries:

Test semantic search queries.

```bash

```bash# Run from project root

python query_vectorstore.py "your search text" [top_k].venv/bin/python3 json_to_vectorstore/query_vectorstore.py "concrete foundation"

```

# Examples

python query_vectorstore.py "asphalt concrete base"**Examples:**

python query_vectorstore.py "excavation depth 0.5m" 10```bash

```# Search for excavation items (top 5 by default)

.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "excavation"

## Next Steps

# Get top 10 results

After uploading to Pinecone, use **rate_filler_pipeline** to auto-fill missing rates:.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "steel reinforcement" 10



```bash# Search for specific work

cd ../rate_filler_pipeline.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "pumping station 80kw"

python process_single.py your_file.xlsx "Sheet Name"```

```

**Output shows:**

## Troubleshooting- Similarity score (0-1)

- Item description

**No JSON files found?**- Unit

- Run `excel_to_json_pipeline` first- Rate

- Check that JSON files exist in `../excel_to_json_pipeline/output/`- Item code

- Source project

**OpenAI API errors?**

- Verify `OPENAI_API_KEY` in `.env` file```

- Check API rate limits
- Ensure billing is active

**Pinecone connection issues?**
- Verify `PINECONE_API_KEY` in `.env` file
- Check index name is `almabani`
- Ensure index exists (or will be created automatically)

**Embedding dimension mismatch?**
- Always use `text-embedding-3-small` model (1536 dimensions)
- Delete and recreate index if dimension changes

## Version History

- **v2.0** (Nov 2025): Removed labels from embedding format for cleaner matching
- **v1.5** (Nov 2025): Added grandparent/parent hierarchy to embeddings
- **v1.0** (Oct 2025): Initial release
