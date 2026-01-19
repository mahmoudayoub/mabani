"""Twilio client utilities for WhatsApp messaging."""

import os
import json
import hashlib
import hmac
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError


class TwilioClient:
    """Client for Twilio WhatsApp API operations."""

    def __init__(self):
        """Initialize Twilio client with credentials from Parameter Store."""
        self.ssm_client = boto3.client("ssm")
        self.region = os.environ.get("AWS_REGION", "eu-west-1")
        self._credentials = None

    def _get_credentials(self) -> Dict[str, str]:
        """Retrieve Twilio credentials from AWS Systems Manager Parameter Store."""
        if self._credentials:
            return self._credentials

        parameter_path = os.environ.get("TWILIO_PARAMETER_PATH", "/mabani/twilio")

        try:
            # Get all parameters under the path
            response = self.ssm_client.get_parameters_by_path(
                Path=parameter_path,
                Recursive=True,
                WithDecryption=True,  # Decrypt SecureString parameters
            )

            parameters = response.get("Parameters", [])

            if not parameters:
                raise ValueError(f"No parameters found at path: {parameter_path}")

            # Convert parameters to dictionary
            credentials = {}
            for param in parameters:
                # Extract the key name from the full path (e.g., /mabani/twilio/auth_token -> auth_token)
                key = param["Name"].split("/")[-1]
                credentials[key] = param["Value"]

            self._credentials = credentials
            return self._credentials

        except ClientError as error:
            print(f"Error retrieving Twilio credentials from Parameter Store: {error}")
            raise

    def validate_signature(
        self, signature: str, url: str, params: Dict[str, Any]
    ) -> bool:
        """
        Validate Twilio request signature for security.

        Args:
            signature: X-Twilio-Signature header value
            url: Full URL of the webhook
            params: Request parameters

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            credentials = self._get_credentials()
            auth_token = credentials.get("auth_token")

            if not auth_token:
                print("Auth token not found in credentials")
                return False

            # Sort parameters and concatenate with URL
            sorted_params = sorted(params.items())
            data = url + "".join([f"{k}{v}" for k, v in sorted_params])

            # Compute HMAC-SHA1
            computed_signature = hmac.new(
                auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1
            ).digest()

            # Base64 encode
            import base64

            computed_signature_b64 = base64.b64encode(computed_signature).decode()
            
            is_valid = hmac.compare_digest(computed_signature_b64, signature)
            if not is_valid:
                print(f"Signature Mismatch: Expected {computed_signature_b64}, Got {signature}")
                # print(f"Data used for sig: {data}") # CAUTION: Logs PII
                
            return is_valid

        except Exception as error:
            print(f"Error validating Twilio signature: {error}")
            return False

    def send_message(
        self, to_number: str, message: str, media_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send WhatsApp message via Twilio API.

        Args:
            to_number: Recipient WhatsApp number (with whatsapp: prefix)
            message: Message body
            media_url: Optional media URL to attach

        Returns:
            Response from Twilio API
        """
        try:
            credentials = self._get_credentials()
            account_sid = credentials.get("account_sid")
            auth_token = credentials.get("auth_token")
            from_number = credentials.get("whatsapp_number")

            if not all([account_sid, auth_token, from_number]):
                raise ValueError("Missing required Twilio credentials")

            # Use Twilio REST API
            import requests
            from requests.auth import HTTPBasicAuth

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            data = {"From": from_number, "To": to_number, "Body": message}

            if media_url:
                data["MediaUrl"] = media_url

            response = requests.post(
                url, data=data, auth=HTTPBasicAuth(account_sid, auth_token)
            )

            response.raise_for_status()
            return response.json()

        except Exception as error:
            print(f"Error sending Twilio message: {error}")
            raise

    def send_interactive_message(
        self, to_number: str, body_text: str, interactive_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send an interactive message (Buttons or List) using Twilio Content API.
        Creates a session-based content object on the fly using direct HTTP requests.
        """
        try:
            # Ensure "whatsapp:" prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            
            # Use the configured from_number
            credentials = self._get_credentials()
            from_number = credentials.get("whatsapp_number")
            account_sid = credentials.get("account_sid")
            auth_token = credentials.get("auth_token")

            # 1. Construct Content Payload
            content_type = ""
            content_body = {}
            
            msg_type = interactive_data.get("type")
            
            if msg_type == "button":
                # Quick Reply (Buttons)
                # Twilio Content API Type: twilio/quick-reply
                content_type = "twilio/quick-reply"
                actions = []
                for btn in interactive_data.get("buttons", []):
                    # Title max 20 chars
                    title = btn["title"]
                    if len(title) > 20: 
                         title = title[:19] + "…"
                    actions.append({
                        "title": title, 
                        "id": btn["id"]
                    })
                    
                content_body = {
                    "body": body_text[:1000],
                    "actions": actions
                }
                
            elif msg_type == "list":
                # List Picker
                # Twilio Content API Type: twilio/list-picker
                content_type = "twilio/list-picker"
                items = []
                for item in interactive_data.get("items", [])[:10]: # Enforce max 10 limit
                    # Item title max 24 chars
                    title = item["title"]
                    if len(title) > 24:
                        title = title[:23] + "…"
                        
                    itm = {
                        "item": title, 
                        "id": item["id"]
                    }
                    if item.get("description"):
                        desc = item["description"]
                        if len(desc) > 72:
                            desc = desc[:71] + "…"
                        itm["description"] = desc
                    items.append(itm)
                    
                content_body = {
                    "body": body_text[:1000],
                    "button": interactive_data.get("button_text", "Select")[:20],
                    "items": items
                }
                
            else:
                # Fallback to text if unknown type
                print(f"Unknown interactive type {msg_type}, falling back to text.")
                return self.send_message(to_number, body_text)

            # 2. Create Content Resource (Dynamic) via Direct HTTP
            import requests
            from requests.auth import HTTPBasicAuth
            
            # URL for creating content
            # API: https://content.twilio.com/v1/Content
            content_url = "https://content.twilio.com/v1/Content"
            
            payload = {
                "friendly_name": f"Session_Content_{msg_type}",
                "variables": {},
                "types": {
                    content_type: content_body
                },
                "language": "en" 
            }
            
            # Create content
            content_resp = requests.post(
                content_url,
                json=payload,
                auth=HTTPBasicAuth(account_sid, auth_token),
                headers={"Content-Type": "application/json"}
            )
            
            if content_resp.status_code not in [200, 201]:
                print(f"Failed to create content: {content_resp.status_code} - {content_resp.text}")
                raise Exception(f"Content API Error: {content_resp.text}")
                
            content_data = content_resp.json()
            content_sid = content_data["sid"]
            print(f"Created ephemeral content {content_sid} for {to_number}")
            
            # 3. Send Message linked to Content SID
            # Use Message resource
            msg_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            
            msg_data = {
                "From": from_number,
                "To": to_number,
                "ContentSid": content_sid
            }
            
            msg_resp = requests.post(
                msg_url,
                data=msg_data,
                auth=HTTPBasicAuth(account_sid, auth_token)
            )
            
            if msg_resp.status_code not in [200, 201]:
                 print(f"Failed to send message linked to content: {msg_resp.status_code} - {msg_resp.text}")
                 raise Exception(f"Message Send Error: {msg_resp.text}")
                 
            msg_json = msg_resp.json()
            print(f"Interactive message sent: {msg_json['sid']}")
            return msg_json
            
        except Exception as error:
            print(f"Error sending interactive message: {error}")
            import traceback
            traceback.print_exc()
            # Fallback to plain text with instructions
            fallback_text = f"{body_text}\n\n[Display Error: Please reply with your choice]"
            return self.send_message(to_number, fallback_text)

    def parse_webhook(self, body: str) -> Dict[str, Any]:
        """
        Parse Twilio webhook body from form-encoded format.
        Does NOT modify the payload to ensure signature validation passes.

        Args:
            body: Request body string

        Returns:
            Parsed parameters as dictionary
        """
        from urllib.parse import parse_qs

        if not body:
            return {}

        parsed = parse_qs(body)
        # Convert single-item lists to values
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def process_interactive_response(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract the actual selected ID from InteractionData if present.
        Returns a COPY of params with 'Body' updated to the selected ID.
        """
        data = params.copy()
        
        # Check for Interactive Message Payload
        if 'InteractionData' in data:
            try:
                interaction = json.loads(data['InteractionData'])
                interaction_type = interaction.get('type')
                
                selected_id = None
                
                if interaction_type == 'list_response':
                    selected_id = interaction.get('list_reply', {}).get('id')
                elif interaction_type == 'quick_reply':
                    selected_id = interaction.get('button_reply', {}).get('id')
                elif interaction_type == 'button_reply': # Standard button
                     selected_id = interaction.get('button_reply', {}).get('id')

                if selected_id:
                    print(f"Interactive Reply Detected. Overriding Body '{data.get('Body')}' with ID '{selected_id}'")
                    data['Body'] = selected_id
                    
            except Exception as e:
                print(f"Error parsing InteractionData: {e}")
                
        return data


def format_hs_response(report_data: Dict[str, Any]) -> str:
    """
    Format H&S report response for WhatsApp.

    Args:
        report_data: Complete report data

    Returns:
        Formatted message string
    """
    request_id = report_data.get("requestId", "Unknown")
    report_number = report_data.get("reportNumber", "N/A")
    description = report_data.get("rewrittenDescription", "")
    severity = report_data.get("severity", "MEDIUM")
    hazard_types = report_data.get("hazardTypes", [])
    control_measure = report_data.get("controlMeasure", "")
    reference = report_data.get("reference", "")

    # Severity emoji
    severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")

    message = f"""✅ H&S Report Received - #{report_number}

📋 Description:
{description}

{severity_emoji} Severity: {severity}"""

    if hazard_types:
        message += f"\n\n🎯 Hazard Type:\n{hazard_types[0]}"

    if control_measure:
        message += f"\n\n🛡️ Recommended Action:\n{control_measure}"

    if reference:
        message += f"\n\n📚 Reference: {reference}"

    message += "\n\nYour report has been logged and relevant teams have been notified."

    return message


def format_quality_response(report_data: Dict[str, Any]) -> str:
    """
    Format Quality report response for WhatsApp.

    Args:
        report_data: Complete report data

    Returns:
        Formatted message string
    """
    request_id = report_data.get("requestId", "Unknown")
    report_number = report_data.get("reportNumber", "N/A")
    description = report_data.get("rewrittenDescription", "")
    severity = report_data.get("severity", "MEDIUM")
    hazard_types = report_data.get("hazardTypes", [])

    # Priority emoji
    severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")

    message = f"""✅ Quality Report Received - #{report_number}

📋 Description:
{description}

{severity_emoji} Priority: {severity}"""

    if hazard_types:
        message += f"\n\n🔍 Issue Type:\n{hazard_types[0]}"

    message += (
        "\n\nYour report has been logged and the quality team will review it shortly."
    )

    return message


def format_error_response() -> str:
    """Format error response for missing required fields."""
    return """❌ Unable to process your report.

Please ensure you include both:
• An image
• A description of the issue

Try sending your report again with both items."""
