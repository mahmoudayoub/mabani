# Fixing 502 Error on AWS - Numpy Import Issue

## Problem

CloudWatch logs show:

```
Runtime.ImportModuleError: Unable to import module 'lambdas/knowledge_bases':
Error importing numpy: you should not try to import numpy from its source directory
```

## Root Cause

1. **Numpy packaging conflict**: Numpy is being packaged in a way that conflicts with the Lambda layer
2. **Top-level import**: `knowledge_bases.py` was importing FAISSService at module level (which imports numpy)
3. **Deployed code is old**: The Lambda still has code that imports FAISS at module load time

## Solution Applied

1. ✅ **Made FAISS import lazy** - Only imports when actually needed (not for listKnowledgeBases)
2. ✅ **Added numpy/faiss exclusions** in package patterns
3. ✅ **Removed top-level FAISSService import**

## Next Step: Redeploy

The fix requires redeploying the Lambda functions:

```bash
cd backend
export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"

# Redeploy all functions
npm run deploy

# OR just deploy the listKnowledgeBases function to test:
npx serverless deploy function --function listKnowledgeBases --stage dev
```

## Verification

After redeployment, test:

```bash
curl -X GET https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev/knowledge-bases \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Expected Result

Should return:

```json
{
  "knowledgeBases": [],
  "total": 0
}
```

Instead of 502 error.
