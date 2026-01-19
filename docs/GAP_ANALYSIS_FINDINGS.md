# Client Requirements Gap Analysis & Implementation Plan

**Date**: 2026-01-16
**Status**: Pending Implementation

## Executive Summary
Following a review of the "Golden Set" requirements against the current system state, the following functional gaps have been identified. These features are required to fully align with the client's expected workflow.

---

## 1. Project Selection Workflow
**Gap**: Missing a dedicated step for selecting the specific project context.
- **Current State**: Users select a "Location" (e.g., Main Building, Site Office), but the higher-level "Project" (e.g., Dubai Marina, Riyadh Metro) is not explicitly selected or stored.
- **Requirement**: Add a `WAITING_FOR_PROJECT` step to the WhatsApp workflow, likely after the Responsible Person step (or as per 10-step flow).
- **Action**: 
    - Create `handle_project_selection` in backend.
    - Add `PROJECTS` list to configuration.
    - Store `projectId` in report metadata.

## 2. Excel Export (Golden Set Format)
**Gap**: No facility to export logs from the frontend.
- **Current State**: Logs are viewable in the `SafetyLogs` table but cannot be downloaded.
- **Requirement**: Add an "Export to Excel" button that generates an `.xlsx` file with the exact 8 columns defined by the client:
    1. **Name** (Responsible Person/Reporter)
    2. **Observation** (Category Name)
    3. **Hazard Type** (UA/UC/nm)
    4. **Date and Time**
    5. **Project**
    6. **AI Proposed Mitigation** (HSG150)
    7. **Positive/Negative** (Derived from Type)
    8. **Image** (URL)
- **Action**: 
    - Implement `export_reports` Lambda endpoint.
    - Add "Export CSV/Excel" button to `SafetyLogs.tsx`.

## 3. Dynamic Supply Chain Lists
**Gap**: Lists for "Breach Source" and "Responsible Person" are static or placeholder-only.
- **Current State**: Users choose from generic "Almabani" vs "Subcontractor".
- **Requirement**: These must be **configurable lists** (Dynamic).
    - **Breach Sources**: Should list specific subcontractors (e.g., "Kone", "Schindler").
    - **Responsible Persons**: Should list key site contacts.
- **Action**: Update `ConfigManager` to support project-specific lists for `BREACH_SOURCES` and `RESPONSIBLE_PERSONS`.

## 4. Observation Type Timing
**Gap**: Sequence of the "Observation Type" question.
- **Current State**: AI predicts Observation Type (UA, UC, etc.) at the very start (Step 2) combined with Category confirmation.
- **Requirement**: The Golden Set workflow specifies asking for Observation Type **after** the Location step.
- **Action**: 
    - Decouple Observation Type from the initial AI confirmation.
    - Add an explicit `WAITING_FOR_OBSERVATION_TYPE` step after `WAITING_FOR_LOCATION`.

## 5. Safety Check "Gate"
**Gap**: Explicit confirmation step for "Stop Work".
- **Current State**: The system generates safety advice but flows directly into the "Stop Work" question.
- **Requirement**: Ensure the **Safety Check** (Immediate Action advice) is presented as a distinct "Gate" or information step *before* prompting for strict "Stop Work" confirmation.
- **Action**: Verify `finalization_handler` flow to ensure the Advice message is sent purely as info before the interactive Stoppage question.

---

## ✅ Completed / Verified Items
*   **Taxonomy Update**: The 56-category taxonomy (without A1/A2 codes in display names) is **already implemented** in the configuration.
*   **Multimedia Support**: Image handling and S3 storage are functioning.
*   **Interactive Maps**: Native Location sharing and Frontend Map visualization are **implemented**.
*   **Interactive Messages**: Button and List support is **implemented**.
