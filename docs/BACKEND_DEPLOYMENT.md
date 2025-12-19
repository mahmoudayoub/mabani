# Deployment Guide

## Quick Deploy

Simply run the deployment script:

```bash
cd backend
./deploy.sh
```

This will:

1. ✅ Load environment variables from `deployment.config.sh`
2. ✅ Sync layers from `lambdas/shared/` to `layers/` directories
3. ✅ Deploy all Lambda functions and layers to AWS

## What Gets Deployed

### Layers (3 total)

1. **PythonRequirementsLambdaLayer** (auto-generated)

   - Contains Python dependencies from `requirements.txt`
   - Excludes: `numpy`, `faiss-cpu` (provided separately)

2. **SharedCodeLambdaLayer** (custom)

   - Common shared code: `lambda_helpers`, `bedrock_client`, `s3_client`, `twilio_client`, `validators`
   - Used by: All Lambda functions

3. **KbSharedCodeLambdaLayer** (custom)
   - KB-specific code: `kb_repositories`, `faiss_utils`, `document_processing`, `dynamic_bedrock`, `lambda_helpers`
   - Used by: KB Lambda functions only

### Lambda Functions (20 total)

- Common functions: `healthCheck`, `getUserProfile`, `updateUserProfile`, `createItem`, `getUserItems`, `updateItem`, `deleteItem`, `twilioWebhook`, `reportProcessor`
- KB functions: `listKnowledgeBases`, `createKnowledgeBase`, `getKnowledgeBase`, `updateKnowledgeBase`, `deleteKnowledgeBase`, `generateKnowledgeBaseUploadUrl`, `confirmKnowledgeBaseDocument`, `listKnowledgeBaseDocuments`, `deleteKnowledgeBaseDocument`, `queryKnowledgeBase`, `knowledgeBaseIndexingWorker`

## Deployment Process

1. **Sync Layers**: Copies code from `lambdas/shared/` to layer directories

   - Common code → `layers/shared/python/lambdas/shared/`
   - KB code → `layers/kb/python/lambdas/shared/`

2. **Package Functions**: Each function packages only its handler file

   - Shared code comes from layers (not packaged with each function)
   - Dependencies come from PythonRequirements layer

3. **Deploy to AWS**:
   - Creates/updates Lambda layers
   - Creates/updates Lambda functions
   - Updates API Gateway routes

## Environment Variables

Required environment variables are loaded from:

- `deployment.config.sh` (preferred)
- `.env.local` (fallback)

Required:

- `COGNITO_USER_POOL_ARN` - Cognito User Pool ARN for authentication
- `AWS_PROFILE` - AWS profile name
- `AWS_REGION` - AWS region
- `STAGE` - Deployment stage (default: `dev`)

## Manual Steps

If you need to sync layers without deploying:

```bash
./layers/sync-from-source.sh
```

If you need to deploy without syncing (uses existing layer files):

```bash
source deployment.config.sh
npx serverless deploy --stage dev --verbose
```

## Troubleshooting

### Layers not syncing

- Check that `layers/sync-from-source.sh` exists and is executable
- Verify `lambdas/shared/` contains all source files

### Python 3.13 warning

- This is harmless - AWS Lambda supports Python 3.13
- Serverless Framework validation just hasn't updated yet

### Deployment fails

- Check AWS credentials: `aws sts get-caller-identity --profile mia40`
- Verify environment variables are set correctly
- Check CloudWatch logs for Lambda errors
