"""End-to-end tests for deployed AWS Lambda functions."""

import pytest
import os
from tests.helpers.serverless_test_helpers import (
    ServerlessTestClient,
    assert_health_response,
    assert_api_success,
)


@pytest.mark.e2e
@pytest.mark.aws
@pytest.fixture(scope="module")
def deployed_api_client():
    """Create API test client for deployed AWS API."""
    base_url = os.getenv(
        "DEPLOYED_API_BASE_URL",
        "https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev",
    )
    return ServerlessTestClient(base_url)


@pytest.mark.e2e
@pytest.mark.aws
def test_deployed_health_endpoint(deployed_api_client):
    """Test health endpoint on deployed API."""
    response = deployed_api_client.health_check()
    assert_health_response(response)


@pytest.mark.e2e
@pytest.mark.aws
@pytest.mark.skip(reason="Requires valid Cognito JWT token")
def test_deployed_user_profile(deployed_api_client):
    """Test user profile endpoint on deployed API."""
    # Get token from environment or Cognito
    token = os.getenv("TEST_JWT_TOKEN")
    if not token:
        pytest.skip("TEST_JWT_TOKEN environment variable not set")

    auth_client = deployed_api_client.with_auth(token)
    response = auth_client.get("/user-profile")
    assert_api_success(response)


@pytest.mark.e2e
@pytest.mark.aws
@pytest.mark.skip(reason="Requires valid Cognito JWT token")
def test_deployed_knowledge_bases(deployed_api_client):
    """Test knowledge bases endpoints on deployed API."""
    token = os.getenv("TEST_JWT_TOKEN")
    if not token:
        pytest.skip("TEST_JWT_TOKEN environment variable not set")

    auth_client = deployed_api_client.with_auth(token)

    # List knowledge bases
    response = auth_client.get("/knowledge-bases")
    data = assert_api_success(response)
    assert "knowledgeBases" in data
    assert "total" in data
