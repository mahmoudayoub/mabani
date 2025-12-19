"""Helper utilities for testing Lambda functions."""

import json
from typing import Any, Dict, Optional


def create_api_response(
    status_code: int,
    body: Any,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Create a standardized API Gateway response."""
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }


def parse_event_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse event body from API Gateway event."""
    if not event.get("body"):
        return {}

    body = event["body"]
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body


def get_user_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from authenticated API Gateway event."""
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def create_error_response(
    error: str,
    status_code: int = 400,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a standardized error response."""
    body = {"error": error}
    if details:
        body["details"] = details

    return create_api_response(status_code, body)


def assert_api_response(response: Dict[str, Any], expected_status: int = 200):
    """Assert that a response has the expected structure and status code."""
    assert "statusCode" in response
    assert "headers" in response
    assert "body" in response
    assert response["statusCode"] == expected_status

    # Parse body to ensure it's valid JSON
    body = json.loads(response["body"])
    return body


def assert_error_response(response: Dict[str, Any], expected_status: int = 400):
    """Assert that an error response has the expected structure."""
    body = assert_api_response(response, expected_status)
    assert "error" in body
    return body
