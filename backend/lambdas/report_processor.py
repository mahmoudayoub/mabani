"""Report processor orchestrator for image analysis and LLM operations."""

import json
import os
from typing import Dict, Any
from datetime import datetime
import boto3

# Import from parent directory when running locally, or from shared when deployed
try:
    from shared.bedrock_client import BedrockClient
    from shared.s3_client import S3Client
    from shared.twilio_client import (
        TwilioClient,
        format_hs_response,
        format_quality_response,
    )
    from shared.validators import determine_report_type
except ImportError:
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.s3_client import S3Client
    from lambdas.shared.twilio_client import (
        TwilioClient,
        format_hs_response,
        format_quality_response,
    )
    from lambdas.shared.validators import determine_report_type


# Initialize clients
bedrock_client = BedrockClient()
s3_client = S3Client()
twilio_client = TwilioClient()
dynamodb = boto3.resource("dynamodb")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process report: image analysis, LLM operations, and response.

    This is the main orchestrator that:
    1. Determines report type (H&S vs Quality)
    2. Rewrites description
    3. Uploads image to S3
    4. Generates image caption
    5. Classifies severity
    6. Classifies hazard type
    7. Generates control measures (H&S only)
    8. Stores complete report
    9. Sends WhatsApp response

    Args:
        event: Input from Step Functions or direct invocation
        context: Lambda context

    Returns:
        Complete report data
    """
    print(f"Processing report: {json.dumps(event)}")

    try:
        request_id = event["requestId"]
        report_number = event.get("reportNumber", "N/A")
        sender = event["sender"]
        description = event["description"]
        image_url = event["imageUrl"]

        # Step 1: Determine report type
        report_type = determine_report_type(description)
        print(f"Report type: {report_type}")

        # Step 2: Get project information (mock for now)
        project_info = _get_project_info(sender)

        # Step 3: Rewrite description
        print("Rewriting description...")
        rewritten_description = bedrock_client.rewrite_description(
            description, timestamp=event["timestamp"]
        )
        print(f"Rewritten: {rewritten_description}")

        # Step 4: Upload image to S3
        print("Uploading image to S3...")
        image_data = s3_client.upload_image(
            image_url=image_url,
            request_id=request_id,
            metadata={
                "request-id": request_id,
                "sender": sender,
                "report-type": report_type,
                "timestamp": event["timestamp"],
            },
        )
        print(f"Image uploaded to: {image_data['s3Key']}")

        # Step 5: Generate image caption
        print("Generating image caption...")
        image_bytes = s3_client.download_image(image_data["s3Key"])
        image_caption = bedrock_client.caption_image(
            image_data=image_bytes,
            description=rewritten_description,
            report_type=report_type,
        )
        print(f"Image caption: {image_caption}")

        # Step 6: Classify severity
        print("Classifying severity...")
        severity_data = bedrock_client.classify_severity(
            description=rewritten_description, image_caption=image_caption
        )
        severity = severity_data["severity"]
        severity_reason = severity_data["reason"]
        print(f"Severity: {severity} - {severity_reason}")

        # Step 7: Classify hazard type
        print("Classifying hazard type...")
        hazard_types = bedrock_client.classify_hazard_type(
            description=rewritten_description,
            image_caption=image_caption,
            severity=severity,
            report_type=report_type,
        )
        print(f"Hazard types: {hazard_types}")

        # Step 8: Generate control measures (H&S only)
        control_measure = None
        reference = None

        if report_type == "HS":
            print("Generating control measures...")
            control_data = bedrock_client.generate_control_measure(
                description=rewritten_description,
                image_caption=image_caption,
                severity=severity,
                hazard_types=hazard_types,
                project_name=project_info["name"],
            )
            control_measure = control_data["controlMeasure"]
            reference = control_data["reference"]
            print(f"Control measure: {control_measure}")

        # Step 9: Build complete report
        report_data = {
            "requestId": request_id,
            "reportNumber": report_number,
            "timestamp": event["timestamp"],
            "reportType": report_type,
            "sender": sender,
            "project": project_info,
            "originalDescription": description,
            "rewrittenDescription": rewritten_description,
            "image": image_data,
            "imageCaption": image_caption,
            "severity": severity,
            "severityReason": severity_reason,
            "hazardTypes": hazard_types,
            "controlMeasure": control_measure,
            "reference": reference,
            "status": "PROCESSED",
            "processedAt": datetime.utcnow().isoformat(),
        }

        # Step 10: Store complete report in DynamoDB
        print("Storing report in DynamoDB...")
        _store_report(report_data)

        # Step 11: Send WhatsApp response
        print("Sending WhatsApp response...")
        response_message = _format_response(report_data)
        print(f"Response message: {response_message[:200]}...")  # Log first 200 chars

        send_result = twilio_client.send_message(
            to_number=f"whatsapp:{sender}", message=response_message
        )
        print(
            f"WhatsApp message sent successfully! SID: {send_result.get('sid', 'N/A')}"
        )

        print(f"Report processing completed for {request_id}")
        return report_data

    except Exception as error:
        print(f"Error processing report: {error}")
        import traceback

        traceback.print_exc()

        # Try to send error message to user
        try:
            error_msg = """⚠️ We encountered an issue processing your report.

Our team has been notified and will review your submission manually. Thank you for your patience."""

            twilio_client.send_message(
                to_number=f"whatsapp:{event.get('sender', '')}", message=error_msg
            )
        except Exception as send_error:
            print(f"Failed to send error message: {send_error}")

        raise


def _get_project_info(sender: str) -> Dict[str, Any]:
    """
    Get project information for sender.

    Args:
        sender: Phone number

    Returns:
        Project information
    """
    try:
        # Query DynamoDB for user-project mapping
        table_name = os.environ.get("USER_PROJECT_TABLE", "UserProjectMappings-dev")
        table = dynamodb.Table(table_name)

        response = table.get_item(Key={"phoneNumber": sender})

        if "Item" in response:
            item = response["Item"]
            return {
                "id": item.get("projectId", "default-project"),
                "name": item.get("projectName", "Default Project"),
                "type": item.get("projectType", "construction"),
            }

    except Exception as error:
        print(f"Error fetching project info: {error}")

    # Return default project if not found
    return {"id": "default-project", "name": "Default Project", "type": "construction"}


def _store_report(report_data: Dict[str, Any]) -> None:
    """
    Store complete report in DynamoDB.

    Args:
        report_data: Complete report data
    """
    table_name = os.environ.get("REPORTS_TABLE", "IncidentReports-dev")
    table = dynamodb.Table(table_name)

    request_id = report_data["requestId"]
    project_id = report_data["project"]["id"]
    sender = report_data["sender"]
    timestamp = report_data["timestamp"]
    severity = report_data["severity"]

    # Create DynamoDB item
    item = {
        "PK": f"REPORT#{request_id}",
        "SK": "METADATA",
        "requestId": request_id,
        "reportNumber": report_data.get("reportNumber"),
        "reportType": report_data["reportType"],
        "timestamp": timestamp,
        "sender": sender,
        "project": report_data["project"],
        "originalDescription": report_data["originalDescription"],
        "rewrittenDescription": report_data["rewrittenDescription"],
        "image": report_data["image"],
        "imageCaption": report_data["imageCaption"],
        "severity": severity,
        "severityReason": report_data["severityReason"],
        "hazardTypes": report_data["hazardTypes"],
        "status": "PROCESSED",
        "processedAt": report_data["processedAt"],
        "createdAt": timestamp,
        "updatedAt": report_data["processedAt"],
        # GSI keys for querying
        "GSI1PK": f"PROJECT#{project_id}",
        "GSI1SK": f"SEVERITY#{severity}#{timestamp}",
        "GSI2PK": f"SENDER#{sender}",
        "GSI2SK": timestamp,
    }

    # Add control measure if present (H&S only)
    if report_data.get("controlMeasure"):
        item["controlMeasure"] = report_data["controlMeasure"]
        item["reference"] = report_data["reference"]

    table.put_item(Item=item)
    print(f"Report stored in DynamoDB: {request_id}")


def _format_response(report_data: Dict[str, Any]) -> str:
    """
    Format response message based on report type.

    Args:
        report_data: Complete report data

    Returns:
        Formatted message
    """
    if report_data["reportType"] == "HS":
        return format_hs_response(report_data)
    else:
        return format_quality_response(report_data)
