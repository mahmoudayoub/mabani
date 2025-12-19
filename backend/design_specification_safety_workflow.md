# Design Specification: Interactive Safety Reporting Workflow

## 1. Overview
This document specifies the technical design for the "Interactive Safety Reporting Agent". The system transforms the current one-way reporting endpoint into a stateful, conversational AI agent capable of gathering detailed safety data, validating inputs, and providing real-time safety advice using the Knowledge Base.

## 2. Infrastructure Changes (`serverless.yml`)

### 2.1. New DynamoDB Table: `ConversationsTable`
Used to maintain the state of the user's interaction. This allows the Lambda to "remember" the context of the conversation across multiple WhatsApp messages.

*   **Resource Name**: `ConversationsTable`
*   **Table Name**: `${self:service}-${self:provider.stage}-conversations`
*   **Primary Key**:
    *   `PK` (Partition Key): `PHONE#{phoneNumber}` (e.g., `PHONE#+1234567890`)
*   **Attributes**:
    *   `currentState` (String): The current step in the workflow (e.g., `WAITING_FOR_LOCATION`).
    *   `reportId` (String): ID of the report currently being created.
    *   `draftData` (Map): Accumulates data as it is collected (e.g., `{ "location": "Building A", "severity": "HIGH" }`).
    *   `lastMessageId` (String): To prevent duplicate processing.
    *   `expiresAt` (Number): TTL timestamp (e.g., 24 hours) to auto-clean old sessions.

### 2.2. IAM Permissions
The `twilioWebhook` function requires expanded permissions:
*   `dynamodb:GetItem/PutItem/UpdateItem` on `ConversationsTable`.
*   `bedrock:InvokeModel` (already exists).
*   `bedrock:Retrieve` (for Knowledge Base queries).

### 2.3. Environment Variables
*   `CONVERSATIONS_TABLE`: Reference to the new table.
*   `KNOWLEDGE_BASE_ID`: ID of the AWS Bedrock Knowledge Base to query for safety checks.

## 3. Data Flow & Logic

### 3.1. State Machine Definitions
The `twilioWebhook` will act as a state machine dispatcher.

| State | Trigger (User Input) | System Action | Next State | Response Template |
| :--- | :--- | :--- | :--- | :--- |
| **(None)** | Image + Text | 1. Initialize `draftData`.<br>2. Call Bedrock Vision to classify image.<br>3. Save draft. | `WAITING_FOR_CONFIRMATION` | "I've identified a potential **[Classification]**. Is this correct?" |
| **WAITING_FOR_CONFIRMATION** | "Yes" | 1. Update `draftData.classification`. | `WAITING_FOR_LOCATION` | "Great. Please provide the specific **location** of this observation." |
| **WAITING_FOR_CONFIRMATION** | "No" | 1. Retrieve list of classifications. | `WAITING_FOR_CLASSIFICATION_SELECTION` | "Please select the correct category from the list below:<br>1. Electrical<br>2. Working at Height<br>..." |
| **WAITING_FOR_LOCATION** | Text (Location) | 1. Update `draftData.location`. | `WAITING_FOR_OBSERVATION_TYPE` | "What type of observation is this? (e.g., Unsafe Act, Unsafe Condition, Near Miss)" |
| **WAITING_FOR_OBSERVATION_TYPE** | Text (Type) | 1. Update `draftData.observationType`. | `WAITING_FOR_BREACH_SOURCE` | "Who or what is the source of this breach? (e.g., Subcontractor X, Equipment Y)" |
| **WAITING_FOR_BREACH_SOURCE** | Text (Source) | 1. Update `draftData.source`. | `WAITING_FOR_SEVERITY` | "How would you rate the severity? (Low, Medium, High)" |
| **WAITING_FOR_SEVERITY** | Text (Severity) | 1. Update `draftData.severity`.<br>2. **KB QUERY**: Query Knowledge Base using `"{Classification} handling procedure"`. | `WAITING_FOR_STOP_WORK` | "Based on the safety manual, [KB_Excerpt].<br>Do you need to stop work immediately?" |
| **WAITING_FOR_STOP_WORK** | "Yes"/"No" | 1. Update `draftData.stopWork`. | `WAITING_FOR_RESPONSIBLE_PERSON` | "Who is the responsible person for this area? (Name or Phone)" |
| **WAITING_FOR_RESPONSIBLE_PERSON** | Text (Name) | 1. Update `draftData.responsiblePerson`. | `COMPLETED` | *Final Summary Message (See Section 4)* |

### 3.2. Knowledge Base Integration (Twilio/Bedrock)
When the user provides severity, the system performs a RAG (Retrieval-Augmented Generation) lookup:
1.  **Query**: `"{Classification} safety protocol severity {Severity}"`
2.  **Context**: Retrieved chunks from the Safety Manual.
3.  **Prompt**: "Given the user observed a [Classification] of [Severity] severity, and the safety manual says [Context], should they stop work? Output a brief advice string."
4.  **Result**: The advice is prepended to the "Do you need to stop work?" question.

## 4. Final Output Specification

### 4.1. WhatsApp Final Response
Once the workflow is `COMPLETED`, the user receives:

```text
✅ Observation Logged Successfully

🆔 Report #: 1024
📍 Location: Building A, Floor 2
🚧 Type: Unsafe Condition (Electrical)
⚠️ Severity: High
👤 Responsible: John Doe
🛑 Work Stopped: Yes

The safety team has been notified. Thank you for maintaining a safe site!
```

### 4.2. Stored Record (`ReportsTable`)
The final JSON object stored in the main `ReportsTable`:

```json
{
  "PK": "REPORT#uuid-1234",
  "SK": "METADATA",
  "reportId": "uuid-1234",
  "reportNumber": 1024,
  "status": "OPEN",
  "timestamp": "2025-12-13T10:00:00Z",
  "reporter": "+1234567890",
  "data": {
    "classification": "Electrical Hazard",
    "location": "Building A, Floor 2",
    "observationType": "Unsafe Condition",
    "breachSource": "Exposed Wiring",
    "severity": "HIGH",
    "stopWork": true,
    "responsiblePerson": "John Doe",
    "aiAnalysis": {
      "imageCaption": "Exposed wires hanging from ceiling",
      "kbAdvice": "Electrical faults require immediate isolation."
    }
  }
}
```

## 5. API Changes

### 5.1. `POST /webhook/twilio`
*   **Existing**: Accepts raw form data, triggers async process.
*   **New**:
    1.  Parse `From` (Phone Number).
    2.  `DynamoDB.GetItem(PK=PHONE#{From})` to get state.
    3.  Switch Logic based on state.
    4.  Execute Bedrock calls (Vision or Text).
    5.  `DynamoDB.PutItem` to update state and draft data.
    6.  Return TwiML response immediately.

## 6. Implementation Checklist
1.  [ ] **Serverless.yml**: Add `ConversationsTable`.
2.  [ ] **Serverless.yml**: Add IAM roles for `twilioWebhook`.
3.  [ ] **Code**: Create `lambdas/shared/conversation_state.py` (Helper for DB ops).
4.  [ ] **Code**: Update `lambdas/twilio_webhook.py` to implement the Dispatcher.
5.  [ ] **Code**: Create `lambdas/handlers/` directory for individual state handlers (cleaner code structure).
