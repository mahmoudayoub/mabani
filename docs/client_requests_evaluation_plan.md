# Client Requests Evaluation & Implementation Plan

This document outlines the evaluation of the 16 points requested by the client and the proposed implementation plan to address each of them across the backend lambdas and frontend management UI.

## Evaluation & Proposed Changes

### Workflow Routing & Flow logic
**Point 1: "When selecting change type before project, flow is skipping the change project step."**
- **Evaluation:** When a user selects "Change Type" during the first confirmation, the state transitions to `WAITING_FOR_OBSERVATION_TYPE`. After selecting a type, the handler incorrectly bypasses project confirmation and transitions directly to `WAITING_FOR_CATEGORY_CONFIRMATION`. 
- **Plan:** Update `handle_observation_type` in `data_collection_handlers.py` to route back to `WAITING_FOR_CONFIRMATION`, allowing the user to correctly confirm both the newly selected type and their project.


**Point 5: "Clicking next on sub-categories should not take you to a different main category."**
- **Evaluation:** I found a bug in `handle_classification_selection` where it attempts to read `parentCategory` from `state_item.get("currData")`. Since DynamoDB merges `currData` into `draftData`, `currData` is always `None` after the initial state transition, causing the category to fall back to the default `"Safety"`. 
- **Plan:** Update the state retrieval in `handle_classification_selection` to read `parentCategory` from `draftData`.

**Point 9 & 10: "Include the full list instead of projects by user."**
- **Evaluation:** Point 10 originally requested filtering the project list per-user because of the 10-item limit in Twilio interactive lists. Point 9 overrides this, noticing we implemented pagination ("Next" button), so we can just show the full list to everyone instead of building complex per-user filters. Currently `project_handler.py` has pagination, but `start_handler.py` (when a user has no previous project) simply limits to `projects[:10]` without a "Next" option.
- **Plan:** Add pagination logic to the initial project selection list in `start_handler.py` and ensure `project_handler.py` handles the full paginated list correctly. We will keep the "auto-suggest last project" feature since Point 10 asks to "confirm or change project".

### Content & Messaging Updates
**Point 2: "Random characters when selecting change type."**
- **Evaluation:** Double slashed newlines (`\\n\\n`) are hardcoded in the string payload returned by `handle_observation_type`.
- **Plan:** Fix the string formatting in `data_collection_handlers.py` replacing `\\n` with standard `\n` line breaks.

**Point 6: "Clarify to the user on the remark section..."**
- **Evaluation:** The current prompt just says "Do you have any additional remarks or details?".
- **Plan:** Update the text in `handle_stop_work` to: *"Do you have any additional remarks or details? Please type and send your remarks, or click 'No Remarks' if you do not have any."*

**Point 13: "Remove the send location option - keep only a drop list."**
- **Evaluation:** The text explicitly instructs the user they can use the Paperclip to share a native location.
- **Plan:** Remove the `(Paperclip -> Location)` instruction string in `handle_category_confirmation`.

**Point 16: "Responsible person and notified person to be swapped in final message."**
- **Evaluation:** The notification string order currently prints Responsible Person, then Notified Person.
- **Plan:** Reorder the string templating in `_save_final_report` (inside `finalization_handler.py`) to swap their order visually for the final WhatsApp message.

### Contact Handling & AI 
**Point 7 & 15 & 10: "Share multiple contacts for notified person", "Responsible phone number not recorded", "Phone number appeared in notified list"**
- **Evaluation:** `handle_notified_persons` currently does not accept `contact_vcard_url` (vCards). Additionally, the system doesn't gracefully loop for multiple notified persons. Furthermore, because of confusing prompts, users may share contacts at the wrong time, leading to mixed up variables in the final message.
- **Plan:** 
  - Update `handle_notified_persons` to process `contact_vcard_url` exactly like `handle_responsible_person`.
  - Add logic to allow the user to keep adding contacts until they press a `"Done"` button.
  - Review how the `responsiblePerson` phone string is being saved to ensure it natively flows cleanly into the DynamoDB `draftData` logs without stripping numbers.

**Point 8: "Explore the possibility of AI classifying severity"**
- **Evaluation:** Severity is currently manually selected by the user via High/Medium/Low buttons.
- **Plan:** We can inject an asynchronous call to Bedrock in `handle_breach_source` (or state transition) to analyze the observation description and predict the severity. We will then present the predicted severity to the user to either Confirm or Change, improving the speed of reporting.

### Frontend Enhancements
**Point 11: Export option for safety configuration**
- **Plan:** Add a "Download CSV" button in the React frontend admin portal to export the active safety configurations (Taxonomy, Projects, Personnel).

**Point 12 & 14: Batch import for names/numbers & edit project numbers**
- **Plan:** Add a CSV Upload feature in the React frontend to batch import Stakeholders and Responsible Persons. Also, implement an edit button on the project configuration table to allow adding/removing phone numbers easily over time.

## Verification Plan
1. **Automated Unit Context:** I will write targeted unit tests (via `pytest`) against `data_collection_handlers.py` and `confirmation_handler.py` to ensure the state dict perfectly transitions to `WAITING_FOR_CONFIRMATION` instead of `WAITING_FOR_CATEGORY_CONFIRMATION` on "Change Type" operations.
2. **State Transition Mock Tests:** Validate the `"parentCategory"` parsing fix by passing a mock DynamoDB `state_item` with `draftData` to verify it retains "Health" or "Environment" properly during pagination.
3. **Regex & Formatting Checks:** Manually assert string outputs from the patched lambdas.
4. **End-to-end Local Run:** Use a local mock wrapper script mimicking Twilio payloads to simulate a full conversation flow covering vCards and pagination to ensure the user isn't dropped into dead-ends.

## Prioritized Execution Plan (Quick Wins First)
Here is the ordered list of tasks, starting with the clearest, easiest fixes, and progressing to the larger or more complex workflow logic.

**Phase 1: Quick Formatting & Text Fixes (Easiest)**
1. **Point 2:** Fix `\\n` formatting bug in `handle_observation_type` payload (`backend/lambdas/handlers/data_collection_handlers.py`).
2. **Point 6:** Clarify the remark question text in `handle_stop_work` (`backend/lambdas/handlers/finalization_handler.py`).
3. **Point 13:** Remove the Paperclip hint string in `handle_category_confirmation` (`backend/lambdas/handlers/confirmation_handler.py`).
4. **Point 16:** Swap the physical string order of Responsible Person and Notified Person in `_save_final_report` (`backend/lambdas/handlers/finalization_handler.py`).

**Phase 2: Simple Logic Adjustments (Medium-Low Complexity)**
5. **Point 5:** Fix parent category state reference mapping bug from `currData` to `draftData` in `handle_classification_selection` (`backend/lambdas/handlers/confirmation_handler.py`).
6. **Point 9 & 10:** Add pagination to `start_handler.py` initial project list to natively handle more than 10 projects without filtering per-user.
7. **Point 1:** Fix the routing bug so that "Change Type" routes to `WAITING_FOR_CONFIRMATION` instead of `WAITING_FOR_CATEGORY_CONFIRMATION` in `handle_observation_type` (`backend/lambdas/handlers/data_collection_handlers.py`).

**Phase 3: Contacts & DynamoDB Variables (Medium Complexity)**
8. **Point 7, 10, 15:** Update `handle_notified_persons` to correctly parse vCard URLs the same way as responsible person, and ensure the phone number extraction logs correctly without clashing arrays in `finalization_handler.py`. Let user loop to add multiple notified contacts until they press "Done".

**Phase 4: AI & Frontend Builds (Highest Complexity)**
9. **Point 8:** Implement Bedrock AI severity classification injection into `handle_breach_source` transition step.
10. **Point 11:** Implement CSV Export for Safety Configurations globally on the Frontend.
11. **Point 12, 14:** Implement CSV Batch Import for Contacts and the add/remove modal interactions within project administration components on the React Frontend.
