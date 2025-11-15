# JSON to Vector Store Pipeline# JSON to Vector Store Pipeline# JSON to Vector Store Pipeline



Extract items from JSON BOQ files, generate enriched embeddings with hierarchical context, and upload to Pinecone vector database for semantic search.



## OverviewExtract items from JSON BOQ files, generate enriched embeddings, and upload to Pinecone vector database.Extract BOQ items from JSON files, generate embeddings, and upload to Pinecone vector database.



This pipeline processes JSON files from the `excel_to_json_pipeline`, extracts items with hierarchical context (grandparent, parent, description), generates OpenAI embeddings, and uploads them to Pinecone for semantic search. The embeddings include enriched text to improve search quality.



## Features## Overview## Overview



- ✅ **Hierarchical Context**: Embeddings include grandparent, parent, and item description

- ✅ **Enriched Embeddings**: Format: `[grandparent] | [parent] | [description]`

- ✅ **Batch Processing**: Efficient embedding generation with rate limitingThis pipeline processes JSON files from the `excel_to_json_pipeline`, extracts items with hierarchical context, generates OpenAI embeddings with enriched text (grandparent | parent | description), and uploads them to Pinecone for semantic search.This pipeline processes hierarchical JSON BOQ files, extracts individual items, generates vector embeddings using OpenAI, and uploads them to Pinecone for semantic search.

- ✅ **Metadata Storage**: Full item details stored in Pinecone for retrieval

- ✅ **Progress Tracking**: Real-time progress bars with tqdm

- ✅ **Error Handling**: Robust error handling with retry logic

- ✅ **Export Support**: Generates JSONL files for backup/analysis## Features## Features

- ✅ **Sheet Tracking**: Stores sheet name in metadata for filtering

- ✅ **Utilities**: Delete index, delete specific sheets, query testing



## Directory Structure- ✅ **Hierarchical Context**: Embeddings include grandparent, parent, and item description- ✅ Extract items from hierarchical JSON



```- ✅ **Batch Processing**: Efficient embedding generation with rate limiting- ✅ Generate embeddings with OpenAI (text-embedding-3-small)

json_to_vectorstore/

├── src/- ✅ **Metadata Storage**: Full item details stored in Pinecone for retrieval- ✅ Upload to Pinecone serverless vector database

│   ├── json_processor.py         # Extract & enrich items from JSON

│   ├── embeddings_generator.py   # Generate OpenAI embeddings- ✅ **Progress Tracking**: Real-time progress bars with tqdm- ✅ Batch processing with progress tracking

│   ├── pinecone_uploader.py      # Upload to Pinecone

│   ├── exporter.py               # Export to JSONL- ✅ **Error Handling**: Robust error handling with retry logic- ✅ ASCII-safe ID generation

│   ├── models.py                 # Data models

│   └── pipeline.py               # Main orchestration- ✅ **Export Support**: Generates JSONL files for backup/analysis

├── input/                        # Place JSON files here (from excel_to_json_pipeline)

├── output/                       # JSONL exports## Directory Structure

├── logs/                         # Processing logs

├── process_json_to_vectorstore.py # Main entry point## Directory Structure

├── delete_index.py               # Utility: Delete entire Pinecone index

├── delete_sheet.py               # Utility: Delete specific sheet from index```

├── query_vectorstore.py          # Utility: Test vector search queries

└── requirements.txt              # Dependencies```json_to_vectorstore/

```

json_to_vectorstore/├── src/                      # Core modules

## Installation

├── src/│   ├── json_processor.py     # JSON parsing & item extraction

```bash

# Install dependencies│   ├── json_processor.py         # Extract & enrich items from JSON│   ├── embeddings_generator.py # OpenAI embeddings

pip install -r json_to_vectorstore/requirements.txt

```│   ├── embeddings_generator.py   # Generate OpenAI embeddings│   ├── pinecone_uploader.py  # Pinecone upload



## Configuration│   ├── pinecone_uploader.py      # Upload to Pinecone│   ├── exporter.py           # JSONL export



All configuration is in the root `.env` file at `/Almabani/.env`:│   ├── exporter.py               # Export to JSONL│   ├── models.py             # Data models



```bash│   ├── models.py                 # Data models│   └── pipeline.py           # Pipeline orchestration

# OpenAI API Key (for embeddings)

OPENAI_API_KEY=sk-...│   └── pipeline.py               # Main orchestration├── input/                    # Place JSON files here



# Pinecone API Key (for vector database)├── input/                        # (not used - reads from excel_to_json_pipeline/output)├── output/                   # Generated JSONL files

PINECONE_API_KEY=pc-...

```├── output/                       # JSONL exports├── logs/                     # Log files



**Pinecone Configuration** (hardcoded in scripts):├── logs/                         # Processing logs├── prepare_and_upload.py     # Main script

- **Index Name**: `almabani`

- **Dimension**: 1536 (text-embedding-3-small)├── process_json_to_vectorstore.py # Main entry point├── requirements.txt          # Dependencies

- **Metric**: cosine

- **Cloud**: AWS├── delete_index.py               # Utility to delete Pinecone index├── .env                      # API keys (not in git)

- **Region**: us-east-1

- **Plan**: Serverless (free tier)├── query_vectorstore.py          # Utility to test queries└── README.md                 # This file



## Usage└── requirements.txt              # Dependencies```



### First Time Setup```



1. **Convert Excel to JSON** (using excel_to_json_pipeline)

2. **Place JSON files** in `input/` directory## Installation

3. **Run the pipeline:**

```bash

```bash

cd json_to_vectorstore```bash# Install dependencies

python process_json_to_vectorstore.py

```# From project rootpip install -r requirements.txt



This will:pip install -r requirements.txt

1. Load all JSON files from `input/`

2. Extract items with hierarchy (grandparent, parent, description)```# Create .env file with API keys

3. Generate embeddings: `[grandparent] | [parent] | [description]`

4. Upload to Pinecone index `almabani`cat > .env << EOF

5. Export to JSONL in `output/`

## ConfigurationOPENAI_API_KEY=your_openai_key_here

### Adding New Data

PINECONE_API_KEY=your_pinecone_key_here

To add new BOQ files to existing database:

Create `.env` file in `json_to_vectorstore/` directory:EOF

```bash

# 1. Convert new Excel to JSON (in excel_to_json_pipeline)```

cd ../excel_to_json_pipeline

python process_separate_sheets.py```bash



# 2. Copy new JSON files to json_to_vectorstore/input/# OpenAI API Key## Usage

cp output/*.json ../json_to_vectorstore/input/

OPENAI_API_KEY=sk-...

# 3. Run process_json_to_vectorstore.py (will ADD to existing data)

cd ../json_to_vectorstore### First Time Setup

python process_json_to_vectorstore.py

```# Pinecone API Key



### Delete Entire IndexPINECONE_API_KEY=pc-...1. **Place JSON files** in the `input/` directory (from excel_to_json_pipeline)



```bash```

# WARNING: This deletes ALL data from Pinecone index

python delete_index.py2. **Configure environment:**



# Prompts for confirmation before deleting## Usage   - Set `OPENAI_API_KEY` in `.env`

```

   - Set `PINECONE_API_KEY` in `.env`

### Delete Specific Sheet

### Process All JSON Files

```bash

# Delete all items from a specific sheet3. **Run the pipeline:**

python delete_sheet.py "Sheet Name"

```bash   ```bash

# Example:

python delete_sheet.py "Terminal"# Pipeline automatically reads from excel_to_json_pipeline/output   cd json_to_vectorstore

python delete_sheet.py "9-PA"

```cd json_to_vectorstore   python prepare_and_upload.py



### Query/Test Vector Storepython process_json_to_vectorstore.py   ```



```bash```

# Test semantic search

python query_vectorstore.py "excavation depth 2m"4. **Output:**



# Shows:This will:   - JSONL file in `output/` directory (flattened items)

# - Top 5 similar items

# - Similarity scores1. Load all JSON files from `../excel_to_json_pipeline/output/`   - Vectors uploaded to Pinecone index "almabani"

# - Full metadata (description, unit, rate, parent, grandparent, sheet)

```2. Extract items with hierarchy (grandparent, parent, description)



## How It Works3. Generate embeddings: `[grandparent] | [parent] | [description]`### Adding New Data



### 1. JSON Processing4. Upload to Pinecone index `almabani`



Reads JSON files and extracts items with hierarchy:5. Export to JSONL in `output/`To add new BOQ files to existing database:



```python```bash

# For each item in JSON:

item = {### Delete and Rebuild Index# 1. Convert new Excel to JSON (in excel_to_json_pipeline)

    "item_code": "3.1.02",

    "description": "Depth not exceeding 0.25m",# 2. Copy new JSON files to json_to_vectorstore/input/

    "unit": "m³",

    "rate": 45.50,```bash# 3. Run prepare_and_upload.py (will ADD to existing data)

    "parent": "Apron area",

    "grandparent": "General Excavation: material...",# Delete existing indexcd json_to_vectorstore

    "sheet_name": "Terminal"  # From JSON filename

}python delete_index.pypython prepare_and_upload.py

```

```

### 2. Embedding Generation

# Rebuild from scratch

Creates enriched text for better semantic search:

python process_json_to_vectorstore.py**Note:** This ADDS to existing data. If same items exist, they will be overwritten (same ID) or duplicated (different ID).

```python

# Enriched text format```

enriched_text = f"{grandparent} | {parent} | {description}"

### Complete Refresh (Delete & Reprocess)

# Example:

# "General Excavation: material... | Apron area | Depth not exceeding 0.25m"### Query Vector Store



# Generate embeddingTo delete everything and start fresh with all JSON files:

embedding = openai.embeddings.create(

    model="text-embedding-3-small",```bash```bash

    input=enriched_text

)# Test a querycd json_to_vectorstore

```

python query_vectorstore.py "cement treated base course"python delete_and_reprocess.py

**Why enriched embeddings?**

- Captures hierarchical context``````

- Improves search relevance

- Matches how rate_filler_pipeline searches

- Better disambiguation (same description, different parent)

## Embedding FormatThis will:

### 3. Pinecone Upload

1. Delete the entire Pinecone index

Uploads vectors with full metadata:

**Enriched Text Format:**2. Find all JSON files from `excel_to_json_pipeline/output/`

```python

vector = {```3. Process all files from scratch

    "id": "terminal-row123",  # Unique ID

    "values": embedding,      # 1536-dimensional vector[grandparent] | [parent] | [description]4. Upload to fresh index

    "metadata": {

        "item_code": "3.1.02",```

        "description": "Depth not exceeding 0.25m",

        "unit": "m³",### Delete Index Only

        "rate": 45.50,

        "parent": "Apron area",**Example:**

        "grandparent": "General Excavation: material...",

        "sheet_name": "Terminal",```To just delete the Pinecone index without reprocessing:

        "enriched_text": "[grandparent] | [parent] | [description]",

        "project": "Terminal"  # Simplified sheet name4.1 - Granular Base & Sub base | 4.2 - Cement Treated Base | Cement treated base course to PCC apron, thickness 150mm```bash

    }

}```cd json_to_vectorstore

```

python delete_index.py

**Metadata fields:**

- All original item data preserved**Key Changes (Nov 2025):**```

- Sheet name for filtering

- Enriched text for reference- ❌ Removed labels: `Context:`, `Parent:`, `Item:`

- Project name (simplified sheet)

- ✅ Clean format: just values separated by `|`## Input Format

### 4. JSONL Export

- ✅ Better alignment with query format in rate_filler_pipeline

Exports flattened items to JSONL for backup:

JSON files from `excel_to_json_pipeline` with hierarchical structure:

```jsonl

{"item_code": "3.1.02", "description": "Depth not exceeding 0.25m", "unit": "m³", "rate": 45.50, "parent": "Apron area", "grandparent": "General Excavation: material...", "sheet_name": "Terminal", "enriched_text": "General Excavation: material... | Apron area | Depth not exceeding 0.25m"}## Metadata Stored in Pinecone

{"item_code": "3.1.03", "description": "Depth 0.25m to 0.50m", "unit": "m³", "rate": 52.00, "parent": "Apron area", "grandparent": "General Excavation: material...", "sheet_name": "Terminal", "enriched_text": "General Excavation: material... | Apron area | Depth 0.25m to 0.50m"}

``````json



## OutputEach vector includes metadata:{



### JSONL File```json  "source_file": "example.xlsx",



`output/vectorstore_items_{timestamp}.jsonl`{  "source_sheet": "Sheet1",



Contains all processed items in flattened format:  "description": "Cement treated base course...",  "hierarchy": [...]

- One item per line

- Valid JSON on each line  "unit": "m2",}

- Includes all metadata

- Useful for analysis, backup, or re-processing  "rate": 137.4,```



### Pinecone Index  "grandparent_description": "4.1 - Granular Base & Sub base",



**Index**: `almabani`  "parent_description": "4.2 - Cement Treated Base",## Output Format



Contains:  "item_code": "4.2.01",

- Vectors (1536 dimensions)

- Metadata (item details)  "trade": "C",JSONL file with one item per line:

- Searchable by semantic similarity

  "code": "C0300411",

**Query example:**

```python  "full_description": "Rigid Pavement P304...",```json

results = index.query(

    vector=query_embedding,  "source_file": "Book_2.xlsx",{"item_code": "1.1.1", "description": "Concrete C40", "unit": "m3", "rate": 450.0, "source_sheet": "Sheet1"}

    top_k=6,

    include_metadata=True  "sheet_name": "9-PA"{"item_code": "1.1.2", "description": "Steel reinforcement", "unit": "ton", "rate": 2500.0, "source_sheet": "Sheet1"}

)

```}```



## Costs```



Approximate costs for processing:## Vector Database



**Embeddings** (OpenAI text-embedding-3-small):## Output Files

- $0.00002 per 1,000 tokens

- Average item: ~50 tokens- **Provider:** Pinecone serverless

- 1,000 items ≈ $0.001 (one tenth of a cent)

### JSONL Export- **Index:** almabani

**Pinecone Serverless**:

- Free tier: 2 million vector operations/month- **Dimensions:** 1536

- Storage: First 1GB free

- Typical BOQ database: < 100MBSaved to `output/vectorstore_items_YYYYMMDD_HHMMSS.jsonl`- **Metric:** cosine similarity

- **Cost: $0 for most use cases**



**Example costs for 10,000 items:**

- Embeddings: ~$0.01```jsonlEach vector includes metadata:

- Pinecone: $0 (free tier)

- **Total: ~$0.01**{"description": "...", "embedding": [...], "metadata": {...}}- `item_code`: Item code



Very affordable for vector search capabilities!{"description": "...", "embedding": [...], "metadata": {...}}- `description`: Full description



## Performance```- `unit`: Unit of measurement



Typical processing times for 1,000 items:- `rate`: Unit rate

- **JSON Processing**: < 1 second

- **Embedding Generation**: ~1-2 minutes (OpenAI rate limits)## Pinecone Index Configuration- `source_sheet`: Original Excel sheet name

- **Pinecone Upload**: ~10-20 seconds (batch upload)

- **JSONL Export**: < 1 second

- **Total**: ~2-3 minutes

- **Index Name:** `almabani`## API Costs

**Batch Processing:**

- Embeddings: 100 items per batch- **Dimension:** 1536 (OpenAI text-embedding-3-small)

- Pinecone upload: 100 vectors per batch

- Progress bars show real-time status- **Metric:** cosine- **OpenAI Embeddings:** ~$0.0001 per 1K tokens



## Troubleshooting- **Cloud:** AWS- **Pinecone:** Free tier includes 100K vectors



### OpenAI API errors?- **Region:** us-east-1

- Verify `OPENAI_API_KEY` in root `.env`

- Check API key has credits## Requirements

- Review rate limit errors in logs

- Try reducing batch size if rate limited## Processing Stats



### Pinecone connection errors?- Python 3.8+

- Verify `PINECONE_API_KEY` in root `.env`

- Check index `almabani` exists (auto-created if not)Typical processing for ~30,000 items:- openai

- Verify region is `us-east-1`

- Check Pinecone dashboard for status- **Embedding Generation:** ~5-10 minutes- pinecone-client



### No items extracted from JSON?- **Pinecone Upload:** ~2-3 minutes (batches of 100)- pandas

- Verify JSON files are in `input/` directory

- Check JSON structure matches expected format- **Total Time:** ~10-15 minutes- python-dotenv

- Review logs for parsing errors

- Ensure items have required fields (description, unit, rate)- tqdm



### Embedding generation slow?## Utilities

- Normal for large datasets (rate limited by OpenAI)

- Progress bar shows estimated time remaining## Notes

- Consider processing in smaller batches

- Check OpenAI account tier limits### delete_index.py



### Duplicate vectors in Pinecone?- Item IDs are sanitized to ASCII (non-ASCII characters converted)

- IDs are generated from sheet-row combinations

- Re-running with same data will **update** existing vectorsSafely delete the Pinecone index with confirmation prompt.- Batch size: 100 items for embeddings

- Use `delete_sheet.py` to remove before re-uploading

- Use `delete_index.py` for clean slate- Progress bars show real-time status



### Query returns no results?```bash- Logs saved in `logs/` directory

- Check index has data (use `query_vectorstore.py`)

- Verify query format matches embedding formatpython delete_index.py

- Lower similarity threshold in search

- Check if items were actually uploaded (review logs)# Prompts: Delete index 'almabani'? (yes/no):---



## Utilities```



### query_vectorstore.py## Query the Vector Store



Test semantic search queries:### query_vectorstore.py



```bashTest your vector database with text queries:

python query_vectorstore.py "concrete C30/20"

Test semantic search queries.

# Output:

# Top 5 matches:```bash

# 1. Score: 0.92 | Concrete C30/20 unreinforced (m³ @ 320.00 QAR)

#    Sheet: Terminal | Parent: Structural Work```bash# Run from project root

# 2. Score: 0.87 | Concrete C40/20 (m³ @ 350.00 QAR)

#    Sheet: Hilton | Parent: Foundationpython query_vectorstore.py "your search text" [top_k].venv/bin/python3 json_to_vectorstore/query_vectorstore.py "concrete foundation"

# ...

``````



### delete_sheet.py# Examples



Remove all vectors from a specific sheet:python query_vectorstore.py "asphalt concrete base"**Examples:**



```bashpython query_vectorstore.py "excavation depth 0.5m" 10```bash

python delete_sheet.py "Terminal"

```# Search for excavation items (top 5 by default)

# Output:

# Searching for items from sheet: Terminal.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "excavation"

# Found 450 items from Terminal

# Deleting in batches of 100...## Next Steps

# ✓ Deleted all 450 items from Terminal

```# Get top 10 results



### delete_index.pyAfter uploading to Pinecone, use **rate_filler_pipeline** to auto-fill missing rates:.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "steel reinforcement" 10



Delete entire Pinecone index:



```bash```bash# Search for specific work

python delete_index.py

cd ../rate_filler_pipeline.venv/bin/python3 json_to_vectorstore/query_vectorstore.py "pumping station 80kw"

# Output:

# WARNING: This will delete the entire Pinecone index 'almabani'python process_single.py your_file.xlsx "Sheet Name"```

# Are you sure? (yes/no): yes

# ✓ Index deleted successfully```

```

**Output shows:**

## Integration with Other Pipelines

## Troubleshooting- Similarity score (0-1)

This pipeline is the **middle step** in the BOQ processing workflow:

- Item description

```

Excel Files**No JSON files found?**- Unit

    ↓

[excel_to_json_pipeline] ← Converts Excel to JSON- Run `excel_to_json_pipeline` first- Rate

    ↓

JSON Files- Check that JSON files exist in `../excel_to_json_pipeline/output/`- Item code

    ↓

[json_to_vectorstore] ← YOU ARE HERE- Source project

    ↓

Pinecone Vector Database**OpenAI API errors?**

    ↓

[rate_filler_pipeline] ← Uses vector search to fill rates- Verify `OPENAI_API_KEY` in `.env` file```

    ↓

Filled Excel Files- Check API rate limits

```- Ensure billing is active



**Inputs from:****Pinecone connection issues?**

- excel_to_json_pipeline: JSON files with hierarchical structure- Verify `PINECONE_API_KEY` in `.env` file

- Check index name is `almabani`

**Outputs to:**- Ensure index exists (or will be created automatically)

- Pinecone: Vector database for semantic search

- rate_filler_pipeline: Uses embeddings for matching**Embedding dimension mismatch?**

- Always use `text-embedding-3-small` model (1536 dimensions)

## Best Practices- Delete and recreate index if dimension changes



### When to Re-upload

**Full re-upload** (delete_index.py → process):
- Major data corrections
- Schema changes
- Clean slate needed

**Incremental upload** (just process new files):
- Adding new sheets
- Adding new projects
- Updating specific sheets (delete_sheet.py → process)

### Embedding Quality

**Good enriched text:**
```
"General Excavation: material... | Apron area | Depth not exceeding 0.25m"
```

**Why it works:**
- Specific context from grandparent
- Category from parent
- Detailed description

**Poor enriched text:**
```
"None | None | Item description"
```

**Why it fails:**
- Missing hierarchical context
- Less semantic meaning
- Harder to disambiguate

### Data Validation

Before uploading, verify:
1. All items have descriptions
2. Parent/grandparent populated where possible
3. Units and rates are numeric
4. Sheet names are consistent
5. No special characters in IDs

## Development

### Customizing Embedding Format

To change enriched text format, edit `json_processor.py`:

```python
# Current format
enriched_text = f"{grandparent} | {parent} | {description}"

# Alternative: Include unit
enriched_text = f"{grandparent} | {parent} | {description} ({unit})"

# Alternative: No separators
enriched_text = f"{grandparent} {parent} {description}"
```

**Note:** Must match format used in rate_filler_pipeline for queries!

### Adding Custom Metadata

Edit `pinecone_uploader.py` to add fields:

```python
metadata = {
    "item_code": item.item_code,
    "description": item.description,
    "custom_field": item.custom_value,  # Add your field
    # ... rest of metadata
}
```

### Testing

```bash
# Test with small dataset
cp ../excel_to_json_pipeline/output/test.json input/
python process_json_to_vectorstore.py

# Query to verify
python query_vectorstore.py "test query"

# Clean up
python delete_sheet.py "test"
```

## Dependencies

Key libraries:
- **openai**: Embedding generation
- **pinecone-client**: Vector database
- **tqdm**: Progress bars
- **pydantic**: Data validation
- **python-dotenv**: Environment variables

All configuration in root `.env` file.

---

**Version**: 2.0  
**Last Updated**: November 14, 2025  
**Status**: Production Ready
