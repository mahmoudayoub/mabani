# Rate Filler Pipeline

Automatically fill missing unit rates in Excel BOQ files using AI-powered semantic search and validation.

## Overview

This pipeline takes Excel BOQ files with missing units/rates, uses semantic search to find similar items from a vector database, validates matches with GPT-5-mini, and fills the missing data with confidence scores and color coding.

## Features

- ✅ **Semantic Search**: Find similar items using OpenAI embeddings + Pinecone
- ✅ **LLM Validation**: GPT validates matches based on 5 comprehensive rules
- ✅ **Hierarchical Context**: Uses grandparent/parent hierarchy for better matching
- ✅ **Smart Filling**: Fills units and/or rates based on what's missing
- ✅ **Color Coding**: Green for matched, red for unmatched cells
- ✅ **Detailed Reports**: Text reports with fill statistics and unmatched items
- ✅ **Preview Mode**: Test queries without API calls (test_query_preview.py)

## Directory Structure

```
rate_filler_pipeline/
├── src/
│   ├── excel_reader.py           # Read Excel & extract hierarchy
│   ├── rate_matcher.py           # Vector search + LLM validation
│   └── excel_writer.py           # Write filled Excel with formatting
├── input/                        # Place Excel files here
├── output/                       # Filled Excel files + reports
├── logs/                         # Processing logs
├── fill_rates.py                 # Core pipeline logic
├── process_single.py             # Process one file
├── process_folder.py             # Process all files in input/
└── requirements.txt              # Dependencies
```

## Installation

```bash
# From project root
pip install -r requirements.txt
```

## Configuration

Create `.env` file in `rate_filler_pipeline/` directory:

```bash
# OpenAI API Key (for embeddings and GPT validation)
OPENAI_API_KEY=sk-...

# Pinecone API Key (for vector search)
PINECONE_API_KEY=pc-...
```

## Usage

### Process Single File

```bash
cd rate_filler_pipeline
python process_single.py "your_file.xlsx" "Sheet Name"

# Example
python process_single.py "Book_2.xlsx" "9-PA"
```

### Process All Files

```bash
# Processes all .xlsx files in input/ folder
python process_folder.py
```

### Preview Queries (No API Calls)

```bash
# Test what queries will be sent (saves $$)
cd ..
python test_query_preview.py input/Book_2.xlsx "9-PA" 10
```

## How It Works

### 1. Read Excel & Extract Hierarchy

For each item row (empty Level, has Item code):
- Extracts: description, unit, rate
- Builds hierarchy from c-levels (same logic as excel_to_json_pipeline)
- Tracks grandparent and parent for context

### 2. Semantic Search (Vector Search)

For items missing unit or rate:
```python
# Query format (matches embedding format)
query = "[grandparent] | [parent] | [description]"

# Search Pinecone
results = index.query(
    embedding=query_embedding,
    top_k=6,
    include_metadata=True,
    filter={"similarity": {"$gte": 0.7}}  # Threshold
)
```

### 3. LLM Validation (GPT-5-mini)

Top 6 candidates sent to GPT with 5 matching rules:

**Matching Rules:**
1. **Core Identity**: Same thing, different wording OK
2. **Specifications**: Critical details must align (thickness, grade, capacity)
3. **Scope of Work**: Must be equivalent (supply vs supply+install matters)
4. **Units**: Must be compatible (m2 vs m3 incompatible)
5. **Hierarchical Context**: Should be in same domain

**LLM Response:**
```json
{
  "is_match": true,
  "confidence": 0.92,
  "explanation": "Both are cement treated base course, same thickness..."
}
```

### 4. Fill Excel & Format

- **Green cells**: Successfully matched (confidence > threshold)
- **Red cells**: No match found
- Original formatting preserved
- Report generated with statistics

## Configuration Options

### In `fill_rates.py`

```python
# Similarity threshold (0.0 to 1.0)
similarity_threshold = 0.7  # Lower = more candidates

# Top-K candidates for LLM
top_k = 6

# GPT model
model = "gpt-4o-mini"  # or "gpt-4o"

# Match confidence threshold
confidence_threshold = 0.7  # For accepting LLM match
```

### Column Detection

Pipeline auto-detects columns by looking for:
- **Level**: First unnamed column
- **Item**: Second unnamed column  
- **Description**: Third unnamed column
- **Unit**: Fourth unnamed column
- **Pricing**: Column named "Pricing"

Customize in `excel_reader.py` if needed.

## Output

### Filled Excel File

`output/{filename}_filled_{timestamp}.xlsx`

- ✅ Green cells: Matched and filled
- ❌ Red cells: No match found
- 📝 Original formatting preserved
- 🔢 All formulas maintained

### Text Report

`output/{filename}_filled_{timestamp}_report.txt`

```
================================================================================
RATE FILLING REPORT
================================================================================

File: Book_2.xlsx
Sheet: 9-PA
Date: 2025-11-10 14:30:00

Summary:
--------
Total items processed: 562
Items filled: 470
Items not filled: 92
Fill rate: 83.6%

Top Unmatched Items:
--------------------
Row 45: "Specific item that couldn't be matched"
  Reason: No similar items found above threshold
  Top candidate: "..." (similarity: 0.65)
...
```

## Hierarchy Matching Logic

**Same as excel_to_json_pipeline:**

When consecutive c-levels appear:
1. First c followed by second c → Clear stack, add first
2. Second c followed by items → Add to stack
3. Items get: grandparent=first_c, parent=second_c

**Example:**
```
c | 3.1 - General Excavation
c | General Excavation: material...
c | Apron area
  | 3.1.02 | Depth not exceeding 0.25m

Hierarchy for item 3.1.02:
- Grandparent: "General Excavation: material..."
- Parent: "Apron area"
- Description: "Depth not exceeding 0.25m"

Embedding query:
"General Excavation: material... | Apron area | Depth not exceeding 0.25m"
```

## Costs

Approximate costs for 500-item BOQ:

- **Embeddings**: 500 queries × $0.00002 = $0.01
- **GPT-4o-mini**: 500 validations × $0.0001 = $0.05
- **Total**: ~$0.06 per sheet

Using `test_query_preview.py` helps minimize costs during testing.

## Performance

Typical processing for 500 items:
- **Read Excel**: <1 second
- **Vector Search**: ~2-3 minutes (rate limited)
- **LLM Validation**: ~3-5 minutes (rate limited)
- **Write Excel**: <1 second
- **Total**: ~5-10 minutes

## Troubleshooting

**No matches found?**
- Lower `similarity_threshold` (try 0.6 or 0.65)
- Check that vector database is populated (`json_to_vectorstore`)
- Verify embedding format matches (no labels, just `[gp] | [p] | [desc]`)

**Wrong matches?**
- Increase `confidence_threshold` (try 0.8 or 0.9)
- Review LLM matching rules in `rate_matcher.py`
- Check that hierarchy is extracted correctly (use preview script)

**Hierarchy incorrect?**
- Verify c-levels are marked with "c" in Level column
- Check for empty rows between c-levels (auto-skipped)
- Review logs for hierarchy decisions

**API rate limits?**
- Pipeline includes automatic rate limiting
- Increase delays in `rate_matcher.py` if needed
- Consider upgrading OpenAI plan for higher limits

**Excel formatting lost?**
- Only matched cells are colored (green/red)
- All other formatting is preserved
- Check `excel_writer.py` if issues persist

## Next Steps

After filling rates:
1. **Review** output Excel file
2. **Check** red cells in report
3. **Manual fill** remaining items if needed
4. **Re-run** with adjusted thresholds if needed

## Utilities

### test_query_preview.py (Root)

Preview what will be sent to APIs without making calls:

```bash
# From root directory
python test_query_preview.py input/Book_2.xlsx "9-PA" 15

# Shows:
# - Hierarchy for each item
# - Embedding query format
# - LLM prompt format
# - No API calls = no cost
```
