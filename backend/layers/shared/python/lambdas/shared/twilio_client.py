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

            return hmac.compare_digest(computed_signature_b64, signature)

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


    def parse_webhook(self, body: str) -> Dict[str, Any]:
        """
        Parse Twilio webhook body from form-encoded format.

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
