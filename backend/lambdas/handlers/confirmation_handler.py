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

# We still need a default fallback logic or use ConfigManager for classifications too?
# Since `start_handler` generates classifications using AI, the fallback selection 
# should ideally match what the AI is trained on or the configurable list.
# Let's use ConfigManager for the fallback list as well.

def handle_confirmation(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state: Dict[str, Any]
) -> str:
    """
    Handle the confirmation step (Workflow Step 2).
    """
    text = user_input_text.strip().lower()
    
    # 1. Handle "Yes"
    if text in ["yes", "y", "correct", "yeah", "yep"]:
        # Transition to Location
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_LOCATION"
        )
        
        # Fetch Locations options for the prompt
        config = ConfigManager()
        locations = config.get_options("LOCATIONS")
        
        return {
            "text": "Where did this happen?\n\n📍 Share your *Location* (Paperclip -> Location) or select from the list:",
            "interactive": {
                "type": "list",
                "button_text": "Select Location",
                "items": [{"id": f"loc_{i}", "title": loc} for i, loc in enumerate(locations)]
            }
        }
        
    # 2. Handle "No"
    elif text in ["no", "n", "nope", "incorrect"]:
        # Transition to Classification Selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_CLASSIFICATION_SELECTION"
        )
        
        # Fallback classifications
        CLASSIFICATIONS = [
            "Falls from Height", "Electrical Hazards", "Fire Hazards", 
            "Chemical Exposure", "Manual Handling", "Confined Spaces", 
            "Vehicle Movement", "Slips, Trips, Falls", "Equipment Malfunction", 
            "Other" 
        ]
        
        return {
            "text": "Please select the correct category:",
            "interactive": {
                "type": "list",
                "button_text": "Select Category",
                "items": [{"id": f"{i+1}", "title": c} for i, c in enumerate(CLASSIFICATIONS)]
            }
        }
        
    else:
        # Re-ask with buttons
        classification = current_state.get('draftData', {}).get('classification', 'Unknown')
        return {
            "text": f"I didn't understand. I identified *{classification}*.\n\nIs this correct?",
            "interactive": {
                "type": "button",
                "buttons": [
                    {"id": "yes", "title": "Yes"},
                    {"id": "no", "title": "No"}
                ]
            }
        }

def handle_classification_selection(
    user_input_text: str,
    phone_number: str,
    state_manager: ConversationState
) -> str:
    """
    Handle selection if user said "No" previously.
    """
    text = user_input_text.strip()
    
    CLASSIFICATIONS = [
        "Falls from Height", "Electrical Hazards", "Fire Hazards", 
        "Chemical Exposure", "Manual Handling", "Confined Spaces", 
        "Vehicle Movement", "Slips, Trips, Falls", "Equipment Malfunction", 
        "Other" 
    ]
    
    # Check if user sent a number (from List or Text)
    # Interactive List might send ID or Title depending on client used, 
    # but our fallback instructions say "Reply with number".
    # User might also click valid list item.
    
    selected_class = None
    
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(CLASSIFICATIONS):
            selected_class = CLASSIFICATIONS[idx]
            
    # Also define logic if they type the name exactly
    elif text in CLASSIFICATIONS:
        selected_class = text
        
    if selected_class:
        # Update data with manual selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_LOCATION",
            curr_data={"classification": selected_class}
        )
        
        # Fetch Locations options for the next prompt
        config = ConfigManager()
        locations = config.get_options("LOCATIONS")
        
        return {
            "text": f"Got it: *{selected_class}*.\n\nWhere did this happen?\n\n📍 Share your *Location* or select below:",
            "interactive": {
                "type": "list",
                "button_text": "Select Location",
                "items": [{"id": f"loc_{i}", "title": loc} for i, loc in enumerate(locations)]
            }
        }
            
    return "Please reply with the *number* corresponding to the correct category."
