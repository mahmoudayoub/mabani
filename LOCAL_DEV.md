# Almabani Local Development Guide

The web application (Flask) used for local development is preserved alongside the cloud batch worker. You can run the application locally to test logic, debug pipelines, or use the visual interface.

## 1. Running the Web App (GUI)

The Web App provides a user interface for Parsing, Indexing, and Filling rates.

### Prerequisites
*   Python 3.9+
*   Dependencies installed (`pip install -r backend/requirements.txt`)
*   `backend/env` file configured with API keys.

### Steps
1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```

2.  Run the application:
    ```bash
    python app/main.py
    ```

3.  Access the UI at `http://localhost:5000`.

**Note**: By default, the app is configured to use S3 for storage. If you want to use **local storage** (files saved to disk instead of S3), update your `backend/env`:
```bash
STORAGE_TYPE=local
```

---

## 2. Testing the Worker Locally

You can simulate the cloud "Process & Die" behavior on your local machine to verify `worker.py` logic.

### Steps
1.  Ensure your `backend/env` has `STORAGE_TYPE=s3` and valid AWS credentials in your environment.

2.  Manually upload a file to your S3 bucket (e.g., `input/fill/test.xlsx`).

3.  Run the worker script with the required environment variables:
    ```bash
    cd backend
    
    # 1. Simulate a FILL job
    export JOB_MODE=FILL
    export S3_KEY=input/fill/test.xlsx
    python worker.py
    
    # 2. Simulate a PARSE job
    export JOB_MODE=PARSE
    export S3_KEY=input/parse/test.xlsx
    python worker.py
    ```

4.  Check S3 `output/` folder for results.

---

## 3. Testing the Price Code Worker Locally

```bash
cd backend

# Index price codes
export JOB_MODE=INDEX
export S3_KEY=input/pricecode/index/catalog.xlsx
python pricecode_worker.py

# Allocate price codes to BOQ items
export JOB_MODE=ALLOCATE
export S3_KEY=input/pricecode/allocate/boq.xlsx
python pricecode_worker.py
```

Check S3 `output/pricecode/` folder for allocated results.

---

## 4. Testing the Chat Handler Locally

The chat handler is designed for Lambda, but you can test it locally by calling the handler function directly:

```python
# test_chat.py
from chat_handler import handler

event = {
    "body": '{"message": "HDPE pipe DN200 PN16", "chat_type": "unitrate"}'
}
result = handler(event, None)
print(result)
```

```bash
cd backend
python test_chat.py
```

---

## 5. CLI Tool

The `almabani` package includes a Typer-based CLI:

```bash
cd backend
pip install -e .

# Then use the CLI commands (run with --help for options)
python -m almabani.cli.main --help
```

---

## 6. Docker Compose (Web GUI)

Run the Flask web GUI in a Docker container:

```bash
cd backend
docker-compose up --build
# Access at http://localhost:8080
```

The compose file mounts persistent volumes for uploads, fills, indexes, and logs.

