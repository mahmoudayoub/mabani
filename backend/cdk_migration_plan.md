# Migration Plan: Serverless Framework to AWS CDK

## 1. Executive Summary
This document outlines the effort and changes required to migrate the backend infrastructure from **Serverless Framework** to **AWS Cloud Development Kit (CDK)**. The goal is to consolidate the infrastructure-as-code (IaC) into a single TypeScript-based CDK project, eliminating the dependency on Serverless Framework (YAML).

**Estimated Effort:** ~1 week (3-5 days)
**Complexity:** Medium-High (due to number of functions and stateful resources)

---

## 2. Current Architecture vs. Target Architecture

### Current State (Mixed)
- **Infrastructure**: Split between CDK (`infrastructure/cdk`) and Serverless Framework (`backend/serverless.yml`).
- **Lambda Management**: Serverless Framework handles packaging, layers, and deployment.
- **Resources Managed by Serverless**:
  - 6 DynamoDB Tables
  - 2 S3 Buckets
  - 2 SQS Queues
  - 1 API Gateway (RestApi)
  - ~20 Lambda Functions
- **Resources Managed by CDK**:
  - Cognito User Pool & Client
  - Frontend S3 Bucket & CloudFront

### Target State (Pure CDK)
- **Infrastructure**: All resources defined in `infrastructure/cdk` using TypeScript.
- **Lambda Management**: CDK handles packaging (via `aws-lambda-python-alpha` or Docker bundling).
- **Consolidated Stacks**:
  - `AuthStack` (Cognito - existing)
  - `DatabaseStack` (DynamoDB - new)
  - `StorageStack` (S3 - new)
  - `BackendStack` (Lambdas, API Gateway, SQS - update existing)

---

## 3. Detailed Migration Steps

### Phase 1: Stateful Resources (Critical)
*Objective: Define databases and buckets in CDK to match existing production resources.*

1.  **DynamoDB Tables**:
    -   Define the following tables in a new `DatabaseStack` construct:
        -   `MainTable` (PK, SK, GSI1)
        -   `ReportsTable` (PK, SK, GSI1, GSI2)
        -   `UserProjectTable` (phoneNumber)
        -   `KnowledgeBasesTable` (userId, kbId + indexes)
        -   `DocumentsTable` (kbId, documentId + indexes)
        -   `ConversationsTable` (PK + TTL)
    -   **Migration Strategy**:
        -   *Option A (Greenfield)*: Deploy new tables. **Data loss**.
        -   *Option B (Import)*: Use `cdk import` to bring existing tables under CDK management.

2.  **S3 Buckets**:
    -   Define `ReportsBucket` and `KnowledgeBaseBucket` in CDK.
    -   Implement Lifecycle Rules and CORS policies matching `serverless.yml`.

### Phase 2: Compute & Integration
*Objective: Port Lambda functions and API Gateway.*

1.  **Lambda Layers**:
    -   Replace `serverless-python-requirements` with CDK bundling.
    -   **Action**: Create a `PythonLayerVersion` construct that uses Docker to install `requirements.txt` (specifically for `numpy` and `faiss-cpu`).

2.  **Lambda Functions**:
    -   Migrate 20+ functions from `serverless.yml` to CDK `backend-stack.ts`.
    -   Map definitions:
        -   **Handler**: Update path mapping.
        -   **Timeout/Memory**: Copy settings (e.g., `kb_indexing_worker` needs 900s timeout, 3008MB memory).
        -   **Permissions**: Convert IAM statements to `function.addToRolePolicy()`.
        -   **Environment Variables**: Map constructs (Table Names, ARNs) directly to env vars.

3.  **SQS Queues**:
    -   Define `KnowledgeBaseIndexingQueue` and its DLQ in CDK.
    -   Add `SqsEventSource` to `knowledgeBaseIndexingWorker` lambda.

4.  **API Gateway**:
    -   The existing `MabaniApi` in `backend-stack.ts` is a good start.
    -   Add `LambdaIntegration` for all HTTP events defined in `serverless.yml`.
    -   Ensure CORS settings match (some endpoints have `cors: true`).

### Phase 3: Missing Pieces & Cleanup
1.  **Step Functions**:
    -   The `serverless.yml` IAM policy references `stateMachine`-`report-workflow`.
    -   **Action**: Locate the definition. If it doesn't exist, remove the permission. If it does, define `StateMachine` in CDK.

2.  **Clean Up**:
    -   Remove `serverless.yml`.
    -   Remove `node_modules` related to Serverless Framework.

---

## 4. Development Workflow Changes

| Feature | Serverless Framework | AWS CDK |
| :--- | :--- | :--- |
| **Code Definition** | YAML | TypeScript (Type-safe) |
| **Local Dev** | `serverless offline` | `sam local` or `cdk watch` (hotswap) |
| **Deployment** | `sls deploy` | `cdk deploy` |
| **Dependency Bundling**| Plugin (Dockerized) | Native/Construct (Dockerized) |

## 5. Risk Assessment
-   **Data Migration**: If existing tables are not correctly imported, there is a risk of data loss or resource duplication.
-   **Dependencies**: `numpy` and `faiss` are architecture-sensitive. CDK bundling must use the correct Amazon Linux 2/2023 Docker image to ensure compatibility.
-   **Downtime**: Switching API Gateway endpoints will result in a URL change unless a Custom Domain is used.
