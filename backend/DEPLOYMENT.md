# Deployment & Troubleshooting Guide

## Overview

This backend uses **Serverless Framework** with **Python 3.13** on **AWS Lambda (arm64)**.
To handle complex binary dependencies like `faiss-cpu`, `numpy`, and `pydantic-core`, we utilize **Docker** for the build process.

## Prerequisites

1.  **Docker Desktop** must be installed and running.
2.  **Node.js & NPM** (for Serverless Framework).
3.  **AWS CLI** configured with valid credentials.
4.  **Python 3.13** (optional for local dev, but recommended).

## Deployment

We provide a robust deployment script that handles cache cleaning and verification.

```bash
# Run from backend directory
./deploy_robust.sh
```

### What the script does:
1.  **Checks Docker**: Ensures the Docker daemon is active.
2.  **Cleans Caches**: Removes `.serverless` and local `serverless-python-requirements` caches. This is critical when switching architectures (x86 vs arm64) or updating binary-heavy requirements.
3.  **Verifies Dependencies**: Basic sanity check on `requirements.txt`.
4.  **Deploys**: Runs `serverless deploy` which triggers the Docker container build.

## Architecture & Build Details

*   **Runtime**: Python 3.13
*   **Architecture**: `arm64` (Graviton2). This offers better price/performance.
*   **Build System**:
    *   We use the `serverless-python-requirements` plugin.
    *   `dockerizePip: non-linux` is set to `true`. This forces a Docker build on macOS.
    *   Docker Image: `public.ecr.aws/sam/build-python3.13:latest`. This image ensures that the compiled wheels (for `faiss`, etc.) are compatible with the AWS Lambda environment.

## Troubleshooting

### `Runtime.ImportModuleError: No module named 'pydantic_core._pydantic_core'`
*   **Cause**: The binary wheel for `pydantic-core` was compiled for the wrong architecture or OS (e.g., macOS x86 instead of Linux arm64), or the dependency was missing from `requirements.txt`.
*   **Fix**:
    1.  Ensure `pydantic` is in `requirements.txt`.
    2.  Ensure `architecture: arm64` is in `serverless.yml`.
    3.  Run `./deploy_robust.sh` to clean caches and force a fresh Docker build.

### `ModuleNotFoundError: No module named 'faiss'`
*   **Cause**: FAISS is a complex C++ library wrapped in Python. It requires specific system libraries (OpenBLAS, etc.) that must be present in the Lambda environment or statically linked.
*   **Fix**:
    *   The project uses `faiss-cpu`.
    *   The Docker build process (`public.ecr.aws/sam/build-python3.13`) generally handles this correctly.
    *   Ensure strict version pinning in `requirements.txt`.

### Deployment Stuck or Slow
*   **Cause**: Docker image pulling or large layer uploads.
*   **Fix**: Be patient. The first deployment after a cache clear involves pulling a large Docker image and uploading ~50MB+ layers.
