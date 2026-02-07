
import sys
import os
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas/shared")))

# Mock Dependencies before import
sys.modules["shared.conversation_state"] = MagicMock()
sys.modules["shared.twilio_client"] = MagicMock()
sys.modules["shared.config_manager"] = MagicMock()

# Mock boto3
import boto3
boto3.resource = MagicMock()

from handlers.finalization_handler import handle_responsible_person, handle_responsible_person_selection
from handlers.data_collection_handlers import handle_remarks
from shared.config_manager import ConfigManager
from shared.conversation_state import ConversationState

def run_test():
    print("--- Verifying Responsible Person Flow ---")
    
    # Setup Mocks
    cm = MagicMock()
    ConfigManager.return_value = cm
    
    # Mock Project Configuration
    cm.get_options.side_effect = lambda key: {
        "PROJECTS": [
            {
                "id": "PROJ-1", 
                "name": "Project Alpha", 
                "responsible_persons": ["Alpha Eng 1", "Alpha Eng 2"]
            },
            {
                "id": "PROJ-2", 
                "name": "Project Beta", 
                "responsible_persons": ["Beta Eng 1"]
            }
        ],
        "RESPONSIBLE_PERSONS": ["Default Person 1"],
        "STAKEHOLDERS": ["Stakeholder 1"]
    }.get(key, [])

    state_manager = MagicMock()
    
    # Test 1: Handle Remarks -> Prompt with Project Specific List (Project Alpha)
    print("\nTest 1: Project-Specific Prompt")
    current_state = {
        "draftData": {"projectId": "PROJ-1"}
    }
    resp = handle_remarks("Some remarks", "123", state_manager, current_state)
    items = resp["interactive"]["items"]
    print(f"Items for PROJ-1: {[i['title'] for i in items]}")
    assert "Alpha Eng 1" in items[0]["title"]
    
    # Test 2: Handle vCard with Single Number
    print("\nTest 2: vCard Single Number")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "BEGIN:VCARD\nFN:John Doe\nTEL;CELL:+123456789\nEND:VCARD"
        
        resp = handle_responsible_person("", "123", state_manager, current_state, contact_vcard_url="http://vcard")
        
    # Check if state updated with resolved person
    # handle_responsible_person updates state to WAITING_FOR_NOTIFIED_PERSONS
    call_args = state_manager.update_state.call_args[1]
    print(f"State Update: {call_args['new_state']}")
    print(f"Resolved Data: {call_args['curr_data']}")
    assert call_args["new_state"] == "WAITING_FOR_NOTIFIED_PERSONS"
    assert "John Doe" in call_args["curr_data"]["responsiblePerson"]

    # Test 3: Handle vCard with Multiple Numbers
    print("\nTest 3: vCard Multiple Numbers")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "BEGIN:VCARD\nFN:Jane Smith\nTEL;CELL:+111\nTEL;WORK:+222\nEND:VCARD"
        
        resp = handle_responsible_person("", "123", state_manager, current_state, contact_vcard_url="http://vcard2")
        
    # Should resolve to SELECTION state
    call_args = state_manager.update_state.call_args[1]
    print(f"State Update: {call_args['new_state']}")
    assert call_args["new_state"] == "WAITING_FOR_RESPONSIBLE_PERSON_SELECTION"
    assert len(resp["interactive"]["items"]) == 2
    print("Prompted for Selection")

    # Test 4: Handle Selection
    print("\nTest 4: Selection of Number")
    selection_state = {
        "contactName": "Jane Smith",
        "contactPhones": ["+111", "+222"],
        "draftData": {"projectId": "PROJ-1"}
    }
    resp = handle_responsible_person_selection("sel_contact_1", "123", state_manager, selection_state)
    
    # Should resolve to NOTIFIED PERSONS
    call_args = state_manager.update_state.call_args[1]
    print(f"State Update: {call_args['new_state']}")
    print(f"Resolved Data: {call_args['curr_data']}")
    assert call_args["new_state"] == "WAITING_FOR_NOTIFIED_PERSONS"
    assert "+222" in call_args["curr_data"]["responsiblePerson"]

    print("\n--- Responsible Person Flow Verified ---")

if __name__ == "__main__":
    run_test()
