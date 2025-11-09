# Almabani BOQ System - Complete Usage Guide

## System Overview

Three independent pipelines that work sequentially:
1. **Excel → JSON** (Structure preservation)
2. **JSON → Vector Database** (Semantic search setup)
3. **Auto-fill Rates** (AI-powered matching)

---

## Pipeline 1: Excel to JSON

### Purpose
Convert Excel BOQ files into structured JSON with hierarchy preservation.

### Location
```bash
cd /home/ali/Desktop/Almabani/excel_to_json_pipeline
```

### Input Requirements
- **Location:** `excel_to_json_pipeline/input/`
- **Format:** Excel files (`.xlsx`)
- **Required columns:**
  - `Level` (1, 2, 3, or c)
  - `Item` (item code)
  - `Bill description` (text description)
  - `Unit` (m2, m3, ton, etc.)
  - `Rate` (numeric or empty)

### How to Run
```bash
cd excel_to_json_pipeline
python process_separate_sheets.py
```

### Output
- **Location:** `excel_to_json_pipeline/output/`
- **Format:** JSON files (one per Excel sheet)
- **Naming:** `{filename}_{sheetname}.json`
- **Structure:**
```json
{
  "source_file": "example.xlsx",
  "source_sheet": "Sheet1",
  "hierarchy": [
    {
      "level": 1,
      "code": "1",
      "description": "Main Category",
      "children": [
        {
          "level": 2,
          "code": "1.1",
          "description": "Sub Category",
          "children": [
            {
              "level": 3,
              "code": "1.1.1",
              "description": "Concrete C40",
              "unit": "m3",
              "rate": 450.0
            }
          ]
        }
      ]
    }
  ]
}
```

### What It Does
1. Reads all Excel files from `input/`
2. Processes each sheet separately
3. Builds hierarchical structure (Level 1 → 2 → 3)
4. Flattens level "c" items into level 3
5. Saves one JSON file per sheet
6. Logs everything to `logs/`

### Notes
- Original Excel files are NOT modified
- Empty rows are skipped
- Invalid data is logged and skipped
- Level "c" becomes level 3 automatically

---

## Pipeline 2: JSON to Vector Database

### Purpose
Extract items from JSON, generate embeddings, upload to Pinecone for semantic search.

### Location
```bash
cd /home/ali/Desktop/Almabani/json_to_vectorstore
```

### Prerequisites
- Pipeline 1 completed (JSON files exist)
- OpenAI API key in `.env`
- Pinecone API key in `.env`

### Input Requirements
- **Location:** `json_to_vectorstore/input/` OR auto-detect from `excel_to_json_pipeline/output/`
- **Format:** JSON files from Pipeline 1

### How to Run

#### Option A: First Time (or add to existing)
```bash
cd json_to_vectorstore
# Copy JSON files to input/ or they'll be auto-detected
python prepare_and_upload.py
```

**Behavior:** ADDS to existing Pinecone index (appends new data)

#### Option B: Complete Refresh (delete all & rebuild)
```bash
cd json_to_vectorstore
python delete_and_reprocess.py
```

**Behavior:** 
1. Deletes entire Pinecone index
2. Finds ALL JSON from `excel_to_json_pipeline/output/`
3. Processes everything from scratch
4. Creates fresh index

#### Option C: Just Delete Index
```bash
cd json_to_vectorstore
python delete_index.py
```

**Behavior:** Only deletes Pinecone index, no processing

### Output

#### 1. JSONL File
- **Location:** `json_to_vectorstore/output/`
- **Naming:** `vectorstore_items_{timestamp}.jsonl`
- **Format:** One item per line
```json
{"id": "Sheet1__1.1.1", "text": "Concrete C40", "metadata": {"item_code": "1.1.1", "description": "Concrete C40", "unit": "m3", "rate": 450.0, "source_sheet": "Sheet1"}}
{"id": "Sheet1__1.1.2", "text": "Steel reinforcement", "metadata": {"item_code": "1.1.2", "description": "Steel reinforcement", "unit": "ton", "rate": 2500.0, "source_sheet": "Sheet1"}}
```

#### 2. Pinecone Index
- **Index name:** `almabani`
- **Dimensions:** 1536
- **Metric:** Cosine similarity
- **Contains:** All items as searchable vectors

### What It Does
1. Reads JSON files (hierarchical)
2. Flattens hierarchy → extracts individual items
3. Creates text representation for each item
4. Generates embeddings via OpenAI (text-embedding-3-small)
5. Uploads vectors to Pinecone with metadata
6. Exports JSONL for backup

### API Costs
- **OpenAI Embeddings:** ~$0.00001 per item
- **Example:** 10,000 items = ~$0.10 USD

### Notes
- Progress bars show real-time status
- Batch processing (100 items at a time)
- Confirmation prompts before API calls
- IDs are sanitized to ASCII only

---

## Pipeline 3: Rate Filler (Auto-fill Missing Rates)

### Purpose
Use AI to find matching items from database and auto-fill missing rates in Excel.

### Location
```bash
cd /home/ali/Desktop/Almabani
```

**IMPORTANT:** Must run from `/home/ali/Desktop/Almabani` (root directory)

### Prerequisites
- Pipeline 2 completed (Pinecone database populated)
- OpenAI API key in `.env`
- Pinecone API key in `.env`
- Vector database has data

### Input Requirements
- **Location:** `rate_filler_pipeline/input/`
- **Format:** Excel files (`.xlsx`)
- **Columns needed:** Auto-detected, but should include:
  - Item/Code column
  - Description column
  - Unit column
  - Rate column (the one to fill)

**Auto-detection handles:**
- Header row location (scans first 10 rows)
- Column name variations ("Rate" vs "Unit rate")
- Different Excel structures

### How to Run

#### Option A: Single File
```bash
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_single filename.xlsx
```

**Input:** Looks for file in `rate_filler_pipeline/input/filename.xlsx`

#### Option B: All Files in Input Folder
```bash
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_folder
```

**Input:** Processes ALL `.xlsx` files in `rate_filler_pipeline/input/`

#### Option C: Custom (Python API)
```python
from rate_filler_pipeline.fill_rates import run_pipeline

output = run_pipeline(
    input_excel="/full/path/to/file.xlsx",
    output_excel="/full/path/to/output.xlsx",  # Optional
    similarity_threshold=0.76,  # 0.0-1.0 (higher = stricter)
    top_k=6                     # Number of candidates to check
)
print(f"Output: {output}")
```

### Output

#### 1. Excel File
- **Location:** `rate_filler_pipeline/output/`
- **Naming:** `{original_name}_filled_{timestamp}.xlsx`
- **Features:**
  - ✅ **Green cells** = Successfully filled rates
  - ❌ **Red cells** = No match found (empty)
  - Same structure as input
  - Only missing rates are modified

#### 2. Text Report
- **Location:** `rate_filler_pipeline/output/`
- **Naming:** `{original_name}_report_{timestamp}.txt`
- **Contains:**
```
RATE FILLING REPORT
===================

Summary:
--------
Total items needing rates: 417
Items filled: 156 (37.4%)
Items not filled: 261 (62.6%)

Details:
--------
Row 10: ✓ FILLED
  Description: General Clearance
  Unit: ha @ 176,697.38 SAR
  Match source: Candy Jobs for UR Allocation Tool.xlsx (Sheet1)
  Reasoning: Exact match - same scope and specifications

Row 15: ✗ NOT FILLED
  Description: Double handling excavated material
  Reasoning: No candidates above similarity threshold (0.76)
```

### What It Does
1. **Read Excel:** Auto-detect headers, find items with missing rates
2. **Vector Search:** For each item, search Pinecone for top-K similar items
3. **LLM Validation:** GPT-4o-mini checks if candidates are exact matches
4. **Fill Rates:** Calculate average rate from validated matches
5. **Write Output:** Color-coded Excel + detailed report

### Matching Process

**Step 1: Vector Search**
- Converts item description to embedding
- Searches Pinecone for top-K similar items (default: 6)
- Filters by similarity threshold (default: 0.76)

**Step 2: LLM Validation**
- Sends candidates to GPT-4o-mini
- Checks for EXACT match criteria:
  - ✅ Same construction work (wording can differ)
  - ✅ Same specifications (materials, dimensions)
  - ✅ Same scope (supply vs install)
  - ✅ Compatible units

**Step 3: Rate Calculation**
- If matches found: Average of all matched rates
- If no matches: Leave empty (red cell)

### Settings

**Similarity Threshold (0.0 - 1.0):**
- `0.76` (default) = Balanced (recommended)
- `0.85+` = Very strict (fewer matches, higher accuracy)
- `0.60-0.75` = Looser (more matches, check carefully)

**Top-K (number of candidates):**
- `6` (default) = Good coverage
- `10+` = More options but slower
- `3-5` = Faster but might miss matches

### API Costs per Item
- **Embedding:** ~$0.00001 (1 API call)
- **LLM validation:** ~$0.0001 (only if candidates found)
- **Example:** 100 items with 30% matches = ~$0.004 USD

### Notes
- Only processes items with missing rates
- Original file is NEVER modified
- Safe to interrupt (no partial writes)
- All API calls are logged
- Progress bar shows real-time status

---

## Complete Workflow Example

### First Time Setup (Build Database)

```bash
# 1. Place Excel files in input
cp my_boq.xlsx /home/ali/Desktop/Almabani/excel_to_json_pipeline/input/

# 2. Convert to JSON
cd /home/ali/Desktop/Almabani/excel_to_json_pipeline
python process_separate_sheets.py

# 3. Upload to vector database
cd /home/ali/Desktop/Almabani/json_to_vectorstore
python delete_and_reprocess.py  # Fresh start
# OR
python prepare_and_upload.py    # If adding to existing
```

### Daily Use (Fill Rates)

```bash
# 1. Place file to process
cp new_file.xlsx /home/ali/Desktop/Almabani/rate_filler_pipeline/input/

# 2. Run rate filler
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_single new_file.xlsx

# 3. Get results
ls rate_filler_pipeline/output/
# → new_file_filled_20251108_123456.xlsx
# → new_file_report_20251108_123456.txt
```

### Adding New BOQ to Database

```bash
# 1. Convert new Excel to JSON
cd /home/ali/Desktop/Almabani/excel_to_json_pipeline
cp new_boq.xlsx input/
python process_separate_sheets.py

# 2. Add to vector database
cd /home/ali/Desktop/Almabani/json_to_vectorstore
python prepare_and_upload.py  # Adds to existing database
```

---

## Troubleshooting

### Pipeline 1 Issues
**Problem:** "No Excel files found"
- Check: Files are in `excel_to_json_pipeline/input/`
- Check: Files have `.xlsx` extension

**Problem:** "Column not found"
- Check: Excel has required columns (Level, Item, Bill description, Unit, Rate)
- Edit: `config/settings.yaml` to match your column names

### Pipeline 2 Issues
**Problem:** "OPENAI_API_KEY not found"
- Check: `.env` file exists in `json_to_vectorstore/`
- Check: Contains `OPENAI_API_KEY=sk-...`

**Problem:** "No JSON files found"
- Check: Pipeline 1 completed successfully
- Check: JSON files exist in `excel_to_json_pipeline/output/`

**Problem:** "Duplicate items"
- Solution: Run `python delete_and_reprocess.py` for fresh start

### Pipeline 3 Issues
**Problem:** "ModuleNotFoundError"
- Check: Running from `/home/ali/Desktop/Almabani` (root directory)
- Command: `python -m rate_filler_pipeline.process_single file.xlsx`

**Problem:** "Found 0 items"
- Check: Excel file has items with missing rates
- Check: Columns are detected correctly (see logs)

**Problem:** "No candidates found"
- Reason: Item is too unique or different from database
- Solution: Lower similarity threshold or add more data to database

---

## Quick Reference

| Pipeline | Command | Input | Output |
|----------|---------|-------|--------|
| **1. Excel→JSON** | `cd excel_to_json_pipeline && python process_separate_sheets.py` | `input/*.xlsx` | `output/*.json` |
| **2. JSON→Vector** | `cd json_to_vectorstore && python prepare_and_upload.py` | `input/*.json` | Pinecone + `output/*.jsonl` |
| **2. Delete & Refresh** | `cd json_to_vectorstore && python delete_and_reprocess.py` | All JSON from Pipeline 1 | Fresh Pinecone index |
| **3. Fill Rates (Single)** | `cd /home/ali/Desktop/Almabani && python -m rate_filler_pipeline.process_single file.xlsx` | `rate_filler_pipeline/input/file.xlsx` | `rate_filler_pipeline/output/file_filled_*.xlsx` |
| **3. Fill Rates (Batch)** | `cd /home/ali/Desktop/Almabani && python -m rate_filler_pipeline.process_folder` | `rate_filler_pipeline/input/*.xlsx` | `rate_filler_pipeline/output/*_filled_*.xlsx` |

---

## File Locations Summary

```
/home/ali/Desktop/Almabani/
│
├── excel_to_json_pipeline/
│   ├── input/              ← PUT: Excel files here
│   └── output/             ← GET: JSON files here
│
├── json_to_vectorstore/
│   ├── input/              ← PUT: JSON files here (optional)
│   └── output/             ← GET: JSONL backup here
│
└── rate_filler_pipeline/
    ├── input/              ← PUT: Excel to fill here
    └── output/             ← GET: Filled Excel + reports here
```
