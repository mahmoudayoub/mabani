# H&S + Quality Report Processing Lambdas

This directory contains Lambda functions for processing Health & Safety and Quality reports via WhatsApp.

## Architecture

### Lambda Functions

#### 1. `twilio_webhook.py`

**Purpose**: Receives incoming WhatsApp messages from Twilio webhook

**Responsibilities**:

- Validates Twilio signature for security
- Validates required fields (image + description)
- Creates initial DynamoDB record
- Starts Step Functions execution (optional)
- Returns 200 OK to Twilio within 15 seconds

**Timeout**: 30 seconds  
**Memory**: 256 MB

**Environment Variables**:

- `REPORTS_TABLE`: DynamoDB table for reports
- `STATE_MACHINE_ARN`: Step Functions ARN (optional)
- `TWILIO_SECRETS_NAME`: Secrets Manager secret name

#### 2. `report_processor.py`

**Purpose**: Main orchestrator for report processing

**Responsibilities**:

- Determines report type (H&S vs Quality)
- Rewrites description using Bedrock
- Uploads image to S3
- Generates image caption using Bedrock vision
- Classifies severity (HIGH/MEDIUM/LOW)
- Classifies hazard type
- Generates control measures (H&S only)
- Stores complete report in DynamoDB
- Sends WhatsApp response to user

**Timeout**: 300 seconds (5 minutes)  
**Memory**: 1024 MB

**Environment Variables**:

- `REPORTS_TABLE`: DynamoDB table for reports
- `USER_PROJECT_TABLE`: DynamoDB table for user-project mappings
- `REPORTS_BUCKET`: S3 bucket for images
- `BEDROCK_MODEL_ID`: Bedrock model ID
- `TWILIO_SECRETS_NAME`: Secrets Manager secret name

### Shared Utilities (Lambda Layer)

Located in `lambdas/shared/`:

#### `twilio_client.py`

- Twilio API integration
- Signature validation
- Message formatting
- WhatsApp message sending

#### `bedrock_client.py`

- AWS Bedrock AI/ML operations
- Text rewriting
- Image captioning (vision model)
- Severity classification
- Hazard type classification
- Control measure generation

#### `s3_client.py`

- Image upload to S3
- Image download from S3
- Organized folder structure (year/month)
- Metadata tagging

#### `validators.py`

- Webhook validation
- Report type determination
- Phone number sanitization

#### `lambda_helpers.py`

- API Gateway response formatting
- Error handling
- CORS handling

## Workflow

```
1. WhatsApp Message → Twilio
2. Twilio → API Gateway → twilio_webhook Lambda
3. twilio_webhook → Validates & Creates Record
4. twilio_webhook → Starts Step Functions (optional) or Direct Invocation
5. report_processor → Processes Report
   a. Rewrite description (Bedrock)
   b. Upload image (S3)
   c. Generate caption (Bedrock Vision)
   d. Classify severity (Bedrock)
   e. Classify hazard type (Bedrock)
   f. Generate control measures (Bedrock - H&S only)
   g. Store in DynamoDB
   h. Send WhatsApp response (Twilio)
```

## Deployment

### Prerequisites

1. **Install dependencies**:

```bash
cd backend
npm install
```

2. **Configure Twilio credentials in AWS Secrets Manager**:

```bash
aws secretsmanager create-secret \
  --name mabani/twilio/credentials \
  --secret-string '{
    "account_sid": "ACxxxxxxxxx",
    "auth_token": "your_auth_token",
    "whatsapp_number": "whatsapp:+14155238886"
  }' \
  --region eu-west-1
```

3. **Enable Bedrock models**:

- Go to AWS Console → Bedrock → Model Access
- Request access to: `anthropic.claude-3-haiku-20240307-v1:0`

### Deploy

```bash
# Deploy all resources
cd backend
serverless deploy --stage dev

# Deploy single function
serverless deploy function -f twilioWebhook --stage dev
serverless deploy function -f reportProcessor --stage dev
```

### Outputs

After deployment, you'll get:

- **TwilioWebhookUrl**: Configure this in Twilio console
- **ReportsBucketName**: S3 bucket for images
- **ReportsTableName**: DynamoDB table for reports

## Configuration

### Twilio Webhook Setup

1. Log in to Twilio Console
2. Go to: Messaging → Settings → WhatsApp Sandbox Settings
3. Set "WHEN A MESSAGE COMES IN" to your webhook URL
4. Method: `POST`
5. Example: `https://abc123.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio`

### DynamoDB Tables

#### Reports Table

- **Primary Key**: `PK` (PARTITION), `SK` (SORT)
- **GSI1**: Project reports by severity (`GSI1PK`, `GSI1SK`)
- **GSI2**: Sender reports by date (`GSI2PK`, `GSI2SK`)

#### User-Project Mappings Table

- **Primary Key**: `phoneNumber` (PARTITION)
- Store project assignments for users

### S3 Bucket Structure

```
s3://taskflow-backend-dev-reports/
├── images/
│   ├── 2025/
│   │   ├── 11/
│   │   │   ├── uuid-1.jpg
│   │   │   ├── uuid-2.jpg
```

## Testing

### Test Webhook Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REPORTS_TABLE=taskflow-backend-dev-reports
export TWILIO_SECRETS_NAME=mabani/twilio/credentials
export AWS_REGION=eu-west-1

# Invoke locally (requires SAM CLI)
sam local invoke twilioWebhook -e test-events/twilio-webhook.json
```

### Test via WhatsApp

1. Join Twilio WhatsApp Sandbox
2. Send message with image and description
3. Verify response

### Example Test Message

Send to Twilio WhatsApp number:

```
Scaffolding material falling from height - urgent inspection needed
[Attach image]
```

Expected response:

```
✅ H&S Report Received - #abc12345

📋 Description:
Materials were observed falling from scaffolding structure. Immediate inspection required to assess structural integrity.

🔴 Severity: HIGH

🎯 Hazard Type:
Falling Objects

🛡️ Recommended Action:
Immediately install debris netting below all scaffolding work areas...

📚 Reference: HSE WCFAG 2013 Section 4.7

Your report has been logged and relevant teams have been notified.
```

## Monitoring

### CloudWatch Logs

- Lambda logs: `/aws/lambda/taskflow-backend-dev-twilioWebhook`
- Lambda logs: `/aws/lambda/taskflow-backend-dev-reportProcessor`

### CloudWatch Metrics

Monitor:

- Lambda invocations
- Lambda errors
- Lambda duration
- DynamoDB read/write capacity
- S3 PUT requests

### Alarms (Recommended)

```bash
# High error rate
aws cloudwatch put-metric-alarm \
  --alarm-name report-processor-errors \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold
```

## Cost Estimates (Per 1000 Reports)

| Service            | Cost        |
| ------------------ | ----------- |
| Lambda Invocations | $0.60       |
| S3 Storage (10GB)  | $0.23       |
| DynamoDB Writes    | $2.50       |
| Bedrock API Calls  | $40.00      |
| API Gateway        | $0.01       |
| **Total**          | **~$43.34** |

## Troubleshooting

### "Invalid signature" errors

- Verify Twilio credentials in Secrets Manager
- Check webhook URL is correct (HTTPS)
- Ensure `X-Twilio-Signature` header is present

### "Bedrock model not available"

- Request model access in Bedrock console
- Verify IAM permissions for `bedrock:InvokeModel`

### "Image upload failed"

- Check S3 bucket permissions
- Verify bucket name is correct
- Check Twilio image URL is accessible

### "No response from WhatsApp"

- Check Twilio account balance
- Verify Twilio credentials
- Check CloudWatch logs for errors

## Security

### Best Practices

1. **Signature Validation**: Always validate Twilio signatures
2. **Secrets Management**: Store credentials in Secrets Manager
3. **Encryption**: Enable S3 encryption at rest
4. **Access Control**: Use least privilege IAM roles
5. **Monitoring**: Enable CloudWatch alarms for anomalies

### IAM Permissions Required

- `dynamodb:PutItem`, `dynamodb:GetItem`, `dynamodb:Query`
- `s3:PutObject`, `s3:GetObject`
- `secretsmanager:GetSecretValue`
- `bedrock:InvokeModel`
- `states:StartExecution` (if using Step Functions)

## Future Enhancements

- [ ] Step Functions integration for async processing
- [ ] SNS notifications for high-severity incidents
- [ ] Multi-language support (Arabic, French)
- [ ] Voice message support
- [ ] Real-time dashboard
- [ ] Advanced analytics

## Support

For issues or questions:

- Check CloudWatch logs
- Review documentation in `/docs/HS_QUALITY_WORKFLOW.md`
- Contact DevOps team

---

**Last Updated**: November 8, 2025  
**Version**: 1.0  
**Maintained by**: Backend Team
