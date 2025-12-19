# Health & Safety Reporting Workflow - Implementation Plan

## 1. Executive Summary
This document outlines the plan to implement the "Log Observation" workflow, transforming the current "fire-and-forget" reporting system into the interactive, state-aware AI Agent depicted in the provided requirements. The new system will use AWS Lambda, DynamoDB, and Amazon Bedrock to drive a conversational flow via WhatsApp (Twilio), enforcing data quality and providing real-time safety advice sourced from the Knowledge Base.

## 2. Requirement Analysis (Visual Workflow "A1")
The target workflow requires an **Interactive AI Agent** that guides the user through the following steps:
1.  **Capture**: User sends photo + description.
2.  **Analysis & Confirmation**: AI Classifies the breach and asks "Is this [Classification]?".
3.  **Correction**: If user says "No", AI provides a list of options.
4.  **Data Enrichment**: AI sequentially requests:
    -   Location
    -   Observation Type
    -   Breach Source
    -   Severity Level
5.  **Safety Advice**: **(Critical)** AI analyzes the situation (using Knowledge Base) and asks "Do you need to stop work?" or provides stop-work advice.
6.  **Responsibility**: Tag responsible person.
7.  **Finalization**: Log observation and tag status as open.

## 3. Current System vs. Target State

| Feature | Current State (`report_processor.py`) | Target State (Image Requirement) |
| :--- | :--- | :--- |
| **Interaction Model** | One-Way (Receive -> Process -> Reply Final) | Two-Way Conversational (Ask -> Reply -> Confirm -> Next Question) |
| **State Management** | Stateless (Fire-and-forget) | **Stateful** (Must remember "Waiting for Location", etc.) |
| **Classification** | Automatic (Bedrock decides) | **Interactive** (Bedrock suggests -> User Confirms/Corrects) |
| **Knowledge Base** | Not integrated in flow | **Integrated** (Retrieve data to analyze stop-work need) |
| **Data Collection** | Inferred from text/image | Explicitly solicited (Location, Responsible Person) |

## 4. Architecture Design

### 4.1. Infrastructure Components
*   **WhatsApp/Twilio**: User Interface.
*   **`twilioWebhook` Lambda**: The "Brain" of the conversation. It receives every message, checks the user's state, and decides the next response.
*   **`ConversationsTable` (DynamoDB)**: Stores the current step and accumulated data for each phone number.
*   **`KnowledgeBase`**: Source of truth for safety regulations (used for the "Stop Work" logic).
*   **`Bedrock` (AWS)**: 
    *   *Vision*: Analyze uploaded photos.
    *   *Text*: Extract intents ("Yes/No", "Location is X") and query KB.

### 4.2. Data Model (`ConversationsTable`)
*   **PK**: `PHONE#{phoneNumber}`
*   **Fields**:
    *   `state`: Current step (e.g., `WAITING_FOR_CONFIRMATION`, `WAITING_FOR_LOCATION`).
    *   `reportId`: Reference to the report being built.
    *   `cachedAnalysis`: Provisional classification data.
    *   `collectedData`: JSON object with `location`, `severity`, `source`, etc.
    *   `lastMessageTimestamp`: TTL management.

### 4.3. State Machine Logic
The conversation will follow this state flow:

1.  **`start`**: User sends Image/Text.
    *   *Action*: Invoke Bedrock (Analysis). Save draft.
    *   *Transition*: `WAITING_FOR_CONFIRMATION`.
    *   *Reply*: "I identified a [Hazard]. Is this correct?"
2.  **`WAITING_FOR_CONFIRMATION`**:
    *   *Input*: "Yes" or "No".
    *   *Action (Yes)*: Transition to `WAITING_FOR_LOCATION`. Reply: "Where did this happen?"
    *   *Action (No)*: Transition to `WAITING_FOR_CLASSIFICATION_SELECT`. Reply: "Please choose from output list..."
3.  **`WAITING_FOR_LOCATION`**:
    *   *Input*: Text (Location).
    *   *Action*: Save location. Transition to `WAITING_FOR_OBSERVATION_TYPE`.
4.  **... (Subsequent Steps for Type, Source, Severity)**
5.  **`WAITING_FOR_STOP_WORK_CHECK`**:
    *   *System Action*: **Query Knowledge Base** with `{Hazard} + {Severity}` to check Safety Manual policy.
    *   *Reply*: "Based on safety manual (KB), high severity electrical faults require immediate work stoppage. Do you need to stop work?"
6.  **`COMPLETED`**:
    *   *Action*: Finalize Report in `ReportsTable`. Notify Responsible Person.

## 5. Implementation Plan

### Phase 1: Infrastructure Setup
1.  **Update `serverless.yml`**:
    *   Add `ConversationsTable` definition (DynamoDB).
    *   Add permissions to `twilioWebhook` to Read/Write `ConversationsTable`.
    *   Ensure `twilioWebhook` has permissions to invoke Bedrock and Query KB.
2.  **Install Dependencies**:
    *   Add `twilio` to `requirements.txt` (currently manual HTTP requests are used; the official SDK is recommended for complex flows but existing client is fine if extended).

### Phase 2: Refactor `twilio_webhook` (The Dispatcher)
1.  **State Lookup**: At the start of `handler`, fetch the user's current state from `ConversationsTable`.
2.  **Dispatcher**: Switch logic based on `(CurrentState, IncomingInput)`.
    *   *If State is None*: Assume New Report.
    *   *If State Exists*: Route to specific handler function (e.g., `handle_confirmation`, `handle_location_input`).

### Phase 3: Implement "AI Agent" Logic
1.  **Image Analysis Step**: Reuse `bedrock_client.py` logic but return *provisional* data instead of saving the final report.
2.  **Interactive Handlers**: Implement functions to:
    *   Parse specific inputs (e.g., extracting "Building A" from "It was at Building A").
    *   Update `ConversationsTable` with new data.
    *   Generate the next question.
3.  **KB Integration**:
    *   In the "Stop Work" phase, use `kb_query.py` logic to semantic search the Safety Manual for the specific hazard.
    *   Inject the retrieved policy into the context of the question generated by Bedrock.

### Phase 4: Integration & Testing
1.  **Twilio Configuration**: Ensure the Webhook URL is updated in Twilio Console.
2.  **End-to-End Test**:
    *   Send Image -> Verify "Confirmation" response.
    *   Reply "Yes" -> Verify "Location" question.
    *   ...
    *   Verify final record in `ReportsTable`.

## 6. Next Steps
1.  **Approve this Plan**: Confirm the state machine complexity aligns with needs.
2.  **Execute Phase 1**: I can proceed to update `serverless.yml` and create the `ConversationsTable`.
