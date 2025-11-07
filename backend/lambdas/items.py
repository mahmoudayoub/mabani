import json
import base64
from datetime import datetime
from botocore.exceptions import ClientError
from .shared.lambda_helpers import (
    with_error_handling,
    create_response,
    create_error_response,
    get_user_id,
    validate_required_fields,
    table,
)


@with_error_handling
def create_item(event, context):
    """Create a new item."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    try:
        body = json.loads(event["body"])
        validation = validate_required_fields(body, ["title", "description"])

        if not validation["is_valid"]:
            return create_error_response(
                400,
                "Missing required fields",
                {"missing_fields": validation["missing_fields"]},
            )

        timestamp = datetime.utcnow().isoformat()
        item_id = f"ITEM#{int(datetime.utcnow().timestamp() * 1000)}"

        item = {
            "PK": f"USER#{user_id}",
            "SK": item_id,
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": timestamp,
            "itemId": item_id,
            "userId": user_id,
            "title": body["title"],
            "description": body["description"],
            "status": body.get("status", "active"),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

        table.put_item(Item=item)

        return create_response(
            201,
            {
                "message": "Item created successfully",
                "itemId": item_id,
                "createdAt": timestamp,
            },
        )
    except Exception as error:
        return create_error_response(500, "Failed to create item", error)


@with_error_handling
def get_user_items(event, context):
    """Get user items."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    try:
        query_params = event.get("queryStringParameters") or {}
        limit = int(query_params.get("limit", 20))
        last_key = query_params.get("lastKey")

        params = {
            "TableName": table.table_name,
            "IndexName": "GSI1",
            "KeyConditionExpression": "GSI1PK = :userId",
            "ExpressionAttributeValues": {":userId": f"USER#{user_id}"},
            "ScanIndexForward": False,
            "Limit": limit,
        }

        if last_key:
            params["ExclusiveStartKey"] = json.loads(
                base64.b64decode(last_key).decode()
            )

        response = table.query(**params)

        items = []
        for item in response.get("Items", []):
            items.append(
                {
                    "itemId": item.get("itemId"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "status": item.get("status"),
                    "createdAt": item.get("createdAt"),
                    "updatedAt": item.get("updatedAt"),
                }
            )

        last_key_encoded = None
        if "LastEvaluatedKey" in response:
            last_key_encoded = base64.b64encode(
                json.dumps(response["LastEvaluatedKey"]).encode()
            ).decode()

        return create_response(
            200,
            {
                "items": items,
                "lastKey": last_key_encoded,
                "count": response.get("Count", 0),
            },
        )
    except Exception as error:
        return create_error_response(500, "Failed to fetch items", error)


@with_error_handling
def update_item(event, context):
    """Update item."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    item_id = event.get("pathParameters", {}).get("itemId")
    if not item_id:
        return create_error_response(400, "Item ID is required")

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    try:
        body = json.loads(event["body"])
        timestamp = datetime.utcnow().isoformat()

        update_expression = "SET updatedAt = :updatedAt"
        expression_attribute_values = {":updatedAt": timestamp, ":userId": user_id}
        expression_attribute_names = {}

        if "title" in body:
            update_expression += ", #title = :title"
            expression_attribute_values[":title"] = body["title"]
            expression_attribute_names["#title"] = "title"

        if "description" in body:
            update_expression += ", #description = :description"
            expression_attribute_values[":description"] = body["description"]
            expression_attribute_names["#description"] = "description"

        if "status" in body:
            update_expression += ", #status = :status"
            expression_attribute_values[":status"] = body["status"]
            expression_attribute_names["#status"] = "status"

        if len(expression_attribute_names) == 0:
            return create_error_response(400, "No fields to update")

        table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": f"ITEM#{item_id}"},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ConditionExpression="attribute_exists(PK) AND userId = :userId",
        )

        return create_response(
            200, {"message": "Item updated successfully", "updatedAt": timestamp}
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return create_error_response(404, "Item not found or access denied")
        return create_error_response(500, "Failed to update item", error)
    except Exception as error:
        return create_error_response(500, "Failed to update item", error)


@with_error_handling
def delete_item(event, context):
    """Delete item."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    item_id = event.get("pathParameters", {}).get("itemId")
    if not item_id:
        return create_error_response(400, "Item ID is required")

    try:
        table.delete_item(
            Key={"PK": f"USER#{user_id}", "SK": f"ITEM#{item_id}"},
            ConditionExpression="attribute_exists(PK) AND userId = :userId",
            ExpressionAttributeValues={":userId": user_id},
        )

        return create_response(200, {"message": "Item deleted successfully"})
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return create_error_response(404, "Item not found or access denied")
        return create_error_response(500, "Failed to delete item", error)
    except Exception as error:
        return create_error_response(500, "Failed to delete item", error)
