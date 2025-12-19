# Twilio Parameter Store Migration Guide

## Summary

Migrated Twilio credentials from **AWS Secrets Manager** to **AWS Systems Manager Parameter Store** for better cost efficiency and simpler management.

## Changes Made

### 1. Updated `serverless.yml`

- ✅ Replaced Secrets Manager IAM permissions with Parameter Store permissions
- ✅ Changed environment variable from `TWILIO_SECRETS_NAME` to `TWILIO_PARAMETER_PATH`
- ✅ New parameter path: `/mabani/twilio`

### 2. Updated `twilio_client.py`

- ✅ Replaced `boto3.client("secretsmanager")` with `boto3.client("ssm")`
- ✅ Updated credential retrieval to use `get_parameters_by_path()`
- ✅ Added automatic decryption for SecureString parameters
- ✅ Improved error handling

### 3. Created Setup Script

- ✅ Created `/scripts/setup-twilio-parameters.sh` for easy parameter creation

## Parameter Store Structure

Parameters will be stored at:

```
/mabani/twilio/
  ├── account_sid       (String)
  ├── auth_token        (SecureString - encrypted)
  └── whatsapp_number   (String)
```

## Setup Instructions

### Option 1: Using the Setup Script (Recommended)

```bash
cd /Users/mayoub/Desktop/mabani
./scripts/setup-twilio-parameters.sh dev
```

The script will prompt you for:

1. Twilio Account SID (from logs: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
2. Twilio Auth Token (from Twilio Console)
3. Twilio WhatsApp Number (e.g., `whatsapp:+14155238886`)

### Option 2: Manual AWS CLI Commands

```bash
# Set your Twilio credentials
ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
AUTH_TOKEN="your-auth-token-here"
WHATSAPP_NUMBER="whatsapp:+14155238886"

# Create parameters
aws ssm put-parameter \
  --name "/mabani/twilio/account_sid" \
  --value "$ACCOUNT_SID" \
  --type "String" \
  --description "Twilio Account SID for Mabani WhatsApp integration" \
  --profile mia40 \
  --region eu-west-1 \
  --overwrite

aws ssm put-parameter \
  --name "/mabani/twilio/auth_token" \
  --value "$AUTH_TOKEN" \
  --type "SecureString" \
  --description "Twilio Auth Token for Mabani WhatsApp integration (encrypted)" \
  --profile mia40 \
  --region eu-west-1 \
  --overwrite

aws ssm put-parameter \
  --name "/mabani/twilio/whatsapp_number" \
  --value "$WHATSAPP_NUMBER" \
  --type "String" \
  --description "Twilio WhatsApp sandbox number for Mabani" \
  --profile mia40 \
  --region eu-west-1 \
  --overwrite
```

## Verification

### 1. Verify Parameters Were Created

```bash
aws ssm get-parameters-by-path \
  --path /mabani/twilio \
  --with-decryption \
  --profile mia40 \
  --region eu-west-1
```

Expected output:

```json
{
  "Parameters": [
    {
      "Name": "/mabani/twilio/account_sid",
      "Type": "String",
      "Value": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "Version": 1,
      "ARN": "arn:aws:ssm:eu-west-1:...",
      "DataType": "text"
    },
    {
      "Name": "/mabani/twilio/auth_token",
      "Type": "SecureString",
      "Value": "your-decrypted-auth-token",
      "Version": 1,
      "ARN": "arn:aws:ssm:eu-west-1:...",
      "DataType": "text"
    },
    {
      "Name": "/mabani/twilio/whatsapp_number",
      "Type": "String",
      "Value": "whatsapp:+14155238886",
      "Version": 1,
      "ARN": "arn:aws:ssm:eu-west-1:...",
      "DataType": "text"
    }
  ]
}
```

## Deployment

### Deploy Updated Lambda Function

```bash
cd /Users/mayoub/Desktop/mabani/backend
npx serverless deploy --stage dev --profile mia40
```

Or deploy just the webhook function:

```bash
cd /Users/mayoub/Desktop/mabani
./scripts/deploy/deploy-single-lambda.sh twilioWebhook dev
```

## Testing

### 1. Monitor Logs

```bash
# Watch logs in real-time
aws logs tail /aws/lambda/taskflow-backend-dev-twilioWebhook \
  --follow \
  --profile mia40 \
  --region eu-west-1
```

### 2. Send Test Message

Send a WhatsApp message to your Twilio number with:

- An image attachment
- A description (e.g., "Test H&S report")

### 3. Expected Log Output

✅ Success:

```
Received webhook: {...}
Retrieved Twilio credentials from Parameter Store
Signature validated successfully
Report received and processing started
```

❌ Before (Secrets Manager error):

```
Error retrieving Twilio credentials: Secret marked for deletion
Invalid Twilio signature
```

## Cost Comparison

### Secrets Manager

- $0.40 per secret per month
- $0.05 per 10,000 API calls

### Parameter Store (Standard)

- **FREE** for up to 10,000 parameters
- **FREE** API calls (no charge for standard parameters)

**Savings**: ~$0.40/month per secret (small but cleaner architecture)

## Cleanup (Optional)

If you want to remove the old Secrets Manager secret permanently:

```bash
# Check deletion status
aws secretsmanager describe-secret \
  --secret-id mabani/twilio/credentials \
  --profile mia40 \
  --region eu-west-1

# Force immediate deletion (cannot be undone!)
aws secretsmanager delete-secret \
  --secret-id mabani/twilio/credentials \
  --force-delete-without-recovery \
  --profile mia40 \
  --region eu-west-1
```

## Rollback (If Needed)

To rollback to Secrets Manager:

1. Revert changes in `serverless.yml`:

   - Change IAM permissions back to `secretsmanager:GetSecretValue`
   - Change env var back to `TWILIO_SECRETS_NAME`

2. Revert changes in `twilio_client.py`:

   - Change back to `boto3.client("secretsmanager")`
   - Use `get_secret_value()` instead of `get_parameters_by_path()`

3. Recreate the secret in Secrets Manager

4. Redeploy

## Benefits of Parameter Store

✅ **Free** for standard parameters
✅ **Simpler** API (no JSON parsing needed)
✅ **Hierarchical** structure (/mabani/twilio/\*)
✅ **Built-in encryption** with SecureString
✅ **Version history** automatic
✅ **Change notifications** via CloudWatch Events
✅ **Perfect for configuration** and simple secrets

## References

- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Parameter Store Pricing](https://aws.amazon.com/systems-manager/pricing/)
