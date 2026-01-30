"""
Handler for the 'Project Selection' state.
Updates user profile with selected project and proceeds to confirmation.
"""

from typing import Dict, Any, Union

try:
    from shared.conversation_state import ConversationState
    from shared.user_project_manager import UserProjectManager
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.user_project_manager import UserProjectManager

def handle_project_selection(
    user_input: str, 
    phone_number: str, 
    state_manager: ConversationState,
    state_item: Dict[str, Any] = None
) -> Union[str, Dict[str, Any]]:
    """
    Handle the project selection step.
    
    Args:
        user_input: The project name/ID selected by the user.
        phone_number: User's phone number.
        state_manager: State manager instance.
        state_item: Current state item from DB.
        
    Returns:
        Response message to sending to user.
    """
    
    # 1. Update User Preference
    user_project_manager = UserProjectManager()
    # We trust the input from the interactive list, or text if typed.
    # In a stricter version, we would validate against ConfigManager.get_options("PROJECTS")
    selected_project = user_input.strip()
    
    user_project_manager.set_last_project(phone_number, selected_project)

    # 2. Retrieve Draft Data
    # If state_item wasn't passed, fetch it (though workflow_worker usually passes it if available, 
    # but let's be safe or just use what we have if we assume it exists).
    draft_data = {}
    if state_item:
        draft_data = state_item.get("draftData", {})
    else:
        # Fallback fetch if needed, though workflow_worker should handle this
        current_state = state_manager.get_state(phone_number)
        if current_state:
            draft_data = current_state.get("draftData", {})

    # 3. Update State to Confirmation
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_CONFIRMATION",
        curr_data={"projectId": selected_project}
    )

    # 4. Format Response (Proceed to Confirmation Question)
    observation_type = draft_data.get("observationType", "Observation")
    hazard_category = draft_data.get("classification", "Unknown Hazard")

    return {
        "text": f"Project set to *{selected_project}*.\n\nI've analyzed the photo and identified a *{observation_type}* related to *{hazard_category}*.\n\nIs this correct?",
        "interactive": {
            "type": "button",
            "buttons": [
                {"id": "yes", "title": "Yes"},
                {"id": "no", "title": "No"}
            ]
        }
    }
