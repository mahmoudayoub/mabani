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
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.twilio_client import TwilioClient

import boto3
import os

def handle_stop_work(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState
) -> str:
    """Handle Stop Work Input."""
    text = user_input_text.strip().lower()
    stop_work = False
    
    if text in ["yes", "y", "true"]:
        stop_work = True
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_RESPONSIBLE_PERSON",
        curr_data={"stopWork": stop_work}
    )
    
    return "Who is the responsible person for this area? (Name or Phone Number)"

def handle_responsible_person(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> str:
    """
    Handle Responsible Person Input and Finalize Report.
    """
    responsible_person = user_input_text.strip()
    
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
    hazard_type = draft_data.get("observationType", draft_data.get("classification", "General")).title()
    description = draft_data.get("originalDescription", "")
    s3_https_url = draft_data.get("s3Url", "").replace("s3://", "https://").replace(".s3.eu-central-1.amazonaws.com", ".s3.eu-central-1.wasabisys.com/in-files") # Placeholder logic for URL, using s3Url from metadata
    # Actually, we should use the proper HTTPS URL if stored, or construct it.
    # The s3Url stored in draftData is usually s3://bucket/key
    # Ideally we should have stored 'httpsUrl' in start_handler. Let's try to infer or use what we have.
    # For now, let's assume we can link to the image if public or via portal. Unauthenticated S3 links might fail if bucket is private.
    # But for the requested format, we try our best.
    
    image_link = draft_data.get("imageUrl")
    if not image_link:
        # Fallback to s3Url if imageUrl is missing (legacy data) and try to convert
        s3_url = draft_data.get("s3Url", "")
        if s3_url.startswith("s3://"):
             # Convert s3://bucket/key to https://bucket.s3.region.amazonaws.com/key
             # However, we don't have region handy here easily unless we import env. 
             # Simpler to just say Not Available or let it remain s3:// for legacy.
             image_link = s3_url
        else:
             image_link = "Image Link Not Available"
    
    # Advice / Control Measure
    # We stored this in severity_handler as 'controlMeasure' (formerly safetyAdvice)
    advice = draft_data.get("controlMeasure", draft_data.get("safetyAdvice", "Conduct immediate safety assessment."))
    source_ref = draft_data.get("reference", draft_data.get("safetySource", ""))
    
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    location = draft_data.get("location", "Unknown")
    source = draft_data.get("breachSource", "Unknown")

    message = f"""🔍 Hazard Type: {hazard_type}
📍 Location: {location}
👤 Source: {source}
⚠️ Severity: {severity}
🔒 Control measures: {advice}
Date: {date_str}
🖼️ - {image_link}
🔎 - {description}
Log ID {report_num}
——————————————————"""

    if source_ref and source_ref != "Standard Safety Protocols":
        message += f"\n\n📚 Source: {source_ref}\n(Reference from Safety Knowledge Base)"

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
