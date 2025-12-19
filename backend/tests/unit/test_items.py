"""Unit tests for items Lambda functions."""

import pytest
import json
from unittest.mock import patch

from lambdas.items import create_item, get_user_items
from tests.helpers.lambda_test_helpers import (
    assert_api_response,
    assert_error_response,
)


@pytest.mark.unit
def test_create_item_unauthorized(mock_lambda_context, api_gateway_event):
    """Test create item without authentication."""
    api_gateway_event["httpMethod"] = "POST"
    api_gateway_event["body"] = json.dumps({"title": "Test", "description": "Test"})

    response = create_item(api_gateway_event, mock_lambda_context)

    assert_error_response(response, expected_status=401)


@pytest.mark.unit
def test_create_item_missing_fields(mock_lambda_context, authenticated_event):
    """Test create item with missing required fields."""
    authenticated_event["httpMethod"] = "POST"
    authenticated_event["body"] = json.dumps(
        {"title": "Test Item"}
    )  # Missing description

    response = create_item(authenticated_event, mock_lambda_context)

    body = assert_error_response(response, expected_status=400)
    assert "description" in body.get("details", {}).get("missing_fields", [])


@pytest.mark.unit
@patch("lambdas.items.table")
def test_create_item_success(
    mock_table, mock_lambda_context, authenticated_event, sample_item_data
):
    """Test successful item creation."""
    mock_table.put_item.return_value = {}

    authenticated_event["httpMethod"] = "POST"
    authenticated_event["body"] = json.dumps(
        {
            "title": sample_item_data["title"],
            "description": sample_item_data["description"],
        }
    )

    response = create_item(authenticated_event, mock_lambda_context)

    body = assert_api_response(response, expected_status=201)
    assert "itemId" in body
    assert body["title"] == sample_item_data["title"]


@pytest.mark.unit
@patch("lambdas.items.table")
def test_get_user_items_success(
    mock_table, mock_lambda_context, authenticated_event, sample_item_data
):
    """Test successful retrieval of user items."""
    mock_table.query.return_value = {
        "Items": [sample_item_data],
        "Count": 1,
    }

    authenticated_event["httpMethod"] = "GET"

    response = get_user_items(authenticated_event, mock_lambda_context)

    body = assert_api_response(response, expected_status=200)
    assert len(body["items"]) == 1
    assert body["items"][0]["itemId"] == sample_item_data["itemId"]
