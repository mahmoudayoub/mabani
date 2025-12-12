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
