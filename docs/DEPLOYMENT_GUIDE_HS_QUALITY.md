# Deployment Guide: H&S + Quality Report Processing

This guide walks you through deploying the H&S and Quality report processing system.

## Prerequisites

### 1. AWS Account Setup

- AWS Account with appropriate permissions
- AWS CLI configured with credentials
- AWS profile configured (default: `mia40`)

### 2. Node.js and Python

```bash
# Check versions
node --version  # Should be >= 14.x
python --version  # Should be >= 3.13
npm --version
```

### 3. Install Serverless Framework

```bash
npm install -g serverless
```

## Step 1: Install Dependencies

```bash
cd backend

# Install Node.js dependencies
npm install

# Install Python dependencies (local testing)
pip install -r requirements.txt
```

## Step 2: Configure AWS Parameter Store

### Create Twilio Credentials Parameters

```bash
# Use the interactive setup script (recommended)
cd /Users/mayoub/Desktop/mabani
./scripts/setup-twilio-parameters.sh dev

# Or manually create parameters
aws ssm put-parameter \
  --name "/mabani/twilio/account_sid" \
  --description "Twilio Account SID for WhatsApp integration" \
  --value "ACxxxxxxxxxxxxxxxxxxxxxxxxx" \
  --type "String" \
  --region eu-west-1 \
  --profile mia40

aws ssm put-parameter \
  --name "/mabani/twilio/auth_token" \
  --description "Twilio Auth Token (encrypted)" \
  --value "your_auth_token_here" \
  --type "SecureString" \
  --region eu-west-1 \
  --profile mia40

aws ssm put-parameter \
  --name "/mabani/twilio/whatsapp_number" \
  --description "Twilio WhatsApp number" \
  --value "whatsapp:+14155238886" \
  --type "String" \
  --region eu-west-1 \
  --profile mia40
```

**Get your Twilio credentials**:

1. Log in to [Twilio Console](https://console.twilio.com)
2. Find Account SID and Auth Token on the dashboard
3. Get WhatsApp number from: Messaging → Try it out → Send a WhatsApp message

## Step 3: Enable AWS Bedrock Models

### Via AWS Console:

1. Go to AWS Console → Bedrock → Model access
2. Click "Manage model access"
3. Select: `Claude 3 Haiku` by Anthropic
4. Click "Request model access"
5. Wait for approval (usually instant)

### Verify Access:

```bash
aws bedrock list-foundation-models \
  --region eu-west-1 \
  --profile mia40 \
  --query 'modelSummaries[?contains(modelId, `anthropic.claude-3-haiku`)].modelId'
```

Expected output:

```json
["anthropic.claude-3-haiku-20240307-v1:0"]
```

## Step 4: Deploy Infrastructure

### Deploy All Resources

```bash
cd backend

# Deploy to dev environment
serverless deploy --stage dev --verbose

# Deploy to production
serverless deploy --stage prod --verbose
```

This will create:

- ✅ Lambda functions (twilioWebhook, reportProcessor)
- ✅ API Gateway endpoints
- ✅ DynamoDB tables (reports, user-projects)
- ✅ S3 bucket (encrypted)
- ✅ IAM roles and policies

### Expected Output:

```
✔ Service deployed to stack taskflow-backend-dev (123s)

endpoints:
  POST - https://abc123xyz.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio

functions:
  twilioWebhook: taskflow-backend-dev-twilioWebhook
  reportProcessor: taskflow-backend-dev-reportProcessor

Stack Outputs:
  TwilioWebhookUrl: https://abc123xyz.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio
  ReportsBucketName: taskflow-backend-dev-reports
  ReportsTableName: taskflow-backend-dev-reports
```

**Save the `TwilioWebhookUrl` - you'll need it in Step 5!**

## Step 5: Configure Twilio Webhook

### Option A: WhatsApp Sandbox (Testing)

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to: **Messaging → Try it out → Send a WhatsApp message**
3. Scroll to "Sandbox Configuration"
4. Under **"WHEN A MESSAGE COMES IN"**:
   - Paste your webhook URL from Step 4
   - Method: `POST`
5. Click **Save**

### Option B: Production WhatsApp Number

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to: **Messaging → Senders → WhatsApp senders**
3. Select your WhatsApp number
4. Under **"Messaging"**:
   - Webhook URL: Paste your webhook URL
   - HTTP Method: `POST`
   - Fallback URL: (optional)
5. Click **Save**

## Step 6: Seed User-Project Mappings (Optional)

Create initial user-project mappings:

```bash
aws dynamodb put-item \
  --table-name taskflow-backend-dev-user-projects \
  --item '{
    "phoneNumber": {"S": "+1234567890"},
    "projectId": {"S": "proj-001"},
    "projectName": {"S": "Construction Site Alpha"},
    "projectType": {"S": "construction"},
    "userName": {"S": "John Doe"},
    "role": {"S": "Site Manager"}
  }' \
  --region eu-west-1 \
  --profile mia40
```

## Step 7: Test the System

### Test via WhatsApp

1. **Join Twilio Sandbox** (if using sandbox):

   - Send the join code to the Twilio number
   - Example: `join <your-sandbox-code>`

2. **Send Test Report**:

   ```
   Scaffolding material falling from height - urgent inspection needed
   [Attach an image of scaffolding or similar]
   ```

3. **Expected Response** (within 30-60 seconds):

   ```
   ✅ H&S Report Received - #abc12345

   📋 Description:
   Materials were observed falling from scaffolding structure...

   🔴 Severity: HIGH

   🎯 Hazard Type:
   Falling Objects

   🛡️ Recommended Action:
   Immediately install debris netting...

   📚 Reference: HSE WCFAG 2013 Section 4.7

   Your report has been logged...
   ```

### Check Logs

```bash
# Webhook handler logs
serverless logs -f twilioWebhook --stage dev --tail

# Report processor logs
serverless logs -f reportProcessor --stage dev --tail
```

### Check DynamoDB

```bash
# List all reports
aws dynamodb scan \
  --table-name taskflow-backend-dev-reports \
  --region eu-west-1 \
  --profile mia40
```

### Check S3

```bash
# List uploaded images
aws s3 ls s3://taskflow-backend-dev-reports/images/ \
  --recursive \
  --profile mia40
```

## Step 8: Set Up Monitoring (Recommended)

### CloudWatch Alarms

```bash
# High error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name hs-quality-high-error-rate \
  --alarm-description "Alert when error rate is high" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=taskflow-backend-dev-reportProcessor \
  --region eu-west-1 \
  --profile mia40

# Long duration alarm
aws cloudwatch put-metric-alarm \
  --alarm-name hs-quality-slow-processing \
  --alarm-description "Alert when processing is slow" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 120000 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=taskflow-backend-dev-reportProcessor \
  --region eu-west-1 \
  --profile mia40
```

### CloudWatch Dashboard (Optional)

Create a dashboard to monitor:

- Lambda invocations
- Lambda errors
- Lambda duration
- DynamoDB read/write capacity
- S3 request count

## Troubleshooting

### Issue: "Invalid signature" from Twilio webhook

**Solution**:

1. Verify webhook URL is correct (HTTPS)
2. Check Parameter Store has correct auth token (`/mabani/twilio/auth_token`)
3. Ensure no proxy or firewall is modifying requests

```bash
# Verify parameters
aws ssm get-parameters-by-path \
  --path /mabani/twilio \
  --with-decryption \
  --region eu-west-1 \
  --profile mia40
```

### Issue: "Bedrock model not available"

**Solution**:

1. Request model access in Bedrock console
2. Verify region is `eu-west-1` (or update in serverless.yml)
3. Check IAM permissions

```bash
# Test Bedrock access
aws bedrock-runtime invoke-model \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}' \
  --region eu-west-1 \
  --profile mia40 \
  output.json
```

### Issue: "S3 upload failed"

**Solution**:

1. Verify S3 bucket was created
2. Check IAM permissions for Lambda
3. Ensure bucket name matches environment variable

```bash
# List buckets
aws s3 ls --profile mia40 | grep taskflow-backend

# Test upload
echo "test" > test.txt
aws s3 cp test.txt s3://taskflow-backend-dev-reports/test/ --profile mia40
```

### Issue: No response from WhatsApp

**Solution**:

1. Check CloudWatch logs for errors
2. Verify Twilio account has funds
3. Test with Twilio API directly

```bash
# Check logs
serverless logs -f reportProcessor --stage dev --startTime 5m
```

### Issue: Lambda timeout

**Solution**:

1. Increase timeout in serverless.yml (currently 300s)
2. Check Bedrock API latency
3. Optimize image size

```yaml
# In serverless.yml
reportProcessor:
  handler: lambdas/report_processor.handler
  timeout: 600 # Increase to 10 minutes
```

## Post-Deployment Checklist

- [ ] Twilio webhook configured and responding
- [ ] Test report sent and processed successfully
- [ ] CloudWatch logs showing successful execution
- [ ] DynamoDB contains report records
- [ ] S3 contains uploaded images
- [ ] WhatsApp response received
- [ ] CloudWatch alarms configured
- [ ] User-project mappings seeded (if needed)
- [ ] Parameter Store contains valid Twilio credentials
- [ ] Bedrock model access enabled

## Updating After Deployment

### Update Single Function

```bash
# Update webhook handler only
serverless deploy function -f twilioWebhook --stage dev

# Update report processor only
serverless deploy function -f reportProcessor --stage dev
```

### Update Environment Variables

```bash
# Update via AWS Console or CLI
aws lambda update-function-configuration \
  --function-name taskflow-backend-dev-reportProcessor \
  --environment Variables={BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0} \
  --region eu-west-1 \
  --profile mia40
```

### Rollback Deployment

```bash
# List deployments
serverless deploy list --stage dev

# Rollback to specific timestamp
serverless rollback --timestamp 1699459200000 --stage dev
```

## Clean Up (Remove All Resources)

```bash
# Remove all resources
serverless remove --stage dev --verbose
```

**Warning**: This will delete:

- All Lambda functions
- API Gateway
- DynamoDB tables (and all data)
- S3 bucket (must be empty first)
- IAM roles

**To preserve data**, backup DynamoDB and S3 first:

```bash
# Backup DynamoDB
aws dynamodb create-backup \
  --table-name taskflow-backend-dev-reports \
  --backup-name reports-backup-$(date +%Y%m%d) \
  --region eu-west-1 \
  --profile mia40

# Sync S3 to local
aws s3 sync s3://taskflow-backend-dev-reports ./backup-images/ \
  --profile mia40
```

## Cost Management

### Estimate Monthly Costs

For **1,000 reports/month**:

- Lambda: ~$0.60
- DynamoDB: ~$2.50
- S3: ~$0.23
- Bedrock: ~$40.00
- API Gateway: ~$0.01
- **Total**: ~$43.34/month

### Cost Optimization Tips

1. **Use S3 Lifecycle Policies** (already configured):

   - Moves to S3-IA after 90 days
   - Archives to Glacier after 365 days

2. **Monitor Bedrock Usage**:

   ```bash
   # Check Bedrock usage
   aws ce get-cost-and-usage \
     --time-period Start=2025-11-01,End=2025-11-30 \
     --granularity MONTHLY \
     --metrics UsageQuantity \
     --filter file://bedrock-filter.json \
     --profile mia40
   ```

3. **Set Budget Alerts**:
   ```bash
   aws budgets create-budget \
     --account-id YOUR_ACCOUNT_ID \
     --budget file://budget.json \
     --notifications-with-subscribers file://notifications.json \
     --profile mia40
   ```

## Support

For deployment issues:

- Check CloudWatch logs first
- Review this guide's troubleshooting section
- Consult the main documentation: `/docs/HS_QUALITY_WORKFLOW.md`
- Contact DevOps team

---

**Version**: 1.0  
**Last Updated**: November 8, 2025  
**Maintained by**: DevOps Team
