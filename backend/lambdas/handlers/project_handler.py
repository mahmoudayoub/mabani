"""
Handler for the 'Project Selection' state.
Updates user profile with selected project and proceeds to Confirmation/Location.
"""

from typing import Dict, Any, Union

try:
    from shared.conversation_state import ConversationState
    from shared.user_project_manager import UserProjectManager
    from shared.config_manager import ConfigManager
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.user_project_manager import UserProjectManager
    from lambdas.shared.config_manager import ConfigManager

def handle_project_selection(
    user_input: str, 
    phone_number: str, 
    state_manager: ConversationState,
    state_item: Dict[str, Any] = None
) -> Union[str, Dict[str, Any]]:
    """
    Handle the project selection step.
    Supports "Smart Selection" (Yes/Change) and direct list selection.
    """
    
    if not state_item:
        current_state = state_manager.get_state(phone_number)
        state_item = current_state if current_state else {}
        
    draft_data = state_item.get("draftData", {})
    suggested_project_id = draft_data.get("suggestedProject")
    
    text = user_input.strip()
    selected_project_id = None
    
    config = ConfigManager()
    all_projects = config.get_options("PROJECTS")
    
    # Determine Page Number
    page = 0
    if text.startswith("next_projects:"):
        try:
            page = int(text.split(":")[1])
        except:
            pass

    # 1. Handle "Yes" (Smart Selection)
    if suggested_project_id and text.lower() in ["yes", "y", "confirm"] and page == 0:
        selected_project_id = suggested_project_id
        
    # 2. Handle "Change" (User wants to see list) OR Pagination
    elif text.lower() in ["change", "change project", "no", "n"] or text.startswith("next_projects:"):
        
        # Setup Pagination
        start_idx = page * 9
        end_idx = start_idx + 9
        
        list_items = []
        paginated = all_projects[start_idx:end_idx]
        
        for p in paginated:
            if isinstance(p, dict):
                 list_items.append({"id": p["id"], "title": p["name"][:24]})
            else:
                 list_items.append({"id": p, "title": p[:24]})
                 
        # Add "Next" if more items exist
        if len(all_projects) > end_idx:
             list_items.append({"id": f"next_projects:{page+1}", "title": "Next ➡️"})
             
        return {
            "text": f"Please select the project (Page {page+1}):",
            "interactive": {
                "type": "list",
                "button_text": "Select Project",
                "items": list_items
            }
        }
        
    # 3. Handle Direct Selection (ID or Name)
    else:
        # Check against IDs first
        for p in all_projects:
            p_id = p.get("id") if isinstance(p, dict) else p
            p_name = p.get("name") if isinstance(p, dict) else p
            
            if text == p_id or text.lower() == p_name.lower():
                selected_project_id = p_id
                break
        
        # Fallback
        if not selected_project_id:
             selected_project_id = text

    # 4. Save Preference & Update Data
    user_project_manager = UserProjectManager()
    user_project_manager.set_last_project(phone_number, selected_project_id)
    
    # Resolve full Project Details
    project_name = selected_project_id
    project_locations = []
    responsible_persons = []
    
    for p in all_projects:
        if isinstance(p, dict) and p["id"] == selected_project_id:
            project_name = p["name"]
            project_locations = p.get("locations", [])
            responsible_persons = p.get("responsiblePersons", [])
            break
    
    # Update draftData with complete project information
    updated_draft = draft_data.copy()
    updated_draft["projectId"] = selected_project_id
    updated_draft["project"] = project_name
    updated_draft["projectLocations"] = project_locations
    updated_draft["responsiblePersons"] = responsible_persons
    
    # Update State -> Proceed to CONFIRMATION (Classification)
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_CONFIRMATION", 
        curr_data=updated_draft
    )
    
    # Generate Confirmation Message
    observation_type = draft_data.get("observationType", "Observation")
    
    return {
        "text": f"Project set to *{project_name}*.\n\nI identified a *{observation_type}*.\n\nIs this correct?",
        "interactive": {
            "type": "button",
            "buttons": [
                {"id": "yes", "title": "Yes"},
                {"id": "change_type", "title": "Change Type"}
            ]
        }
    }
