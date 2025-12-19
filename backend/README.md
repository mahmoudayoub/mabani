# TaskFlow Backend

Serverless backend for TaskFlow intelligent task management platform with Knowledge Base (RAG) capabilities.

## Features

- 🔐 **Cognito Authentication** - Secure user authentication and authorization
- 📊 **Task Management** - CRUD operations for tasks and items
- 👤 **User Profiles** - User profile management
- 📱 **WhatsApp Integration** - H&S Quality report processing via Twilio
- 🧠 **Knowledge Base (RAG)** - Document upload, indexing, and intelligent querying
  - PDF, DOCX, and TXT support
  - FAISS vector search
  - AWS Bedrock integration (Nova models)
  - Conversation history support
  - Optimistic locking for concurrent updates

## Architecture

### Lambda Functions

#### Core Functions

- `healthCheck` - Health check endpoint
- `getUserProfile` - Get user profile
- `updateUserProfile` - Update user profile
- `createItem` - Create task item
- `getUserItems` - List user items
- `updateItem` - Update task item
- `deleteItem` - Delete task item

#### Knowledge Base Functions

- `listKnowledgeBases` - List user's knowledge bases
- `createKnowledgeBase` - Create new KB
- `getKnowledgeBase` - Get KB details
- `updateKnowledgeBase` - Update KB settings
- `deleteKnowledgeBase` - Delete KB and all resources
- `generateKnowledgeBaseUploadUrl` - Get S3 presigned URL for document upload
- `confirmKnowledgeBaseDocument` - Confirm upload and trigger indexing
- `listKnowledgeBaseDocuments` - List documents in a KB
- `deleteKnowledgeBaseDocument` - Delete a document
- `queryKnowledgeBase` - RAG query with conversation history
- `knowledgeBaseIndexingWorker` - SQS-triggered document processor

#### Integration Functions

- `twilioWebhook` - WhatsApp webhook handler
- `reportProcessor` - H&S report processor

### AWS Resources

#### DynamoDB Tables

- `taskflow-backend-dev-table` - Main application data
- `taskflow-backend-dev-reports` - H&S quality reports
- `taskflow-backend-dev-user-projects` - User project mappings
- `taskflow-backend-dev-knowledge-bases` - KB metadata
- `taskflow-backend-dev-documents` - Document metadata

#### S3 Buckets

- `taskflow-backend-dev-reports` - H&S report images
- `taskflow-backend-dev-kb` - KB documents, chunks, and FAISS indexes

#### SQS Queues

- `taskflow-backend-dev-kb-indexing` - Document indexing queue
- `taskflow-backend-dev-kb-indexing-dlq` - Dead letter queue

## Local Development

### Prerequisites

- Python 3.13 (via pyenv)
- Node.js 18+
- AWS CLI configured with `mia40` profile
- AWS credentials with access to dev resources

### Quick Start

```bash
# Install dependencies
npm install
pip install -r requirements.txt

# Start local development server
./local-server.sh

# Or use npm
npm run dev
```

The server will start on **http://localhost:3001**

See [Local Development Guide](../docs/LOCAL_DEVELOPMENT.md) for detailed instructions.

### Testing

The test suite is organized into unit, integration, and e2e tests. See [tests/README.md](tests/README.md) for detailed documentation.

```bash
# Run all tests
npm test

# Run specific test types
npm run test:unit          # Unit tests (fast, isolated)
npm run test:integration    # Integration tests (requires serverless-offline)
npm run test:e2e            # End-to-end tests (requires deployed AWS)

# Run with coverage
npm run test:coverage

# Test KB endpoints with curl
./test-kb-endpoints.sh <your-jwt-token>

# Import Postman collection
# File: postman-collection.json
```

## Deployment

### Deploy All Functions

```bash
# Set Cognito User Pool ARN
export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"

# Deploy
npm run deploy
```

### Deploy Single Function

```bash
npx serverless deploy function --function <function-name>
```

## API Endpoints

### Production

```
https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev
```

### Local Development

```
http://localhost:3001
```

### Knowledge Base Endpoints

All KB endpoints require authentication via Cognito JWT token.

```
GET    /knowledge-bases                           - List KBs
POST   /knowledge-bases                           - Create KB
GET    /knowledge-bases/{kbId}                    - Get KB
PUT    /knowledge-bases/{kbId}                    - Update KB
DELETE /knowledge-bases/{kbId}                    - Delete KB
POST   /knowledge-bases/{kbId}/upload-url         - Get upload URL
POST   /knowledge-bases/{kbId}/documents          - Confirm document
GET    /knowledge-bases/{kbId}/documents          - List documents
DELETE /knowledge-bases/{kbId}/documents/{docId}  - Delete document
POST   /knowledge-bases/{kbId}/query              - Query KB (RAG)
```

See [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) for detailed API documentation and examples.

## Knowledge Base Features

### Document Processing

- **Supported formats**: PDF, DOCX, TXT
- **Chunking**: RecursiveCharacterTextSplitter with semantic separators
- **Chunk size**: 1000 tokens with 200 token overlap
- **Metadata**: Page numbers, source file, token counts

### Vector Search

- **Engine**: FAISS (Facebook AI Similarity Search)
- **Embeddings**: Amazon Titan Embed Text v2
- **Distance metric**: L2 (Euclidean)
- **Configurable threshold**: Filter results by similarity

### RAG (Retrieval Augmented Generation)

- **LLM Models**: Amazon Nova (Pro, Lite, Micro)
- **Cross-region support**: us-east-1, eu-central-1, me-central-1
- **Conversation history**: Last 5 turns
- **Citation tracking**: Source references with page numbers
- **Strict boundaries**: Only answers from KB context

### Concurrency Control

- **Optimistic locking**: Prevents race conditions during index updates
- **Retry logic**: Linear backoff with jitter (5 attempts)
- **Lock TTL**: 300 seconds (5 minutes)

## Environment Variables

```bash
# AWS Configuration
AWS_REGION=eu-west-1
AWS_PROFILE=mia40

# DynamoDB Tables
DYNAMODB_TABLE_NAME=taskflow-backend-dev-table
REPORTS_TABLE=taskflow-backend-dev-reports
USER_PROJECT_TABLE=taskflow-backend-dev-user-projects
KB_TABLE_NAME=taskflow-backend-dev-knowledge-bases
DOCS_TABLE_NAME=taskflow-backend-dev-documents

# S3 Buckets
REPORTS_BUCKET=taskflow-backend-dev-reports
KB_BUCKET_NAME=taskflow-backend-dev-kb

# SQS Queues
INDEXING_QUEUE_URL=https://sqs.eu-west-1.amazonaws.com/239146712026/taskflow-backend-dev-kb-indexing

# Bedrock Models
BEDROCK_MODEL_ID=eu.amazon.nova-lite-v1:0
BEDROCK_VISION_MODEL_ID=eu.amazon.nova-pro-v1:0

# Twilio
TWILIO_PARAMETER_PATH=/mabani/twilio

# Cognito
COGNITO_USER_POOL_ARN=arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M
```

## Project Structure

```
backend/
├── lambdas/                    # Lambda function handlers
│   ├── items.py               # Task item handlers
│   ├── user_profile.py        # Profile handlers
│   ├── knowledge_bases.py     # KB CRUD handlers
│   ├── kb_documents.py        # Document management handlers
│   ├── kb_query.py            # RAG query handler
│   ├── kb_indexing_worker.py  # Document indexing worker
│   ├── twilio_webhook.py      # WhatsApp webhook
│   ├── report_processor.py    # H&S report processor
│   └── shared/                # Shared utilities
│       ├── lambda_helpers.py  # Common Lambda utilities
│       ├── kb_repositories.py # DynamoDB repositories
│       ├── document_processing.py # Document extraction & chunking
│       ├── faiss_utils.py     # FAISS index management
│       ├── dynamic_bedrock.py # Bedrock client
│       ├── s3_client.py       # S3 utilities
│       └── validators.py      # Input validation
├── tests/                     # Test files
├── serverless.yml             # Serverless Framework config
├── requirements.txt           # Python dependencies
├── package.json               # Node.js dependencies
├── local-server.sh            # Local dev server script
├── test-kb-endpoints.sh       # KB endpoint test script
├── postman-collection.json    # Postman API collection
├── .env.local                 # Local environment config
├── LOCAL_DEVELOPMENT.md       # Local dev guide
└── README.md                  # This file
```

## Dependencies

### Python

- `boto3` - AWS SDK
- `pydantic` - Data validation
- `PyPDF2` - PDF processing
- `python-docx` - DOCX processing
- `langchain-text-splitters` - Text chunking
- `tiktoken` - Token counting
- `numpy` - Numerical operations
- `faiss-cpu` - Vector search
- `python-jose` - JWT handling
- `requests` - HTTP client

### Node.js

- `serverless` - Deployment framework
- `serverless-python-requirements` - Python dependency packaging
- `serverless-offline` - Local development server

## Troubleshooting

### Import Errors

```bash
pip install -r requirements.txt
```

### Port Already in Use

Edit `serverless.yml` and change `httpPort` in the `serverless-offline` config.

### AWS Credentials

Ensure `~/.aws/credentials` has the `mia40` profile configured.

### FAISS Installation

FAISS requires numpy. If you encounter issues:

```bash
pip install numpy==1.26.4 faiss-cpu==1.9.0.post1
```

## Documentation

- [Local Development Guide](../docs/LOCAL_DEVELOPMENT.md)
- [Backend Structure](../docs/BACKEND_STRUCTURE.md)
- [Backend Deployment](../docs/BACKEND_DEPLOYMENT.md)
- [Knowledge Base Architecture](../docs/KNOWLEDGE_BASE_ARCHITECTURE.md)
- [Deployment Guide](../docs/DEPLOYMENT_GUIDE_HS_QUALITY.md)
- [Testing Guide](../docs/TESTING_GUIDE.md)
- [Twilio WhatsApp Setup](../docs/TWILIO_WHATSAPP_SETUP.md)
- [Troubleshooting](../docs/DEBUG_TIPS.md)

## License

Proprietary - All rights reserved
