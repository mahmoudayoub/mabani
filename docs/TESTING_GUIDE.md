# H&S + Quality System Testing Guide

This guide will help you test the complete H&S + Quality report processing system end-to-end.

## Pre-Test Checklist

Before testing, verify:

- [ ] Twilio webhook configured: `https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio`
- [ ] Lambda functions deployed
- [ ] Twilio credentials in Secrets Manager
- [ ] AWS Bedrock models enabled (Nova Lite + Nova Pro)
- [ ] Phone number connected to WhatsApp

---

## Test 1: Verify AWS Bedrock Model Access

**Command:**

```bash
aws bedrock list-foundation-models \
  --region eu-west-1 \
  --profile mia40 \
  --query 'modelSummaries[?contains(modelId, `amazon.nova`)].{ID:modelId,Name:modelName}' \
  --output table
```

**Expected Output:**

```
-----------------------------------------------------------
|              ListFoundationModels                       |
+----------------------------+----------------------------+
|            ID              |           Name             |
+----------------------------+----------------------------+
|  amazon.nova-lite-v1:0     |  Nova Lite                 |
|  amazon.nova-pro-v1:0      |  Nova Pro                  |
|  amazon.nova-micro-v1:0    |  Nova Micro                |
+----------------------------+----------------------------+
```

**If models not found:**

1. Go to AWS Console → Bedrock → Model access
2. Request access to Nova Lite and Nova Pro
3. Wait for approval (instant)

---

## Test 2: Verify Lambda Functions Deployed

**Command:**

```bash
aws lambda list-functions \
  --region eu-west-1 \
  --profile mia40 \
  --query 'Functions[?contains(FunctionName, `taskflow-backend-dev`)].FunctionName' \
  --output table
```

**Expected Output:**

```
taskflow-backend-dev-twilioWebhook
taskflow-backend-dev-reportProcessor
(plus other existing functions)
```

---

## Test 3: Verify Twilio Credentials

**Command:**

```bash
aws secretsmanager get-secret-value \
  --secret-id mabani/twilio/credentials \
  --region eu-west-1 \
  --profile mia40 \
  --query 'SecretString' \
  --output text | jq .
```

**Expected Output:**

```json
{
  "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "auth_token": "your_auth_token_here",
  "whatsapp_number": "whatsapp:+1XXXXXXXXXX"
}
```

---

## Test 4: Test Webhook Endpoint (Direct API Call)

**Command:**

```bash
curl -X POST https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:%2B1234567890&Body=Test+message&NumMedia=0"
```

**Expected Output:**

```json
{
  "message": "Validation failed",
  "errors": ["Missing image attachment"]
}
```

**Good Sign:** ✅ Webhook is responding and validating correctly

---

## Test 5: Monitor Lambda Logs (Real-Time)

Open **two terminal windows**:

**Terminal 1 - Webhook Logs:**

```bash
cd /Users/mayoub/Desktop/mabani/backend
serverless logs -f twilioWebhook --stage dev --tail
```

**Terminal 2 - Processor Logs:**

```bash
cd /Users/mayoub/Desktop/mabani/backend
serverless logs -f reportProcessor --stage dev --tail
```

Keep these running while you test!

---

## Test 6: Send Test Message via WhatsApp

### Option A: Using WhatsApp Sandbox (Quick Test)

1. **Join Sandbox** (if not already joined):

   - Send this message to `+1 415 523 8886`:

   ```
   join <your-sandbox-code>
   ```

2. **Send Test Report**:

   - Message: `Worker without hardhat on construction site`
   - Attach: Any construction site image

3. **Expected Response**:
   - Either validation error (if image/text missing)
   - Or processing acknowledgment

### Option B: Using Your Production Number

1. **Send WhatsApp Message** to `+15419452583`:

   ```
   Scaffolding material falling from height - urgent inspection needed
   ```

   📎 **Attach an image** of scaffolding or construction hazard

2. **Watch Logs** in your terminals:

   - Terminal 1 should show webhook receiving message
   - Terminal 2 should show AI processing

3. **Expected Timeline**:
   - Webhook response: **< 1 second**
   - Initial storage: **< 2 seconds**
   - AI processing: **30-60 seconds**
   - WhatsApp response: **60-90 seconds total**

---

## Expected Response Format

### H&S Report Response:

```
✅ H&S Report Received - #abc12345

📋 Description:
Materials were observed falling from scaffolding structure.
Immediate inspection required to assess structural integrity
and prevent potential hazards.

🔴 Severity: HIGH

🎯 Hazard Type:
Falling Objects

🛡️ Recommended Action:
Immediately install debris netting below all scaffolding work
areas and secure all materials with tie-downs or edge protection.

📚 Reference: HSE WCFAG 2013 Section 4.7 - Prevention of falling materials

Your report has been logged and relevant teams have been notified.
```

### Quality Report Response:

```
✅ Quality Report Received - #abc12345

📋 Description:
Concrete surface shows visible cracking and uneven finish.
Quality inspection required.

🟡 Priority: MEDIUM

🔍 Issue Type:
Material Defect

Your report has been logged and the quality team will review it shortly.
```

---

## Test Scenarios

### Test Scenario 1: H&S Report (High Severity)

**Message:**

```
Worker fell from scaffolding - immediate medical attention needed
```

**Image:** Person on high scaffolding (or similar safety hazard)

**Expected:**

- Severity: HIGH
- Hazard Type: Falls from Height
- Control Measure: Safety recommendations

---

### Test Scenario 2: Quality Issue (Medium Priority)

**Message:**

```
Concrete pour has visible cracks and uneven surface finish
```

**Image:** Concrete with visible defects

**Expected:**

- Priority: MEDIUM
- Issue Type: Material Defect or Workmanship Issue
- No control measures (Quality reports don't include this)

---

### Test Scenario 3: Missing Image (Validation Error)

**Message:**

```
Safety issue on site
```

**Image:** None

**Expected Response:**

```
❌ Unable to process your report. Please ensure you include both:
• An image
• A description of the issue
```

---

### Test Scenario 4: Missing Description (Validation Error)

**Message:** (empty)

**Image:** Any image

**Expected Response:**

```
❌ Unable to process your report. Please ensure you include both:
• An image
• A description of the issue
```

---

## Verify Data Storage

After sending a test report, verify data is stored:

### Check DynamoDB:

**Command:**

```bash
aws dynamodb scan \
  --table-name taskflow-backend-dev-reports \
  --region eu-west-1 \
  --profile mia40 \
  --max-items 5 \
  --output table
```

**Expected:** Should show your test report with all fields

### Check S3:

**Command:**

```bash
aws s3 ls s3://taskflow-backend-dev-reports/images/ \
  --recursive \
  --profile mia40
```

**Expected:** Should show uploaded images with timestamps

---

## Troubleshooting

### Issue: No response after 2 minutes

**Check:**

```bash
# Check Lambda errors
aws lambda list-function-event-invoke-configs \
  --function-name taskflow-backend-dev-reportProcessor \
  --region eu-west-1 \
  --profile mia40

# Check recent invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=taskflow-backend-dev-reportProcessor \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region eu-west-1 \
  --profile mia40
```

### Issue: "Model not found" in logs

**Solution:**

```bash
# Enable Bedrock models
echo "Go to: https://console.aws.amazon.com/bedrock/home?region=eu-west-1#/modelaccess"
echo "Enable: Nova Lite and Nova Pro"
```

### Issue: "Invalid signature" in logs

**Check webhook URL:**

```bash
aws lambda get-function-url-config \
  --function-name taskflow-backend-dev-twilioWebhook \
  --region eu-west-1 \
  --profile mia40
```

**Verify in Twilio Console:**

- Webhook URL matches exactly
- Method is POST
- No extra parameters

### Issue: Lambda timeout

**Increase timeout:**

```bash
aws lambda update-function-configuration \
  --function-name taskflow-backend-dev-reportProcessor \
  --timeout 600 \
  --region eu-west-1 \
  --profile mia40
```

---

## Performance Metrics

Monitor these metrics after testing:

### Lambda Duration:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=taskflow-backend-dev-reportProcessor \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum \
  --region eu-west-1 \
  --profile mia40
```

**Expected:**

- Average: 30,000-60,000 ms (30-60 seconds)
- Maximum: 90,000 ms (90 seconds)

### Lambda Errors:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=taskflow-backend-dev-reportProcessor \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region eu-west-1 \
  --profile mia40
```

**Expected:** 0 errors

---

## Test Report Template

Document your test results:

| Test                      | Status | Notes |
| ------------------------- | ------ | ----- |
| Bedrock models enabled    | ⬜     |       |
| Lambda functions deployed | ⬜     |       |
| Twilio credentials valid  | ⬜     |       |
| Webhook responds          | ⬜     |       |
| Validation errors work    | ⬜     |       |
| H&S report processes      | ⬜     |       |
| Quality report processes  | ⬜     |       |
| DynamoDB storage works    | ⬜     |       |
| S3 storage works          | ⬜     |       |
| WhatsApp response sent    | ⬜     |       |

---

## Success Criteria

✅ **System is working correctly if:**

1. Webhook receives messages (check logs)
2. Validation errors are sent immediately
3. Valid reports are processed within 90 seconds
4. AI-generated descriptions are coherent
5. Severity is classified correctly
6. Hazard types are identified
7. Control measures generated (H&S only)
8. Data stored in DynamoDB
9. Images stored in S3
10. WhatsApp response sent successfully

---

## Next Steps After Successful Testing

1. **Add more test scenarios** (different hazard types)
2. **Test with real team members**
3. **Set up CloudWatch alarms** for errors
4. **Create dashboard** for monitoring
5. **Document common issues** for team
6. **Plan production rollout**

---

**Document Version**: 1.0  
**Last Updated**: November 8, 2025  
**Status**: Ready for Testing 🧪
