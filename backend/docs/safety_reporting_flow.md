# Safety Reporting Workflow Documentation

## Overview

This document outlines the end-to-end technical flow of the Safety Reporting System via WhatsApp. The system allows users to report safety observations by sending an image and answering a series of questions. It leverages AWS Lambda, DynamoDB, Bedrock (AI), and Twilio.

## Architecture Components

*   **Twilio**: WhatsApp messaging provider.
*   **API Gateway**: Exposes the webhook endpoint.
*   **Lambda Functions**:
    *   `twilioWebhook`: Entry point, verifies request and pushes to queue.
    *   `workflowWorker`: Async worker processing the conversation logic.
*   **SQS**: `SafetyWorkflowQueue` decouples ingestion from processing.
*   **DynamoDB**:
    *   `ReportsTable` (PK=`STATE#...`): Stores temporary conversation state.
    *   `ReportsTable` (PK=`REPORT#...`): Stores finalized reports.
    *   `ReportsTable` (PK=`CONFIG`): Stores dynamic options (Taxonomy, Locations).
*   **Amazon Bedrock**:
    *   `amazon.nova-pro-v1:0` (Vision): Image analysis.
    *   `amazon.nova-lite-v1:0` (Text): Classification mapping and safety advice.
*   **S3**: Stores uploaded images and Knowledge Base embeddings.

---

## Detailed Flow

### 1. Message Ingestion
1.  **User** sends a message (Text or Image) to the Twilio WhatsApp number.
2.  **Twilio** attempts to send this to the configured Webhook URL.
3.  **`twilioWebhook` Lambda** receives the payload.
    *   **Validation**: Verifies the Twilio signature (`X-Twilio-Signature`) to ensure authenticity.
    *   **Queueing**: Extracts `From`, `Body`, and `MediaUrl` and pushes a message to **SQS** (`SafetyWorkflowQueue`).
    *   **Response**: Returns `200 OK` (TwiML empty response) to Twilio immediately.

### 2. Workflow Processing (Async)
The **`workflowWorker` Lambda** polls the SQS queue.

1.  **State Retrieval**:
    *   Worker extracts the user's phone number.
    *   Calls `ConversationState.get_state(phone_number)` to load current context from DynamoDB.
    *   Determines `currentState` (e.g., `None`, `WAITING_FOR_LOCATION`).

2.  **Handler Dispatch**:
    Based on the current state and input type, the worker routes execution to specific handlers:

    *   **Reset/Cancel**: If user says "stop", "reset", state is cleared.
    *   **New Report** (`currentState` is `None`):
        *   Triggered if input contains an Image.
        *    Calls `handle_start`.

### 3. Step-by-Step Handlers

#### A. Start / Image Analysis (`start_handler.py`)
*   **Image Processing**:
    *   Downloads image from Twilio.
    *   Uploads to public **S3** bucket (`taskflow-backend-dev-reports`).
    *   Generates separate `s3://` (internal) and `https://` (public) URLs.
*   **AI Classification**:
    *   Fetches **Hazard Taxonomy** (A/B/C list) from `ConfigManager` (DynamoDB).
    *   Calls **Bedrock (Nova Pro)** with image and taxonomy.
    *   Returns:
        *   `Observation Type` (e.g., "Unsafe Condition").
        *   `Detailed Classification` (e.g., "A15 Working at Height").
*   **State Update**: Saves draft data and transitions to `WAITING_FOR_LOCATION`.
*   **User Response**: "I identified a *Unsafe Condition* related to *A15 Working at Height*. Is this correct?"

#### B. Location & Classification Verification (`data_collection_handlers.py`)
*   **Location**: User selects or types location. Saved to state.
*   **Classification Correction**:
    *   User replies "Yes" -> Keeps AI result.
    *   User replies with Code (e.g., "A1") -> Updates to "A1 Confined Spaces".
    *   User replies with Text (e.g., "Dust") -> Calls **Bedrock (Nova Lite)** to smartly map "Dust" to "B4 Dust Suppression".
*   **Breach Source**: User identifies who caused the issue.

#### C. Severity & Safety Advice (`severity_handler.py`)
*   **Severity Input**: User selects High/Medium/Low.
*   **RAG Check (Knowledge Base)**:
    *   System queries the stored documents/embeddings (FAISS) using the classification and severity as search terms.
    *   Retrieves relevant safety protocol snippets.
*   **AI Advice**:
    *   Calls **Bedrock** with the snippets to generate specific `Control Measure` advice (limit 1-2 sentences).
*   **State Update**: Saves `controlMeasure` and `reference` source.

#### D. Finalization (`finalization_handler.py`)
*   **Stop Work**: Checks if immediate stop is needed.
*   **Responsible Person**: Captures name.
*   **Save Report**:
    *   Generates unique `reportId`.
    *   Writes full JSON record to **DynamoDB** (`PK=REPORT#...`).
*   **Final Summary**:
    *   Constructs a formatted WhatsApp message with:
        *   Hazard Type
        *   Severity
        *   Control Measures (AI recommended)
        *   Image Link
    *   Sends to User via **Twilio API**.
*   **Cleanup**: Calls `state_manager.clear_state()` to end session.

---

## Data Models

**DynamoDB Report Item Structure:**
```json
{
  "PK": "REPORT#<uuid>",
  "SK": "METADATA",
  "reportNumber": 101,
  "status": "OPEN",
  "phoneNumber": "+1234567890",
  "observationType": "Unsafe Condition",
  "classification": "A15 Working at Height",
  "location": "Site Office",
  "severity": "High",
  "controlMeasure": "Ensure harness is worn at all times.",
  "reference": "Safety Manual pg 42",
  "imageUrl": "https://...",
  "s3Url": "s3://...",
  "completedAt": "2023-10-27T10:00:00Z"
}
```

## Logging
*   All steps log to **CloudWatch Logs** (`/aws/lambda/taskflow-backend-dev-workflowWorker`).
*   Logs include incoming events, state transitions, AI responses, and any errors.

## Error Handling
*   **Retry Logic**: SQS handles retries for failed worker executions.
*   **User Feedback**: If a fatal error occurs in logic, the worker attempts to send a "Sorry, internal error" message to the user.
*   **State Fallback**: If inputs are invalid (e.g., wrong code), handlers return a specific prompt asking the user to try again without advancing the state.
