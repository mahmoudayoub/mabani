"""Twilio webhook handler for incoming WhatsApp messages."""

import json
import os
from datetime import datetime
from typing import Dict, Any
import boto3

try:
    from shared.twilio_client import TwilioClient
    from shared.lambda_helpers import create_response
except ImportError:
    from lambdas.shared.twilio_client import TwilioClient
    from lambdas.shared.lambda_helpers import create_response

# Initialize clients
twilio_client = TwilioClient()
lambda_client = boto3.client("lambda")

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle incoming Twilio WhatsApp webhook (Ingest & Ack Only).
    """
    print(f"Received webhook: {json.dumps(event)}")

    try:
        # 1. Parse webhook
        body_str = event.get("body", "")
        params = twilio_client.parse_webhook(body_str)
        
        # 2. Validate Signature
        headers = event.get("headers", {})
        signature = headers.get("X-Twilio-Signature", "")
        request_url = _build_request_url(event)

        if not twilio_client.validate_signature(signature, request_url, params):
            print(f"WARNING: Invalid Twilio signature. Sig: {signature}, Url: {request_url}")
            # return create_response(403, {"error": "Invalid signature"}) # TODO: Re-enable after debugging
            pass

        # 3. Extract Payload
        # Process interactive response (extract ID if present)
        processed_params = twilio_client.process_interactive_response(params)
        
        from_number = processed_params.get("From")
        body_content = processed_params.get("Body", "").strip()
        num_media = int(processed_params.get("NumMedia", "0"))
        
        # Handle Location Message
        if processed_params.get("Latitude") and processed_params.get("Longitude"):
            lat = processed_params.get("Latitude")
            lon = processed_params.get("Longitude")
            body_content = f"Location: {lat},{lon}"
            print(f"Location received: {body_content}")
        
        payload = {
            "from_number": from_number,
            "body_content": body_content,
            "media_url": params.get("MediaUrl0") if num_media > 0 else None
        }
        
        # 4. Invoke Worker Async
        worker_function_name = os.environ.get("WORKFLOW_FUNCTION_NAME")
        
        if worker_function_name:
            lambda_client.invoke(
                FunctionName=worker_function_name,
                InvocationType='Event', # Async
                Payload=json.dumps(payload)
            )
            print(f"Invoked worker: {worker_function_name}")
        else:
             print("Error: WORKFLOW_FUNCTION_NAME not set")

        # 5. Return 200 OK (Ack)
        # Empty TwiML tells Twilio "Message received, no immediate reply"
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/xml"},
            "body": "<Response></Response>"
        }

    except Exception as error:
        print(f"Error processing webhook: {error}")
        return create_response(200, {"message": "Error received"}) # Always return 200 to stop retry loops

def _build_request_url(event: Dict[str, Any]) -> str:
    """Build full request URL for signature validation."""
    headers = event.get("headers", {})
    request_context = event.get("requestContext", {})
    protocol = headers.get("X-Forwarded-Proto", "https")
    host = headers.get("Host", "")
    path = request_context.get("path", event.get("path", ""))
    return f"{protocol}://{host}{path}"
