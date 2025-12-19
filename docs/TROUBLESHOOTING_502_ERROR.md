# Fixing the 502 Bad Gateway Error

## Root Cause

The 502 error is happening because:

1. **Environment Variables Not Resolving**: The `INDEXING_QUEUE_URL` uses CloudFormation `Ref` which doesn't work in serverless-offline
2. **Lambda Function Crashing**: The function crashes when repositories try to initialize with missing env vars

## Solution

### Step 1: Restart the Server

**IMPORTANT**: The server must be restarted after code changes!

```bash
# Stop the server (Ctrl+C in the terminal running serverless-offline)
# Then restart:
cd backend
./local-server.sh
```

### Step 2: Verify Environment Variables

After restarting, the script will now automatically set:

- `INDEXING_QUEUE_URL` = `https://sqs.eu-west-1.amazonaws.com/239146712026/taskflow-backend-dev-kb-indexing`

### Step 3: Test the Health Endpoint First

```bash
curl http://localhost:3001/health
```

This should return:

```json
{ "status": "ok", "service": "taskflow-backend" }
```

### Step 4: Check Server Logs

The actual error will appear in the terminal where you started serverless-offline. Look for:

- Python tracebacks
- Import errors
- Environment variable errors
- Any exceptions

## What Was Fixed

1. ✅ **Lazy Loading**: Repositories now initialize only when needed
2. ✅ **Better Error Handling**: Clear error messages if env vars are missing
3. ✅ **INDEXING_QUEUE_URL**: Automatically set in local-server.sh
4. ✅ **Error Messages**: Now show which env var is missing

## If Still Getting 502

1. **Check the server terminal** - The actual error is printed there
2. **Verify Python dependencies** are installed: `pip install -r requirements.txt`
3. **Check AWS credentials**: `aws sts get-caller-identity --profile mia40`
4. **Verify environment variables** are set correctly

## Common Errors

### "KB_TABLE_NAME environment variable is required"

- The serverless.yml environment variables aren't being set
- Restart the server
- Check serverless.yml configuration

### "Module not found" or ImportError

- Python dependencies missing
- Run: `pip install -r requirements.txt`

### "Access Denied" or AWS errors

- AWS credentials not configured
- Check `~/.aws/credentials` has `mia40` profile
