from typing import Dict, Any, List, Optional
try:
    from shared.conversation_state import ConversationState
    from shared.config_manager import ConfigManager
    from shared.bedrock_client import BedrockClient
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.config_manager import ConfigManager
    from lambdas.shared.bedrock_client import BedrockClient

def _find_best_match(user_input: str, taxonomy_map: Dict[str, str]) -> Optional[str]:
    """Use Bedrock to map free text to the closest Taxonomy Code."""
    bedrock = BedrockClient()
    
    # We can't send the entire 50 item dict maybe? 
    # Bedrock can handle it, 50 lines is small token count (< 500 tokens).
    
    prompt = f"""Map the following User Input to the single best Category Code from the list below.
    
User Input: "{user_input}"

Categories:
{taxonomy_map}

Return ONLY the Key (e.g. A1, B3). If no reasonable match exists, return NONE.
Code:"""
    try:
        code = bedrock._invoke_model(prompt, max_tokens=10, temperature=0.0).strip().upper()
        code = code.replace("CODE:", "").strip()
        
        if code in taxonomy_map:
            return taxonomy_map[code]
        return None
    except Exception as e:
        print(f"Error matching category: {e}")
        return None

def _get_taxonomy_map() -> Dict[str, str]:
    """Unpack list ['A1 Confined Spaces', ...] into dict {'A1': 'A1 Confined Spaces'}."""
    config = ConfigManager()
    options = config.get_options("HAZARD_TAXONOMY")
    taxonomy = {}
    for opt in options:
        # split by space
        parts = opt.split(' ', 1)
        if len(parts) > 0:
            code = parts[0].strip().upper()
            taxonomy[code] = opt
    return taxonomy

def _format_options(options: List[str]) -> str:
    """Format list as numbered string."""
    return "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])

def _resolve_selection(user_input: str, options: List[str]) -> str:
    """Resolve user input (number or text) to a valid option."""
    text = user_input.strip()
    
    # Try as number
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(options):
            return options[idx]
            
    # Try as text match
    text_lower = text.lower()
    for opt in options:
        if opt.lower() == text_lower:
            return opt
            
    return None

def handle_location(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> Dict[str, Any]:
    # Resolve Location Selection
    config = ConfigManager()
    
    # Context-Aware Locations
    draft_data = current_state_data.get("draftData", {})
    project_id = draft_data.get("projectId")
    
    locations = []
    
    if project_id:
        all_projects = config.get_options("PROJECTS")
        target_proj = None
        for p in all_projects:
            if isinstance(p, dict) and p["id"] == project_id:
                target_proj = p
                break
        
        if target_proj and "locations" in target_proj:
            locations = target_proj["locations"]
    
    # Fallback to global if no project selected or project has no locations
    if not locations:
        locations = config.get_options("LOCATIONS")
    
    selected_loc = None
    text = user_input_text.strip()
    
    # Handle Native Location Share
    if text.startswith("Location:"):
        selected_loc = text.replace("Location:", "").strip()
    
    # Handle Interactive ID
    elif text.startswith("loc_"):
        try:
            idx = int(text.split("_")[1])
            if 0 <= idx < len(locations):
                selected_loc = locations[idx]
        except:
            pass
            
    if not selected_loc:
        selected_loc = _resolve_selection(text, locations)
        
    location_val = selected_loc if selected_loc else text
    
    # Check if we need to ask for Observation Type (UA/UC)
    # If start_handler set it (confident), we might skip.
    # Currently assuming we skip if present, or we can force ask.
    # Let's Skip to Breach Source to streamline, as per user request to "Replace with AI".
    
    # Update draftData with location
    updated_draft = draft_data.copy()
    updated_draft["location"] = location_val
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_BREACH_SOURCE",
        curr_data=updated_draft
    )
    
    # Prepare Next Question (Breach Source)
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    
    return {
        "text": f"Location saved: {location_val}\n\nWho/What is the source?",
        "interactive": {
            "type": "list",
            "button_text": "Select Source",
            "items": [{"id": f"src_{i}", "title": src} for i, src in enumerate(sources)]
        }
    }

def handle_observation_type(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Observation Type (UA/UC/NM) if we didn't skip it.
    """
    config = ConfigManager()
    types = config.get_options("OBSERVATION_TYPES")
    
    selected_type = _resolve_selection(user_input_text, types)
    start_val = selected_type if selected_type else user_input_text.strip()
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_BREACH_SOURCE",
        curr_data={"observationType": start_val}
    )
    
    # Prepare Next Question (Breach Source)
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    
    return {
        "text": f"Type saved: {start_val}\n\nWho/What is the source?",
        "interactive": {
            "type": "list",
            "button_text": "Select Source",
            "items": [{"id": f"src_{i}", "title": src} for i, src in enumerate(sources)]
        }
    }

def handle_breach_source(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle Breach Source Input."""
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    
    selected_source = None
    text = user_input_text.strip()
    
    # Handle Interactive ID
    if text.startswith("src_"):
        try:
            idx = int(text.split("_")[1])
            if 0 <= idx < len(sources):
                selected_source = sources[idx]
        except:
            pass
            
    if not selected_source:
        selected_source = _resolve_selection(text, sources)
        
    source_val = selected_source if selected_source else text
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_SEVERITY",
        curr_data={"breachSource": source_val}
    )
    
    # Prepare Next Question (Severity)
    levels = ["High", "Medium", "Low"]
    
    return {
        "text": "How would you rate the severity?",
        "interactive": {
            "type": "button",
            "buttons": [{"id": lvl.lower(), "title": lvl} for lvl in levels]
        }
    }

def handle_remarks(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Handle Remarks Input (Free Text).
    Transitions to Responsible Person selection.
    """
    remarks = user_input_text.strip()
    
    # Save remarks
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_RESPONSIBLE_PERSON",
        curr_data={"remarks": remarks}
    )
    
    # Prepare Next Question (Responsible Person) using Project Specific List
    if not current_state_data:
        current_state_data = state_manager.get_state(phone_number) or {}
        
    draft_data = current_state_data.get("draftData", {})
    project_id = draft_data.get("projectId")
    
    config = ConfigManager()
    all_projects = config.get_options("PROJECTS")
    persons = []
    
    if project_id:
        for p in all_projects:
            p_id = p.get("id") if isinstance(p, dict) else p
            if p_id == project_id and isinstance(p, dict):
                 persons = p.get("responsible_persons", [])
                 break
                 
    if not persons:
        persons = config.get_options("RESPONSIBLE_PERSONS")
    
    return {
        "text": "Remarks saved.\n\nWho is the *Responsible Person* for this area?\n(You can also share a Contact Card)",
        "interactive": {
            "type": "list",
            "button_text": "Select Person",
            "items": [{"id": f"p_{i}", "title": p[:24]} for i, p in enumerate(persons)]
        }
    }
