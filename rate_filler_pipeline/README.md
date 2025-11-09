# Rate Filler Pipeline

Automatically fill missing unit rates in Excel BOQ files using AI-powered semantic search and validation.

## Overview

This pipeline uses vector search and GPT-4o-mini to find matching items from your database and auto-fill missing unit rates in Excel BOQ files. It combines semantic similarity search with LLM validation to ensure accurate matches.

## Features

- ✅ Auto-detect Excel headers and columns
- ✅ Vector search for similar items (Pinecone)
- ✅ LLM validation for exact matches (GPT-4o-mini)
- ✅ Batch processing of multiple files
- ✅ Color-coded Excel output (green=filled, red=no match)
- ✅ Detailed text reports

## Directory Structure

```
rate_filler_pipeline/
├── src/                      # Core modules
│   ├── excel_reader.py       # Excel parsing with auto-detection
│   ├── rate_matcher.py       # Vector search + LLM validation
│   └── excel_writer.py       # Excel output with formatting
├── input/                    # Place Excel files here
├── output/                   # Generated files (Excel + reports)
├── fill_rates.py             # Main pipeline
├── process_single.py         # Process one file
├── process_folder.py         # Process all files in input/
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

### Process Single File

```bash
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_single your_file.xlsx
```

### Process All Files in input/

```bash
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_folder
```

### Advanced (Custom Settings)

```python
from rate_filler_pipeline.fill_rates import run_pipeline

run_pipeline(
    input_excel="path/to/file.xlsx",
    output_excel="path/to/output.xlsx",
    similarity_threshold=0.76,  # Minimum similarity score
    top_k=6                      # Number of candidates to retrieve
)
```

## Input Format

Excel file with columns (auto-detected):
- **Item** or **Code**: Item code
- **Bill description** or **Description**: Item description  
- **Unit**: Unit of measurement (m2, m3, ton, etc.)
- **Rate** or **Unit rate**: Unit rate (to be filled if missing)

The pipeline automatically detects:
- Header row location
- Column names (handles variations)
- Items with missing rates

## Output

### Excel File
- **Green cells**: Successfully filled rates
- **Red cells**: No match found
- Same structure as input
- Filename: `{original}_filled_{timestamp}.xlsx`

### Text Report
- Total items processed
- Items filled vs. not filled
- Match details (description, unit, rate, source)
- Reasoning for matches/no-matches

## How It Works

1. **Read Excel**: Auto-detect headers and extract items with missing rates
2. **Vector Search**: Find similar items from Pinecone (31K+ items)
3. **LLM Validation**: GPT-4o-mini checks if candidates are exact matches
4. **Fill Rates**: Calculate average rate from validated matches
5. **Write Output**: Color-coded Excel + detailed report

## Matching Logic

**Exact Match Criteria:**
- Same construction work (even if wording differs)
- Same specifications (materials, dimensions, standards)
- Same scope of work
- Compatible units

**Example Matches:**
- ✅ "EXCAVATION FOR FOUNDATIONS" ↔ "EXCAVATION IN FOUNDATION AREAS"
- ✅ "SUPPLY PUMPING STATION 80KW" ↔ "PUMPING STATION 80KW SUPPLY & INSTALL"
- ❌ "CONCRETE C40" ↔ "CONCRETE C30" (different specs)

## Settings

- **Similarity threshold**: 0.76 (adjustable, range: 0.0-1.0)
- **Top-K candidates**: 6 (how many similar items to retrieve)
- **LLM model**: gpt-4o-mini (cost-effective, accurate)
- **Embedding model**: text-embedding-3-small (1536 dimensions)

## API Costs

- **OpenAI Embeddings**: ~$0.00001 per item
- **GPT-4o-mini**: ~$0.0001 per validation
- **Pinecone**: Free tier (100K vectors)

**Estimated cost for 1000 items:** ~$0.10 USD

## Requirements

- Python 3.8+
- openai
- pinecone-client
- pandas
- openpyxl
- python-dotenv
- tqdm

## Prerequisites

Must have completed:
1. `excel_to_json_pipeline` - Convert BOQ to JSON
2. `json_to_vectorstore` - Upload items to Pinecone

The vector database must be populated before running this pipeline.

## Notes

- Processes only items with missing rates
- Skips header rows automatically
- Handles multi-sheet Excel files
- Progress bars show real-time status
- All API calls are logged
- Safe: Creates new files, doesn't modify originals
