"""Pytest configuration and shared fixtures for all tests."""

import pytest
from unittest.mock import MagicMock
import json


@pytest.fixture
def mock_lambda_context():
    """Create a mock Lambda context object."""
    context = MagicMock()
    context.function_name = "test-function"
    context.function_version = "$LATEST"
    context.invoked_function_arn = (
        "arn:aws:lambda:eu-west-1:123456789012:function:test-function"
    )
    context.memory_limit_in_mb = 256
    context.aws_request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/test-function"
    context.log_stream_name = "2024/01/01/[$LATEST]test-stream"
    context.get_remaining_time_in_millis = MagicMock(return_value=30000)
    return context


@pytest.fixture
def api_gateway_event():
    """Create a basic API Gateway event."""
    return {
        "httpMethod": "GET",
        "path": "/test",
        "pathParameters": None,
        "queryStringParameters": None,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": None,
        "isBase64Encoded": False,
        "requestContext": {
            "requestId": "test-request-id",
            "stage": "dev",
            "resourceId": "test-resource-id",
            "resourcePath": "/test",
            "httpMethod": "GET",
            "requestTime": "01/Jan/2024:00:00:00 +0000",
            "requestTimeEpoch": 1704067200,
            "identity": {
                "sourceIp": "127.0.0.1",
                "userAgent": "test-agent",
            },
            "authorizer": None,
        },
    }


@pytest.fixture
def authenticated_event(api_gateway_event):
    """Create an authenticated API Gateway event with Cognito claims."""
    event = api_gateway_event.copy()
    event["requestContext"]["authorizer"] = {
        "claims": {
            "sub": "test-user-id",
            "email": "test@example.com",
            "cognito:username": "test-user-id",
            "given_name": "Test",
            "family_name": "User",
        }
    }
    return event


@pytest.fixture
def sqs_event():
    """Create a mock SQS event."""
    return {
        "Records": [
            {
                "messageId": "test-message-id",
                "receiptHandle": "test-receipt-handle",
                "body": json.dumps({"test": "data"}),
                "attributes": {
                    "ApproximateReceiveCount": "1",
                    "SentTimestamp": "1704067200000",
                },
                "messageAttributes": {},
                "md5OfBody": "test-md5",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:eu-west-1:123456789012:test-queue",
                "awsRegion": "eu-west-1",
            }
        ]
    }


@pytest.fixture
def mock_dynamodb_table():
    """Create a mock DynamoDB table."""
    table = MagicMock()
    table.table_name = "test-table"
    return table


@pytest.fixture
def mock_s3_client():
    """Create a mock S3 client."""
    s3_client = MagicMock()
    return s3_client


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    sqs_client = MagicMock()
    return sqs_client


@pytest.fixture
def mock_bedrock_client():
    """Create a mock Bedrock client."""
    bedrock_client = MagicMock()
    return bedrock_client


@pytest.fixture(autouse=True)
def mock_aws_services(monkeypatch):
    """Mock AWS services for unit tests."""
    # Mock boto3 clients
    mock_boto3 = MagicMock()
    monkeypatch.setattr("boto3.client", mock_boto3)
    monkeypatch.setattr("boto3.resource", mock_boto3)

    # Mock environment variables
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "test-table")
    monkeypatch.setenv("KB_TABLE_NAME", "test-kb-table")
    monkeypatch.setenv("DOCS_TABLE_NAME", "test-docs-table")
    monkeypatch.setenv("KB_BUCKET_NAME", "test-kb-bucket")
    monkeypatch.setenv(
        "INDEXING_QUEUE_URL",
        "https://sqs.eu-west-1.amazonaws.com/123456789012/test-queue",
    )

    return mock_boto3


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "userId": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_item_data():
    """Sample item data for testing."""
    return {
        "itemId": "test-item-id",
        "userId": "test-user-id",
        "title": "Test Item",
        "description": "Test Description",
        "status": "pending",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_kb_data():
    """Sample knowledge base data for testing."""
    return {
        "kbId": "test-kb-id",
        "userId": "test-user-id",
        "name": "Test Knowledge Base",
        "description": "Test Description",
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
    }
