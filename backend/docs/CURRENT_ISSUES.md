# Current Issues and Debugging Status

## Overview

This document tracks the current issues with the knowledge base indexing and vectorization system, along with their status and potential solutions.

---

## Issue #1: Pydantic Core Import Error (RESOLVED)

### Status: ✅ RESOLVED

### Error Message

```
Runtime.ImportModuleError: Unable to import module 'lambdas/kb_indexing_worker':
No module named 'pydantic_core._pydantic_core'
```

### Root Cause

- `pydantic==2.9.0` was in `requirements.txt` but not actually used in any Lambda code
- `pydantic_core` is a binary dependency that requires compilation for the target platform
- The layer contained macOS binaries (`cpython-313-darwin.so`) instead of Linux binaries

### Solution Applied

- ✅ Removed `pydantic==2.9.0` from `requirements.txt` (not needed)
- ✅ Confirmed no code imports pydantic

### Files Changed

- `backend/requirements.txt` - Removed pydantic dependency

---

## Issue #2: Numpy Import Error (RESOLVED)

### Status: ✅ RESOLVED

### Error Message

```
Runtime.ImportModuleError: Unable to import module 'lambdas/kb_indexing_worker':
Error importing numpy: you should not try to import numpy from its source directory
```

### Root Cause

- Module-level imports of `numpy` and `faiss` in `faiss_utils.py` and `kb_indexing_worker.py`
- These imports happened at module load time, causing conflicts with Lambda's layer structure

### Solution Applied

- ✅ Made numpy and faiss imports lazy in `faiss_utils.py`
- ✅ Moved numpy import inside functions that use it
- ✅ Converted all module-level service initialization to lazy initialization

### Files Changed

- `backend/lambdas/shared/faiss_utils.py` - Lazy imports for numpy/faiss
- `backend/lambdas/kb_indexing_worker.py` - Lazy initialization and imports
- `backend/lambdas/kb_query.py` - Lazy initialization
- `backend/lambdas/knowledge_bases.py` - Already had lazy initialization

---

## Issue #3: LXML Import Error (RESOLVED)

### Status: ✅ RESOLVED

### Error Message

```
Runtime.ImportModuleError: Unable to import module 'lambdas/kb_indexing_worker':
cannot import name 'etree' from 'lxml'
```

### Root Cause

- `python-docx` depends on `lxml` which requires binary compilation
- Module-level import of `from docx import Document` caused import at module load time

### Solution Applied

- ✅ Made docx import lazy in `document_processing.py`
- ✅ Import only happens when processing DOCX files
- ✅ Enabled `dockerizePip: true` to build lxml correctly

### Files Changed

- `backend/lambdas/shared/document_processing.py` - Lazy docx import
- `backend/serverless.yml` - Enabled dockerizePip

---

## Issue #4: Binary Dependencies Not Built for Linux (PARTIALLY RESOLVED)

### Status: ⚠️ PARTIALLY RESOLVED

### Problem

- Binary dependencies (numpy, faiss-cpu, lxml) need to be compiled for Linux (Lambda environment)
- Current layer may contain macOS binaries when built on macOS
- `dockerizePip: non-linux` should force Docker builds, but layer version hasn't incremented

### Current Configuration

```yaml
pythonRequirements:
  dockerizePip: non-linux # Force Docker for all builds (including macOS)
  dockerImage: public.ecr.aws/sam/build-python3.13:latest
  layer: true
```

### Status

- ✅ Docker image configured correctly
- ✅ dockerizePip set to force Docker usage
- ⚠️ Layer version still at 3 (may need manual rebuild)
- ✅ Lazy imports prevent module-load-time errors

### Next Steps

1. Force rebuild the pythonRequirements layer
2. Verify binaries are Linux-compatible after rebuild
3. Deploy and test indexing worker

### Verification Command

```bash
# Check if binaries are Linux-compatible
unzip -l .serverless/pythonRequirements.zip | grep "\.so" | grep -v "linux"
```

---

## Issue #5: Document Status Polling (RESOLVED)

### Status: ✅ RESOLVED

### Problem

- Frontend couldn't determine when document indexing was complete
- Documents showed "processing" status indefinitely

### Solution Applied

- ✅ Added automatic polling in `KnowledgeBaseDetails.tsx`
- ✅ Polls every 3 seconds when documents are processing
- ✅ Stops polling when all documents are indexed or failed
- ✅ Visual feedback with spinner for processing status

### Files Changed

- `frontend/src/components/knowledgebase/KnowledgeBaseDetails.tsx` - Added polling logic
- `frontend/src/components/knowledgebase/DocumentList.tsx` - Improved status display

---

## Issue #6: S3 CORS Configuration (RESOLVED)

### Status: ✅ RESOLVED

### Problem

- CORS errors when uploading documents directly to S3
- Browser blocked cross-origin PUT requests

### Solution Applied

- ✅ Added CORS configuration to `KnowledgeBaseBucket` in serverless.yml
- ✅ Allowed origins: localhost:3000, localhost:3001, \*.amazonaws.com
- ✅ Allowed methods: GET, PUT, POST, HEAD
- ✅ Improved presigned URL generation with proper MIME types

### Files Changed

- `backend/serverless.yml` - Added CorsConfiguration to KnowledgeBaseBucket
- `backend/lambdas/kb_documents.py` - Improved MIME type mapping

---

## Current Testing Status

### Working

- ✅ Health check endpoint
- ✅ Knowledge base CRUD operations
- ✅ Document upload URL generation
- ✅ S3 direct upload (CORS fixed)
- ✅ Document list endpoint
- ✅ Frontend polling for document status

### Needs Testing

- ⚠️ Document indexing worker (after layer rebuild)
- ⚠️ FAISS index creation and updates
- ⚠️ Knowledge base query endpoint
- ⚠️ Vector search functionality

---

## Recommended Next Steps

1. **Force Rebuild Python Requirements Layer**

   ```bash
   cd backend
   rm -rf .serverless/pythonRequirements*
   export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"
   npx serverless deploy --stage dev
   ```

2. **Verify Layer Contents**

   ```bash
   # Check for Linux binaries
   unzip -l .serverless/pythonRequirements.zip | grep "\.so" | grep linux
   ```

3. **Test Document Indexing**

   - Upload a test document
   - Monitor CloudWatch logs for indexing worker
   - Verify document status changes to "indexed"

4. **Monitor Indexing Worker Logs**
   ```bash
   aws logs tail /aws/lambda/taskflow-backend-dev-knowledgeBaseIndexingWorker \
     --since 5m --profile mia40 --region eu-west-1 --format short --follow
   ```

---

## Architecture Improvements Made

1. **Lazy Initialization Pattern**

   - All services (repositories, clients) now use lazy initialization
   - Prevents import-time errors
   - Better error handling and configuration validation

2. **Shared S3 Client**

   - Centralized S3 client in `lambda_helpers.py`
   - Consistent usage across all Lambda functions
   - Follows same pattern as DynamoDB table

3. **Decimal Serialization**

   - Fixed JSON serialization for DynamoDB Decimal values
   - Automatic conversion in `create_response()`
   - Prevents "Object of type Decimal is not JSON serializable" errors

4. **Test Structure**
   - Organized into unit, integration, and e2e tests
   - Proper fixtures and helpers
   - Ready for CI/CD integration

---

## Known Limitations

1. **Layer Compatibility**

   - Serverless Framework doesn't officially support python3.13 for layers
   - Using python3.13 anyway (AWS supports it, Serverless just shows warning)
   - Layer runtime set to python3.13 (works despite warning)

2. **Binary Dependencies**

   - numpy, faiss-cpu, lxml require Linux binaries
   - Must use Docker to build correctly
   - Layer rebuild needed when dependencies change

3. **Layer Versioning**
   - Layer version may not increment automatically
   - May need manual cache clearing to force rebuild

---

## Monitoring Commands

### Check Indexing Worker Status

```bash
aws logs tail /aws/lambda/taskflow-backend-dev-knowledgeBaseIndexingWorker \
  --since 10m --profile mia40 --region eu-west-1 --format short
```

### Check Document Upload Status

```bash
aws logs tail /aws/lambda/taskflow-backend-dev-confirmKnowledgeBaseDocumentUpload \
  --since 10m --profile mia40 --region eu-west-1 --format short
```

### Check SQS Queue

```bash
aws sqs get-queue-attributes \
  --queue-url <QUEUE_URL> \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --profile mia40 --region eu-west-1
```

---

## Last Updated

2025-11-29

## Status Summary

- ✅ Most import errors resolved with lazy initialization
- ✅ CORS configuration fixed
- ✅ Frontend polling implemented
- ⚠️ Python requirements layer needs rebuild for Linux binaries
- ⚠️ Indexing worker needs testing after layer rebuild
