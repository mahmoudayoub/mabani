# Health & Safety Interactive Reporting Process

This document outlines the end-to-end interactive workflow for the Safety Reporting Assistant. It describes how site personnel report issues via WhatsApp and how the AI Assistant guides them through the process to ensure complete and accurate data collection.

## 1. Process Overview

The system acts as a smart digital assistant that is available 24/7. Instead of filling out complex forms, users simply send a photo, and the AI engages in a conversation to gather all necessary details. This ensures that every report is standardized, accurate, and actionable.

---

## 2. Interactive Workflow Steps

The reporting process follows a natural conversation flow. The system moves through specific "Wait States" as it gathers information.

### Step 1: Initial Report
*   **User Action:** The user takes a photo of a hazard or safety issue and sends it to the dedicated WhatsApp number.
*   **System Action:** The AI analyzes the image and generates a hazard classification.
*   **System Status:** Enters `WAITING_FOR_CONFIRMATION`
*   **Response:** "I've identified a potential **Electrical Hazard**. Is this correct?"

### Step 2: Confirmation & Classification
*   **User Action:** Confirms with "Yes" or corrects with "No".
*   **System Action:** Locks in the hazard category.
*   **System Status:** Enters `WAITING_FOR_LOCATION`
*   **Response:** "Great. Please provide the specific **location** of this observation."

### Step 3: Location Details
*   **User Action:** User types the location (e.g., "Building A, 2nd Floor").
*   **System Action:** Records location data.
*   **System Status:** Enters `WAITING_FOR_OBSERVATION_TYPE`
*   **Response:** "What type of observation is this? (e.g., Unsafe Act, Unsafe Condition...)"

### Step 4: Observation Type
*   **User Action:** User specifies the type.
*   **System Action:** Categorizes the nature of the observation.
*   **System Status:** Enters `WAITING_FOR_BREACH_SOURCE`
*   **Response:** "Who or what is the source of this breach?"

### Step 5: Identifying the Source
*   **User Action:** User identifies the responsible party.
*   **System Action:** Records the source entity.
*   **System Status:** Enters `WAITING_FOR_SEVERITY`
*   **Response:** "How would you rate the severity? (Low, Medium, High)"

### Step 6: Severity & Safety Advice
*   **User Action:** User selects the severity level.
*   **System Action:** AI retrieves specific safety protocols based on severity and hazard type.
*   **System Status:** Enters `WAITING_FOR_STOP_WORK`
*   **Response:** "[Safety Advice]. **Do you need to stop work immediately?**"

### Step 7: Responsible Person & Finalization
*   **User Action:** Confirms stop work status and provides supervisor name.
*   **System Action:** Finalizes the data collection.
*   **System Status:** Enters `WAITING_FOR_RESPONSIBLE_PERSON` (Internal check before closing)
*   **Response:** Final Summary Report.

---

## 3. Final Output & Logging

Once the conversation is complete, the system automatically generates a formal report and saves it to the central dashboard.

### The Final Report Includes:
*   **Digital Log ID:** A unique reference number for tracking.
*   **Photo Evidence:** The original image submitted by the user.
*   **Categorization:** Verified hazard type and risk level.
*   **Safety Control:** The specific safety advice provided by the system.
*   **Status:** Automatically marked as "OPEN" for the safety team to review.

### Business Value
*   **Speed:** Reporting takes less than a minute.
*   **Accuracy:** AI ensures reports are correctly classified, reducing human error.
*   **Compliance:** Immediate access to safety protocols ensures on-site decisions align with regulations.
*   **Zero-Training:** Users don't need to learn a new app; they just use WhatsApp.
