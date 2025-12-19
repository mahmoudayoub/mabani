"""Unit tests for Twilio webhook handler."""

import json
import pytest
from unittest.mock import patch, MagicMock

from lambdas.twilio_webhook import handler
from tests.helpers.lambda_test_helpers import assert_api_response


@pytest.mark.unit
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


@pytest.mark.unit
@patch("lambdas.twilio_webhook.twilio_client")
@patch("lambdas.twilio_webhook.sfn_client")
@patch("lambdas.twilio_webhook.dynamodb")
def test_valid_webhook(
    mock_dynamodb, mock_sfn, mock_twilio, twilio_webhook_event, mock_lambda_context
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
    response = handler(twilio_webhook_event, mock_lambda_context)

    # Assertions
    body = assert_api_response(response, expected_status=200)
    assert "requestId" in body

    # Verify DynamoDB was called
    mock_table.put_item.assert_called_once()


@pytest.mark.unit
@patch("lambdas.twilio_webhook.twilio_client")
def test_invalid_signature(mock_twilio, twilio_webhook_event, mock_lambda_context):
    """Test invalid Twilio signature."""
    mock_twilio.parse_webhook.return_value = {}
    mock_twilio.validate_signature.return_value = False

    response = handler(twilio_webhook_event, mock_lambda_context)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert "error" in body
