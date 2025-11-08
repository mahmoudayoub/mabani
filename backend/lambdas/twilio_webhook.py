"""Twilio webhook handler for incoming WhatsApp messages."""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any
import boto3

# Import from parent directory when running locally, or from shared when deployed
try:
    from shared.twilio_client import TwilioClient, format_error_response
    from shared.validators import validate_twilio_webhook, sanitize_phone_number
    from shared.lambda_helpers import create_response
except ImportError:
    from lambdas.shared.twilio_client import TwilioClient, format_error_response
    from lambdas.shared.validators import validate_twilio_webhook, sanitize_phone_number
    from lambdas.shared.lambda_helpers import create_response


# Initialize clients
twilio_client = TwilioClient()
sfn_client = boto3.client("stepfunctions")
dynamodb = boto3.resource("dynamodb")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle incoming Twilio WhatsApp webhook.

    This function:
    1. Validates Twilio signature
    2. Validates required fields (image + description)
    3. Starts Step Functions execution for processing
    4. Returns 200 OK to Twilio

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    print(f"Received webhook: {json.dumps(event)}")

    try:
        # Parse webhook body
        body = event.get("body", "")
        params = twilio_client.parse_webhook(body)

        # Validate Twilio signature for security
        signature = event.get("headers", {}).get("X-Twilio-Signature", "")
        request_url = _build_request_url(event)

        if not twilio_client.validate_signature(signature, request_url, params):
            print("Invalid Twilio signature")
            return create_response(403, {"error": "Invalid signature"})

        # Validate required fields
        validation = validate_twilio_webhook(params)

        if not validation["isValid"]:
            print(f"Validation failed: {validation['errors']}")

            # Send error message to user
            from_number = params.get("From")
            if from_number:
                error_message = format_error_response()
                twilio_client.send_message(from_number, error_message)

            return create_response(
                200, {"message": "Validation failed", "errors": validation["errors"]}
            )

        # Generate request ID
        request_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Extract validated data
        data = validation["data"]
        sender = sanitize_phone_number(data["sender"])

        # Create initial payload for Step Functions
        payload = {
            "requestId": request_id,
            "timestamp": timestamp,
            "sender": sender,
            "description": data["description"],
            "imageUrl": data["imageUrl"],
            "messageSid": data["messageSid"],
            "status": "RECEIVED",
        }

        # Store initial record in DynamoDB
        _store_initial_record(payload)

        # Start Step Functions execution OR invoke processor directly
        state_machine_arn = os.environ.get("STATE_MACHINE_ARN")

        if state_machine_arn:
            sfn_response = sfn_client.start_execution(
                stateMachineArn=state_machine_arn,
                name=f"report-{request_id}",
                input=json.dumps(payload),
            )
            print(f"Started Step Functions execution: {sfn_response['executionArn']}")
        else:
            # Invoke report processor Lambda directly
            print(
                "STATE_MACHINE_ARN not configured, invoking processor Lambda directly"
            )
            lambda_client = boto3.client("lambda")
            processor_function = os.environ.get(
                "PROCESSOR_FUNCTION_NAME", "taskflow-backend-dev-reportProcessor"
            )
            lambda_client.invoke(
                FunctionName=processor_function,
                InvocationType="Event",  # Async invocation
                Payload=json.dumps(payload),
            )
            print(f"Invoked processor Lambda: {processor_function}")

        # Return success to Twilio (must respond within 15 seconds)
        return create_response(
            200, {"message": "Report received", "requestId": request_id}
        )

    except Exception as error:
        print(f"Error processing webhook: {error}")
        import traceback

        traceback.print_exc()

        # Still return 200 to Twilio to avoid retries
        return create_response(
            200,
            {
                "error": "Internal error",
                "message": "We received your report but encountered an issue. Our team will follow up.",
            },
        )


def _build_request_url(event: Dict[str, Any]) -> str:
    """
    Build full request URL for signature validation.

    Args:
        event: API Gateway event

    Returns:
        Full request URL
    """
    headers = event.get("headers", {})
    request_context = event.get("requestContext", {})

    # Get protocol
    protocol = headers.get("X-Forwarded-Proto", "https")

    # Get host
    host = headers.get("Host", "")

    # Get path
    path = request_context.get("path", event.get("path", ""))

    return f"{protocol}://{host}{path}"


def _store_initial_record(payload: Dict[str, Any]) -> None:
    """
    Store initial record in DynamoDB.

    Args:
        payload: Initial report data
    """
    try:
        table_name = os.environ.get("REPORTS_TABLE", "IncidentReports-dev")
        table = dynamodb.Table(table_name)

        request_id = payload["requestId"]

        item = {
            "PK": f"REPORT#{request_id}",
            "SK": "METADATA",
            "requestId": request_id,
            "timestamp": payload["timestamp"],
            "sender": payload["sender"],
            "description": payload["description"],
            "imageUrl": payload["imageUrl"],
            "messageSid": payload["messageSid"],
            "status": "RECEIVED",
            "createdAt": payload["timestamp"],
            "updatedAt": payload["timestamp"],
        }

        table.put_item(Item=item)
        print(f"Stored initial record for request {request_id}")

    except Exception as error:
        print(f"Error storing initial record: {error}")
        # Don't fail the webhook if DynamoDB write fails
