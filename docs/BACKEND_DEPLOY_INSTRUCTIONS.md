# Deployment Instructions

## Current Status

- **Local Development**: Now uses Python 3.12 (serverless-offline compatible)
- **AWS Production**: Still using Python 3.13 (but this is fine - AWS supports it)

## Redeployment Decision

**You don't NEED to redeploy immediately** because:
- ✅ AWS Lambda supports Python 3.13 (the deployed functions work fine)
- ✅ The runtime mismatch only affects local development
- ✅ Changing to Python 3.12 is mainly for local dev compatibility

However, **if you want consistency**, you can redeploy.

## How to Deploy (When Ready)

Deployments can take 5-10 minutes, so don't worry if it seems slow:

```bash
cd backend

# Set required environment variable
export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"

# Deploy all functions (this will take several minutes)
npm run deploy

# OR deploy just one function to test:
npx serverless deploy function --function listKnowledgeBases --stage dev
```

## Priority: Local Development First

**More important right now**: Make sure your local development server is working!

1. **Restart your local server** with Python 3.12:
   ```bash
   cd backend
   ./local-server.sh
   ```

2. **Test locally first**:
   ```bash
   curl http://localhost:3001/health
   ```

3. **Once local dev works**, then worry about redeploying to AWS (if needed).

## Note

The deployed AWS functions will continue working with Python 3.13. The redeployment is optional for consistency, but not urgent.

