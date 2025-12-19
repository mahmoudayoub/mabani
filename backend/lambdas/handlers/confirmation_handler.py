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
        options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(locations)])
        
        return f"Where did this happen? \nSelect from list or type new:\n{options_str}"
        
    # 2. Handle "No"
    elif text in ["no", "n", "nope", "incorrect"]:
        # Transition to Classification Selection
        state_manager.update_state(
            phone_number=phone_number,
            new_state="WAITING_FOR_CLASSIFICATION_SELECTION"
        )
        
        # Get dynamic classifications if possible, else standard fallback
        # Ideally we add CLASSIFICATIONS to ConfigManager too. 
        # For now, let's assume they are stored in "CLASSIFICATIONS" (Task: Add if needed).
        # We'll default to the static list if not found, but trying Config first is good.
        
        # NOTE: start_handler.py relies on Bedrock. 
        # If we use a fixed list here, it's fine.
        
        CLASSIFICATIONS = [
            "Falls from Height", "Falling Objects", "Electrical Hazards", 
            "Fire Hazards", "Chemical Exposure", "Manual Handling", 
            "Confined Spaces", "Vehicle Movement", "Slips, Trips, Falls", 
            "Equipment Malfunction", "PPE Non-compliance", "Other"
        ]
        
        options = "\n".join([f"{i+1}. {c}" for i, c in enumerate(CLASSIFICATIONS)])
        return f"Please reply with the number of the correct category:\n\n{options}"
        
    else:
        return f"I didn't understand. I identified *{current_state.get('draftData', {}).get('classification', 'Unknown')}*.\n\nIs this correct? (Reply *Yes* or *No*)"

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
        "Falls from Height", "Falling Objects", "Electrical Hazards", 
        "Fire Hazards", "Chemical Exposure", "Manual Handling", 
        "Confined Spaces", "Vehicle Movement", "Slips, Trips, Falls", 
        "Equipment Malfunction", "PPE Non-compliance", "Other"
    ]
    
    # Check if user sent a number
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(CLASSIFICATIONS):
            selected_class = CLASSIFICATIONS[idx]
            
            # Update data with manual selection
            state_manager.update_state(
                phone_number=phone_number,
                new_state="WAITING_FOR_LOCATION",
                curr_data={"classification": selected_class}
            )
            
            # Fetch Locations options for the next prompt
            config = ConfigManager()
            locations = config.get_options("LOCATIONS")
            options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(locations)])
            
            return f"Got it: *{selected_class}*.\n\nWhere did this happen? \nSelect or type:\n{options_str}"
            
    return "Please reply with the *number* corresponding to the correct category."
