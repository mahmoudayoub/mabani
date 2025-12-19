# Lambda Layers

This directory contains Lambda layers for shared code.

## Structure

- `shared/` - Single unified layer containing all shared modules
  - `python/lambdas/shared/` - Python package structure for Lambda layer

## Source of Truth

The source code is in `../lambdas/shared/`. This layer directory is built from that source.

## Syncing

To sync the layer from source before deployment:

```bash
./sync-from-source.sh
```

This copies all modules from `lambdas/shared/` to the layer structure.

## Layer Contents

The shared layer contains all shared modules:

- Common: `lambda_helpers.py`, `bedrock_client.py`, `s3_client.py`, `twilio_client.py`, `validators.py`
- KB-specific: `kb_repositories.py`, `faiss_utils.py`, `document_processing.py`, `dynamic_bedrock.py`

All Lambda functions use this single unified layer along with the Python requirements layer.
