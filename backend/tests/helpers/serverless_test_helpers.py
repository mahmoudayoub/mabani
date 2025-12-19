"""Helper utilities for testing serverless architecture."""

import os
import requests
from typing import Dict, Any, Optional
from urllib.parse import urljoin


class ServerlessTestClient:
    """Client for testing serverless functions locally or remotely."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize test client.

        Args:
            base_url: Base URL for API (defaults to local serverless-offline)
        """
        self.base_url = base_url or os.getenv(
            "TEST_API_BASE_URL", "http://localhost:3001"
        )
        self.session = requests.Session()

    def _make_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Make HTTP request to serverless API."""
        url = urljoin(self.base_url, path.lstrip("/"))

        request_headers = {
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)

        if json_data:
            response = self.session.request(
                method, url, headers=request_headers, json=json_data
            )
        elif data:
            response = self.session.request(
                method, url, headers=request_headers, data=data
            )
        else:
            response = self.session.request(method, url, headers=request_headers)

        return response

    def get(
        self, path: str, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Make GET request."""
        return self._make_request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """Make POST request."""
        return self._make_request("POST", path, headers=headers, json_data=json_data)

    def put(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """Make PUT request."""
        return self._make_request("PUT", path, headers=headers, json_data=json_data)

    def delete(
        self, path: str, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Make DELETE request."""
        return self._make_request("DELETE", path, headers=headers)

    def health_check(self) -> requests.Response:
        """Check health endpoint."""
        return self.get("/health")

    def with_auth(self, token: str) -> "AuthenticatedClient":
        """Create authenticated client."""
        return AuthenticatedClient(self.base_url, token)


class AuthenticatedClient(ServerlessTestClient):
    """Authenticated test client."""

    def __init__(self, base_url: str, token: str):
        """Initialize authenticated client."""
        super().__init__(base_url)
        self.token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _make_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Make authenticated request."""
        if headers is None:
            headers = {}
        headers.setdefault("Authorization", f"Bearer {self.token}")
        return super()._make_request(method, path, headers, data, json_data)


def create_test_token(user_id: str = "test-user-id") -> str:
    """
    Create a test JWT token for local testing.

    Note: This is a mock token for local testing only.
    For integration tests, use real Cognito tokens.
    """
    # This is a placeholder - in real tests, you'd get a token from Cognito
    # or use a test token generator
    return f"test-token-{user_id}"


def assert_health_response(response: requests.Response):
    """Assert health check response is valid."""
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "healthy"]
    assert "service" in data
    return data


def assert_api_success(response: requests.Response, expected_status: int = 200):
    """Assert API response is successful."""
    assert response.status_code == expected_status
    assert response.headers["Content-Type"] == "application/json"
    return response.json()


def assert_api_error(response: requests.Response, expected_status: int = 400):
    """Assert API error response."""
    assert response.status_code == expected_status
    data = response.json()
    assert "error" in data
    return data
