"""Unit tests for Twilio webhook handler."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from lambdas.twilio_webhook import handler


@pytest.fixture
def twilio_webhook_event():
    """Sample Twilio webhook event."""
    return {
        "body": "MessageSid=SM123&From=whatsapp%3A%2B1234567890&Body=Test+incident&NumMedia=1&MediaUrl0=https%3A%2F%2Ftest.com%2Fimage.jpg",
        "headers": {
            "X-Twilio-Signature": "valid_signature",
            "Host": "test.execute-api.eu-west-1.amazonaws.com",
        },
        "httpMethod": "POST",
        "path": "/dev/webhook/twilio",
        "requestContext": {"path": "/dev/webhook/twilio"},
    }


@pytest.fixture
def context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = "twilio-webhook-test"
    context.memory_limit_in_mb = 256
    context.invoked_function_arn = "arn:aws:lambda:eu-west-1:123456789:function:test"
    return context


@patch("lambdas.twilio_webhook.twilio_client")
@patch("lambdas.twilio_webhook.sfn_client")
@patch("lambdas.twilio_webhook.dynamodb")
def test_valid_webhook(
    mock_dynamodb, mock_sfn, mock_twilio, twilio_webhook_event, context
):
    """Test valid webhook processing."""
    # Setup mocks
    mock_twilio.parse_webhook.return_value = {
        "MessageSid": "SM123",
        "From": "whatsapp:+1234567890",
        "Body": "Test incident",
        "NumMedia": "1",
        "MediaUrl0": "https://test.com/image.jpg",
    }
    mock_twilio.validate_signature.return_value = True

    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Call handler
    response = handler(twilio_webhook_event, context)

    # Assertions
    assert response["statusCode"] == 200
    assert "requestId" in json.loads(response["body"])

    # Verify DynamoDB was called
    mock_table.put_item.assert_called_once()


@patch("lambdas.twilio_webhook.twilio_client")
def test_invalid_signature(mock_twilio, twilio_webhook_event, context):
    """Test invalid Twilio signature."""
    mock_twilio.parse_webhook.return_value = {}
    mock_twilio.validate_signature.return_value = False

    response = handler(twilio_webhook_event, context)

    assert response["statusCode"] == 403
    assert "error" in json.loads(response["body"])


@patch("lambdas.twilio_webhook.twilio_client")
@patch("lambdas.twilio_webhook.dynamodb")
def test_missing_image(mock_dynamodb, mock_twilio, twilio_webhook_event, context):
    """Test webhook with missing image."""
    mock_twilio.parse_webhook.return_value = {
        "MessageSid": "SM123",
        "From": "whatsapp:+1234567890",
        "Body": "Test incident",
        "NumMedia": "0",
    }
    mock_twilio.validate_signature.return_value = True
    mock_twilio.send_message.return_value = {"sid": "SM456"}

    response = handler(twilio_webhook_event, context)

    # Should return 200 but with validation errors
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "errors" in body or "message" in body

    # Verify error message was sent to user
    mock_twilio.send_message.assert_called_once()


@patch("lambdas.twilio_webhook.twilio_client")
@patch("lambdas.twilio_webhook.dynamodb")
def test_missing_description(mock_dynamodb, mock_twilio, twilio_webhook_event, context):
    """Test webhook with missing description."""
    mock_twilio.parse_webhook.return_value = {
        "MessageSid": "SM123",
        "From": "whatsapp:+1234567890",
        "Body": "",
        "NumMedia": "1",
        "MediaUrl0": "https://test.com/image.jpg",
    }
    mock_twilio.validate_signature.return_value = True
    mock_twilio.send_message.return_value = {"sid": "SM456"}

    response = handler(twilio_webhook_event, context)

    # Should return 200 but with validation errors
    assert response["statusCode"] == 200

    # Verify error message was sent to user
    mock_twilio.send_message.assert_called_once()
