import pytest
import json
from unittest.mock import patch, MagicMock
from lambdas.user_profile import health_check, get_user_profile, update_user_profile
from lambdas.items import create_item, get_user_items, update_item, delete_item


def test_health_check():
    """Test health check endpoint."""
    event = {}
    context = {}

    response = health_check(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "healthy"
    assert "timestamp" in body
    assert body["service"] == "taskflow-backend"


def test_get_user_profile_unauthorized():
    """Test get user profile without authentication."""
    event = {}
    context = {}

    response = get_user_profile(event, context)

    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["error"] == "Unauthorized"


@patch("lambdas.user_profile.table")
def test_get_user_profile_success(mock_table):
    """Test successful get user profile."""
    mock_table.get_item.return_value = {
        "Item": {
            "userId": "test-user",
            "email": "test@example.com",
            "name": "Test User",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        }
    }

    event = {"requestContext": {"authorizer": {"claims": {"sub": "test-user"}}}}
    context = {}

    response = get_user_profile(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["userId"] == "test-user"
    assert body["email"] == "test@example.com"


def test_create_item_unauthorized():
    """Test create item without authentication."""
    event = {}
    context = {}

    response = create_item(event, context)

    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["error"] == "Unauthorized"


def test_create_item_missing_fields():
    """Test create item with missing required fields."""
    event = {
        "requestContext": {"authorizer": {"claims": {"sub": "test-user"}}},
        "body": json.dumps(
            {
                "title": "Test Item"
                # Missing description
            }
        ),
    }
    context = {}

    response = create_item(event, context)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"] == "Missing required fields"
    assert "description" in body["details"]["missing_fields"]
