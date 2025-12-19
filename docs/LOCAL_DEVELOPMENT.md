# Local Development Guide

This guide explains how to run the TaskFlow backend locally for development and testing.

## Prerequisites

1. **Python 3.13** (via pyenv)
2. **Node.js** (v18+)
3. **AWS CLI** configured with `mia40` profile
4. **AWS credentials** with access to dev resources

## Setup

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install
```

### 2. Configure Environment

The `.env.local` file is already configured with the dev environment settings. If you need to modify any values, edit that file.

### 3. Start Local Server

```bash
# Option 1: Use the startup script
./local-server.sh

# Option 2: Use npm directly
npm run dev
```

The server will start on **http://localhost:3001**

## Knowledge Base Endpoints

All endpoints require a valid Cognito JWT token in the `Authorization` header.

### List Knowledge Bases

```bash
GET http://localhost:3001/knowledge-bases
Authorization: Bearer <your-jwt-token>
```

### Create Knowledge Base

```bash
POST http://localhost:3001/knowledge-bases
Authorization: Bearer <your-jwt-token>
Content-Type: application/json

{
  "name": "My Knowledge Base",
  "description": "Description of the KB",
  "embeddingModel": "amazon.titan-embed-text-v2:0",
  "llmModel": "eu.amazon.nova-lite-v1:0"
}
```

### Get Knowledge Base

```bash
GET http://localhost:3001/knowledge-bases/{kbId}
Authorization: Bearer <your-jwt-token>
```

### Update Knowledge Base

```bash
PUT http://localhost:3001/knowledge-bases/{kbId}
Authorization: Bearer <your-jwt-token>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description"
}
```

### Delete Knowledge Base

```bash
DELETE http://localhost:3001/knowledge-bases/{kbId}
Authorization: Bearer <your-jwt-token>
```

### Generate Upload URL

```bash
POST http://localhost:3001/knowledge-bases/{kbId}/upload-url
Authorization: Bearer <your-jwt-token>
Content-Type: application/json

{
  "filename": "document.pdf",
  "contentType": "application/pdf"
}
```

### Confirm Document Upload

```bash
POST http://localhost:3001/knowledge-bases/{kbId}/documents
Authorization: Bearer <your-jwt-token>
Content-Type: application/json

{
  "documentId": "doc-uuid",
  "filename": "document.pdf",
  "s3Key": "documents/user-id/kb-id/doc-uuid.pdf"
}
```

### List Documents

```bash
GET http://localhost:3001/knowledge-bases/{kbId}/documents
Authorization: Bearer <your-jwt-token>
```

### Delete Document

```bash
DELETE http://localhost:3001/knowledge-bases/{kbId}/documents/{documentId}
Authorization: Bearer <your-jwt-token>
```

### Query Knowledge Base (RAG)

```bash
POST http://localhost:3001/knowledge-bases/{kbId}/query
Authorization: Bearer <your-jwt-token>
Content-Type: application/json

{
  "query": "What is the main topic of the documents?",
  "modelId": "eu.amazon.nova-lite-v1:0",
  "k": 5,
  "history": [
    {
      "role": "user",
      "content": "Previous question"
    },
    {
      "role": "assistant",
      "content": "Previous answer"
    }
  ],
  "config": {
    "temperature": 0.7,
    "maxTokens": 2048,
    "topP": 0.9
  },
  "distanceThreshold": 1.0
}
```

## Testing with Real AWS Resources

The local server connects to **real AWS resources** in the dev environment:

- ✅ DynamoDB tables (dev)
- ✅ S3 buckets (dev)
- ✅ SQS queues (dev)
- ✅ Bedrock models
- ✅ Cognito authentication

This means:

- Documents you upload will be stored in the real S3 bucket
- Indexing will trigger real SQS messages and Lambda invocations
- Queries will use real FAISS indexes from S3

## Getting a Test JWT Token

### Option 1: From Frontend

1. Run the frontend locally: `cd frontend && npm run dev`
2. Sign in with a test user
3. Open browser DevTools → Application → Local Storage
4. Copy the `idToken` value

### Option 2: Using AWS CLI

```bash
aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id 2cdfcsipvcun3fd5if88atp925 \
  --auth-parameters USERNAME=test@example.com,PASSWORD=YourPassword123! \
  --profile mia40 \
  --region eu-west-1
```

## Testing the Indexing Worker

The indexing worker is triggered by SQS messages. To test it locally:

```bash
# Set environment variables
export KB_TABLE_NAME=taskflow-backend-dev-knowledge-bases
export DOCS_TABLE_NAME=taskflow-backend-dev-documents
export KB_BUCKET_NAME=taskflow-backend-dev-kb
export AWS_REGION=eu-west-1

# Run the worker with a test event
python -c "
import json
from lambdas.kb_indexing_worker import handler

event = {
    'Records': [{
        'body': json.dumps({
            'documentId': 'your-doc-id',
            'kbId': 'your-kb-id',
            'ownerId': 'your-user-id',
            's3Key': 'documents/user/kb/doc.pdf',
            'filename': 'doc.pdf'
        })
    }]
}

handler(event, None)
"
```

## Troubleshooting

### Port Already in Use

If port 3001 is already in use, edit `serverless.yml`:

```yaml
custom:
  serverless-offline:
    httpPort: 3003 # Change to any available port
```

### AWS Credentials

Ensure your `~/.aws/credentials` has the `mia40` profile:

```ini
[mia40]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```

### Python Dependencies

If you get import errors, ensure all dependencies are installed:

```bash
pip install -r requirements.txt
```

### FAISS Import Error

FAISS requires numpy. If you get import errors:

```bash
pip install numpy==1.26.4 faiss-cpu==1.9.0.post1
```

## Hot Reload

serverless-offline supports hot reload for Python Lambda functions. Changes to your Lambda code will be automatically picked up without restarting the server.

## Logs

All Lambda logs will appear in your terminal where you started the server. This makes debugging much easier than checking CloudWatch logs.

## Next Steps

- Test all KB endpoints with Postman or curl
- Integrate with the frontend
- Add more test cases
- Monitor CloudWatch logs for the indexing worker
