
import sys
import os
import io

# Modify path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock, patch

# Mock AWS and External Services before importing handlers
sys.modules["boto3"] = MagicMock()
sys.modules["botocore"] = MagicMock()
sys.modules["botocore.exceptions"] = MagicMock()

# Mock Shared Modules
mock_config_mgr = MagicMock()
mock_user_proj_mgr = MagicMock()
mock_bedrock = MagicMock()
mock_s3 = MagicMock()
mock_twilio = MagicMock()
mock_state_mgr = MagicMock()

with patch.dict(sys.modules, {
    "shared.config_manager": MagicMock(),
    "shared.user_project_manager": MagicMock(),
    "shared.bedrock_client": MagicMock(),
    "shared.s3_client": MagicMock(),
    "shared.twilio_client": MagicMock(),
    "shared.conversation_state": MagicMock(),
}):
    # Import Handlers (now using mocked dependencies if they import from shared)
    # But wait, the handlers import 'from shared...' so I need to make sure those are intercepted.
    pass

# We can manually mock the classes inside the handlers if needed, 
# or simpler: Just define the mocks and set them on the sys.modules
# The imports in the handlers are like:
# from shared.config_manager import ConfigManager

# Let's try to mock the specific classes
class MockConfigManager:
    def get_options(self, key):
        if key == "PROJECTS":
            return [
                {"id": "PROJ-A", "name": "Project Alpha", "locations": ["Alpha Loc 1", "Alpha Loc 2"]},
                {"id": "PROJ-B", "name": "Project Beta", "locations": ["Beta Loc 1"]}
            ]
        if key == "LOCATIONS":
            return ["Global Loc 1", "Global Loc 2"]
        if key == "HAZARD_TAXONOMY":
            return ["A1 Hazard"]
        return []

class MockUserProjectManager:
    def __init__(self, table=None): pass
    def get_last_project(self, phone):
        if phone == "CLIENT_RETURNING":
            return "PROJ-A"
        return None
    def set_last_project(self, phone, pid):
        print(f"  [DB] Saved Last Project for {phone}: {pid}")

class MockBedrockClient:
    def caption_image(self, **kwargs): return "A construction site"
    def classify_observation_type(self, **kwargs): return "Unsafe Act"
    def classify_hazard_type(self, **kwargs): return ["A1 Hazard"]

class MockS3Client:
    def upload_image(self, **kwargs): 
        return {
            "s3Key": "key",
            "s3Url": "s3://bucket/key",
            "httpsUrl": "https://bucket/key"
        }
    def download_image(self, key): return b"bytes"

class MockState:
    def __init__(self):
        self.state = {}
    def start_conversation(self, phone_number, report_id, draft_data, start_state):
        print(f"  [STATE] START: {start_state} data={draft_data}")
        self.state[phone_number] = {"state": start_state, "draftData": draft_data}
    def update_state(self, phone_number, new_state, curr_data=None):
        print(f"  [STATE] UPDATE: {new_state} data={curr_data}")
        if phone_number in self.state:
            self.state[phone_number]["state"] = new_state
            if curr_data:
                self.state[phone_number]["draftData"].update(curr_data)
    def get_state(self, phone_number):
        return self.state.get(phone_number)
    def clear_state(self, phone_number):
        print(f"  [STATE] CLEAR: {phone_number}")
        self.state.pop(phone_number, None)

# Apply Mocks globally
import builtins
# real_import = builtins.__import__
# def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
#     if "shared.config_manager" in name:
#         m = MagicMock()
#         m.ConfigManager = MockConfigManager
#         return m
#     return real_import(name, globals, locals, fromlist, level)
# builtins.__import__ = mock_import

# ... Actually, simpler to just start the handlers using the file content directly or importing after sys.modules patch.

# Patching sys.modules for 'shared' packages
m_conf = MagicMock()
m_conf.ConfigManager = MockConfigManager
sys.modules["shared.config_manager"] = m_conf
sys.modules["lambdas.shared.config_manager"] = m_conf

m_usr = MagicMock()
m_usr.UserProjectManager = MockUserProjectManager
sys.modules["shared.user_project_manager"] = m_usr
sys.modules["lambdas.shared.user_project_manager"] = m_usr

m_bed = MagicMock()
m_bed.BedrockClient = MockBedrockClient
sys.modules["shared.bedrock_client"] = m_bed
sys.modules["lambdas.shared.bedrock_client"] = m_bed

m_s3 = MagicMock()
m_s3.S3Client = MockS3Client
sys.modules["shared.s3_client"] = m_s3
sys.modules["lambdas.shared.s3_client"] = m_s3

m_state = MagicMock()
m_state.ConversationState = MockState # This might fail if we need an instance
sys.modules["shared.conversation_state"] = m_state
sys.modules["lambdas.shared.conversation_state"] = m_state


# NOW Import Handlers
from lambdas.handlers.start_handler import handle_start
from lambdas.handlers.project_handler import handle_project_selection
from lambdas.handlers.data_collection_handlers import handle_location

def run_test():
    print("=== TEST START ===")
    state_mgr = MockState() # Use the class directly
    
    # 1. NEW USER FLOW
    print("\n--- Test 1: New User (No history) ---")
    user_input = {"imageUrl": "http://img", "description": "test"}
    phone = "CLIENT_NEW"
    
    # START
    resp = handle_start(user_input, phone, state_mgr)
    print(f"Resp: {resp['text'] if isinstance(resp, dict) else resp[:50]}")
    
    # Verify State: Should be WAITING_FOR_PROJECT
    curr = state_mgr.get_state(phone)
    assert curr["state"] == "WAITING_FOR_PROJECT", f"Expected WAITING_FOR_PROJECT, got {curr['state']}"
    
    # PROJECT SELECTION
    print("\n[Input] 'Project Alpha'")
    resp = handle_project_selection("Project Alpha", phone, state_mgr)
    print(f"Resp: {resp['text']}")
    
    # Verify State: Should be WAITING_FOR_CONFIRMATION
    curr = state_mgr.get_state(phone)
    assert curr["state"] == "WAITING_FOR_CONFIRMATION", f"Expected WAITING_FOR_CONFIRMATION, got {curr['state']}"
    assert curr["draftData"]["projectId"] == "PROJ-A", "Project ID not set"
    
    # LOCATION (Assuming confirmation said Yes -> WAITING_FOR_LOCATION would be managed by confirmation_handler, let's simulate transition)
    state_mgr.update_state(phone, "WAITING_FOR_LOCATION", {}) 
    
    # Handle Location Input (Should filter by PROJ-A locations)
    print("\n[Input] 'Alpha Loc 1'") # Valid
    resp = handle_location("Alpha Loc 1", phone, state_mgr, curr)
    print(f"Resp: {resp['text']}")
    # Should accept it.
    
    print("\n[Input] 'Global Loc 1'") # Invalid for this project? 
    # Current logic accepts FREE TEXT if no match, BUT we want to verify it populated the LIST options correctly?
    # handle_location doesn't return list options for *next* step (Breach Source), so we can't see the location options.
    # But we can verify logic:
    # Actually handle_location *receives* the location. To verify the *list* presented TO the user, we need to see what the PREVIOUS handler returned.
    # The previous handler was 'handle_confirmation' or 'project_handler' (if confirmation skipped).
    
    # 'project_handler' returned: "Is this correct?".
    # If user says "Yes" -> 'confirmation_handler' (mocked validation) -> returns "Where is the location?" with OPTIONS.
    # I didn't write confirmation_handler here, but I can check logic in 'data_collection_handlers.py' if I had a function to 'get_location_prompt'.
    # But wait, 'handle_location' IS the one that processes the answer.
    
    # 2. RETURNING USER FLOW
    print("\n--- Test 2: Returning User (Has history) ---")
    phone = "CLIENT_RETURNING" # Mock returns 'PROJ-A'
    
    # START
    resp = handle_start(user_input, phone, state_mgr)
    print(f"Resp: {resp['text']}")
    
    # Check if prompt asks to confirm project
    if "Project: *Project Alpha*" in resp["text"]:
        print("  [PASS] Auto-selected Project Alpha")
    else:
        print("  [FAIL] Did not auto-select")
        
    # Verify State: Should be WAITING_FOR_CONFIRMATION (Context: Project + Analysis)
    curr = state_mgr.get_state(phone)
    assert curr["state"] == "WAITING_FOR_CONFIRMATION", f"Expected WAITING_FOR_CONFIRMATION, got {curr['state']}"
    
    # 3. CHANGE PROJECT FLOW
    print("\n--- Test 3: Returning User Changes Project ---")
    # Simulate user clicking "Change Project" button (ID: change_project)
    from lambdas.handlers.confirmation_handler import handle_confirmation
    
    # Mocking current state for confirmation handler
    curr = {"draftData": {"projectId": "PROJ-A", "classification": "A1 Hazard"}}
    
    print("[Input] 'change_project'")
    resp = handle_confirmation("change_project", phone, state_mgr, curr)
    print(f"Resp: {resp['text']}")
    
    # Verify State: Should be WAITING_FOR_PROJECT
    curr = state_mgr.get_state(phone)
    assert curr["state"] == "WAITING_FOR_PROJECT", f"Expected WAITING_FOR_PROJECT, got {curr['state']}"
    
    # Select new project
    print("[Input] 'Project Beta'")
    resp = handle_project_selection("Project Beta", phone, state_mgr)
    print(f"Resp: {resp['text']}")
    
    # Verify New Project set
    curr = state_mgr.get_state(phone)
    assert curr["draftData"]["projectId"] == "PROJ-B", f"Expected PROJ-B, got {curr['draftData']['projectId']}"
    
    print("=== TEST COMPLETE ===")

if __name__ == "__main__":
    run_test()
