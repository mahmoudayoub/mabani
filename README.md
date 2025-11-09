# Almabani BOQ Management System

AI-powered Bill of Quantities (BOQ) processing and rate filling system with three modular pipelines.

## Overview

This system processes Excel BOQ files, creates a searchable vector database, and automatically fills missing unit rates using semantic search and AI validation.

## System Architecture

```
┌─────────────────────┐
│  Excel BOQ Files    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────┐
│ 1. excel_to_json_pipeline   │  Convert Excel → JSON
│    - Preserves hierarchy     │  
│    - Flattens level 'c'      │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 2. json_to_vectorstore      │  JSON → Vector Database
│    - Extract items           │
│    - Generate embeddings     │
│    - Upload to Pinecone      │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ 3. rate_filler_pipeline     │  Auto-fill Missing Rates
│    - Vector search           │
│    - LLM validation          │
│    - Excel output            │
└─────────────────────────────┘
```

## Pipelines

### 1. Excel to JSON Pipeline
Converts Excel BOQ files into structured JSON format.

**Directory:** `excel_to_json_pipeline/`

**Usage:**
```bash
cd excel_to_json_pipeline
python process_separate_sheets.py
```

**Input:** Excel files in `input/`  
**Output:** JSON files in `output/`

[More details →](excel_to_json_pipeline/README.md)

---

### 2. JSON to Vector Store Pipeline
Extracts items, generates embeddings, and uploads to Pinecone.

**Directory:** `json_to_vectorstore/`

**Usage:**
```bash
cd json_to_vectorstore
python prepare_and_upload.py
```

**Input:** JSON files in `input/`  
**Output:** JSONL files in `output/` + Pinecone upload

**Requirements:** OpenAI API key, Pinecone API key

[More details →](json_to_vectorstore/README.md)

---

### 3. Rate Filler Pipeline
Auto-fills missing rates using AI-powered matching.

**Directory:** `rate_filler_pipeline/`

**Usage:**
```bash
cd /home/ali/Desktop/Almabani
python -m rate_filler_pipeline.process_single your_file.xlsx
```

**Input:** Excel files in `rate_filler_pipeline/input/`  
**Output:** Filled Excel + reports in `rate_filler_pipeline/output/`

**Requirements:** OpenAI API key, Pinecone API key, populated vector database

[More details →](rate_filler_pipeline/README.md)

---

## Quick Start

### Initial Setup (One-time)

1. **Clone/download** this repository

2. **Create virtual environment:**
   ```bash
   cd /home/ali/Desktop/Almabani
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   # For each pipeline
   pip install -r excel_to_json_pipeline/requirements.txt
   pip install -r json_to_vectorstore/requirements.txt
   pip install -r rate_filler_pipeline/requirements.txt
   ```

4. **Configure API keys:**
   ```bash
   # json_to_vectorstore/.env
   OPENAI_API_KEY=your_key_here
   PINECONE_API_KEY=your_key_here
   
   # rate_filler_pipeline/.env
   OPENAI_API_KEY=your_key_here
   PINECONE_API_KEY=your_key_here
   ```

### Build Vector Database (One-time)

1. **Convert Excel to JSON:**
   - Place Excel files in `excel_to_json_pipeline/input/`
   - Run: `cd excel_to_json_pipeline && python process_separate_sheets.py`

2. **Upload to Pinecone:**
   - Copy JSON files to `json_to_vectorstore/input/`
   - Run: `cd json_to_vectorstore && python prepare_and_upload.py`

### Fill Missing Rates (Daily Use)

1. **Place Excel file** in `rate_filler_pipeline/input/`

2. **Run pipeline:**
   ```bash
   cd /home/ali/Desktop/Almabani
   python -m rate_filler_pipeline.process_single your_file.xlsx
   ```

3. **Get results** from `rate_filler_pipeline/output/`

## Features

✅ **Automated Processing** - Minimal manual intervention  
✅ **AI-Powered Matching** - GPT-4o-mini validation for accuracy  
✅ **Semantic Search** - Find similar items even with different wording  
✅ **Auto-Detection** - Handles various Excel formats automatically  
✅ **Color-Coded Output** - Visual feedback on filled vs. unfilled items  
✅ **Detailed Reports** - Complete match information and reasoning  
✅ **Batch Processing** - Handle multiple files at once  
✅ **Production-Ready** - Modular, tested, documented

## Technology Stack

- **Language:** Python 3.8+
- **Excel Processing:** pandas, openpyxl
- **Embeddings:** OpenAI text-embedding-3-small
- **Vector Database:** Pinecone serverless
- **LLM:** GPT-4o-mini
- **Data Models:** Pydantic

## Cost Estimates

- **One-time setup** (31K items): ~$3 USD
- **Daily use** (100 items): ~$0.01 USD
- **Pinecone:** Free tier (100K vectors)

## Project Structure

```
Almabani/
├── excel_to_json_pipeline/       # Pipeline 1: Excel → JSON
│   ├── src/                      # Core modules
│   ├── input/                    # Excel files
│   ├── output/                   # JSON files
│   └── process_separate_sheets.py
│
├── json_to_vectorstore/          # Pipeline 2: JSON → Pinecone
│   ├── src/                      # Core modules
│   ├── input/                    # JSON files
│   ├── output/                   # JSONL files
│   └── prepare_and_upload.py
│
├── rate_filler_pipeline/         # Pipeline 3: Auto-fill rates
│   ├── src/                      # Core modules
│   ├── input/                    # Excel files to process
│   ├── output/                   # Filled Excel + reports
│   ├── fill_rates.py             # Main pipeline
│   ├── process_single.py         # Process one file
│   └── process_folder.py         # Process all files
│
├── .venv/                        # Virtual environment
└── README.md                     # This file
```

## Requirements

- Python 3.8 or higher
- OpenAI API account
- Pinecone API account
- ~500MB disk space for vector database cache

## Support

For detailed usage instructions, see the README in each pipeline directory:
- [excel_to_json_pipeline/README.md](excel_to_json_pipeline/README.md)
- [json_to_vectorstore/README.md](json_to_vectorstore/README.md)
- [rate_filler_pipeline/README.md](rate_filler_pipeline/README.md)

## Notes

- All pipelines can run independently
- Pipeline 3 requires pipelines 1 & 2 to be run first (one-time setup)
- Original files are never modified
- All operations are logged
- Safe to interrupt and restart
