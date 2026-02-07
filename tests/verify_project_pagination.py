
import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/lambdas/shared")))

# Mock Dependencies
sys.modules["shared.conversation_state"] = MagicMock()
sys.modules["shared.user_project_manager"] = MagicMock()
sys.modules["shared.config_manager"] = MagicMock()

from handlers.project_handler import handle_project_selection
from shared.config_manager import ConfigManager

def run_test():
    print("--- Verifying Project Pagination ---")
    
    # 1. Setup Mock Projects (25 items)
    projects = [f"Project {i}" for i in range(25)]
    
    cm = MagicMock()
    cm.get_options.return_value = projects
    ConfigManager.return_value = cm
    
    csm = MagicMock()
    
    # 2. Test Page 0 (Change)
    print("\nTest 1: Request Page 0")
    resp = handle_project_selection("change", "123", csm)
    items = resp["interactive"]["items"]
    print(f"Items count: {len(items)}")
    print(f"Last item: {items[-1]}")
    
    assert len(items) == 10
    assert items[-1]["id"] == "next_projects:1"
    
    # 3. Test Page 1 (Next)
    print("\nTest 2: Request Page 1")
    resp = handle_project_selection("next_projects:1", "123", csm)
    items = resp["interactive"]["items"]
    print(f"Items count: {len(items)}")
    print(f"First item: {items[0]}")
    print(f"Last item: {items[-1]}")
    
    assert len(items) == 10
    assert items[0]["title"] == "Project 9"[:24]
    assert items[-1]["id"] == "next_projects:2"

    # 4. Test Page 2 (Final)
    print("\nTest 3: Request Page 2")
    resp = handle_project_selection("next_projects:2", "123", csm)
    items = resp["interactive"]["items"]
    print(f"Items count: {len(items)}")
    print(f"First item: {items[0]}")
    
    # Projects 0-8 (9), 9-17 (9), 18-24 (7 items remaining).
    # Page 0: 0-8
    # Page 1: 9-17
    # Page 2: 18-24 (7 items)
    # Total 25.
    
    assert len(items) == 7
    assert items[0]["title"] == "Project 18"[:24]
    if items[-1]["id"].startswith("next"):
        print("FAIL: Next button present on last page")
    else:
        print("SUCCESS: No Next button on last page")

    print("\n--- Pagination Verified ---")

if __name__ == "__main__":
    run_test()
