"""
Handers for the final steps: Stop Work Check, Responsible Person, and Finalization.
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
import re
import requests

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
        new_state="WAITING_FOR_REMARKS",
        curr_data={"stopWork": stop_work}
    )
    
    return {
        "text": "Do you have any additional remarks or details? Please type and send your remarks, or click 'No Remarks' if you do not have any.",
        "interactive": {
             "type": "button",
             "buttons": [
                 {"id": "none", "title": "No Remarks"}
             ]
        }
    }

def handle_responsible_person(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any],
    contact_vcard_url: str = None
) -> Dict[str, Any]:
    """
    Handle Responsible Person Input (Text or vCard).
    Transitions to Notified Persons.
    """
    text = user_input_text.strip()
    draft_data = current_state_data.get("draftData", {})
    project_id = draft_data.get("projectId")
    
    # 1. Fetch Project-Specific List
    config = ConfigManager()
    all_projects = config.get_options("PROJECTS")
    persons = []
    
    # Find project and get persons
    if project_id:
        for p in all_projects:
            p_id = p.get("id") if isinstance(p, dict) else p
            if p_id == project_id and isinstance(p, dict):
                persons = p.get("responsiblePersons", [])
                break
    
    # Fallback
    if not persons:
        persons = config.get_options("RESPONSIBLE_PERSONS")
        
    responsible_person = text
    
    # 2. Handle vCard (Contact Shared)
    if contact_vcard_url:
        try:
            print(f"Fetching vCard: {contact_vcard_url}")
            # Twilio media URLs require HTTP Basic Auth
            from lambdas.shared.twilio_client import TwilioClient
            twilio_client = TwilioClient()
            creds = twilio_client._get_credentials()
            resp = requests.get(
                contact_vcard_url,
                auth=(creds.get("account_sid"), creds.get("auth_token"))
            )
            if resp.status_code == 200:
                vcard_data = resp.text
                # Extract Valid Name (FN)
                fn_match = re.search(r"FN:(.*)", vcard_data)
                full_name = fn_match.group(1).strip() if fn_match else "Unknown Contact"
                
                # Extract Phones (TEL)
                phones = re.findall(r"TEL.*:(.*)", vcard_data)
                phones = [p.strip() for p in phones if p.strip()]
                
                if len(phones) > 1:
                    # Edge Case: Multiple Numbers -> Ask User
                    rows = [{"id": f"sel_contact_{i}", "title": p[:24], "description": full_name[:72]} for i, p in enumerate(phones)]
                    # Store temp state to handle selection
                    state_manager.update_state(
                        phone_number=phone_number,
                        new_state="WAITING_FOR_RESPONSIBLE_PERSON_SELECTION",
                        curr_data={"contactName": full_name, "contactPhones": phones}
                    )
                    return {
                        "text": f"I found multiple numbers for *{full_name}*. Please select one:",
                        "interactive": {
                            "type": "list",
                            "button_text": "Select Number",
                            "items": rows
                        }
                    }
                elif len(phones) == 1:
                    responsible_person = f"{full_name} ({phones[0]})"
                else:
                    responsible_person = full_name
            else:
                print("Failed to download vCard")
        except Exception as e:
            print(f"Error Parsing vCard: {e}")

    # 3. Handle Text Selection (List or Manual)
    elif text.startswith("p_"):
        try:
            idx = int(text.split("_")[1])
            if 0 <= idx < len(persons):
                responsible_person = persons[idx]
        except:
            pass
    # Text Match
    else:
         for p in persons:
            if p.lower() == text.lower():
                responsible_person = p
                break

    # 4. Save and Proceed
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_NOTIFIED_PERSONS",
        curr_data={"responsiblePerson": responsible_person}
    )
    
    # Prepare Next Step (Notified Persons)
    # Use project-specific responsible persons, fallback to global stakeholders
    stakeholders = persons if persons else config.get_options("STAKEHOLDERS")
        
    return {
        "text": "Who should be notified about this observation? (Select from list or share a contact card)",
        "interactive": {
            "type": "list",
            "button_text": "Select Person",
            "items": [{"id": f"n_{i}", "title": (p.get("name", "Unknown") if isinstance(p, dict) else p)[:24]} for i, p in enumerate(stakeholders)]
        }
    }

def handle_responsible_person_selection(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle selection of phone number for a contact.
    """
    text = user_input_text.strip()
    contact_name = current_state_data.get("contactName", "Unknown")
    contact_phones = current_state_data.get("contactPhones", [])
    
    selected_phone = text
    if text.startswith("sel_contact_"):
        try:
            idx = int(text.split("_")[2])
            if 0 <= idx < len(contact_phones):
                selected_phone = contact_phones[idx]
        except:
             pass
             
    responsible_person = f"{contact_name} ({selected_phone})"
    
    # Save to draftData and Proceed
    draft_data = current_state_data.get("draftData", {})
    updated_draft = draft_data.copy()
    updated_draft["responsiblePerson"] = responsible_person
    
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_NOTIFIED_PERSONS",
        curr_data=updated_draft
    )
    
    config = ConfigManager()
    draft_data = current_state_data.get("draftData", {})
    project_id = draft_data.get("projectId")
    all_projects = config.get_options("PROJECTS")
    persons = config.get_options("RESPONSIBLE_PERSONS") # Default
    
    if project_id:
        for p in all_projects:
             if isinstance(p, dict) and p.get("id") == project_id:
                  persons = p.get("responsiblePersons", [])
                  break
    
    stakeholders = config.get_options("STAKEHOLDERS") 
    if not stakeholders:
        stakeholders = persons
        
    return {
        "text": "Who should be notified about this observation? (Select from list or share a contact card)",
        "interactive": {
            "type": "list",
            "button_text": "Select Person",
            "items": [{"id": f"n_{i}", "title": p[:24]} for i, p in enumerate(stakeholders)]
        }
    }

def handle_notified_persons(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any],
    contact_vcard_url: str = None
) -> Dict[str, Any]:
    """
    Handle Notified Persons (supports vCard and multiple).
    """
    text = user_input_text.strip()
    draft_data = current_state_data.get("draftData", {})
    existing_notified = draft_data.get("notifiedPersons", [])
    
    # If user explicitly clicked "Done"
    if text.lower() == "done" or text.lower() == "finish":
        return _finish_report(phone_number, state_manager, draft_data)

    config = ConfigManager()
    stakeholders = config.get_options("STAKEHOLDERS")
    if not stakeholders:
         stakeholders = config.get_options("RESPONSIBLE_PERSONS")
         
    notified_person = text
    
    # 1. Handle vCard
    if contact_vcard_url:
        try:
            from lambdas.shared.twilio_client import TwilioClient
            twilio_client = TwilioClient()
            creds = twilio_client._get_credentials()
            resp = requests.get(
                contact_vcard_url,
                auth=(creds.get("account_sid"), creds.get("auth_token"))
            )
            if resp.status_code == 200:
                vcard_data = resp.text
                full_name = re.search(r"FN:(.*)", vcard_data).group(1).strip()
                phones = [p.strip() for p in re.findall(r"TEL.*:(.*)", vcard_data) if p.strip()]
                
                if len(phones) > 1:
                    rows = [{"id": f"sel_notif_{i}", "title": p[:24], "description": full_name[:72]} for i, p in enumerate(phones)]
                    state_manager.update_state(
                        phone_number=phone_number,
                        new_state="WAITING_FOR_NOTIFIED_PERSON_SELECTION",
                        curr_data={"contactName": full_name, "contactPhones": phones}
                    )
                    return {
                        "text": f"Found multiple numbers for *{full_name}*. Please select one:",
                        "interactive": {
                            "type": "list",
                            "button_text": "Select Number",
                            "items": rows
                        }
                    }
                elif len(phones) == 1:
                    notified_person = f"{full_name} ({phones[0]})"
                else:
                    notified_person = full_name
        except Exception as e:
            print(f"Error parsing Notified vCard: {e}")
            
    # 2. Handle Text (List or Manual)
    elif text.startswith("n_"):
        try:
            idx = int(text.split("_")[1])
            if 0 <= idx < len(stakeholders):
                notif_obj = stakeholders[idx]
                notified_person = notif_obj.get("name", notif_obj) if isinstance(notif_obj, dict) else notif_obj
        except:
             pass
    else:
        # Check direct text match
        for s in stakeholders:
             s_name = s.get("name", s) if isinstance(s, dict) else s
             if str(s_name).lower() == text.lower():
                 notified_person = s_name
                 break
                 
    # 3. Add to Notified List and loop
    if notified_person and notified_person.lower() not in ["none", "skip"]:
         if notified_person not in existing_notified:
             existing_notified.append(notified_person)
             
         draft_data["notifiedPersons"] = existing_notified
         state_manager.update_state(
              phone_number=phone_number,
              new_state="WAITING_FOR_NOTIFIED_PERSONS",
              curr_data={"notifiedPersons": existing_notified}
         )
         
         # Present loop to add more or finish
         rows = [{"id": f"n_{i}", "title": (p.get("name", "Unknown") if isinstance(p, dict) else p)[:24]} for i, p in enumerate(stakeholders)]
         
         # Twilio interactive list: prepend Done to the list of items
         final_rows = [{"id": "done", "title": "✅ Done / Finish"}]
         final_rows.extend(rows)
         
         return {
             "text": f"✅ Added: *{notified_person}*\n\nWho else should be notified? (Select from list, share contact, or click Done)",
             "interactive": {
                 "type": "list",
                 "button_text": "Add or Finish",
                 "items": final_rows[:10] # limits to 10
             }
         }
         
    # Fallback to direct finish if skip/none
    return _finish_report(phone_number, state_manager, draft_data)

def handle_notified_person_selection(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> Dict[str, Any]:
    text = user_input_text.strip()
    contact_name = current_state_data.get("contactName", "Unknown")
    contact_phones = current_state_data.get("contactPhones", [])
    
    selected_phone = text
    if text.startswith("sel_notif_"):
        try:
            idx = int(text.split("_")[2])
            if 0 <= idx < len(contact_phones):
                selected_phone = contact_phones[idx]
        except:
             pass
             
    notified_person = f"{contact_name} ({selected_phone})"
    
    draft_data = current_state_data.get("draftData", {})
    existing_notified = draft_data.get("notifiedPersons", [])
    if notified_person not in existing_notified:
        existing_notified.append(notified_person)
        
    draft_data["notifiedPersons"] = existing_notified
    state_manager.update_state(
         phone_number=phone_number,
         new_state="WAITING_FOR_NOTIFIED_PERSONS",
         curr_data={"notifiedPersons": existing_notified}
    )
    
    config = ConfigManager()
    stakeholders = config.get_options("STAKEHOLDERS")
    if not stakeholders:
         stakeholders = config.get_options("RESPONSIBLE_PERSONS")
         
    rows = [{"id": "done", "title": "✅ Done / Finish"}]
    rows.extend([{"id": f"n_{i}", "title": (p.get("name", "Unknown") if isinstance(p, dict) else p)[:24]} for i, p in enumerate(stakeholders)])
    
    return {
         "text": f"✅ Added: *{notified_person}*\n\nWho else should be notified?",
         "interactive": {
             "type": "list",
             "button_text": "Select Person",
             "items": rows[:10] # limit 10
         }
    }

def _finish_report(phone_number: str, state_manager: ConversationState, draft_data: Dict[str, Any]) -> str:
    # Finalize Data
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
    obs_type = draft_data.get("observationType", "Observation")
    category = draft_data.get("hazardCategory", "General")
    
    description = draft_data.get("originalDescription", "")
    
    # Image Link Processing
    image_link = draft_data.get("imageUrl")
    if not image_link:
        s3_url = draft_data.get("s3Url", "")
        if s3_url.startswith("s3://"):
             image_link = s3_url
        else:
             image_link = "Image Link Not Available"
    
    advice = draft_data.get("controlMeasure", draft_data.get("safetyAdvice", "Conduct immediate safety assessment."))
    source_ref = draft_data.get("reference", draft_data.get("safetySource", ""))
    
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    
    project = draft_data.get("project", "Unknown Project")
    location = draft_data.get("location", "Unknown")
    source = draft_data.get("breachSource", "Unknown")
    stop_work_status = "YES" if draft_data.get("stopWork") else "NO"
    remarks = draft_data.get("remarks", "None")
    responsible = draft_data.get("responsiblePerson", "Unknown")
    notified = ", ".join(draft_data.get("notifiedPersons", []))

    # Truncate advice
    if len(advice) > 600:
        advice = advice[:600] + "..."
        
    message = f"""🏗️ Project: {project}
🔍 Hazard Type: {obs_type}
📂 Category: {category}
📍 Location: {location}
👤 Source: {source}
⚠️ Severity: {severity}
🛑 Stop Work: {stop_work_status}
📝 Remarks: {remarks}
📢 Notified: {notified}
👤 Responsible: {responsible}
🔒 Control measures: {advice}
Date: {date_str}
🖼️ {image_link}
🔎 {description}
Log ID {report_num}
—
————————————————"""

    if source_ref and source_ref != "Standard Safety Protocols":
        message += f"\n\n📚 Source: {source_ref}"

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
