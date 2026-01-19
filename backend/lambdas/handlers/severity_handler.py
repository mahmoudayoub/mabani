"""
Handler for the 'Severity' step.
This performs the Critical "Stop Work" check using the Knowledge Base.
"""

from typing import Dict, Any, List
try:
    from shared.conversation_state import ConversationState
    from shared.bedrock_client import BedrockClient
    # Import FAISSService for KB queries
    from shared.faiss_utils import FAISSService
    from shared.kb_repositories import KnowledgeBaseRepository
    from shared.dynamic_bedrock import DynamicBedrockClient
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.faiss_utils import FAISSService
    from lambdas.shared.kb_repositories import KnowledgeBaseRepository
    from lambdas.shared.dynamic_bedrock import DynamicBedrockClient
    from lambdas.handlers.safety_check_handler import perform_safety_check

def handle_severity(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle Severity Input and Trigger KB Safety Check.
    """
    severity_input = user_input_text.strip().upper()
    
    # Normalize input
    valid_severities = ["HIGH", "MEDIUM", "LOW"]
    severity = "MEDIUM" # Default
    
    # Map numbers or keys to severities
    mapping = {"1": "HIGH", "2": "MEDIUM", "3": "LOW", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
    
    if severity_input.lower() in mapping:
        severity = mapping[severity_input.lower()]
    elif any(s in severity_input for s in valid_severities):
        for s in valid_severities:
            if s in severity_input:
                severity = s
                break
    else:
        # Re-ask with buttons
        return {
            "text": "Please select the severity level:",
            "interactive": {
                "type": "button",
                "buttons": [
                    {"id": "high", "title": "High"},
                    {"id": "medium", "title": "Medium"},
                    {"id": "low", "title": "Low"}
                ]
            }
        }

    # Perform Safety Check (RAG)
    classification = current_state_data.get("draftData", {}).get("classification", "General Hazard")
    description = current_state_data.get("draftData", {}).get("originalDescription", "")
    caption = current_state_data.get("draftData", {}).get("imageCaption", "")
    
    # This might take a few seconds
    advice, source = perform_safety_check(classification, severity, description, caption)
    
    # Save advice to draft data and transition
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_STOP_WORK",
        curr_data={
            "severity": severity,
            "controlMeasure": advice,
            "reference": source
        }
    )
    
    # Construct Message
    message_text = f"Got it: *{severity}* severity.\n\n"
    
    if advice:
        message_text += f"⚠️ *Safety Check*:\nBased on our safety manual: \"{advice}\"\n\n"
    
    message_text += "Do you need to stop work immediately?"
    
    return {
        "text": message_text,
        "interactive": {
            "type": "button",
            "buttons": [
                {"id": "yes", "title": "Yes"},
                {"id": "no", "title": "No"}
            ]
        }
    }
