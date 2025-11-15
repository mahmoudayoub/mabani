# Rate Filler Pipeline

Automatically fill missing unit rates in Excel BOQ files using AI-powered semantic search and 3-stage LLM validation.

## Overview

This pipeline takes Excel BOQ files with missing units/rates, uses semantic search to find similar items from a vector database, validates matches through a sophisticated 3-stage LLM process, and fills the missing data with confidence scores and color coding.

## Features

- ✅ **Semantic Search**: Find similar items using OpenAI embeddings + Pinecone
- ✅ **3-Stage LLM Validation**: Sequential matching with specialized prompts
  - **Stage 1 (Matcher)**: Strict exact match detection
  - **Stage 2 (Expert)**: Close matches with minor differences (70-95% confidence)
  - **Stage 3 (Estimator)**: Approximations for cost estimation (50-69% confidence)
- ✅ **Hierarchical Context**: Uses grandparent/parent hierarchy for better matching
- ✅ **Smart Filling**: Fills units and/or rates based on what's missing
- ✅ **Color Coding**: Green (exact), Yellow (close), Blue (approximation), Red (no match)
- ✅ **Detailed Reports**: Text reports with stage info, confidence scores, and adjustment guidance
- ✅ **Auto-Created Columns**: Reference and Reasoning columns auto-added to Excel

## Directory Structure

```
rate_filler_pipeline/
├── src/
│   ├── excel_reader.py           # Read Excel & extract hierarchy
│   ├── rate_matcher.py           # Vector search + 3-stage LLM validation
│   ├── excel_writer.py           # Write filled Excel with formatting
│   └── prompts.py                # LLM prompts for 3 stages (Matcher/Expert/Estimator)
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

All configuration is in the root `.env` file at `/Almabani/.env`:

```bash
# OpenAI API Key (for embeddings and GPT validation)
OPENAI_API_KEY=sk-...

# Pinecone API Key (for vector search)
PINECONE_API_KEY=pc-...
```

**Note**: The project now uses a single `.env` file in the root directory instead of separate files in each pipeline.

## Usage

### Process Single File

```bash
cd rate_filler_pipeline
python process_single.py "your_file.xlsx" "Sheet Name"

# Example
python process_single.py "Book_2.xlsx" "9-PA"

# Optional parameters
python process_single.py "Book_2.xlsx" "9-PA" --threshold 0.5 --top-k 10
```

### Process All Files

```bash
# Processes all .xlsx files in input/ folder
python process_folder.py

# Shows progress for each file and sheet
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
    filter={"similarity": {"$gte": 0.5}}  # Default threshold
)
```

### 3. Three-Stage LLM Validation

The pipeline uses a sophisticated 3-stage sequential approach with specialized LLM prompts:

#### **Stage 1: MATCHER** (Exact Matches Only)
- **Role**: Strict exact match detector
- **Model**: gpt-4o-mini, temperature=0
- **Prompt**: Very strict - "EXACTLY the same with IDENTICAL specifications"
- **Output**: 
  - If exact match found → **Returns immediately** (Green cells, 100% confidence)
  - If no exact match → Proceeds to Stage 2
- **Benefits**: Skips expensive Expert/Estimator calls when exact match exists

#### **Stage 2: EXPERT** (Close Matches)
- **Role**: Find very similar items with minor, acceptable differences
- **Model**: gpt-4o-mini, temperature=0
- **Prompt**: Realistic - "VERY SIMILAR with only minor differences"
- **Confidence Range**: 70-95%
- **Output**: 
  - If close match found → **Returns with differences noted** (Yellow cells)
  - Includes "differences" field explaining variations
  - If no close match → Proceeds to Stage 3

#### **Stage 3: ESTIMATOR** (Approximations)
- **Role**: Find items suitable for cost approximation
- **Model**: gpt-4o-mini, temperature=0
- **Prompt**: Practical - "can be used for COST APPROXIMATION"
- **Confidence Range**: 50-69%
- **Output**: 
  - If approximation possible → **Returns with adjustment guidance** (Blue cells)
  - Includes "adjustment" field with scaling/modification instructions
  - Includes "limitations" field with warnings
  - If no approximation possible → Returns NO_MATCH (Red cells)

### Sequential Flow Diagram

```
Item needs filling
    ↓
Vector Search (top 6 candidates)
    ↓
┌─────────────────────────────────────┐
│  Stage 1: MATCHER (Exact)           │
│  - Very strict validation           │
│  - 100% confidence                  │
└─────────────────────────────────────┘
    ↓
Exact match? ──YES──→ ✓ Fill (Green) ← DONE
    │
    NO
    ↓
┌─────────────────────────────────────┐
│  Stage 2: EXPERT (Close)            │
│  - Realistic similarity check       │
│  - 70-95% confidence                │
│  - Notes differences                │
└─────────────────────────────────────┘
    ↓
Close match? ──YES──→ ≈ Fill (Yellow) ← DONE
    │
    NO
    ↓
┌─────────────────────────────────────┐
│  Stage 3: ESTIMATOR (Approximation) │
│  - Practical approximation check    │
│  - 50-69% confidence                │
│  - Provides adjustment guidance     │
└─────────────────────────────────────┘
    ↓
Approximation? ──YES──→ ~ Fill (Blue) ← DONE
    │
    NO
    ↓
✗ Not Filled (Red)
```

### 4. Fill Excel & Format

**Auto-Created Columns:**
- **AutoRate Reference**: Source of matched item with hierarchy and confidence
  - Format: `"Grandparent > Parent > Description [Sheet-Row@Price] (Confidence: 85%)"`
  - Exact matches show 100% confidence
  
- **AutoRate Reasoning**: LLM's explanation
  - Exact: Why items are identical
  - Close: What minor differences exist
  - Approximation: How to adjust the rate and what limitations apply

**Color Coding:**
- 🟢 **Green cells**: Exact match (Stage 1: MATCHER, 100% confidence)
- 🟡 **Yellow cells**: Close match (Stage 2: EXPERT, 70-95% confidence)
- 🔵 **Blue cells**: Approximation (Stage 3: ESTIMATOR, 50-69% confidence)
- 🔴 **Red cells**: No match in any stage

**Original formatting preserved, all formulas maintained**

## Configuration Options

### Pipeline Settings

```python
# In fill_rates.py or when calling run_pipeline()

# Similarity threshold (0.0 to 1.0)
similarity_threshold = 0.5  # Default, lower = more candidates retrieved

# Top-K candidates for LLM validation
top_k = 6  # Number of similar items to send to each LLM stage

# All stages use gpt-4o-mini with temperature=0
```

### Stage-Specific Prompts

All prompts are defined in `src/prompts.py`:

- **`build_matcher_prompt()`**: Stage 1 (Exact matches)
  - Very strict, any difference = no match
  - Confidence: Always 100% if matched

- **`build_expert_prompt()`**: Stage 2 (Close matches)
  - Realistic similarity evaluation
  - Confidence range: 70-95%
  - Returns differences between items

- **`build_estimator_prompt()`**: Stage 3 (Approximations)
  - Practical cost estimation guidance
  - Confidence range: 50-69%
  - Returns adjustment instructions and limitations

You can customize prompts in `src/prompts.py` to adjust matching strictness for each stage.

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

**Color-Coded Cells:**
- 🟢 **Green**: Exact match (MATCHER stage, 100% confidence)
- 🟡 **Yellow**: Close match (EXPERT stage, 70-95% confidence)
- 🔵 **Blue**: Approximation (ESTIMATOR stage, 50-69% confidence)
- 🔴 **Red**: No match found in any stage

**Auto-Created Columns:**
- **AutoRate Reference**: Shows source with confidence
  - Example: `"General Excavation | Apron area | Depth 0.25m [terminal-45@125.50] (Confidence: 87%)"`
- **AutoRate Reasoning**: LLM explanation
  - Exact: "Identical specifications and scope"
  - Close: "Very similar, differences: DN200 vs DN250"
  - Approximation: "Can approximate, adjust by diameter ratio (250/200)"

**All original formatting and formulas preserved**

### Text Report

`output/{filename}_filled_{timestamp}_report.txt`

```
================================================================================
RATE FILLING REPORT - 3-STAGE MATCHING SYSTEM
================================================================================

File: Book_2.xlsx
Sheet: 9-PA
Date: 2025-11-14 20:30:00

Summary:
--------
Total items processed: 562
Items filled: 501 (89.1%)
  - Exact matches (MATCHER): 387 (68.9%)
  - Close matches (EXPERT): 92 (16.4%)
  - Approximations (ESTIMATOR): 22 (3.9%)
Items not filled: 61 (10.9%)

Filled Items by Stage:
----------------------

✓ EXACT MATCHES (387 items):
  Row 12: Supply and install ceramic tiles 60x60cm
    Rate: 125.50 QAR
    Source: Terminal > Floor Finishes > Ceramic tiles 60x60 [terminal-45@125.50]
    
≈ CLOSE MATCHES (92 items):
  Row 23: HDPE Pipe DN200 PN16
    Rate: 85.00 QAR (Confidence: 87%)
    Source: Hilton > Utilities > HDPE Pipe DN250 PN16 [hilton-78@85.00]
    Differences: Diameter 200mm vs 250mm, same material and pressure rating
    
~ APPROXIMATIONS (22 items):
  Row 45: Concrete C30/20 unreinforced
    Rate: 320.00 QAR (Confidence: 62%)
    Source: Resort > Structural > Concrete C40/20 [resort-92@320.00]
    Adjustment: Lower grade (C30 vs C40), price likely similar or slightly lower
    Limitations: Verify actual grade pricing with supplier

✗ NOT FILLED (61 items):
  Row 78: Specialized custom item XYZ
    Reason: No suitable matches found in any stage
    Matcher: No exact match exists
    Expert: Items too different for close match
    Estimator: No comparable items for approximation
    → Manual entry required
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

Approximate costs for 500-item BOQ with 3-stage matching:

**Best Case** (most items match in Stage 1):
- **Embeddings**: 500 queries × $0.00002 = $0.01
- **Stage 1 (Matcher)**: 500 validations × $0.0001 = $0.05
- **Stage 2 (Expert)**: ~100 validations × $0.0001 = $0.01 (only if Stage 1 fails)
- **Stage 3 (Estimator)**: ~20 validations × $0.0001 = $0.002 (only if Stages 1-2 fail)
- **Total**: ~$0.07 per sheet

**Worst Case** (all items go through all 3 stages):
- **Embeddings**: 500 queries × $0.00002 = $0.01
- **All 3 Stages**: 500 × 3 × $0.0001 = $0.15
- **Total**: ~$0.16 per sheet

**Typical Case** (mixed):
- Most items (~70%) match in Stage 1 (exact)
- Some items (~20%) need Stage 2 (close)
- Few items (~5%) need Stage 3 (approximation)
- **Average Total**: ~$0.08-0.10 per sheet

The sequential approach **reduces costs** by stopping at the first successful match instead of always calling all validation methods.

## Performance

Typical processing for 500 items:
- **Read Excel**: <1 second
- **Vector Search**: ~2-3 minutes (rate limited)
- **Stage 1 (Matcher)**: ~3-4 minutes (most items)
- **Stage 2 (Expert)**: ~1-2 minutes (some items, if Stage 1 fails)
- **Stage 3 (Estimator)**: ~30 seconds (few items, if Stages 1-2 fail)
- **Write Excel**: <1 second
- **Total**: ~7-12 minutes

**Performance Benefits of 3-Stage Approach:**
- Exact matches (typically 60-70% of items) skip Expert and Estimator stages
- Only unmatched items proceed to next stages
- Reduces total LLM calls by ~40-50% compared to always checking all possibilities

## Troubleshooting

### No matches found (too many red cells)?
- **Lower similarity threshold**: Try 0.4 or 0.45 (default is 0.5)
  ```bash
  python process_single.py "file.xlsx" "Sheet" --threshold 0.4
  ```
- **Increase top-k**: Get more candidates for LLM to evaluate (try 10-15)
  ```bash
  python process_single.py "file.xlsx" "Sheet" --top-k 10
  ```
- **Check vector database**: Verify items are uploaded (`json_to_vectorstore`)
- **Verify embedding format**: Should be `[grandparent] | [parent] | [description]` (no labels)

### Too many approximations (blue cells)?
- **Adjust Expert stage**: Edit `build_expert_prompt()` in `src/prompts.py`
- **Tighten Expert confidence**: Require 75-95% instead of 70-95%
- **More specific matching rules**: Add domain-specific requirements to prompts

### Wrong matches (incorrect items matched)?
- **Strengthen Matcher stage**: Make `build_matcher_prompt()` even more strict
- **Review prompts**: Check examples in `src/prompts.py` align with your domain
- **Add domain rules**: Customize prompts with BOQ-specific matching criteria
- **Check hierarchy**: Verify grandparent/parent are extracted correctly (review logs)

### Too many exact matches (seems wrong)?
- **Review Matcher stage**: May be too lenient
- **Tighten exact match criteria**: Edit `build_matcher_prompt()` in `src/prompts.py`
- **Check if items truly identical**: Review green cells in Excel output

### Hierarchy incorrect?
- Verify c-levels are marked with "c" in Level column
- Check for empty rows between c-levels (auto-skipped)
- Review logs for hierarchy decisions
- Ensure consistent c-level format across sheets

### API rate limits?
- Pipeline includes automatic rate limiting
- Increase delays in `rate_matcher.py` if needed
- Consider upgrading OpenAI plan for higher limits
- Monitor logs for rate limit warnings

### Excel formatting lost?
- Only filled cells are colored (green/yellow/blue/red)
- All other formatting is preserved
- AutoRate columns are auto-created if missing
- Check `excel_writer.py` if issues persist

### Understanding Match Types

**Green (Exact)**: Use these rates confidently
- Items are identical or functionally equivalent
- No adjustment needed

**Yellow (Close)**: Review differences before using
- Items very similar with minor variations
- Check "Reasoning" column for differences
- May need small adjustments (usually acceptable as-is)

**Blue (Approximation)**: Use for budgeting, verify before final pricing
- Items similar enough for cost estimation
- Check "Reasoning" column for adjustment guidance
- Read limitations carefully
- Best for preliminary budgets, not final quotes

**Red (No Match)**: Requires manual entry
- No suitable match found in any stage
- Check reasoning to understand why all stages failed
- May need to add similar items to vector database

## Next Steps

After filling rates:

1. **Review Output Excel**
   - 🟢 Green cells: Verify exact matches look correct
   - 🟡 Yellow cells: Check differences in Reasoning column
   - 🔵 Blue cells: Read adjustment guidance, verify before using
   - 🔴 Red cells: Check why all stages failed (in Reasoning column)

2. **Check Reports**
   - Review stage distribution (how many exact/close/approximation)
   - Analyze unfilled items
   - Look for patterns in failed matches

3. **Manual Fill Remaining**
   - Fill red cells manually
   - Or add similar items to vector database and re-run

4. **Adjust & Re-run** (if needed)
   - Lower threshold for more candidates
   - Modify prompts for domain-specific rules
   - Adjust confidence ranges in stages

5. **Quality Check**
   - Review approximations (blue) with subject matter experts
   - Verify close matches (yellow) are acceptable
   - Confirm exact matches (green) are truly identical

## Advanced: Customizing Stages

### Modify Matching Behavior

Edit `src/prompts.py` to customize each stage:

**Make Matcher more lenient:**
```python
# In build_matcher_prompt()
# Change from "EXACTLY the same" to "essentially identical"
# Allows minor wording variations
```

**Adjust Expert confidence ranges:**
```python
# In build_expert_prompt()
# Change from "70-95%" to "75-95%" for stricter close matches
```

**Modify Estimator criteria:**
```python
# In build_estimator_prompt()
# Add domain-specific approximation rules
# Example: "For piping, allow diameter scaling up to 2x"
```

### Add Domain-Specific Rules

Example for construction BOQ:
```python
# In build_expert_prompt(), add:
"""
CONSTRUCTION-SPECIFIC RULES:
- Concrete grades within 1 class acceptable (C30 ≈ C40)
- Pipe diameters within 50mm acceptable for same material
- Equipment capacity ±20% acceptable for similar models
"""
```

## Examples

### Example 1: High Exact Match Rate

```
Processed: 450 items
- Exact (Green): 315 items (70%) ← Most items
- Close (Yellow): 95 items (21%)
- Approximation (Blue): 25 items (5.5%)
- Not filled (Red): 15 items (3.3%)

Interpretation: Good match quality, vector database well-populated
```

### Example 2: Many Approximations

```
Processed: 450 items
- Exact (Green): 180 items (40%)
- Close (Yellow): 120 items (27%)
- Approximation (Blue): 110 items (24%) ← High
- Not filled (Red): 40 items (9%)

Interpretation: Items are somewhat different from database
Action: Review blue cells carefully, consider adding more exact matches to vector DB
```

### Example 3: High Failure Rate

```
Processed: 450 items
- Exact (Green): 90 items (20%)
- Close (Yellow): 45 items (10%)
- Approximation (Blue): 35 items (8%)
- Not filled (Red): 280 items (62%) ← Too high

Interpretation: Poor match quality
Actions:
1. Lower threshold (try 0.3-0.4)
2. Increase top-k (try 15-20)
3. Check if vector database contains relevant items
4. Verify sheet names match between source and target
```
