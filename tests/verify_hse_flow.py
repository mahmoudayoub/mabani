
import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas/shared")))

# Mock external dependencies before importing handlers
sys.modules["shared.bedrock_client"] = MagicMock()
sys.modules["shared.s3_client"] = MagicMock()
sys.modules["shared.twilio_client"] = MagicMock()
sys.modules["shared.faiss_utils"] = MagicMock()
sys.modules["shared.kb_repositories"] = MagicMock()
sys.modules["shared.dynamic_bedrock"] = MagicMock()
sys.modules["boto3"] = MagicMock()
sys.modules["lambdas.handlers.safety_check_handler"] = MagicMock()
sys.modules["lambdas.handlers.safety_check_handler"].perform_safety_check.return_value = ("Always wear PPE", "Safety Manual Page 5")

# Mock ConfigManager and UserProjectManager
from shared.config_manager import ConfigManager
from shared.user_project_manager import UserProjectManager
from shared.conversation_state import ConversationState

# Setup Mock Clients
cm = MagicMock()
cm.get_options.side_effect = lambda key: {
    "PROJECTS": [{"id": "PROJ-001", "name": "Project Alpha", "locations": ["Site Office", "Zone A"]}],
    "LOCATIONS": ["General Site"],
    "BREACH_SOURCES": ["Subcontractor A", "Team B"],
    "RESPONSIBLE_PERSONS": ["Eng. John", "Supervisor Mike"],
    "STAKEHOLDERS": ["Manager Dave", "HSE Officer Sarah"],
    "HAZARD_TAXONOMY": [{"name": "Working at Height", "category": "A1"}, {"name": "Electrical", "category": "B2"}]
}.get(key, [])
ConfigManager.return_value = cm

upm = MagicMock()
upm.get_last_project.return_value = None
UserProjectManager.return_value = upm

# Local State Mock
state_store = {}
def mock_update_state(phone_number, new_state, curr_data=None):
    print(f"STATE UPDATE: {new_state} | Data: {curr_data}")
    state_store[phone_number] = {"currentState": new_state, "draftData": curr_data or {}}
    # Merge data
    if curr_data:
        existing = state_store.get(phone_number, {}).get("draftData", {})
        existing.update(curr_data)
        state_store[phone_number]["draftData"] = existing

def mock_get_state(phone_number):
    return state_store.get(phone_number)
    
def mock_clear_state(phone_number):
    print("STATE CLEARED")
    if phone_number in state_store:
        del state_store[phone_number]

def mock_start_conversation(phone_number, report_id, draft_data, start_state):
    print(f"START CONVERSATION: {start_state} | Report: {report_id}")
    state_store[phone_number] = {"currentState": start_state, "draftData": draft_data}

csm = MagicMock()
csm.update_state.side_effect = mock_update_state
csm.get_state.side_effect = mock_get_state
csm.clear_state.side_effect = mock_clear_state
csm.start_conversation.side_effect = mock_start_conversation
ConversationState.return_value = csm

# Mock Safety Check
sys.modules["handlers.safety_check_handler"] = MagicMock()
sys.modules["handlers.safety_check_handler"].perform_safety_check.return_value = ("Always wear PPE", "Safety Manual Page 5")

# Import Handlers
from handlers.start_handler import handle_start
from handlers.project_handler import handle_project_selection
from handlers.confirmation_handler import handle_confirmation, handle_category_confirmation
from handlers.data_collection_handlers import handle_location, handle_breach_source, handle_remarks
from handlers.severity_handler import handle_severity
import handlers.severity_handler
handlers.severity_handler.perform_safety_check = MagicMock(return_value=("Always wear PPE", "Safety Manual Page 5"))

from handlers.finalization_handler import handle_stop_work, handle_responsible_person, handle_notified_persons
from workflow_worker import handler as worker_handler

def run_simulation():
    phone = "1234567890"
    print("\n--- Starting Simulation ---\n")
    
    # 1. Start (Image Upload)
    print("1. User sends photo")
    # Mock Bedrock classification
    sys.modules["shared.bedrock_client"].BedrockClient().classify_observation_type.return_value = "Unsafe Act"
    sys.modules["shared.bedrock_client"].BedrockClient().classify_hazard_type.return_value = ["Working at Height", "Slip Hazard"]
    
    user_input = {"imageUrl": "http://example.com/photo.jpg", "description": "High work"}
    resp = handle_start(user_input, phone, csm)
    print(f"Bot: {resp['text'] if isinstance(resp, dict) else resp}")
    
    # 2. Select Project
    print("\n2. User selects Project")
    state_store[phone]["currentState"] = "WAITING_FOR_PROJECT" # Force state if not set by start
    resp = handle_project_selection("PROJ-001", phone, csm)
    print(f"Bot: {resp['text']}")
    
    # 3. Confirm Type (Yes)
    print("\n3. User confirms Type (Yes)")
    state_store[phone]["currentState"] = "WAITING_FOR_CONFIRMATION"
    resp = handle_confirmation("yes", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 4. Confirm Category (Yes)
    print("\n4. User confirms Category (Yes)")
    state_store[phone]["currentState"] = "WAITING_FOR_CATEGORY_CONFIRMATION"
    resp = handle_category_confirmation("yes", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 5. Location
    print("\n5. User sends Location")
    state_store[phone]["currentState"] = "WAITING_FOR_LOCATION"
    resp = handle_location("Zone A", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 6. Breach Source
    print("\n6. User selects Source")
    state_store[phone]["currentState"] = "WAITING_FOR_BREACH_SOURCE"
    resp = handle_breach_source("Subcontractor A", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 7. Severity
    print("\n7. User selects Severity")
    state_store[phone]["currentState"] = "WAITING_FOR_SEVERITY"
    resp = handle_severity("High", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 8. Stop Work
    print("\n8. User says Stop Work (Yes)")
    state_store[phone]["currentState"] = "WAITING_FOR_STOP_WORK"
    resp = handle_stop_work("yes", phone, csm)
    print(f"Bot: {resp['text']}")
    
    # 9. Remarks
    print("\n9. User adds Remarks")
    state_store[phone]["currentState"] = "WAITING_FOR_REMARKS" # Check verify if previous step set this
    resp = handle_remarks("Workers not wearing harness.", phone, csm)
    print(f"Bot: {resp['text']}")
    
    # 10. Responsible Person
    print("\n10. User selects Responsible Person")
    state_store[phone]["currentState"] = "WAITING_FOR_RESPONSIBLE_PERSON"
    resp = handle_responsible_person("Eng. John", phone, csm, state_store[phone])
    print(f"Bot: {resp['text']}")
    
    # 11. Notified Persons
    print("\n11. User selects Notified Person")
    state_store[phone]["currentState"] = "WAITING_FOR_NOTIFIED_PERSONS"
    resp = handle_notified_persons("Manager Dave", phone, csm, state_store[phone])
    print(f"Bot: {resp}\n") # This returns the final summary string
    
    print("--- Simulation Complete ---")

if __name__ == "__main__":
    run_simulation()
