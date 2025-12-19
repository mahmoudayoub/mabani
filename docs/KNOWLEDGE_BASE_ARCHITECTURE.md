# Knowledge Base Architecture

This document outlines all Lambda functions and AWS services involved in the Knowledge Base (KB) feature.

## Overview

The Knowledge Base system uses a **serverless architecture** with Lambda functions, SQS for asynchronous processing, DynamoDB for metadata storage, S3 for document storage and FAISS indexes, and API Gateway for REST endpoints.

---

## Lambda Functions

### 1. **KnowledgeBaseFunction** (`functions/knowledge_bases/kb_handler.py`)

**Purpose**: Manage knowledge base CRUD operations

**API Endpoints**:

- `GET /knowledge-bases` - List all KBs for the user
- `POST /knowledge-bases` - Create a new KB
- `GET /knowledge-bases/{kbId}` - Get KB details
- `PUT /knowledge-bases/{kbId}` - Update KB metadata
- `DELETE /knowledge-bases/{kbId}` - Delete KB and all associated resources

**AWS Services Used**:

- **DynamoDB**:
  - `KnowledgeBasesTable` - Store KB metadata (name, description, embedding model, document count, etc.)
  - `KBSharesTable` - Check shared KBs during deletion
- **S3**:
  - `KnowledgeBaseBucket` - Delete all documents, chunks, and FAISS indexes when deleting KB

**Key Operations**:

- Create KB with embedding model selection
- Delete KB with comprehensive cleanup (S3 files, DynamoDB records, FAISS indexes)
- Update KB metadata
- List KBs filtered by user ownership or shared access

---

### 2. **DocumentFunction** (`functions/documents/document_handler.py`)

**Purpose**: Manage document uploads and lifecycle

**API Endpoints**:

- `POST /knowledge-bases/{kbId}/upload-url` - Generate presigned S3 upload URL
- `POST /knowledge-bases/{kbId}/documents` - Confirm upload and trigger indexing
- `GET /knowledge-bases/{kbId}/documents` - List all documents in a KB
- `DELETE /knowledge-bases/{kbId}/documents/{documentId}` - Delete document

**AWS Services Used**:

- **S3**:
  - Generate presigned URLs for direct client uploads
  - Store uploaded documents
- **DynamoDB**:
  - `DocumentsTable` - Store document metadata (filename, status, size, S3 key, etc.)
  - `KnowledgeBasesTable` - Increment document count and update KB stats
  - `KBSharesTable` - Verify access permissions
- **SQS**:
  - `IndexingQueue` - Send async indexing job messages after upload confirmation

**Key Operations**:

- Generate presigned S3 URLs for secure direct uploads
- Create document records in DynamoDB with status "pending"
- Send indexing job to SQS queue (triggers IndexingWorkerFunction)
- Update document status to "processing"
- Delete documents and their associated S3 files and indexes

**Flow**:

```
1. Client requests upload URL
2. Lambda generates presigned S3 URL
3. Client uploads directly to S3
4. Client confirms upload via API
5. Lambda creates DynamoDB record
6. Lambda sends message to SQS queue
7. IndexingWorkerFunction processes asynchronously
```

---

### 3. **IndexingWorkerFunction** (`functions/indexing/indexing_worker.py`)

**Purpose**: Asynchronously process documents and create FAISS vector indexes

**Trigger**: **SQS Queue** (event-driven, not API Gateway)

**Configuration**:

- **Timeout**: 900 seconds (15 minutes) - Max Lambda timeout
- **Memory**: 3008 MB (3 GB) - For FAISS operations
- **Ephemeral Storage**: 10 GB - For temporary files during processing
- **Batch Size**: 1 - Process one document at a time

**AWS Services Used**:

- **SQS**:
  - `IndexingQueue` - Receive indexing job messages
- **S3**:
  - `KnowledgeBaseBucket` - Download original documents
  - Store processed chunks and FAISS indexes
- **DynamoDB**:
  - `DocumentsTable` - Update document status (processing → completed/failed)
  - `KnowledgeBasesTable` - Retrieve KB embedding model
- **Bedrock**:
  - Embedding models (e.g., `amazon.titan-embed-text-v2:0`) - Convert text to vectors

**Key Operations**:

1. **Extract text** from documents (PDF, DOCX, TXT) using PyPDF2, python-docx
2. **Split text** into chunks using langchain-text-splitters
3. **Generate embeddings** using Bedrock embedding models
4. **Create/update FAISS index** with new vectors
5. **Store chunks and indexes** in S3
6. **Update document status** in DynamoDB

**Error Handling**:

- Failed messages go to **Dead Letter Queue (DLQ)** after 3 retries
- Document status set to "failed" on permanent errors
- Extensive logging for debugging

---

### 4. **QueryFunction** (`functions/query/query_handler.py`)

**Purpose**: Perform RAG (Retrieval Augmented Generation) queries on knowledge bases

**API Endpoints**:

- `POST /knowledge-bases/{kbId}/query` - Query KB with user question

**Configuration**:

- **Timeout**: 300 seconds (5 minutes)
- **Memory**: 3008 MB (3 GB) - For FAISS operations

**AWS Services Used**:

- **DynamoDB**:
  - `KnowledgeBasesTable` - Get KB metadata and embedding model
  - `KBSharesTable` - Verify user has access (owner or shared)
- **S3**:
  - `KnowledgeBaseBucket` - Download FAISS index and chunk files
- **Bedrock**:
  - Embedding models - Convert query text to vector
  - LLM models (Claude, etc.) - Generate final answer using retrieved context

**RAG Flow**:

```
1. User sends query question
2. Convert query to embedding vector using Bedrock
3. Load FAISS index from S3
4. Perform similarity search to find top K relevant chunks
5. Retrieve chunk text from S3
6. Build prompt with context chunks
7. Invoke LLM (Claude/Anthropic) with prompt
8. Return LLM response with source citations
```

**Key Operations**:

- Verify KB access permissions
- Load FAISS index from S3 into memory
- Vector similarity search to find relevant chunks
- Construct RAG prompt with retrieved context
- Invoke Bedrock LLM for final answer generation
- Return response with source document citations

---

### 5. **KBShareFunction** (`functions/kb_shares/share_handler.py`)

**Purpose**: Manage knowledge base sharing between users

**API Endpoints**:

- `POST /knowledge-bases/{kbId}/shares` - Share KB with another user
- `GET /knowledge-bases/{kbId}/shares` - List all shares for a KB
- `DELETE /knowledge-bases/{kbId}/shares/{shareId}` - Revoke share

**AWS Services Used**:

- **DynamoDB**:
  - `KnowledgeBasesTable` - Verify KB ownership
  - `KBSharesTable` - Store share records (kbId, shareId, sharedWith, permission level)

**Key Operations**:

- Create share records linking KB to user email
- Verify ownership before allowing shares
- List shares (view who has access)
- Delete shares (revoke access)

---

## AWS Services

### **API Gateway** (`ChatbotApi`)

- **Type**: REST API
- **Authentication**: Cognito User Pool (JWT tokens)
- **CORS**: Manual configuration with OPTIONS routes for preflight
- **Stage**: `prod`

### **DynamoDB Tables**

#### 1. `KnowledgeBasesTable` (`bedrock-chatbot-knowledge-bases`)

- **Primary Key**: `userId` (HASH), `kbId` (RANGE)
- **GSI**: `OwnerIndex` on `userId`
- **Stores**: KB metadata (name, description, embedding model, document count, created date, etc.)

#### 2. `DocumentsTable` (`bedrock-chatbot-documents`)

- **Primary Key**: `kbId` (HASH), `documentId` (RANGE)
- **GSI**: `StatusIndex` on `kbId` and `status` (for querying processing documents)
- **Stores**: Document metadata (filename, file type, size, S3 key, status, created date, etc.)

#### 3. `KBSharesTable` (`bedrock-chatbot-kb-shares`)

- **Primary Key**: `kbId` (HASH), `shareId` (RANGE)
- **GSI**: `SharedWithIndex` on `sharedWith` (email) and `kbId`
- **Stores**: Share records (sharedWith email, permission level, created date)

### **S3 Bucket** (`bedrock-chatbot-kb-{accountId}`)

**Structure**:

```
{KB_BUCKET_NAME}/
├── documents/
│   └── {kbId}/
│       └── {documentId}/
│           └── {filename}  # Original uploaded file
├── chunks/
│   └── {kbId}/
│       └── {documentId}/
│           └── chunks.json  # Text chunks with metadata
└── indexes/
    └── {kbId}/
        └── index.faiss  # FAISS vector index
        └── index.json   # Index metadata (vector count, dimension)
```

### **SQS Queues**

#### 1. `IndexingQueue` (`bedrock-chatbot-indexing-queue`)

- **Purpose**: Asynchronously trigger document indexing
- **Visibility Timeout**: 900 seconds (15 minutes) - Matches Lambda timeout
- **Message Retention**: 14 days
- **Long Polling**: 20 seconds
- **Dead Letter Queue**: After 3 failed attempts, messages go to DLQ

**Message Format**:

```json
{
  "kbId": "uuid",
  "documentId": "uuid",
  "s3Key": "documents/kbId/documentId/filename.pdf",
  "filename": "document.pdf",
  "fileType": "application/pdf",
  "userId": "cognito-user-id",
  "embeddingModel": "amazon.titan-embed-text-v2:0"
}
```

#### 2. `IndexingDeadLetterQueue`

- **Purpose**: Store failed indexing jobs for manual investigation
- **Message Retention**: 14 days

### **Bedrock Models**

#### Embedding Models:

- `amazon.titan-embed-text-v2:0` - Convert text to 1024-dimensional vectors

#### LLM Models (via QueryFunction):

- Anthropic Claude models (Claude 3.5 Sonnet, etc.)
- Any text-generation model available in Bedrock

---

## Lambda Layers

### 1. **DependenciesLayer** (`layers/`)

**Purpose**: Shared dependencies for all Lambda functions
**Dependencies**:

- `boto3`
- `requests`
- Shared utilities (response formatting, etc.)

### 2. **KBProcessingLayer** (`kb_processing_layer/`)

**Purpose**: FAISS and document processing libraries
**Dependencies**:

- `numpy==1.24.3`
- `packaging==23.2`
- `faiss-cpu==1.7.4`
- `PyPDF2==3.0.1`
- `python-docx==1.1.0`
- `lxml==4.9.3`
- `langchain-text-splitters==0.2.0`
- `tiktoken==0.7.0`

---

## Complete Flow Diagrams

### Document Upload & Indexing Flow

```
┌─────────┐
│ Client  │
└────┬────┘
     │ 1. POST /knowledge-bases/{kbId}/upload-url
     ▼
┌─────────────────────┐
│ DocumentFunction    │
│ (Generate presigned │
│  S3 upload URL)     │
└────┬────────────────┘
     │ 2. Return presigned URL
     ▼
┌─────────┐
│ Client  │
└────┬────┘
     │ 3. PUT to S3 (direct upload)
     ▼
┌─────────┐
│   S3    │
│ Bucket  │
└─────────┘
     │
     │ 4. POST /knowledge-bases/{kbId}/documents
     ▼
┌─────────────────────┐
│ DocumentFunction    │
│ (Confirm upload)    │
└────┬────────────────┘
     │ 5. Create DynamoDB record (status: pending)
     │ 6. Send message to SQS
     ▼
┌─────────┐      ┌──────────────────────┐
│   SQS   │─────▶│ IndexingWorkerFunction│
│ Queue   │      │ (Event-triggered)    │
└─────────┘      └────┬─────────────────┘
                      │ 7. Download from S3
                      ▼
                 ┌─────────┐
                 │   S3    │
                 │ Bucket  │
                 └────┬────┘
                      │
                      │ 8. Extract text, split chunks
                      │ 9. Generate embeddings (Bedrock)
                      │ 10. Create/update FAISS index
                      │ 11. Store chunks & index in S3
                      ▼
                 ┌──────────────────────┐
                 │ IndexingWorkerFunction│
                 │ (Update status)      │
                 └────┬─────────────────┘
                      │ 12. Update DynamoDB (status: completed)
                      ▼
                 ┌──────────┐
                 │DynamoDB  │
                 │Documents │
                 │  Table   │
                 └──────────┘
```

### Query/RAG Flow

```
┌─────────┐
│ Client  │
└────┬────┘
     │ POST /knowledge-bases/{kbId}/query
     │ { "query": "What is...?" }
     ▼
┌─────────────────────┐
│   QueryFunction     │
│ (RAG Handler)       │
└────┬────────────────┘
     │ 1. Verify access (DynamoDB)
     │ 2. Get KB metadata (DynamoDB)
     │ 3. Convert query to embedding (Bedrock)
     │ 4. Load FAISS index from S3
     ▼
┌─────────┐
│   S3    │
│ Bucket  │
└────┬────┘
     │
     │ 5. Vector similarity search
     │ 6. Retrieve top K chunks
     ▼
┌─────────────────────┐
│   QueryFunction     │
│ (Build RAG prompt)  │
└────┬────────────────┘
     │ 7. Construct prompt with context
     │ 8. Invoke LLM (Bedrock Claude)
     ▼
┌──────────┐
│ Bedrock  │
│   LLM    │
└────┬─────┘
     │ 9. Return answer
     ▼
┌─────────┐
│ Client  │
│(Answer +│
│Sources) │
└─────────┘
```

---

## Notes

### **No Step Functions**

The architecture does **NOT** use AWS Step Functions. The asynchronous flow is handled by **SQS → Lambda** event triggers.

### **No EventBridge**

The architecture does **NOT** use Amazon EventBridge. Direct SQS → Lambda integration is used.

### **Error Handling**

- **SQS Dead Letter Queue**: Failed indexing jobs after 3 retries
- **DynamoDB Status Tracking**: Documents have status field (pending → processing → completed/failed)
- **Lambda Error Responses**: All Lambda functions return structured error responses via API Gateway

### **Scalability**

- **SQS**: Handles message queuing and retries automatically
- **Lambda**: Auto-scales based on SQS queue depth
- **DynamoDB**: Pay-per-request mode, auto-scales
- **S3**: Unlimited storage, high durability

### **Security**

- **Cognito Authentication**: All API endpoints require valid JWT tokens (except OPTIONS)
- **IAM Policies**: Least-privilege access for each Lambda function
- **S3 Presigned URLs**: Secure direct uploads without exposing bucket
- **Access Control**: KB-level sharing with permission checks

---

## Summary

**5 Lambda Functions** for KB operations:

1. `KnowledgeBaseFunction` - KB CRUD
2. `DocumentFunction` - Document upload management
3. `IndexingWorkerFunction` - Async document processing
4. `QueryFunction` - RAG queries
5. `KBShareFunction` - Sharing management

**4 AWS Services**:

1. **DynamoDB** - Metadata storage (3 tables)
2. **S3** - Document and index storage
3. **SQS** - Async job queue
4. **Bedrock** - Embeddings and LLM inference

**2 Lambda Layers**:

1. `DependenciesLayer` - Shared utilities
2. `KBProcessingLayer` - FAISS and document processing

**No Step Functions, EventBridge, or other orchestration services** - Pure serverless with SQS event triggers.
