import json
import os
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("DYNAMODB_TABLE_NAME", "taskflow-table")
table = dynamodb.Table(table_name)


def create_response(
    status_code: int, body: Any, headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Create a standardized API Gateway response."""
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body),
    }


def create_error_response(
    status_code: int, message: str, error: Optional[Any] = None
) -> Dict[str, Any]:
    """Create a standardized error response."""
    print(f"Error: {message}", error)
    body = {"error": message}
    if error:
        body["details"] = str(error)

    return create_response(status_code, body)


def handle_cors(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle CORS preflight requests."""
    if event.get("httpMethod") == "OPTIONS":
        return create_response(200, {})
    return None


def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from Cognito JWT claims."""
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        return claims.get("sub")
    except Exception as error:
        print(f"Error extracting user ID: {error}")
        return None


def validate_required_fields(
    body: Dict[str, Any], required_fields: list
) -> Dict[str, Any]:
    """Validate that required fields are present in the request body."""
    missing_fields = [field for field in required_fields if not body.get(field)]
    return {"is_valid": len(missing_fields) == 0, "missing_fields": missing_fields}


def with_error_handling(func):
    """Decorator to handle common errors in Lambda functions."""

    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        try:
            # Handle CORS preflight
            cors_response = handle_cors(event)
            if cors_response:
                return cors_response

            return func(event, context)
        except Exception as error:
            print(f"Unhandled error: {error}")
            return create_error_response(500, "Internal server error", error)

    return wrapper
