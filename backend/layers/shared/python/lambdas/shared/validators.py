"""Validation utilities for report processing."""

from typing import Dict, Any, Optional


def validate_twilio_webhook(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate Twilio webhook contains required fields.

    Args:
        params: Parsed webhook parameters

    Returns:
        Dictionary with validation result
    """
    # Check for required fields
    from_number = params.get("From")
    body = params.get("Body")
    num_media = int(params.get("NumMedia", 0))
    media_url = params.get("MediaUrl0")

    errors = []

    if not from_number:
        errors.append("Missing sender phone number")

    if not body or not body.strip():
        errors.append("Missing description text")

    if num_media == 0 or not media_url:
        errors.append("Missing image attachment")

    is_valid = len(errors) == 0

    return {
        "isValid": is_valid,
        "errors": errors,
        "data": {
            "sender": from_number,
            "description": body.strip() if body else "",
            "imageUrl": media_url,
            "numMedia": num_media,
            "messageSid": params.get("MessageSid"),
        },
    }


def determine_report_type(description: str, project_type: Optional[str] = None) -> str:
    """
    Determine if report is H&S or Quality based on description.

    Args:
        description: Report description
        project_type: Optional project type hint

    Returns:
        "HS" or "QUALITY"
    """
    # Keywords for quality issues
    quality_keywords = [
        "quality",
        "defect",
        "workmanship",
        "finish",
        "specification",
        "tolerance",
        "installation",
        "material defect",
        "rework",
    ]

    # Keywords for H&S issues
    hs_keywords = [
        "safety",
        "hazard",
        "danger",
        "risk",
        "injury",
        "fall",
        "ppe",
        "equipment",
        "unsafe",
        "accident",
        "incident",
    ]

    description_lower = description.lower()

    # Count keyword matches
    quality_score = sum(
        1 for keyword in quality_keywords if keyword in description_lower
    )
    hs_score = sum(1 for keyword in hs_keywords if keyword in description_lower)

    # If unclear, default to H&S (safer default)
    if quality_score > hs_score:
        return "QUALITY"
    else:
        return "HS"


def sanitize_phone_number(phone: str) -> str:
    """
    Sanitize phone number from WhatsApp format.

    Args:
        phone: Phone number (e.g., "whatsapp:+1234567890")

    Returns:
        Sanitized phone number (e.g., "+1234567890")
    """
    if phone.startswith("whatsapp:"):
        return phone.replace("whatsapp:", "")
    return phone
