# Almabani Local Development Guide

## 1. Testing Workers Locally

You can simulate the cloud "Process & Die" behavior on your local machine to verify worker logic.

### Prerequisites
- Python 3.11+
- Dependencies installed (`pip install -r boq-backend/requirements.txt && pip install -e boq-backend/`)
- Valid AWS credentials in your environment
- `.env` file in `boq-backend/` with API keys

### Unit Rate Worker

```bash
cd boq-backend

# Parse job (Excel → JSON)
export JOB_MODE=PARSE
export S3_KEY=input/parse/test.xlsx
python worker.py

# Fill job (rate matching)
export JOB_MODE=FILL
export S3_KEY=input/fill/test.xlsx
python worker.py
```

Results appear in S3 under `output/indexes/` (parse) or `output/fills/` (fill).

### Price Code Worker (Lexical)

```bash
cd boq-backend

# Index price codes (build SQLite TF-IDF index)
export JOB_MODE=INDEX
export S3_KEY=input/pricecode/index/catalog.xlsx
python pricecode_worker.py

# Allocate price codes to BOQ items
export JOB_MODE=ALLOCATE
export S3_KEY=input/pricecode/allocate/boq.xlsx
python pricecode_worker.py
```

Results appear in S3 under `output/pricecode/`.

### Price Code Worker (Vector)

```bash
cd boq-backend

# Index price codes (embed → S3 Vectors)
export JOB_MODE=INDEX
export S3_KEY=input/pricecode-vector/index/catalog.xlsx
python pricecode_vector_worker.py

# Allocate price codes to BOQ items
export JOB_MODE=ALLOCATE
export S3_KEY=input/pricecode-vector/allocate/boq.xlsx
python pricecode_vector_worker.py
```

Results appear in S3 under `output/pricecode-vector/`.

---

## 2. Testing the Chat Handler Locally

The chat handler is designed for Lambda, but you can test it locally by calling the handler function directly:

```python
# test_chat.py
from chat_handler import handler

# Unit rate query
event = {"body": '{"message": "HDPE pipe DN200 PN16", "type": "unitrate"}'}
result = handler(event, None)
print(result)

# Price code query
event = {"body": '{"message": "supply and install HDPE pipe", "type": "pricecode"}'}
result = handler(event, None)
print(result)
```

```bash
cd boq-backend
python test_chat.py
```

---

## 3. CLI Tool

The `almabani` package includes a Typer-based CLI:

```bash
cd boq-backend
pip install -e .

# View available commands
almabani --help

# Parse Excel BOQ
almabani parse --input data/sample.xlsx --output data/output/

# Query the vector store
almabani query --text "HDPE pipe DN200" --top-k 5
```
