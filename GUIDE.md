# 📘 Almabani Usage Guide

Complete guide for using the Almabani BOQ Management System.

---

## 🚀 Quick Start

### Installation
```bash
# Navigate to project directory
cd /path/to/Almabani

# Install the package (includes all dependencies)
pip install -e .

# Or use virtual environment
.venv/bin/pip install -e .
```

### Environment Setup
Create `.env` file in project root:
```bash
OPENAI_API_KEY=sk-proj-your-key-here
PINECONE_API_KEY=pcsk_your-key-here
PINECONE_INDEX_NAME=almabani
PINECONE_ENVIRONMENT=us-east-1
```

**Optional settings** (with defaults):
```bash
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
SIMILARITY_THRESHOLD=0.7
TOP_K=6
BATCH_SIZE=500
MAX_WORKERS=5
```

---

## 📋 Complete CLI Reference

### Available Commands
```bash
almabani --help                 # Show all commands
almabani parse --help           # Help for specific command
almabani index --help
almabani fill --help
almabani query --help
almabani delete-index --help
almabani delete-sheet --help
almabani version
```

---

## 1️⃣ Parse: Excel → JSON

### Basic Usage
```bash
# Parse all sheets to separate JSON files
almabani parse input.xlsx

# Specify output directory
almabani parse input.xlsx -o data/output

# Parse specific sheets only
almabani parse input.xlsx -s "Terminal,Hilton,Resort Core"

# Parse to single JSON file (all sheets in one)
almabani parse input.xlsx -m single -o data/output/all_sheets.json

# With custom logging
almabani parse input.xlsx -l logs/parse.log
```

### Options
- `INPUT_FILE` - Excel file path (required)
- `-o, --output PATH` - Output directory (default: `data/output`)
- `-m, --mode TEXT` - `single` or `multiple` (default: `multiple`)
- `-s, --sheets TEXT` - Comma-separated sheet names to process
- `-l, --log PATH` - Log file path

### Output
**Multiple mode** (default):
```
data/output/
├── Master_BOQ_Terminal.json
├── Master_BOQ_Hilton.json
└── Master_BOQ_Resort_Core.json
```

**Single mode**:
```
data/output/
└── Master_BOQ.json  # All sheets in one file
```

### JSON Structure
```json
{
  "sheet_name": "Terminal",
  "hierarchy": [
    {
      "level": "1",
      "description": "APRONS",
      "item_type": "numeric_level",
      "children": [
        {
          "level": "c",
          "description": "Granular Base & Sub base",
          "item_type": "subcategory",
          "children": [
            {
              "item_code": "4.2.01",
              "description": "Cement treated base course...",
              "unit": "m²",
              "rate": 125.50,
              "item_type": "item"
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_rows": 542,
    "total_items": 187,
    "header_row": 3
  }
}
```

---

## 2️⃣ Index: JSON → Vector Database

### Basic Usage
```bash
# Index all JSON files from directory
almabani index data/output/

# Index specific files
almabani index data/output/Master_BOQ_Terminal.json

# Index multiple files (glob pattern)
almabani index "data/output/Master_*.json"

# Create index if doesn't exist
almabani index data/output/ --create

# Use custom namespace (for data isolation)
almabani index data/output/ -n production

# Custom batch size
almabani index data/output/ -b 200

# With logging
almabani index data/output/ -l logs/index.log
```

### Options
- `INPUT_PATH` - JSON file or directory (required)
- `-n, --namespace TEXT` - Pinecone namespace (default: empty)
- `-b, --batch-size INT` - Upload batch size (default: 500)
- `-c, --create` - Create index if doesn't exist
- `-l, --log PATH` - Log file path

### What Happens
1. **Loads JSON files** - Reads hierarchical BOQ data
2. **Extracts items** - Traverses hierarchy, extracts leaf items with rates
3. **Builds embedding text** - Format: `"Category: Parent > Child. Description. Unit: m²"`
4. **Generates embeddings** - OpenAI text-embedding-3-small (1536 dimensions)
5. **Uploads to Pinecone** - Batch upload with metadata

### Output Example
```
📊 Vector Store Indexer
Input: data/output
Namespace: default

Processing JSON file: Master_BOQ_Terminal.json
Extracted 187 items from Terminal
Embedding 187 items...
Estimated cost: $0.02 USD
Estimated tokens: 8,450
Uploading to Pinecone... ████████████████████ 100%

✓ Indexing complete!
  • Uploaded: 187 vectors
  • Total in index: 30,542
```

### Vector Metadata Structure
Each vector includes:
```json
{
  "id": "terminal-45",
  "text": "Category: 4.1 - Base > 4.2 - Cement. Cement treated base course. Unit: m²",
  "metadata": {
    "description": "Cement treated base course to PCC apron, thickness 150mm",
    "unit": "m²",
    "rate": 125.50,
    "level": 4,
    "category_path": "4.1 - Base > 4.2 - Cement",
    "sheet_name": "Terminal",
    "parent": "4.2 - Cement Treated Base",
    "grandparent": "4.1 - Granular Base & Sub base",
    "row_number": 45,
    "item_code": "4.2.01"
  }
}
```

---

## 3️⃣ Fill: Auto-Fill Missing Rates

### Basic Usage
```bash
# Fill rates in a specific sheet
almabani fill new_project.xlsx "Terminal"

# Specify output file
almabani fill new_project.xlsx "Terminal" -o filled_output.xlsx

# Use custom namespace
almabani fill new_project.xlsx "Terminal" -n production

# With logging
almabani fill new_project.xlsx "Terminal" -l logs/fill.log
```

### Options
- `INPUT_FILE` - Excel BOQ file (required)
- `SHEET_NAME` - Sheet name to process (required)
- `-o, --output PATH` - Output file path
- `-n, --namespace TEXT` - Pinecone namespace (default: empty)
- `-l, --log PATH` - Log file path

### How It Works - 3-Stage LLM Matching

**For each item missing a rate:**

1. **Build context** - Extract grandparent, parent, description
2. **Search vector DB** - Find top 6 similar items (cosine similarity)
3. **Stage 1: Matcher (Exact)** 
   - GPT checks for IDENTICAL specifications
   - Temperature: 0
   - If exact match → **Green cell** (100% confidence)
   - If no exact match → Stage 2

4. **Stage 2: Expert (Close)**
   - GPT checks for very similar items with minor differences
   - Temperature: 0
   - Confidence: 70-95%
   - If close match → **Yellow cell** (with differences noted)
   - If no close match → Stage 3

5. **Stage 3: Estimator (Approximation)**
   - GPT calculates adjusted rate using scaling logic
   - Temperature: 0
   - Confidence: 50-69%
   - If approximation possible → **Blue cell** (with calculation explanation)
   - If no approximation → **Red cell** (no match)

### Excel Output

**Original columns preserved** + **2 auto-created columns**:

| Level | Item Code | Description | Unit | **Rate** | Trade | Code | **AutoRate Reference** | **AutoRate Reasoning** |
|-------|-----------|-------------|------|----------|-------|------|------------------------|------------------------|
| | 4.2.01 | Cement treated base... | m² | **125.50** | Civil | CTB150 | Terminal-45@125.50 (100%) | Identical specifications and scope |
| | 5.1.03 | Concrete slab... | m³ | **450.00** | Concrete | CS200 | Hilton-78@445.00 (85%) | Very similar, differences: thickness 200mm vs 180mm |
| | 6.2.15 | Steel reinforcement... | kg | **3.80** | Steel | SR12 | Resort-92@4.20 (62%) | Approximation: scaled by diameter ratio (12mm/16mm) = 3.75→3.80 |
| | 7.3.08 | Custom fabrication... | unit | | | | No match found | No sufficiently similar items in database |

**Color Coding:**
- 🟢 **Green** - Exact match (Matcher stage, 100% confidence)
- 🟡 **Yellow** - Close match (Expert stage, 70-95% confidence)
- 🔵 **Blue** - Approximation (Estimator stage, 50-69% confidence)
- 🔴 **Red** - No match found (all stages failed)

### Output Files
```
data/output/
├── new_project_Terminal_filled_20251130_143022.xlsx   # Filled Excel
└── new_project_Terminal_filled_20251130_143022_report.txt  # Statistics
```

### Statistics Report
```
=== PROCESSING REPORT ===
Date: 2025-11-30 14:30:22

Total Items: 542
Processed Items: 187 (items needing rates)

RESULTS:
  Exact Matches (Green): 112 (60%)
  Close Matches (Yellow): 45 (24%)
  Approximations (Blue): 18 (10%)
  No Match (Red): 12 (6%)

SUCCESS RATE: 94% filled automatically

Average Confidence: 87.5%
Processing Time: 8m 32s
```

---

## 4️⃣ Query: Search Vector Database

### Basic Usage
```bash
# Search for items
almabani query "concrete slab 150mm"

# More results
almabani query "excavation" --top-k 20

# Lower similarity threshold (more results)
almabani query "steel reinforcement" --threshold 0.5

# Search in specific namespace
almabani query "concrete" -n production
```

### Options
- `QUERY_TEXT` - Search text (required)
- `--top-k INT` - Number of results (default: 10)
- `--threshold FLOAT` - Similarity threshold (default: 0.7)
- `-n, --namespace TEXT` - Pinecone namespace

### Output Example
```
🔍 Query the vector store for similar items.

Found 5 results:

1. Score: 0.923
   Category: 4.1 - Concrete Works > 4.2 - Slabs. Reinforced concrete slab, thickness 150mm. Unit: m²
   Unit: m²
   Rate: 285.50
   Source: Terminal

2. Score: 0.891
   Category: 5.3 - Structural > 5.4 - Floors. Concrete floor slab 150mm with mesh. Unit: m²
   Unit: m²
   Rate: 292.00
   Source: Hilton

3. Score: 0.867
   Category: 3.2 - Foundations > 3.3 - Base. Concrete base slab 200mm. Unit: m²
   Unit: m²
   Rate: 310.00
   Source: Resort Core
```

---

## 5️⃣ Delete: Index Management

### Delete Specific Sheet
```bash
# Delete all vectors from a sheet (with confirmation)
almabani delete-sheet "Terminal"

# Skip confirmation
almabani delete-sheet "Terminal" --force
```

**Use case:** Re-index updated sheet without duplicates
```bash
almabani delete-sheet "Terminal" --force
almabani index data/output/Master_BOQ_Terminal.json
```

### Delete Entire Index
```bash
# Delete entire index (with confirmation)
almabani delete-index

# Skip confirmation (dangerous!)
almabani delete-index --force
```

**Use case:** Complete rebuild
```bash
almabani delete-index --force
almabani index data/output/ --create
```

---

## 🔄 Complete Workflows

### Initial Setup (One-Time)
```bash
# 1. Parse master BOQ files to JSON
almabani parse data/input/Master_BOQ.xlsx -o data/output

# 2. Create and populate vector database
almabani index data/output/ --create

# 3. Verify index
almabani query "test" --top-k 5
```

### Daily Usage: Fill New BOQ
```bash
# 1. Fill rates for new project
almabani fill data/input/NewProject.xlsx "Terminal" -o data/output

# 2. Check results in Excel (color-coded cells)
# 3. Review report file for statistics
```

### Update Master Data
```bash
# 1. Re-parse updated master file
almabani parse data/input/Master_BOQ_Updated.xlsx -o data/output

# 2. Delete old sheet from index
almabani delete-sheet "Terminal" --force

# 3. Re-index new data
almabani index data/output/Master_BOQ_Updated_Terminal.json

# 4. Verify
almabani query "concrete slab"
```

### Rebuild Everything
```bash
# 1. Delete index
almabani delete-index --force

# 2. Re-parse all Excel files
almabani parse data/input/*.xlsx -o data/output

# 3. Recreate and populate index
almabani index data/output/ --create
```

---

## 🎯 Advanced Features

### Namespaces (Data Isolation)
```bash
# Index to different namespaces
almabani index data/output/master/ -n production
almabani index data/output/test/ -n testing

# Query specific namespace
almabani query "concrete" -n production

# Fill using specific namespace
almabani fill new.xlsx "Sheet1" -n production
```

### Batch Processing
```bash
# Process multiple files with custom batch size
almabani index data/output/*.json -b 200

# Large datasets benefit from bigger batches
# Smaller batches use less memory
```

### Logging
```bash
# Enable detailed logging for debugging
almabani parse input.xlsx -l logs/parse_$(date +%Y%m%d).log
almabani index output/ -l logs/index_$(date +%Y%m%d).log
almabani fill input.xlsx "Sheet" -l logs/fill_$(date +%Y%m%d).log
```

---

## 📊 Performance & Costs

### Typical Processing Times
- **Parse:** ~30 seconds per 500-row sheet
- **Index:** ~2 minutes per 500 items (includes embedding generation)
- **Fill:** ~10 minutes per 500 items (3-stage LLM validation)

### API Costs (Approximate)
- **Embeddings:** $0.02 per 500 items (text-embedding-3-small)
- **LLM Matching:** $0.06 per 500 items (gpt-4o-mini)
- **Total per sheet:** ~$0.08 for 500 items

### Cost Optimization
- Early-return logic: Exact match (Stage 1) skips Stages 2 & 3
- Batch embedding: 500 texts per API call
- Parallel processing: 5 workers for concurrent matching

---

## 🛠️ Troubleshooting

### Common Issues

#### No matches found (too many red cells)
```bash
# Lower similarity threshold
# Edit .env:
SIMILARITY_THRESHOLD=0.5

# Or query to check database
almabani query "test item" --threshold 0.5
```

#### Wrong matches
```bash
# Check what's in the database
almabani query "concrete slab"

# Verify index has correct data
almabani index data/output/ --create  # Recreate if needed
```

#### Pinecone errors
```bash
# Check index exists
almabani query "test"

# If index missing, create it
almabani index data/output/ --create

# Delete and rebuild
almabani delete-index --force
almabani index data/output/ --create
```

#### OpenAI rate limits
```bash
# Reduce batch size
almabani index data/output/ -b 50

# Reduce workers (in .env)
MAX_WORKERS=3
```

#### Excel parsing errors
```bash
# Check logs
almabani parse input.xlsx -l logs/debug.log

# Verify Excel file structure (headers detected correctly)
```

---

## 📁 File Organization

### Recommended Structure
```
Almabani/
├── .env                        # API keys and config
├── data/
│   ├── input/                  # Place Excel files here
│   │   ├── Master_BOQ.xlsx
│   │   └── NewProject.xlsx
│   ├── output/                 # Generated files
│   │   ├── Master_BOQ_Terminal.json
│   │   ├── Master_BOQ_Hilton.json
│   │   ├── NewProject_filled.xlsx
│   │   └── NewProject_report.txt
│   └── logs/                   # Log files
│       ├── parse_20251130.log
│       ├── index_20251130.log
│       └── fill_20251130.log
└── almabani/                   # Source code (don't modify)
```

---

## 🔐 Security Notes

### API Keys
- **Never commit `.env` to git** - already in `.gitignore`
- Use environment-specific keys (dev/production)
- Rotate keys periodically

### Data Privacy
- BOQ data stored locally and in Pinecone
- Use namespaces to isolate client data
- Delete old data: `almabani delete-sheet "SheetName"`

---

## 📚 Additional Resources

### Version Info
```bash
almabani version
# Output: Almabani BOQ Management System
#         Version: 2.0.0
```

### Shell Completion
```bash
# Install completion for your shell
almabani --install-completion

# Show completion script
almabani --show-completion
```

### Python API Usage
If you need programmatic access, import modules directly:
```python
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.vectorstore.indexer import JSONProcessor, VectorStoreIndexer
from almabani.rate_matcher.pipeline import RateFillerPipeline
from almabani.config.settings import get_settings

# Use the classes directly
```

---

## 💡 Tips & Best Practices

1. **Always parse to JSON first** - Index from JSON, not Excel
2. **Use namespaces** - Separate production and test data
3. **Monitor costs** - Check OpenAI usage dashboard
4. **Version control JSON** - Commit generated JSON for reproducibility
5. **Review red cells** - Manual review needed for no-match items
6. **Update master data regularly** - Re-index when rates change
7. **Use logging for debugging** - Helps troubleshoot issues
8. **Backup Pinecone data** - Export vectors periodically

---

## 🎓 Understanding the System

### Data Flow
```
Excel BOQ → Parse → JSON → Index → Pinecone Vector DB
                                         ↓
New BOQ → Fill → Search + 3-Stage LLM → Filled Excel
```

### Hierarchy System
```
1. APRONS (numeric_level)
  └─ c. Granular Base (subcategory)
      └─ 4.2.01 Cement base... (item) ← Has rate, gets embedded
```

### Embedding Text Format
```
"Category: 4.1 - Base > 4.2 - Cement. Cement treated base course, thickness 150mm. Unit: m²"
```

### LLM Matching Stages
1. **Matcher** - Strict exact match, 100% confidence, green
2. **Expert** - Close match with noted differences, 70-95%, yellow
3. **Estimator** - Approximation with rate calculation, 50-69%, blue

---

**That's everything! The complete Almabani system in one guide.** 🚀
