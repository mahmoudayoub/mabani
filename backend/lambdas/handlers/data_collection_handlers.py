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

def handle_location(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> str:
    # Resolve Location Selection
    config = ConfigManager()
    locations = config.get_options("LOCATIONS")
    
    selected_loc = _resolve_selection(user_input_text, locations)
    location_val = selected_loc if selected_loc else user_input_text.strip()
    
    # Save Location
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_BREACH_SOURCE",
        curr_data={"location": location_val}
    )
    
    # Prepare Next Question (Breach Source)
    # We skip WAITING_FOR_OBSERVATION_TYPE because classification/type is already confirmed in Step 1.
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    
    return f"""Location saved: {location_val}

Who/What is the source?
{_format_options(sources)}
(Or type a name)"""

def handle_observation_type(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> str:
    """Handle Observation Type Confirmation or Correction."""
    text = user_input_text.strip()
    
    draft_data = current_state_data.get("draftData", {})
    current_class = draft_data.get("classification")
    
    taxonomy_map = _get_taxonomy_map()
    
    final_class = current_class
    
    if text.lower() in ["yes", "y", "correct", "confirm"]:
        # Confirmed
        pass
    else:
        # 1. Check strict Code match
        # Handle "A1" or "A1."
        code = text.upper().split(' ')[0].replace('.', '')
        
        if code in taxonomy_map:
            final_class = taxonomy_map[code]
        else:
            # 2. Try Fuzzy/Smart Match
            match = _find_best_match(text, taxonomy_map)
            if match:
                final_class = match
            else:
                return f"⚠️ I couldn't recognize \"{text}\".\n\nPlease reply with *Yes* to accept {current_class}, or try typing the category name again (e.g. 'Noise' or code 'A21')."

    # Save finalized classification
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_BREACH_SOURCE",
        curr_data={"classification": final_class}
    )
    
    # Prepare Next Question (Breach Source)
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    return f"""Category saved: {final_class}

Who/What is the source?
{_format_options(sources)}
(Or type a name)"""

def handle_breach_source(user_input_text: str, phone_number: str, state_manager: ConversationState, current_state_data: Dict[str, Any]) -> str:
    """Handle Breach Source Input."""
    config = ConfigManager()
    sources = config.get_options("BREACH_SOURCES")
    
    selected = _resolve_selection(user_input_text, sources)
    source_val = selected if selected else user_input_text.strip()
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_SEVERITY",
        curr_data={"breachSource": source_val}
    )
    
    # Prepare Next Question (Severity)
    levels = ["High", "Medium", "Low"]
    return f"""How would you rate the severity?
{_format_options(levels)}"""
