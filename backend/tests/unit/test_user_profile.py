"""Unit tests for user profile Lambda functions."""

import pytest
import json
from unittest.mock import patch

from lambdas.user_profile import health_check, get_user_profile, update_user_profile
from tests.helpers.lambda_test_helpers import (
    assert_api_response,
    assert_error_response,
)


@pytest.mark.unit
def test_health_check(mock_lambda_context):
    """Test health check endpoint."""
    event = {}

    response = health_check(event, mock_lambda_context)

    body = assert_api_response(response, expected_status=200)
    assert body["status"] in ["ok", "healthy"]
    assert "timestamp" in body
    assert body["service"] == "taskflow-backend"


@pytest.mark.unit
def test_get_user_profile_unauthorized(mock_lambda_context, api_gateway_event):
    """Test get user profile without authentication."""
    response = get_user_profile(api_gateway_event, mock_lambda_context)

    assert_error_response(response, expected_status=401)


@pytest.mark.unit
@patch("lambdas.user_profile.table")
def test_get_user_profile_success(
    mock_table, mock_lambda_context, authenticated_event, sample_user_data
):
    """Test successful get user profile."""
    mock_table.get_item.return_value = {"Item": sample_user_data}

    response = get_user_profile(authenticated_event, mock_lambda_context)

    body = assert_api_response(response, expected_status=200)
    assert body["userId"] == sample_user_data["userId"]
    assert body["email"] == sample_user_data["email"]


@pytest.mark.unit
@patch("lambdas.user_profile.table")
def test_update_user_profile_success(
    mock_table, mock_lambda_context, authenticated_event, sample_user_data
):
    """Test successful user profile update."""
    mock_table.get_item.return_value = {"Item": sample_user_data}
    mock_table.update_item.return_value = {
        "Attributes": {**sample_user_data, "name": "Updated Name"}
    }

    authenticated_event["httpMethod"] = "PUT"
    authenticated_event["body"] = json.dumps({"name": "Updated Name"})

    response = update_user_profile(authenticated_event, mock_lambda_context)

    body = assert_api_response(response, expected_status=200)
    assert body["name"] == "Updated Name"
