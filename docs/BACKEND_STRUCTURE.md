# Backend Structure

## Overview

Clean, organized structure with source code separate from deployment layers.

## Directory Structure

```
backend/
├── lambdas/                    # Lambda function handlers (source)
│   ├── *.py                    # Individual handler files
│   └── shared/                 # Shared code (source of truth)
│       ├── lambda_helpers.py   # Common utilities
│       ├── bedrock_client.py   # Bedrock integration
│       ├── s3_client.py        # S3 operations
│       ├── twilio_client.py    # Twilio integration
│       ├── validators.py       # Input validation
│       ├── kb_repositories.py  # KB DynamoDB repositories
│       ├── faiss_utils.py      # FAISS index management
│       ├── document_processing.py  # Document extraction
│       └── dynamic_bedrock.py  # Dynamic Bedrock client
├── layers/                     # Lambda layers (built from source)
│   ├── shared/                 # Unified shared code layer
│   │   └── python/
│   │       └── lambdas/
│   │           └── shared/     # All shared modules
│   └── sync-from-source.sh     # Script to sync from source
└── serverless.yml              # Serverless configuration
```

## Lambda Functions

All handler files are in `lambdas/`:

- `user_profile.py` - User profile management
- `items.py` - Task item management
- `knowledge_bases.py` - KB CRUD operations
- `kb_documents.py` - Document management
- `kb_query.py` - RAG queries
- `kb_indexing_worker.py` - Document indexing
- `twilio_webhook.py` - WhatsApp webhook
- `report_processor.py` - H&S report processing

## Shared Code

**Source of Truth**: `lambdas/shared/`

This directory contains all shared modules used by Lambda functions. Handlers import from here using relative imports:

```python
from .shared.lambda_helpers import ...
from .shared.kb_repositories import ...
```

## Lambda Layers

**Two layers total**:

1. **PythonRequirementsLambdaLayer** (auto-generated)

   - Contains Python dependencies from `requirements.txt`
   - Excludes: `numpy`, `faiss-cpu` (provided separately)

2. **SharedCodeLambdaLayer** (custom)
   - Contains all shared modules
   - Built from `lambdas/shared/`
   - Structure: `python/lambdas/shared/`

## Syncing Layers

Before deployment, sync the layer from source:

```bash
cd backend
./layers/sync-from-source.sh
```

This copies all modules from `lambdas/shared/` to `layers/shared/python/lambdas/shared/`.

## Deployment

Each Lambda function:

- Packages only its specific handler file
- Uses two layers: PythonRequirements + SharedCode
- Excludes `lambdas/shared/` from package (comes from layer)

## Benefits

✅ **Single Source of Truth**: All shared code in `lambdas/shared/`  
✅ **No Duplication**: Layer built from source, not maintained separately  
✅ **Small Packages**: Each function only packages its handler  
✅ **Clean Structure**: Clear separation of source and deployment artifacts  
✅ **Easy Updates**: Update source, sync, deploy
