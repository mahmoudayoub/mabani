# Testing Guide for Serverless Architecture

This directory contains a comprehensive testing suite for the serverless backend.

## Test Structure

```
tests/
├── unit/              # Unit tests (fast, isolated, no dependencies)
├── integration/        # Integration tests (require local serverless-offline)
├── e2e/               # End-to-end tests (require deployed AWS resources)
├── fixtures/          # Shared test fixtures
├── helpers/           # Test helper utilities
├── conftest.py        # Pytest configuration and shared fixtures
└── pytest.ini         # Pytest configuration file
```

## Test Types

### Unit Tests (`tests/unit/`)

- **Purpose**: Test individual Lambda functions in isolation
- **Dependencies**: None (all AWS services are mocked)
- **Speed**: Fast (< 1 second per test)
- **Run**: `pytest tests/unit/` or `pytest -m unit`

**Example:**

```python
@pytest.mark.unit
def test_health_check(mock_lambda_context):
    event = {}
    response = health_check(event, mock_lambda_context)
    assert response["statusCode"] == 200
```

### Integration Tests (`tests/integration/`)

- **Purpose**: Test API endpoints via HTTP against local serverless-offline
- **Dependencies**: Local serverless-offline server running
- **Speed**: Medium (1-5 seconds per test)
- **Run**: `pytest tests/integration/` or `pytest -m integration`

**Prerequisites:**

```bash
# Start serverless-offline in another terminal
cd backend
npm run dev
```

**Example:**

```python
@pytest.mark.integration
def test_health_endpoint(api_client):
    response = api_client.health_check()
    assert response.status_code == 200
```

### End-to-End Tests (`tests/e2e/`)

- **Purpose**: Test against deployed AWS Lambda functions
- **Dependencies**: Deployed AWS resources, valid JWT tokens
- **Speed**: Slow (5-30 seconds per test)
- **Run**: `pytest tests/e2e/` or `pytest -m e2e`

**Prerequisites:**

- AWS credentials configured
- Functions deployed to AWS
- Valid Cognito JWT token

**Example:**

```python
@pytest.mark.e2e
@pytest.mark.aws
def test_deployed_health_endpoint(deployed_api_client):
    response = deployed_api_client.health_check()
    assert response.status_code == 200
```

## Running Tests

### Run All Tests

```bash
npm test
# or
pytest
```

### Run by Type

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# E2E tests only
pytest -m e2e
```

### Run Specific Test File

```bash
pytest tests/unit/test_user_profile.py
```

### Run with Coverage

```bash
pytest --cov=lambdas --cov-report=html
```

## Test Helpers

### Lambda Test Helpers (`tests/helpers/lambda_test_helpers.py`)

Utilities for testing Lambda functions directly:

```python
from tests.helpers.lambda_test_helpers import (
    assert_api_response,
    assert_error_response,
    create_error_response,
)
```

### Serverless Test Helpers (`tests/helpers/serverless_test_helpers.py`)

Utilities for testing via HTTP:

```python
from tests.helpers.serverless_test_helpers import (
    ServerlessTestClient,
    assert_health_response,
    assert_api_success,
)
```

## Fixtures

Common fixtures are defined in `conftest.py`:

- `mock_lambda_context`: Mock Lambda context object
- `api_gateway_event`: Basic API Gateway event
- `authenticated_event`: API Gateway event with Cognito claims
- `sqs_event`: SQS event structure
- `mock_dynamodb_table`: Mock DynamoDB table
- `sample_user_data`: Sample user data
- `sample_item_data`: Sample item data

## Environment Variables

### For Integration Tests

```bash
export TEST_API_BASE_URL=http://localhost:3001
```

### For E2E Tests

```bash
export DEPLOYED_API_BASE_URL=https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev
export TEST_JWT_TOKEN=your-cognito-jwt-token
```

## Best Practices

1. **Unit Tests**: Mock all external dependencies (DynamoDB, S3, etc.)
2. **Integration Tests**: Test against local serverless-offline
3. **E2E Tests**: Test against deployed resources, use real tokens
4. **Markers**: Always use appropriate pytest markers (`@pytest.mark.unit`, etc.)
5. **Fixtures**: Reuse fixtures from `conftest.py` instead of creating new ones
6. **Helpers**: Use test helpers for common assertions

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Unit Tests
  run: pytest -m unit

- name: Run Integration Tests
  run: |
    npm run dev &
    sleep 5
    pytest -m integration
```

## Troubleshooting

### Import Errors

```bash
# Ensure you're in the backend directory
cd backend
export PYTHONPATH=$PWD:$PYTHONPATH
pytest
```

### Serverless-Offline Not Running

```bash
# Start in separate terminal
cd backend
npm run dev
```

### AWS Credentials for E2E Tests

```bash
# Configure AWS CLI
aws configure --profile mia40
```
