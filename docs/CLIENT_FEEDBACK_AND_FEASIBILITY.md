# Client Feedback Analysis & Feasibility Report

**Date**: 2026-01-26
**Version**: 1.0

## Executive Summary
This document provides a technical evaluation of the feedback received. Most requests are feasible with low-to-medium risk. The primary challenges are **Response Latency** (requires architectural optimization) and **WhatsApp UI Limitations** (requires workaround UX designs). A new Project Selection step is confirmed as a critical gap.

---

## Technical Feasibility by Item

### 1. Change "AlMabani" to "Almabani"
*   **Feasibility**: ✅ **High** (Trivial)
*   **Analysis**: This is a simple string replacement in the configuration or frontend display. 
*   **Finding**: Codebase currently uses "Almabani" in `config_manager.py`. The "AlMabani" spelling might be appearing in:
    *   Hardcoded logic in older handlers.
    *   Pre-defined prompt templates passed to the AI.
    *   Frontend dashboard labels (if applicable).
*   **Action**: Global find-and-replace in the entire codebase.

### 2. Chatbot Response Time Optimization
*   **Feasibility**: ⚠️ **Medium** (Requires optimization)
*   **Analysis**: 
    *   **Diagnosis**: Currently, the system performs sequential operations: `S3 Upload` -> `Bedrock Captioning` -> `Bedrock Classification` -> `Bedrock Hazard Type`. This serial chain causes high latency (potential 10-15s delay).
    *   **Proposed Solution**: 
        1.  **Parallel Execution**: Run `Observation Type` and `Hazard Category` classifications in parallel using `asyncio`.
        2.  **Optimized Models**: Switch to faster models (e.g., Claude 3 Haiku or Nova Micro) for the initial classification steps.
        3.  **Loading Indicator**: Send a "Working on it..." acknowledgement immediately (though WhatsApp has limits on message spam, a visible status update helps perceived latency).
*   **Risk**: Faster models might be slightly less accurate, requiring prompt tuning.

### 3. Project Selection Step
*   **Feasibility**: ✅ **High**
*   **Analysis**: This is a missing step in the current state machine.
*   **Proposed Implementation**:
    *   Add `WAITING_FOR_PROJECT` state between `Start` and `Location` (or `Start` and `Confirmation`).
    *   Add `PROJECTS` list to `ConfigManager`.
    *   **Default Selection**: Store the last selected `projectId` in the user's DynamoDB profile (`UserProfileTable`). Auto-select or offer "Last Project (X)" as the first option.

### 4. Split Observation Type from Category
*   **Feasibility**: ✅ **High**
*   **Analysis**: Current flow combines them ("I saw a Unsafe Act related to Falls"). If one is wrong, the user rejects both.
*   **Proposed Implementation**:
    *   **Decoupled Flow**: 
        1.  AI proposes Type (UA/UC) and Category (Falls).
        2.  Ask: "Is it a **Unsafe Act**?" (Yes/No).
        3.  Ask: "Is it related to **Falls**?" (Yes/No).
    *   **Alternate**: Present them as an editable summary: "Type: UA, Category: Falls. Reply '1' to change Type, '2' to change Category, 'OK' to confirm."

### 5. Smart Re-classification (Exclude "Other")
*   **Feasibility**: ✅ **High**
*   **Analysis**: Client wants to avoid "Other" being the AI's fallback suggestion when the User rejects the primary suggestion.
*   **Proposed Implementation**:
    *   When user says "No" to the initial prediction, the system currently fallback to a generic static list.
    *   **Smart Fallback**: Instead of a static list, ask the AI to "List the top 5 likely categories *excluding* the one just rejected".
    *   Explicitly filter "Other" from the options unless confidence is extremely low.

### 6. Retrieval of Corrective Actions (RAG Quality)
*   **Feasibility**: ⚠️ **Medium** (Data Dependency)
*   **Analysis**: 
    *   Current implementation uses a basic similarity search (FAISS) which may return irrelevant chunks.
    *   Client assumes it's a "procedure mapping" issue.
*   **Proposed Solution**:
    *   **Metadata Filtering**: Tag every chunk in the Vector DB with its `Category` (e.g., "Working at Height").
    *   **Filtered Search**: When querying, filter *only* for chunks matching the identified category. This guarantees that "Working at Height" observations only retrieve "Working at Height" procedures.

### 7. Free-text Optional Remark
*   **Feasibility**: ✅ **High**
*   **Analysis**: Simple additions to the state machine.
*   **Proposed Implementation**:
    *   Before the final "Report Generated" message, add a step `WAITING_FOR_REMARKS`.
    *   Prompt: "Any additional instructions or remarks? (Reply with text or 'Skip')".

### 8. Error: Observation + Text - Photo
*   **Feasibility**: 🐛 **Bug Fix**
*   **Analysis**: The code currently treats an image message as a "Start" trigger. If text is sent *after* or *with* the image in a way that the webhook parses incorrectly, it might crash.
*   **Action**: Investigate `workflow_worker.py` logic for `media_url` vs `body_content` handling. Ensure mixed-content messages are handled robustly.

### 9. Urdu & Arabic Parsing
*   **Feasibility**: ⚠️ **Medium-High Expense**
*   **Analysis**: 
    *   **Input**: Bedrock models handle multi-language input natively. They can understand Urdu/Arabic instructions without changes.
    *   **Output**: Responses are hardcoded in English.
    *   **Implementation**: 
        *   Detect language (AI).
        *   Store `UserLanguage` preference.
        *   Use an AI translation layer or localized string tables for system responses.

### 10. WhatsApp List Limit (10 items)
*   **Feasibility**: 🛑 **Platform Constraint**
*   **Analysis**: WhatsApp Interactive Lists are strictly limited to 10 rows.
*   **Workarounds**:
    1.  **Pagination**: "Items 1-9" -> "Next Page". (Clunky UX).
    2.  **Search**: Ask user to "Type the first 3 letters of the name". System returns a dynamic list of matches.
    3.  **Groups**: Group by Department first (Civil, MEP, Safety) -> Then Person.

### 11. Cost Estimation
*   **Twilio**: ~$0.005 per message (varies by country/type). Conversation-based pricing applies (24-hour window).
*   **AWS Bedrock**:
    *   **Claude 3 Sonnet** (Analysis): ~$0.003 input / $0.015 output (per 1k tokens).
    *   **Claude 3 Haiku** (Faster/Cheaper): ~$0.00025 input / $0.00125 output.
*   **Estimate**:
    *   Per Report (~15 turns, 3 AI calls): ~$0.15 - $0.30 USD.
    *   **Recommendation**: Monitor costs during pilot. Optimize by using smaller models (Haiku) for classification and larger ones (Sonnet) only for complex RAG tasks.

---

## Next Steps
1.  **Immediate Fixes**: Correct "Almabani" typos and investigate the "Text+Photo" crash.
2.  **Core Updates**: Implement Project Selection and independent Observation Type classification.
3.  **Optimization**: Parallelize LLM calls to fix response time issues.
