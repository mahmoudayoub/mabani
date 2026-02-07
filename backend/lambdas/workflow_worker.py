"""
Async Worker for the Safety Reporting Workflow.
This Lambda executes the heavy business logic (Bedrock, DB, etc.) and sends replies directly via Twilio REST API.
"""

import json
import os
from dateutil import parser
from typing import Dict, Any

import boto3
# Try/Except imports
try:
    from shared.twilio_client import TwilioClient
    from shared.conversation_state import ConversationState
    # Handlers
    from handlers.start_handler import handle_start
    from handlers.project_handler import handle_project_selection
    from handlers.confirmation_handler import (
        handle_confirmation, 
        handle_classification_selection, 
        handle_category_confirmation,
        handle_parent_category_selection
    )
    from handlers.data_collection_handlers import handle_location, handle_observation_type, handle_breach_source, handle_remarks
    from handlers.severity_handler import handle_severity
    from handlers.finalization_handler import handle_stop_work, handle_responsible_person, handle_notified_persons
except ImportError:
    from lambdas.shared.twilio_client import TwilioClient
    from lambdas.shared.conversation_state import ConversationState
    # Handlers
    from lambdas.handlers.start_handler import handle_start
    from lambdas.handlers.project_handler import handle_project_selection
    from lambdas.handlers.confirmation_handler import (
        handle_confirmation, 
        handle_classification_selection, 
        handle_category_confirmation,
        handle_parent_category_selection
    )
    from lambdas.handlers.data_collection_handlers import handle_location, handle_observation_type, handle_breach_source, handle_remarks
    from lambdas.handlers.severity_handler import handle_severity
    from lambdas.handlers.finalization_handler import handle_stop_work, handle_responsible_person, handle_notified_persons, handle_responsible_person_selection

# Initialize clients
twilio_client = TwilioClient()

def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Async Handler.
    Receives payload from twilio_webhook and processes it.
    Exits gracefully on success (no return value needed for Async).
    """
    print(f"Workflow Worker processing event: {json.dumps(event)}")
    
    try:
        # 1. Extract Data
        # Format expects: {"from_number": "...", "body_content": "...", "params": {...}}
        from_number = event.get("from_number")
        body_content = event.get("body_content", "").strip()
        media_url = event.get("media_url")
        contact_vcard_url = event.get("contact_vcard_url")
        
        # Clean phone number
        if not from_number:
            print("Error: Missing 'from_number' in event payload.")
            return # Exit if essential data is missing
        clean_number = from_number.replace("whatsapp:", "")
        
        # 2. Check State
        state_manager = ConversationState()
        state_item = state_manager.get_state(clean_number)
        current_state = state_item.get("currentState") if state_item else None
        
        response_message = ""
        
        # 3. Dispatch Logic (Same as before)
        
        # Case A: Reset
        if body_content.lower() in ["reset", "cancel", "stop", "menu"]:
            state_manager.clear_state(clean_number)
            response_message = "🔄 Conversation reset. Send a photo to start a new report."
            
        # Case B: Start (New conversation or new image, but NOT vCard)
        elif current_state is None or (media_url and not contact_vcard_url):
            user_input = {
                "description": body_content,
                "imageUrl": media_url
            }
            # Inform user we are analyzing (optional, but good UX if slow)
            # twilio_client.send_message(to_number=from_number, message="🔍 Analyzing your photo...")
            
            response_message = handle_start(user_input, clean_number, state_manager)
            
        # Case C: Active State
        elif current_state == "WAITING_FOR_PROJECT":
            response_message = handle_project_selection(body_content, clean_number, state_manager, state_item)

        elif current_state == "WAITING_FOR_CONFIRMATION":
            response_message = handle_confirmation(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_CATEGORY_CONFIRMATION":
            response_message = handle_category_confirmation(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_PARENT_CATEGORY_SELECTION":
            response_message = handle_parent_category_selection(body_content, clean_number, state_manager, state_item)

        elif current_state == "WAITING_FOR_CLASSIFICATION_SELECTION":
            response_message = handle_classification_selection(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_LOCATION":
            response_message = handle_location(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_OBSERVATION_TYPE":
            response_message = handle_observation_type(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_BREACH_SOURCE":
            response_message = handle_breach_source(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_SEVERITY":
            # This triggers KB Query (Heavy)
            # twilio_client.send_message(to_number=from_number, message="📚 Checking safety protocols...")
            response_message = handle_severity(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_STOP_WORK":
            response_message = handle_stop_work(body_content, clean_number, state_manager)
            
        elif current_state == "WAITING_FOR_REMARKS":
            response_message = handle_remarks(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_RESPONSIBLE_PERSON":
            response_message = handle_responsible_person(body_content, clean_number, state_manager, state_item, contact_vcard_url)
            
        elif current_state == "WAITING_FOR_RESPONSIBLE_PERSON_SELECTION":
            response_message = handle_responsible_person_selection(body_content, clean_number, state_manager, state_item)
            
        elif current_state == "WAITING_FOR_NOTIFIED_PERSONS":
            response_message = handle_notified_persons(body_content, clean_number, state_manager, state_item)
            
        else:
            response_message = "⚠️ Unknown state. Send 'reset' to start over."
            
        # 4. Send Response via Twilio API
        if response_message:
            if isinstance(response_message, dict) and "interactive" in response_message:
                print(f"Sending interactive response to {from_number}")
                twilio_client.send_interactive_message(
                    to_number=from_number,
                    body_text=response_message.get("text", ""),
                    interactive_data=response_message["interactive"]
                )
            else:
                text_msg = response_message.get("text", "") if isinstance(response_message, dict) else str(response_message)
                if text_msg:
                    print(f"Sending response to {from_number}: {text_msg}")
                    twilio_client.send_message(to_number=from_number, message=text_msg)
            
    except Exception as e:
        print(f"Error in Workflow Worker: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error to user (if possible)
        try:
            twilio_client.send_message(
                to_number=event.get("from_number"), 
                message="⚠️ Sorry, we experienced an internal error processing your request."
            )
        except:
            pass
