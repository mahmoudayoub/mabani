# Local Server Setup Summary

## What Was Configured

The local development server has been configured with **serverless-offline** to enable testing of all Knowledge Base endpoints locally.

## Changes Made

### 1. Package Configuration (`package.json`)

- ✅ Added `serverless-offline@^13.3.0` as a dev dependency
- ✅ Added `npm run dev` script to start the local server

### 2. Serverless Configuration (`serverless.yml`)

- ✅ Added `serverless-offline` plugin
- ✅ Configured local server on port **3001**
- ✅ Lambda port on **3002**
- ✅ Disabled stage prefix in URLs for cleaner endpoints

### 3. Environment Configuration

- ✅ Created `.env.local` with all required environment variables
- ✅ Points to real AWS dev resources (DynamoDB, S3, SQS, Bedrock)

### 4. Startup Script (`local-server.sh`)

- ✅ Automated server startup with environment loading
- ✅ Displays all available endpoints
- ✅ Color-coded output for better readability
- ✅ Executable permissions set

### 5. Testing Tools

- ✅ `test-kb-endpoints.sh` - Automated endpoint testing script
- ✅ `postman-collection.json` - Postman collection for manual testing
- ✅ Both tools include all 11 KB endpoints

### 6. Documentation

- ✅ `LOCAL_DEVELOPMENT.md` - Comprehensive local dev guide
- ✅ `README.md` - Updated main README with KB features
- ✅ API examples and usage instructions

## Available Endpoints

When you run the local server, these endpoints will be available:

### Knowledge Base Endpoints (New)

```
GET    http://localhost:3001/knowledge-bases
POST   http://localhost:3001/knowledge-bases
GET    http://localhost:3001/knowledge-bases/{kbId}
PUT    http://localhost:3001/knowledge-bases/{kbId}
DELETE http://localhost:3001/knowledge-bases/{kbId}
POST   http://localhost:3001/knowledge-bases/{kbId}/upload-url
POST   http://localhost:3001/knowledge-bases/{kbId}/documents
GET    http://localhost:3001/knowledge-bases/{kbId}/documents
DELETE http://localhost:3001/knowledge-bases/{kbId}/documents/{documentId}
POST   http://localhost:3001/knowledge-bases/{kbId}/query
```

### Existing Endpoints

```
GET    http://localhost:3001/health
GET    http://localhost:3001/profile
PUT    http://localhost:3001/profile
POST   http://localhost:3001/items
GET    http://localhost:3001/items
PUT    http://localhost:3001/items/{itemId}
DELETE http://localhost:3001/items/{itemId}
POST   http://localhost:3001/webhook/twilio
```

## How to Start the Server

### Option 1: Using the Startup Script (Recommended)

```bash
cd backend
./local-server.sh
```

### Option 2: Using npm

```bash
cd backend
npm run dev
```

### Option 3: Manual with Environment

```bash
cd backend
export $(cat .env.local | grep -v '^#' | xargs)
npx serverless offline start
```

## Testing the Server

### 1. Quick Health Check

```bash
curl http://localhost:3001/health
```

### 2. Test All KB Endpoints

```bash
# Get a JWT token first (from frontend or AWS Cognito)
./test-kb-endpoints.sh <your-jwt-token>
```

### 3. Use Postman

1. Import `postman-collection.json` into Postman
2. Set the `jwtToken` variable in the collection
3. Run requests individually or as a collection

### 4. Manual curl Examples

**List Knowledge Bases:**

```bash
curl -X GET http://localhost:3001/knowledge-bases \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Create Knowledge Base:**

```bash
curl -X POST http://localhost:3001/knowledge-bases \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test KB",
    "description": "Testing local server",
    "embeddingModel": "amazon.titan-embed-text-v2:0",
    "llmModel": "eu.amazon.nova-lite-v1:0"
  }'
```

**Query Knowledge Base:**

```bash
curl -X POST http://localhost:3001/knowledge-bases/KB_ID/query \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is this about?",
    "modelId": "eu.amazon.nova-lite-v1:0",
    "k": 5
  }'
```

## Important Notes

### Real AWS Resources

The local server connects to **real AWS resources** in the dev environment:

- ✅ DynamoDB tables
- ✅ S3 buckets
- ✅ SQS queues
- ✅ Bedrock models
- ✅ Cognito authentication

**This means:**

- Documents you upload will be stored in real S3
- Indexing will trigger real SQS messages and Lambda invocations
- Queries will use real FAISS indexes from S3
- All data persists in DynamoDB

### Authentication Required

All KB endpoints (except health check) require a valid Cognito JWT token. Get one by:

1. Running the frontend and signing in
2. Copying the `idToken` from browser localStorage
3. Using AWS CLI to authenticate

### Hot Reload

serverless-offline supports hot reload. Changes to Lambda code will be automatically picked up without restarting the server.

### Logs

All Lambda logs appear in your terminal where you started the server. Much easier than checking CloudWatch!

## Next Steps

1. **Start the server**: `./local-server.sh`
2. **Get a JWT token**: Sign in via the frontend
3. **Test endpoints**: Use curl, Postman, or the test script
4. **Integrate with frontend**: Update frontend API base URL to `http://localhost:3001`
5. **Monitor logs**: Watch terminal output for debugging

## Troubleshooting

### Port 3001 Already in Use

Edit `serverless.yml`:

```yaml
custom:
  serverless-offline:
    httpPort: 3003 # Change to any available port
```

### Missing Dependencies

```bash
npm install
pip install -r requirements.txt
```

### AWS Credentials Error

Ensure `~/.aws/credentials` has the `mia40` profile:

```ini
[mia40]
aws_access_key_id = YOUR_KEY
aws_secret_access_key = YOUR_SECRET
```

### Import Errors

Make sure you're using Python 3.13:

```bash
python --version  # Should show 3.13.x
pyenv local 3.13.0  # If using pyenv
```

## Files Created

- ✅ `package.json` - Updated with serverless-offline
- ✅ `serverless.yml` - Updated with offline config
- ✅ `.env.local` - Local environment variables
- ✅ `local-server.sh` - Startup script
- ✅ `test-kb-endpoints.sh` - Testing script
- ✅ `postman-collection.json` - Postman collection
- ✅ `LOCAL_DEVELOPMENT.md` - Detailed guide
- ✅ `README.md` - Updated main README
- ✅ `LOCAL_SERVER_SETUP.md` - This file

## Success Indicators

When the server starts successfully, you should see:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   GET  | http://localhost:3001/health                                  │
│   POST | http://localhost:3001/knowledge-bases                         │
│   GET  | http://localhost:3001/knowledge-bases                         │
│   ...                                                                   │
│                                                                         │
│   Server ready: http://localhost:3001 🚀                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

The local development server is now fully configured and ready to use! 🎉
