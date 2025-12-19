# Twilio WhatsApp Setup Guide

This guide documents the complete process to set up Twilio with WhatsApp Business for the H&S + Quality report processing system.

## Overview

Twilio WhatsApp integration requires connecting Twilio to Meta (Facebook) WhatsApp Business API. This involves several verification and setup steps.

## Prerequisites

- Valid email address
- Phone number for verification
- Credit card for Twilio account upgrade
- Government-issued ID for identity verification
- Business information (if setting up WhatsApp Business)

---

## Step-by-Step Setup Process

### Step 1: Create Twilio Account

1. **Go to Twilio**: https://www.twilio.com/
2. **Sign Up**:
   - Click "Sign up" or "Start for free"
   - Enter your email address
   - Create a strong password
   - Agree to terms and conditions
3. **Verify Email**:
   - Check your email inbox
   - Click the verification link from Twilio
4. **Initial Setup**:
   - Answer questions about your use case
   - Select "I'm building a product or service"
   - Choose your programming language (Python)
   - Choose your use case (SMS/WhatsApp messaging)

**Status**: ✅ Free trial account created

---

### Step 2: Upgrade Twilio Account

**Why Upgrade?**

- Free trial accounts have limitations
- Cannot send messages to unverified numbers
- Limited WhatsApp capabilities
- Cannot use production WhatsApp numbers

**Upgrade Process**:

1. **Go to Console**: https://console.twilio.com
2. **Navigate to Billing**:
   - Click on your account name (top right)
   - Select "Billing" from dropdown
3. **Upgrade Account**:
   - Click "Upgrade Account" button
   - Choose upgrade tier (pay-as-you-go recommended)
4. **Add Payment Method**:
   - Enter credit card information
   - Add billing address
   - Confirm payment details

**Initial Credits Purchase**:

- Minimum: $20 USD (recommended for testing)
- Typical: $50-100 USD (for production use)
- Credits don't expire
- Used for messages, phone numbers, and API calls

**Status**: ✅ Account upgraded to paid tier

---

### Step 3: Identity Verification (KYC)

**Why Required?**

- Regulatory compliance (A2P 10DLC, GDPR, etc.)
- Prevent spam and fraud
- Required for WhatsApp Business API access

**Verification Process**:

1. **Navigate to Verification**:

   - Console → Settings → Compliance
   - Or direct prompt in console after upgrade

2. **Submit Personal Information**:

   - Full legal name
   - Date of birth
   - Residential address
   - Business information (if applicable)

3. **Upload Government ID**:

   - Passport, Driver's License, or National ID
   - Both front and back (if applicable)
   - Must be clear and readable
   - Must not be expired

4. **Business Verification** (if applicable):

   - Business registration documents
   - Tax ID number
   - Business address
   - Business website (if available)

5. **Wait for Approval**:
   - Typical time: 1-24 hours
   - May take up to 2-3 business days
   - Check email for approval/rejection
   - Status visible in Console → Compliance

**Status**: ✅ Identity verified and approved

---

### Step 4: Create Meta (Facebook) Business Account

**Why Needed?**

- WhatsApp is owned by Meta (Facebook)
- WhatsApp Business API requires Meta Business Manager
- Connection between Twilio and Meta required

**Setup Process**:

1. **Go to Meta Business**: https://business.facebook.com/
2. **Create Business Account**:

   - Click "Create Account"
   - **IMPORTANT**: Use the **same email address** as Twilio account
   - Enter business name
   - Enter your name
   - Enter business email (same as Twilio)

3. **Verify Email**:

   - Check email from Meta
   - Click verification link
   - Return to Business Manager

4. **Complete Business Profile**:
   - Business address
   - Business website (optional)
   - Business phone number
   - Business category

**Status**: ✅ Meta Business account created

---

### Step 5: Request WhatsApp Business Account

**In Meta Business Manager**:

1. **Navigate to WhatsApp**:

   - Business Manager → More Tools → WhatsApp Accounts
   - Or: https://business.facebook.com/wa/manage/home

2. **Add WhatsApp Account**:

   - Click "Add WhatsApp Account"
   - Choose "Create a new WhatsApp Business Account"
   - Enter account name (e.g., "Mabani H&S Reports")

3. **Add Phone Number**:

   - Click "Add phone number"
   - Select your country
   - **Enter the phone number from Twilio**
   - Choose display name for WhatsApp
   - Select business category

4. **Verify Phone Number**:
   - Meta will send verification code
   - **Two options**:
     - SMS verification (to Twilio number)
     - Voice call verification
   - Enter the 6-digit code received
   - Click "Verify"

**Status**: ✅ WhatsApp Business number validated

---

### Step 6: Connect Twilio to Meta WhatsApp

**In Twilio Console**:

1. **Navigate to Messaging**:

   - Console → Messaging → Settings
   - Or: https://console.twilio.com/us1/develop/sms/settings/whatsapp-sender

2. **Add WhatsApp Sender**:

   - Click "WhatsApp senders"
   - Click "Add new sender"
   - Choose "Request to access your existing Meta WhatsApp Business Account"

3. **Authorize Connection**:

   - Click "Connect to Meta"
   - Log in to Meta/Facebook if prompted
   - Select your Business Manager account
   - Select your WhatsApp Business Account
   - Grant permissions to Twilio:
     - Manage WhatsApp Business Account
     - Manage and send WhatsApp messages
     - Read message templates
   - Click "Continue" and "Done"

4. **Select Phone Number**:
   - Choose the verified phone number
   - Associate with Twilio account
   - Confirm connection

**Status**: ✅ Twilio connected to Meta WhatsApp

---

### Step 7: Configure Twilio Webhook

**Set Webhook URL**:

1. **In Twilio Console**:

   - Messaging → Settings → WhatsApp sandbox
   - Or: Messaging → Senders → WhatsApp senders → (your number)

2. **Configure Webhook**:

   - **When a message comes in**:
     ```
     https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev/webhook/twilio
     ```
   - **Method**: POST
   - **Content Type**: application/x-www-form-urlencoded

3. **Configure Status Callback** (optional):

   - For delivery receipts
   - For message status updates

4. **Save Configuration**

**Status**: ✅ Webhook configured and pointing to Lambda

---

### Step 8: Create Message Templates (Production Only)

**For Production WhatsApp**:

1. **In Meta Business Manager**:

   - WhatsApp Manager → Message Templates
   - Create templates for common responses

2. **Template Requirements**:

   - Must follow WhatsApp guidelines
   - Include placeholders for dynamic content
   - Submit for approval (24-48 hour review)
   - Cannot send promotional content

3. **Example Template**:

   ```
   Name: incident_received
   Category: Utility
   Language: English

   Content:
   ✅ H&S Report Received - #{{1}}

   Your incident report has been logged.
   Severity: {{2}}
   Reference: {{3}}
   ```

**Status**: ⚠️ Required for production (not needed for sandbox testing)

---

## Testing the Connection

### Option 1: WhatsApp Sandbox (Quick Testing)

1. **In Twilio Console**:

   - Messaging → Try it out → Send a WhatsApp message

2. **Join Sandbox**:

   - Send join code to Twilio sandbox number
   - Example: Send `join <your-code>` to `+1 415 523 8886`

3. **Send Test Message**:
   - Send any message with an image
   - Should receive automated response

**Sandbox Limitations**:

- Only works with numbers that joined sandbox
- Message templates not required
- Free for testing
- Cannot use for production

### Option 2: Production Number (Full Testing)

1. **Verify Connection**:

   - Send test message to your Twilio WhatsApp number
   - Check Twilio logs: Console → Monitor → Logs → Messaging

2. **Check Webhook**:

   - Verify webhook was called
   - Check Lambda logs:
     ```bash
     serverless logs -f twilioWebhook --stage dev --tail
     ```

3. **Send H&S Report**:
   - Send message with image and description
   - Wait for AI-processed response (~60 seconds)

---

## Troubleshooting

### Issue: "Phone number is already registered"

**Solution**: Number is registered with another WhatsApp account

- Use a different phone number
- Or unregister from previous account

### Issue: "Identity verification failed"

**Solution**:

- Ensure ID is clear and valid
- Use a different ID type
- Contact Twilio support

### Issue: "Cannot connect to Meta"

**Solution**:

- Ensure same email used for both accounts
- Clear browser cache
- Try different browser
- Check Meta Business Manager permissions

### Issue: "Webhook not receiving messages"

**Solution**:

- Verify webhook URL is correct
- Check Lambda function is deployed
- Verify API Gateway endpoint is public
- Check Twilio signature validation

### Issue: "Messages not sending"

**Solution**:

- Check Twilio account credits
- Verify phone number is verified
- Check message template approval (production)
- Review Twilio error logs

---

## Cost Breakdown

### Twilio Costs:

| Item                            | Cost                   |
| ------------------------------- | ---------------------- |
| WhatsApp Sender Number          | $15/month              |
| WhatsApp Business Profile       | Free                   |
| Message (Inbound)               | $0.005 each            |
| Message (Outbound)              | $0.01 each             |
| User-initiated conversation     | Free (first 24h)       |
| Business-initiated conversation | $0.08 per conversation |

**Example Monthly Cost** (1000 reports):

- Number rental: $15
- Inbound messages: $5 (1000 × $0.005)
- Outbound messages: $10 (1000 × $0.01)
- **Total**: ~$30/month

### Meta/WhatsApp Costs:

- WhatsApp Business Account: **Free**
- Meta Business Manager: **Free**
- Message templates: **Free** to create
- API access via Twilio: **Included in Twilio pricing**

---

## Security Best Practices

1. **Enable 2FA**:

   - Both Twilio and Meta accounts
   - Use authenticator app

2. **Rotate Credentials**:

   - Update Twilio auth token periodically
   - Update in AWS Parameter Store (`/mabani/twilio/auth_token`)

3. **Monitor Usage**:

   - Set up billing alerts in Twilio
   - Monitor unusual message patterns

4. **Webhook Security**:

   - Always validate Twilio signature
   - Use HTTPS endpoints only
   - Implement rate limiting

5. **Access Control**:
   - Limit team access in Twilio console
   - Use sub-accounts for different teams
   - Audit access logs regularly

---

## Production Checklist

Before going to production:

- [ ] Twilio account upgraded and verified
- [ ] Meta Business account created and verified
- [ ] WhatsApp number purchased and verified
- [ ] Message templates created and approved
- [ ] Webhook configured and tested
- [ ] Lambda functions deployed
- [ ] Bedrock models enabled
- [ ] DynamoDB tables created
- [ ] S3 bucket configured
- [ ] Monitoring and alerts set up
- [ ] Error handling tested
- [ ] Load testing completed
- [ ] Documentation updated
- [ ] Team training completed

---

## Support Resources

### Twilio:

- **Console**: https://console.twilio.com
- **Documentation**: https://www.twilio.com/docs/whatsapp
- **Support**: https://support.twilio.com
- **Community**: https://www.twilio.com/community

### Meta WhatsApp:

- **Business Manager**: https://business.facebook.com
- **WhatsApp API Docs**: https://developers.facebook.com/docs/whatsapp
- **Support**: https://business.facebook.com/business/help

### AWS:

- **Bedrock**: https://console.aws.amazon.com/bedrock
- **Lambda**: https://console.aws.amazon.com/lambda
- **Systems Manager (Parameter Store)**: https://console.aws.amazon.com/systems-manager/parameters

---

## Summary

The complete setup process:

1. ✅ Created Twilio account
2. ✅ Upgraded Twilio account (added credits)
3. ✅ Completed identity verification (KYC)
4. ✅ Created Meta Business account (same email)
5. ✅ Created WhatsApp Business Account
6. ✅ Verified phone number in Meta
7. ✅ Connected Twilio to Meta WhatsApp
8. ✅ Configured webhook in Twilio
9. ✅ Tested connection

**Total Setup Time**: ~2-4 hours (including verification wait times)
**Initial Cost**: ~$20-50 (Twilio credits)
**Ongoing Cost**: ~$30-50/month (depending on usage)

---

**Document Version**: 1.0  
**Last Updated**: November 8, 2025  
**Validated By**: User (mayoub)  
**Status**: Production Ready ✅
