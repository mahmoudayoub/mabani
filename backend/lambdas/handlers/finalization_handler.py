"""
Handlers for the final steps: Stop Work Check, Responsible Person, and Finalization.
"""

import uuid
import datetime
from typing import Dict, Any
# Import shared utilities
try:
    from shared.conversation_state import ConversationState
    from shared.twilio_client import TwilioClient
    from shared.config_manager import ConfigManager
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.twilio_client import TwilioClient
    from lambdas.shared.config_manager import ConfigManager

import boto3
import os

def handle_stop_work(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState
) -> Dict[str, Any]:
    """Handle Stop Work Input."""
    text = user_input_text.strip().lower()
    stop_work = False
    
    if text in ["yes", "y", "true", "confirm"]:
        stop_work = True
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_RESPONSIBLE_PERSON",
        curr_data={"stopWork": stop_work}
    )
    
    # Prepare Responsible Person Prompt
    config = ConfigManager()
    persons = config.get_options("RESPONSIBLE_PERSONS")
    
    return {
        "text": "Who is the responsible person for this area?",
        "interactive": {
            "type": "list",
            "button_text": "Select Person",
            "items": [{"id": f"p_{i}", "title": p} for i, p in enumerate(persons)]
        }
    }

def handle_responsible_person(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> str:
    """
    Handle Responsible Person Input and Finalize Report.
    """
    text = user_input_text.strip()
    
    # Resolve List Selection
    responsible_person = text
    
    config = ConfigManager()
    persons = config.get_options("RESPONSIBLE_PERSONS")
    
    if text.startswith("p_"):
        try:
            idx = int(text.split("_")[1])
            if 0 <= idx < len(persons):
                responsible_person = persons[idx]
        except:
            pass
            
    # Try name match
    if responsible_person == text: # If not resolved by ID
        for p in persons:
            if p.lower() == text.lower():
                responsible_person = p
                break
    
    # 1. Finalize Data
    draft_data = current_state_data.get("draftData", {})
    draft_data["responsiblePerson"] = responsible_person
    draft_data["reporter"] = phone_number
    draft_data["status"] = "OPEN"
    
    timestamp = datetime.datetime.utcnow().isoformat()
    draft_data["completedAt"] = timestamp
    
    # 2. Save to ReportsTable (DynamoDB)
    _save_final_report(draft_data)
    
    # 3. Clear State (Conversation Ended)
    state_manager.clear_state(phone_number)
    
    # 4. Construct Final Message
    report_num = draft_data.get("reportNumber", "N/A")
    severity = draft_data.get("severity", "Medium").capitalize()
    # hazard_type = Type (UA/UC)
    obs_type = draft_data.get("observationType", "Observation")
    # classification = Category (Working at Height)
    category = draft_data.get("classification", "General")
    
    description = draft_data.get("originalDescription", "")
    s3_https_url = draft_data.get("s3Url", "").replace("s3://", "https://").replace(".s3.eu-central-1.amazonaws.com", ".s3.eu-central-1.wasabisys.com/in-files") 
    
    image_link = draft_data.get("imageUrl")
    if not image_link:
        s3_url = draft_data.get("s3Url", "")
        if s3_url.startswith("s3://"):
             image_link = s3_url
        else:
             image_link = "Image Link Not Available"
    
    # Advice / Control Measure
    advice = draft_data.get("controlMeasure", draft_data.get("safetyAdvice", "Conduct immediate safety assessment."))
    source_ref = draft_data.get("reference", draft_data.get("safetySource", ""))
    
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    location = draft_data.get("location", "Unknown")
    source = draft_data.get("breachSource", "Unknown")
    stop_work_status = "YES" if draft_data.get("stopWork") else "NO"

    # Truncate advice if too long (Twilio limit 1600 chars total)
    if len(advice) > 800:
        advice = advice[:800] + "... (truncated)"
        
    message = f"""🔍 Hazard Type: {obs_type}
📂 Category: {category}
📍 Location: {location}
👤 Source: {source}
⚠️ Severity: {severity}
🛑 Stop Work: {stop_work_status}
👤 Responsible: {responsible_person}
🔒 Control measures: {advice}
Date: {date_str}
🖼️ - {image_link}
🔎 - {description}
Log ID {report_num}
——————————————————"""

    if source_ref and source_ref != "Standard Safety Protocols":
        message += f"\n\n📚 Source: {source_ref}\n(Reference from Safety Knowledge Base)"

    # Final Safety Truncation
    if len(message) > 1590:
        message = message[:1590] + "..."
        
    return message

def _save_final_report(data: Dict[str, Any]) -> None:
    """Save the complete report object to the main ReportsTable."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table_name = os.environ.get("REPORTS_TABLE")
        if not table_name:
            # Fallback checks (should be env var)
            table_name = "taskflow-backend-dev-reports" # Guess or fail
            
        table = dynamodb.Table(table_name)
        
        # PK/SK Scheme
        # PK: REPORT#{uuid}
        # SK: METADATA
        request_id = data.get("imageId", str(uuid.uuid4()))
        
        # Helper to get numeric report number if missing
        if "reportNumber" not in data:
            # Re-implement or import the counter logic
            data["reportNumber"] = _generate_report_number(table)
            
        item = {
            "PK": f"REPORT#{request_id}",
            "SK": "METADATA",
            **data # Flatten all draft data into the item
        }
        
        table.put_item(Item=item)
        print(f"Report {request_id} saved successfully.")
        
    except Exception as e:
        print(f"Error saving final report: {e}")
        # Note: We don't fail the user request here, just log error.
        
def _generate_report_number(table) -> int:
    """Atomic counter gen (duplicate logic, should be shared util)."""
    try:
        response = table.update_item(
            Key={"PK": "COUNTER", "SK": "REPORT_NUMBER"},
            UpdateExpression="ADD reportNumber :inc",
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW"
        )
        return int(response["Attributes"]["reportNumber"])
    except Exception:
        return 0
