# Almabani Event-Driven Processing Deployment Guide

## 1. Architecture: Event-Driven Batch Processing

This deployment implements a **"Process & Die"** architecture using AWS Fargate and S3 Events. There is **no persistent server** running. The system only wakes up when a file is uploaded, processes it, and then terminates.

### Workflow
1.  **Frontend/User** uploads a file to the **S3 Bucket** (`AlmabaniData`) in the `input/` folder.
2.  **S3 Event Notification** triggers a lightweight **AWS Lambda** function.
3.  **Lambda** (`infra/lambdas/trigger.py`) inspection the file path and launches a **Fargate Task** (Docker Container) in a public subnet.
4.  **Fargate Container**:
    *   Downloads the file from S3.
    *   Fetches secrets (API Keys) securely from **AWS SSM Parameter Store**.
    *   Runs the `worker.py` script.
    *   Uploads the result back to S3.
    *   **Exits immediately**.

### Resources Created
| Resource | Purpose | Configuration |
| :--- | :--- | :--- |
| **VPC** | Network isolation | • **Public Subnets Only** (No NAT Gateway = Low Cost) |
| **ECS Cluster** | Logical grouping | • Fargate (Serverless) capacity provider |
| **Fargate Task** | Compute Unit | • **vCPU**: 1 vCPU<br>• **Memory**: 2 GB<br>• **Image**: Docker from ECR |
| **SSM Parameters** | Secrets Management | • Stores API Keys (OpenAI, Pinecone) |
| **Lambda** | Trigger | • Python script to launch tasks |
| **S3 Bucket** | Storage | • Event notifications on `input/` prefix |

---

## 2. Configuration & Secrets (AWS SSM)

Environment variables (API keys, model names) are **NOT** hardcoded in the deployment or container. They are stored in **AWS Systems Manager (SSM) Parameter Store**.

### **Managed Parameters**
The following parameters are stored at the path `/almabani/...`:
*   `OPENAI_API_KEY`
*   `OPENAI_EMBEDDING_MODEL`
*   `OPENAI_CHAT_MODEL`
*   `PINECONE_API_KEY`
*   `PINECONE_ENVIRONMENT`
*   `PINECONE_INDEX_NAME`

### **How to Update configuration**
You do **NOT** need to redeploy the stack to change an API key or switch models.

1.  Log in to the **AWS Console**.
2.  Navigate to **Systems Manager** > **Parameter Store**.
3.  Click on the parameter you want to change (e.g., `/almabani/OPENAI_CHAT_MODEL`).
4.  Click **Edit**, update the **Value**, and click **Save changes**.

**Effect**: The very next file uploaded will trigger a container that fetches this new value at startup.

---

## 3. Cost Analysis (Zero Idle Cost)

This architecture is optimized for minimal cost. You pay **only** for the seconds the container is running.

### **1. AWS Fargate (Compute)**
*   **Cost**: Per vCPU-hour + GB-hour.
*   **Rate** (eu-west-1): ~$0.04048 / vCPU-hour + ~$0.004445 / GB-hour.
*   **Job Cost Example**:
    *   If a file takes **5 minutes** to process:
    *   Compute: (1 vCPU * $0.04) * (5/60) ≈ $0.0033
    *   Memory: (2 GB * $0.004) * (5/60) ≈ $0.0007
    *   **Total per file**: **$0.004 USD** (less than half a cent).

### **2. Networking (Public Subnets)**
*   **NAT Gateway**: **None** ($0 cost).

### **Total Estimated Monthly Cost**
*   **Idle**: **$0.00**.
*   **Active**: **~$0.004 per file processed**.

---

## 4. Usage Instructions

### Deployment
To deploy this stack to your AWS account:

```bash
# 1. Install dependencies
pip install -r infra/requirements.txt

# 2. Bootstrap (if not done)
cdk bootstrap aws://239146712026/eu-west-1

# 3. Deploy
cdk deploy --app "python3 infra/app.py"
```
*Note: The first deployment populates SSM parameters using values from your local `backend/env` file.*

### How to Run a Job
**Bucket Name**: `almabanistack-almabanidataf54b245b-big4a9rsdgn2`

**1. Parse (Excel -> JSON)**:
*   Upload file to: `s3://almabanistack-almabanidataf54b245b-big4a9rsdgn2/input/parse/myfile.xlsx`
*   **Result**: `s3://almabanistack-almabanidataf54b245b-big4a9rsdgn2/output/indexes/myfile.json`

**2. Fill Rates (Excel -> Excel)**:
*   Upload file to: `s3://almabanistack-almabanidataf54b245b-big4a9rsdgn2/input/fill/myfile.xlsx`
*   **Result**: `s3://almabanistack-almabanidataf54b245b-big4a9rsdgn2/output/fills/myfile_filled.xlsx`

### Monitoring
*   **ECS Console**: View running tasks in `AlmabaniCluster`.
*   **Log Groups**: View logs in CloudWatch under `AlmabaniWorker`.
