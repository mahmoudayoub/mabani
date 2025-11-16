# JSON to Vector Store Pipeline

Extract items from JSON BOQ files, generate enriched embeddings with hierarchical context, and upload to Pinecone vector database for semantic search.

## Overview

This pipeline processes JSON files from the `excel_to_json_pipeline`, extracts items with hierarchical context (grandparent, parent, description), generates OpenAI embeddings, and uploads them to Pinecone for semantic search. The embeddings include enriched text to improve search quality.

## Features

- ✅ **Hierarchical Context**: Embeddings include grandparent, parent, and item description
- ✅ **Enriched Embeddings**: Format: `[grandparent] | [parent] | [description]`
- ✅ **Batch Processing**: Efficient embedding generation with rate limiting
- ✅ **Metadata Storage**: Full item details stored in Pinecone for retrieval
- ✅ **Progress Tracking**: Real-time progress bars with tqdm
- ✅ **Error Handling**: Robust error handling with retry logic
- ✅ **Export Support**: Generates JSONL files for backup/analysis
- ✅ **Sheet Tracking**: Stores sheet name in metadata for filtering
- ✅ **Utilities**: Delete index, delete specific sheets, query testing

## Directory Structure

```
json_to_vectorstore/
├── src/
│   ├── json_processor.py         # Extract & enrich items from JSON
│   ├── embeddings_generator.py   # Generate OpenAI embeddings
│   ├── pinecone_uploader.py      # Upload to Pinecone
│   ├── exporter.py               # Export to JSONL
│   ├── models.py                 # Data models
│   └── pipeline.py               # Main orchestration
├── input/                        # Place JSON files here (from excel_to_json_pipeline)
├── output/                       # JSONL exports
├── logs/                         # Processing logs
├── process_json_to_vectorstore.py # Main entry point
├── delete_index.py               # Utility: Delete entire Pinecone index
├── delete_sheet.py               # Utility: Delete specific sheet from index
├── query_vectorstore.py          # Utility: Test vector search queries
└── requirements.txt              # Dependencies
```

## Installation

```bash
# Install dependencies
pip install -r json_to_vectorstore/requirements.txt
```

## Configuration

Set environment variables in `.env` (at project root):

```bash
OPENAI_API_KEY=your_openai_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment  # e.g., us-east-1
```

## Usage

### 1. Prepare Input Files

Place JSON files from `excel_to_json_pipeline/output/` into `json_to_vectorstore/input/`:

```bash
cp excel_to_json_pipeline/output/*.json json_to_vectorstore/input/
```

### 2. Run the Pipeline

```bash
cd json_to_vectorstore
python process_json_to_vectorstore.py
```

**What happens:**
1. Reads all JSON files from `input/`
2. Extracts items with hierarchical context
3. Generates enriched embeddings: `[grandparent] | [parent] | [description]`
4. Uploads to Pinecone with metadata (sheet name, hierarchy, rates, units)
5. Exports to JSONL in `output/`
6. Logs progress to `logs/`

### 3. Verify Upload

The pipeline will show:
- Number of JSON files processed
- Total items extracted
- Embedding generation progress
- Pinecone upload progress
- Export file location

## Utilities

### Delete Entire Index

**⚠️ Warning: This deletes ALL data from Pinecone!**

```bash
cd json_to_vectorstore
python delete_index.py
```

### Delete Specific Sheet

Remove data for a specific sheet from the index:

```bash
cd json_to_vectorstore
python delete_sheet.py
```

**Interactive prompts:**
1. Enter sheet name to delete (e.g., "1-Master_no_ur")
2. Confirms deletion count

**Use cases:**
- Sheet data was corrupted
- Need to remove outdated data before re-uploading
- Want to clean up specific sheet without affecting others

**Note:** After deleting a sheet, you can re-run `process_json_to_vectorstore.py` with the updated JSON file to upload fresh data.

## Core Logic

### 1. JSON Processing (`json_processor.py`)

**Extracts items from hierarchical JSON:**

```python
{
  "description": "GRANDPARENT",
  "children": [
    {
      "description": "PARENT",
      "children": [
        {
          "description": "Item description",
          "unit_rate": 150.0,
          "unit": "m²",
          "qty": 100
        }
      ]
    }
  ]
}
```

**Flattens to:**

```python
{
  "grandparent": "GRANDPARENT",
  "parent": "PARENT",
  "description": "Item description",
  "unit_rate": 150.0,
  "unit": "m²",
  "qty": 100,
  "sheet_name": "1-Master_no_ur"
}
```

### 2. Embedding Generation (`embeddings_generator.py`)

**Enriched text format:**

```
GRANDPARENT | PARENT | Item description
```

**Why?**
- Improves semantic search accuracy
- Provides hierarchical context for better matches
- Helps LLM understand item relationships

**Configuration:**
- Model: `text-embedding-3-small`
- Dimensions: 1536
- Batch size: 100 items
- Rate limiting: Built-in retry logic

### 3. Pinecone Upload (`pinecone_uploader.py`)

**Vector structure:**

```python
{
  "id": "ascii_safe_unique_id",
  "values": [0.123, -0.456, ...],  # 1536-dimensional embedding
  "metadata": {
    "source_sheet": "1-Master_no_ur",
    "grandparent": "GRANDPARENT",
    "parent": "PARENT",
    "description": "Item description",
    "rate": 150.0,
    "unit": "m²",
    "item_code": "A1",
    "category_path": "Level 1 > Level 2",
    "level": 1,
    "row_number": 10
  }
}
```

**Index configuration:**
- Name: `almabani` (configurable via PINECONE_INDEX_NAME env variable)
- Metric: `cosine`
- Dimensions: 1536
- Cloud: Serverless (AWS us-east-1)

**Batch upload:**
- Batch size: 100 vectors
- Progress tracking with tqdm
- Automatic retry on failure

### 4. Export (`exporter.py`)

Generates JSONL backup with timestamp:

```
output/vectorstore_items_YYYYMMDD_HHMMSS.jsonl
```

**Each line:**

```json
{"id": "...", "text": "...", "metadata": {...}, "embedding": [...]}
```

## Integration with Other Pipelines

### Input: excel_to_json_pipeline

**Required JSON format:**

```json
{
  "description": "Level 1",
  "children": [
    {
      "description": "Level 2",
      "children": [
        {
          "description": "Actual item",
          "unit_rate": 100.0,
          "unit": "m²",
          "qty": 50
        }
      ]
    }
  ]
}
```

**Sheet name extraction:**
- From filename: `Book1_1-Master.json` → `"1-Master"`
- Stored in metadata for filtering

### Output: rate_filler_pipeline

**Pinecone index used for:**
- Semantic search to find similar items
- Retrieve unit rates for matching descriptions
- Filter by sheet name if needed

**Query example:**

```python
index.query(
    vector=embedding,
    top_k=5,
    include_metadata=True,
    filter={"source_sheet": "1-Master_no_ur"}
)
```

## Error Handling

### Common Issues

**1. OpenAI API Errors**
- **RateLimitError**: Automatic retry with exponential backoff
- **InvalidRequestError**: Check API key and model name
- **Solution**: Ensure `OPENAI_API_KEY` is valid

**2. Pinecone Errors**
- **ApiException**: Check API key and environment
- **IndexNotFoundError**: Index will be auto-created if missing
- **Solution**: Verify `PINECONE_API_KEY` and `PINECONE_ENVIRONMENT`

**3. JSON Parse Errors**
- **JSONDecodeError**: Invalid JSON file
- **Solution**: Verify input files are valid JSON from excel_to_json_pipeline

**4. Missing Files**
- **FileNotFoundError**: No JSON files in `input/`
- **Solution**: Copy files from excel_to_json_pipeline/output/

## Logs

All operations are logged to `logs/`:

```
logs/json_to_vectorstore_YYYYMMDD_HHMMSS.log
```

**Log levels:**
- `INFO`: Normal operation (file processing, upload progress)
- `WARNING`: Recoverable issues (retries, empty files)
- `ERROR`: Fatal errors (API failures, invalid data)

## Testing

### Verify Embeddings

Check output JSONL file:

```bash
head -n 1 output/vectorstore_items_*.jsonl | python -m json.tool
```

### Test Vector Search

Use rate_filler_pipeline to query:

```bash
cd ../rate_filler_pipeline
python -c "
from src.rate_matcher import RateMatcher
matcher = RateMatcher()
results = matcher.find_matches('Concrete foundation', parent='Foundation Works', grandparent='Structural')
if results['status'] == 'filled':
    match = results['best_match']
    print(f\"Match: {match['description']} - Rate: {match['rate']} {match['unit']}\")
    print(f\"Confidence: {results.get('confidence', 'N/A')}\")
"
```

## Performance

**Typical processing times:**

| Items | Embedding | Upload | Total |
|-------|-----------|--------|-------|
| 100   | 5s        | 2s     | ~10s  |
| 1000  | 45s       | 15s    | ~70s  |
| 5000  | 4m        | 1m     | ~6m   |

**Optimization:**
- Batch size: 100 items (optimal for OpenAI API)
- Parallel uploads: Not implemented (Pinecone handles internally)
- Rate limiting: Automatic retry with exponential backoff

## Troubleshooting

### No Items Extracted

**Symptom:** "No items found in JSON files"

**Causes:**
1. JSON files don't have `children` arrays
2. Files are empty or corrupted
3. Wrong directory structure

**Solution:**
1. Verify JSON structure matches expected format
2. Check `input/` directory has `.json` files
3. Review logs for parse errors

### Upload Fails

**Symptom:** "Failed to upload to Pinecone"

**Causes:**
1. Invalid API credentials
2. Network issues
3. Index quota exceeded

**Solution:**
1. Verify `.env` has correct `PINECONE_API_KEY`
2. Check internet connection
3. Login to Pinecone console and verify index status

### Duplicate Vectors

**Symptom:** Items appear multiple times in search results

**Causes:**
1. Running pipeline multiple times without deleting old data
2. Processing same JSON file twice

**Solution:**
1. Use `delete_index.py` to clear all data
2. Use `delete_and_reprocess.py` to replace specific sheet
3. Check input directory for duplicate files

## Dependencies

```
openai>=1.0.0
pinecone-client>=2.0.0
python-dotenv>=0.19.0
tqdm>=4.62.0
```

## Future Enhancements

- [ ] Support for multiple Pinecone indexes
- [ ] Parallel embedding generation
- [ ] Delta updates (only process changed items)
- [ ] Custom embedding models
- [ ] Advanced metadata filtering
- [ ] Embedding dimension tuning

## Support

For issues or questions:
1. Check logs in `logs/`
2. Verify `.env` configuration
3. Review this README
4. Check related pipelines (excel_to_json_pipeline, rate_filler_pipeline)

## Excel Configuration

### Configuration File Example

```yaml
excel:
  level_column_index: 0      
  item_column_index: 1       
  description_column_index: 2 
  unit_column_index: 3       
  rate_column_index: 4       
  data_start_row: 1          
  skip_empty_rows: true      

hierarchy:
  subcategory_indicator: "c"           
  numeric_level_pattern: "^[0-9]+$"    
  item_pattern: "^[A-Za-z0-9]+.*$"     

output:
  indent: 2                  
  ensure_ascii: false        
```

### Configuration Options

- **excel**: Mapping of Excel columns to JSON fields
  - `level_column_index`: Column index for level (0-based)
  - `item_column_index`: Column index for item code
  - `description_column_index`: Column index for description
  - `unit_column_index`: Column index for unit
  - `rate_column_index`: Column index for rate
  - `data_start_row`: Row number to start reading data (1-based)
  - `skip_empty_rows`: Skip rows where item code or description is empty

- **hierarchy**: Hierarchical structure settings
  - `subcategory_indicator`: Character indicating a subcategory (e.g., "c" for "Concrete")
  - `numeric_level_pattern`: Regex pattern for numeric levels
  - `item_pattern`: Regex pattern for identifying items

- **output**: JSON output formatting options
  - `indent`: Number of spaces for indentation
  - `ensure_ascii`: Ensure ASCII encoding (set to `false` for UTF-8)
