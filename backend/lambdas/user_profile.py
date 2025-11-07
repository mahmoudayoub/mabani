import json
from datetime import datetime
from .shared.lambda_helpers import (
    with_error_handling,
    create_response,
    create_error_response,
    get_user_id,
    table,
)


@with_error_handling
def health_check(event, context):
    """Health check endpoint."""
    return create_response(
        200,
        {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "taskflow-backend",
        },
    )


@with_error_handling
def get_user_profile(event, context):
    """Get user profile."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    try:
        response = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"})

        if "Item" not in response:
            return create_error_response(404, "User profile not found")

        item = response["Item"]
        return create_response(
            200,
            {
                "userId": item.get("userId"),
                "email": item.get("email"),
                "name": item.get("name"),
                "createdAt": item.get("createdAt"),
                "updatedAt": item.get("updatedAt"),
            },
        )
    except Exception as error:
        return create_error_response(500, "Failed to fetch user profile", error)


@with_error_handling
def update_user_profile(event, context):
    """Update user profile."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    try:
        body = json.loads(event["body"])
        name = body.get("name")
        email = body.get("email")

        if not name and not email:
            return create_error_response(
                400, "At least one field (name, email) is required"
            )

        timestamp = datetime.utcnow().isoformat()

        # Build update expression dynamically
        update_expression = "SET updatedAt = :updatedAt"
        expression_attribute_values = {":updatedAt": timestamp}
        expression_attribute_names = {}

        if name:
            update_expression += ", #name = :name"
            expression_attribute_values[":name"] = name
            expression_attribute_names["#name"] = "name"

        if email:
            update_expression += ", #email = :email"
            expression_attribute_values[":email"] = email
            expression_attribute_names["#email"] = "email"

        table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ConditionExpression="attribute_exists(PK)",
        )

        return create_response(
            200, {"message": "Profile updated successfully", "updatedAt": timestamp}
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return create_error_response(404, "User profile not found")
        return create_error_response(500, "Failed to update user profile", error)
    except Exception as error:
        return create_error_response(500, "Failed to update user profile", error)
