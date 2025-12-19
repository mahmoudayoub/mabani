import json
import os
from typing import Dict, Any, Optional
from decimal import Decimal
import boto3

# Lazy initialization of DynamoDB table to avoid import-time failures
_dynamodb = None
_table = None
_table_name = None


def _get_dynamodb():
    """Get or create DynamoDB resource (lazy initialization)."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _get_table():
    """Get or create DynamoDB table (lazy initialization)."""
    global _table, _table_name
    if _table is None:
        _table_name = os.environ.get("DYNAMODB_TABLE_NAME", "taskflow-table")
        _table = _get_dynamodb().Table(_table_name)
    return _table


# For backward compatibility, expose table as a property that initializes lazily
class _LazyTable:
    """Lazy wrapper for DynamoDB table to avoid import-time initialization."""

    def __getattr__(self, name):
        return getattr(_get_table(), name)


table = _LazyTable()

# Lazy initialization of S3 client for shared use
_s3_client = None


def get_s3_client():
    """Get or create S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal objects from DynamoDB."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int if it's a whole number, otherwise float
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def _convert_decimals(obj):
    """Recursively convert Decimal objects to int or float."""
    if isinstance(obj, Decimal):
        # Convert Decimal to int if it's a whole number, otherwise float
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {key: _convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    return obj


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

    # Convert Decimal objects to JSON-serializable types
    body = _convert_decimals(body)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body, cls=DecimalEncoder),
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


def _get_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract authorizer claims from the event."""
    return event.get("requestContext", {}).get("authorizer", {}).get("claims", {}) or {}


def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from Cognito JWT claims."""
    try:
        claims = _get_claims(event)
        return claims.get("sub")
    except Exception as error:
        print(f"Error extracting user ID: {error}")
        return None


def get_user_email(event: Dict[str, Any]) -> Optional[str]:
    """Extract user email from Cognito JWT claims."""
    try:
        claims = _get_claims(event)
        return claims.get("email")
    except Exception as error:
        print(f"Error extracting user email: {error}")
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
