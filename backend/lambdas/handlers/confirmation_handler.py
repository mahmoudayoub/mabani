"""
Handler for the 'Confirmation' state of the safety reporting workflow.
"""

from typing import Dict, Any, List
try:
    from shared.conversation_state import ConversationState
    from shared.config_manager import ConfigManager
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.config_manager import ConfigManager

def handle_confirmation(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle the confirmation step (Workflow Step 2).
    """
    text = user_input_text.strip().lower()
    
    # 1. Handle "Yes" (Type Confirmed)
    if text in ["yes", "y", "correct", "yeah", "yep"]:
        # Transition to Category Confirmation
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_CATEGORY_CONFIRMATION"
        )
        
        # Get Draft Data to show Category
        draft_data = current_state.get("draftData", {})
        category = draft_data.get("hazardCategory", "Unknown")
        
        return {
            "text": f"Great. It is related to *{category}*.\n\nIs this correct?",
            "interactive": {
                "type": "button",
                "buttons": [
                    {"id": "yes", "title": "Yes"},
                    {"id": "change_category", "title": "Change Category"}
                ]
            }
        }
        
    # 2. Handle "Change Project"
    elif text in ["change_project", "change project"]:
        # Transition to Project Selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_PROJECT"
        )
        
        config = ConfigManager()
        projects = config.get_options("PROJECTS")
        
        rows = []
        for p in projects[:10]:
            if isinstance(p, dict):
                rows.append({"id": p["id"], "title": p["name"][:24]})
            else:
                rows.append({"id": p, "title": p[:24]})
                
        return {
            "text": "Okay, please select the correct *Project*:",
            "interactive": {
                "type": "list",
                "button_text": "Select Project",
                "items": rows
            }
        }

    # 3. Handle "Change Type"
    elif text in ["change_type", "change type", "edit_hazard", "edit hazard"]:
        # Transition to Observation Type Selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_OBSERVATION_TYPE"
        )
        
        config = ConfigManager()
        types = config.get_options("OBSERVATION_TYPES")
        
        return {
            "text": "Please select the correct *Observation Type*:",
            "interactive": {
                "type": "list",
                "button_text": "Select Type",
                "items": [{"id": f"type_{i}", "title": t} for i, t in enumerate(types)]
            }
        }
        
    else:
        # Re-ask with buttons
        classification = current_state.get('draftData', {}).get('observationType', 'Unknown')
        return {
            "text": f"I didn't understand. I identified *{classification}*.\n\nIs this observation type correct?",
            "interactive": {
                "type": "button",
                "buttons": [
                    {"id": "yes", "title": "Yes"},
                    {"id": "change_type", "title": "Change Type"}
                ]
            }
        }

def handle_category_confirmation(
    user_input_text: str,
    phone_number: str,
    state_manager: ConversationState,
    current_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle the Category Confirmation step.
    """
    text = user_input_text.strip().lower()
    
    # 1. Handle "Yes" (Category Confirmed)
    if text in ["yes", "y", "correct", "yeah", "yep"]:
        # Transition to Location
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_LOCATION"
        )
        
        # Resolve Location Selection (Context Aware)
        config = ConfigManager()
        draft_data = current_state.get("draftData", {})
        project_id = draft_data.get("projectId")
        
        locations = []
        if project_id:
            all_projects = config.get_options("PROJECTS")
            for p in all_projects:
                if isinstance(p, dict) and p["id"] == project_id:
                    locations = p.get("locations", [])
                    break
        
        if not locations:
            locations = config.get_options("LOCATIONS")
        
        return {
            "text": "Where did this happen?\n\n📍 Share your *Location* (Paperclip -> Location) or select from the list:",
            "interactive": {
                "type": "list",
                "button_text": "Select Location",
                "items": [{"id": f"loc_{i}", "title": loc} for i, loc in enumerate(locations)]
            }
        }
        
    # 2. Handle "Change Category" -> Go to Parent Category Selection
    elif text in ["change_category", "change category", "no", "n"]:
        # Transition to Parent Category Selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_PARENT_CATEGORY_SELECTION"
        )
        
        return {
            "text": "Please select the *Main Category*:",
            "interactive": {
                "type": "button",
                "buttons": [
                    {"id": "Safety", "title": "Safety"},
                    {"id": "Environment", "title": "Environment"},
                    {"id": "Health", "title": "Health"}
                ]
            }
        }
        
    return {
         "text": f"Is the category correct?",
         "interactive": {
            "type": "button",
            "buttons": [
                {"id": "yes", "title": "Yes"},
                {"id": "change_category", "title": "Change Category"}
            ]
        }
    }

def handle_parent_category_selection(
    user_input_text: str,
    phone_number: str,
    state_manager: ConversationState,
    state_item: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Handle selection of Parent Category (Safety, Environment, Health).
    Shows sub-categories.
    """
    text = user_input_text.strip()
    
    # 1. Validate Parent Category
    valid_parents = ["Safety", "Environment", "Health"]
    
    # Simple fuzzy match
    selected_parent = None
    for p in valid_parents:
        if p.lower() in text.lower():
            selected_parent = p
            break
            
    if not selected_parent:
         selected_parent = "Safety" # Default fallback
         
    # 2. Transition to Sub-Category Selection
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_CLASSIFICATION_SELECTION",
        curr_data={"parentCategory": selected_parent}
    )
    
    # 3. Get Subcategories
    config = ConfigManager()
    taxonomy = config.get_options("HAZARD_TAXONOMY") # List of dicts {code, name, category}
    
    # Filter by parent
    sub_categories = [item for item in taxonomy if isinstance(item, dict) and item.get("category") == selected_parent]
    
    # Prepare List Items (Name only, as per requirement)
    # Paging check? If > 10, logic needed. 
    # Safety has 41 items. Need Paging logic.
    
    draft_data = state_item.get("draftData", {}) if state_item else {}
    page = draft_data.get("categoryPage", 0)
    
    # If text indicates pagination (processed by router or here?)
    # Simply listing first 9 for now. Simple implementation.
    # To implement robust paging, we'd need to handle "next_page" input in this handler? NO, this is the *result* of parent selection.
    # Paging is handled in handle_classification_selection if user clicks "More".
    
    rows = []
    for item in sub_categories[:9]:
        name = item.get("name", "Unknown")
        item_id = item.get("code", name)
        rows.append({"id": f"sub_{item_id}", "title": name[:24]})
        
    if len(sub_categories) > 9:
        rows.append({"id": "page_1", "title": "Next ➡️"})
        
    return {
        "text": f"Please select the *{selected_parent}* sub-category:",
        "interactive": {
            "type": "list",
            "button_text": "Select Category",
            "items": rows
        }
    }


def handle_classification_selection(
    user_input_text: str,
    phone_number: str,
    state_manager: ConversationState,
    state_item: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Handle selection of specific Hazard Category.
    Supports Pagination.
    """
    text = user_input_text.strip()
    
    if not state_item:
        state_item = state_manager.get_state(phone_number) or {}
        
    current_data = state_item.get("currData", {}) # currData holds parentCategory
    parent = current_data.get("parentCategory", "Safety") # Default if lost
    
    # 1. Paging Logic
    page = 0
    if text.startswith("page_"):
        try:
            page = int(text.split("_")[1])
        except:
            pass
            
    # If paging, re-show list
    if text.startswith("page_") or text.lower() == "next":
        config = ConfigManager()
        taxonomy = config.get_options("HAZARD_TAXONOMY")
        sub_categories = [item for item in taxonomy if isinstance(item, dict) and item.get("category") == parent]
        
        start_idx = page * 9
        end_idx = start_idx + 9
        
        rows = []
        paginated = sub_categories[start_idx:end_idx]
        
        for item in paginated:
            name = item.get("name", "Unknown")
            item_id = item.get("code", name)
            rows.append({"id": f"sub_{item_id}", "title": name[:24]})
            
        if len(sub_categories) > end_idx:
            rows.append({"id": f"page_{page+1}", "title": "Next ➡️"})
            
        return {
            "text": f"Please select the *{parent}* sub-category (Page {page+1}):",
            "interactive": {
                "type": "list",
                "button_text": "Select Category",
                "items": rows
            }
        }
        
    # 2. Selection Logic
    config = ConfigManager()
    taxonomy = config.get_options("HAZARD_TAXONOMY")
    
    selected_category = None
    
    # Check ID match (sub_A1)
    if text.startswith("sub_"):
        code = text.split("sub_")[1]
        for item in taxonomy:
            if isinstance(item, dict) and (item.get("code") == code or item.get("name") == code):
                selected_category = item.get("name")
                break
                
    # Check Name match
    if not selected_category:
        for item in taxonomy:
             if isinstance(item, dict):
                 if item.get("name", "").lower() == text.lower():
                     selected_category = item.get("name")
                     break
                 # Code match logic just in case
                 if item.get("code", "").lower() == text.lower():
                     selected_category = item.get("name")
                     break
                     
    if selected_category:
        # Update State
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_LOCATION",
            curr_data={"hazardCategory": selected_category}
        )
        
        # Prepare Next Step (Location)
        # Fetch Locations options 
        draft_data = state_item.get("draftData", {})
        project_id = draft_data.get("projectId")
        
        locations = []
        if project_id:
            all_projects = config.get_options("PROJECTS")
            for p in all_projects:
                if isinstance(p, dict) and p["id"] == project_id:
                    locations = p.get("locations", [])
                    break
                    
        if not locations:
            locations = config.get_options("LOCATIONS")
        
        return {
            "text": f"Got it: *{selected_category}*.\n\nWhere did this happen?\n\n📍 Share your *Location* or select below:",
            "interactive": {
                "type": "list",
                "button_text": "Select Location",
                "items": [{"id": f"loc_{i}", "title": loc} for i, loc in enumerate(locations)]
            }
        }
            
    return {"text": "Please select a valid category from the list."}
