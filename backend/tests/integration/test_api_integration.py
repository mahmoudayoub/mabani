"""Integration tests for API endpoints using serverless-offline."""

import pytest
import os
from tests.helpers.serverless_test_helpers import (
    ServerlessTestClient,
    assert_health_response,
    assert_api_success,
    assert_api_error,
)


@pytest.mark.integration
@pytest.fixture(scope="module")
def api_client():
    """Create API test client for local serverless-offline."""
    base_url = os.getenv("TEST_API_BASE_URL", "http://localhost:3001")
    return ServerlessTestClient(base_url)


@pytest.mark.integration
def test_health_endpoint(api_client):
    """Test health check endpoint via HTTP."""
    response = api_client.health_check()
    assert_health_response(response)


@pytest.mark.integration
def test_health_endpoint_structure(api_client):
    """Test health endpoint returns correct structure."""
    response = api_client.health_check()
    data = assert_health_response(response)

    assert "status" in data
    assert "service" in data
    assert data["service"] == "taskflow-backend"


@pytest.mark.integration
def test_unauthenticated_endpoint(api_client):
    """Test that protected endpoints require authentication."""
    response = api_client.get("/user-profile")

    # Should return 401 or 403
    assert response.status_code in [401, 403]
    data = assert_api_error(response, expected_status=response.status_code)
    assert "error" in data or "Unauthorized" in data.get("message", "")


@pytest.mark.integration
@pytest.mark.skip(reason="Requires valid JWT token - use e2e tests instead")
def test_authenticated_endpoint(api_client):
    """Test authenticated endpoint with valid token."""
    # This test requires a valid Cognito JWT token
    # For integration tests, use mock tokens or skip
    token = "valid-jwt-token-here"
    auth_client = api_client.with_auth(token)

    response = auth_client.get("/user-profile")
    assert_api_success(response)
