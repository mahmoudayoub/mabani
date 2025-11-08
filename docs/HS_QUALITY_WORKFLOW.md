# H&S + Quality Workflow Implementation Plan

## Overview
This document describes the architecture and implementation details for an automated Health & Safety (H&S) and Quality reporting system that receives reports via WhatsApp (Twilio), processes them using AWS services and AI, and returns actionable insights.

## System Architecture

### High-Level Flow
```
WhatsApp Message → Twilio Webhook → API Gateway → Lambda (Intake) 
→ Step Functions Orchestration → Multiple Processing Lambdas 
→ Response via Twilio → Database Storage
```

### AWS Services Required
- **AWS Lambda**: Serverless compute for processing steps
- **Step Functions**: Orchestrate the multi-step workflow
- **S3**: Store images and artifacts
- **DynamoDB**: Store reports, metadata, and audit trail
- **Bedrock**: AI/ML for text rewriting, image captioning, classification
- **API Gateway**: HTTP endpoint for Twilio webhooks
- **Secrets Manager**: Store Twilio credentials and API keys
- **CloudWatch**: Logging and monitoring
- **SNS** (optional): Notifications for high-severity incidents
- **SQS** (optional): Queue for async processing

## Detailed Workflow

### 1. Message Reception & Validation
**Lambda**: `twilio-intake-handler`

**Responsibilities**:
- Receive incoming webhook from Twilio WhatsApp Business API
- Validate Twilio signature for security
- Extract message components (image, description, sender phone number)
- Validate required fields are present
- If validation fails: Send rejection message via Twilio and exit
- If validation passes: Start Step Functions execution

**Input**:
```json
{
  "MessageSid": "string",
  "From": "whatsapp:+1234567890",
  "Body": "Description of incident/quality issue",
  "NumMedia": "1",
  "MediaUrl0": "https://...",
  "MediaContentType0": "image/jpeg"
}
```

**Validation Rules**:
- Must have image (NumMedia >= 1)
- Must have description (Body not empty)
- Must have sender (From field present)

**Output**:
```json
{
  "requestId": "uuid",
  "sender": "+1234567890",
  "description": "Original description",
  "imageUrl": "https://...",
  "timestamp": "ISO8601",
  "messageSid": "string"
}
```

**Error Response** (sent to WhatsApp):
```
❌ Unable to process your report. Please ensure you include both:
• An image
• A description of the issue
```

---

### 2. Project Selection
**Lambda**: `project-selector`

**Responsibilities**:
- Identify which project this report belongs to
- Use sender's phone number to lookup project assignment
- Query DynamoDB for user-project mapping

**Input**:
```json
{
  "requestId": "uuid",
  "sender": "+1234567890",
  ...
}
```

**DynamoDB Query**:
- Table: `UserProjectMappings`
- Key: `phoneNumber`
- Returns: `projectId`, `projectName`, `role`

**Output**:
```json
{
  ...previousData,
  "project": {
    "id": "proj-123",
    "name": "Construction Site A",
    "type": "construction"
  },
  "senderInfo": {
    "phoneNumber": "+1234567890",
    "name": "John Doe",
    "role": "Site Manager"
  }
}
```

**Note**: If user not found, use default project or request clarification

---

### 3. Description Rewrite
**Lambda**: `description-rewriter`

**Responsibilities**:
- Clean and standardize the description text
- Use AWS Bedrock (Claude or similar) to rewrite for clarity
- Maintain factual accuracy while improving grammar and structure

**Bedrock Prompt**:
```
You are a Health & Safety documentation specialist. Rewrite the following incident/quality report description to be clear, professional, and structured while maintaining all factual details.

Original Description: {description}

Requirements:
- Keep all facts unchanged
- Improve grammar and clarity
- Use professional language
- Maximum 3 sentences
- Focus on what, where, when, how

Rewritten Description:
```

**Input**:
```json
{
  ...previousData,
  "description": "there was some stuff falling from scaffold need to check it"
}
```

**Output**:
```json
{
  ...previousData,
  "originalDescription": "there was some stuff falling from scaffold need to check it",
  "rewrittenDescription": "Materials were observed falling from scaffolding structure. Immediate inspection required to assess structural integrity and prevent potential hazards."
}
```

---

### 4. Image Storage
**Lambda**: `image-storage-handler`

**Responsibilities**:
- Download image from Twilio's temporary URL
- Validate image format and size
- Upload to S3 with proper naming and metadata
- Generate CloudFront URL if CDN is configured

**S3 Structure**:
```
s3://mabani-reports-{env}/
  ├── images/
  │   ├── {year}/
  │   │   ├── {month}/
  │   │   │   ├── {requestId}.jpg
```

**S3 Object Metadata**:
- `request-id`: UUID
- `sender`: Phone number
- `project-id`: Project identifier
- `upload-timestamp`: ISO8601
- `content-type`: image/jpeg

**Input**:
```json
{
  ...previousData,
  "imageUrl": "https://api.twilio.com/..."
}
```

**Output**:
```json
{
  ...previousData,
  "image": {
    "s3Bucket": "mabani-reports-dev",
    "s3Key": "images/2025/11/uuid.jpg",
    "s3Url": "s3://...",
    "cdnUrl": "https://cdn.../uuid.jpg",
    "size": 245678,
    "format": "jpeg"
  }
}
```

---

### 5. Image Captioning
**Lambda**: `image-captioning`

**Responsibilities**:
- Analyze image using AWS Bedrock (Claude 3 with vision) or Rekognition
- Generate detailed caption describing visible hazards or quality issues
- Identify objects, conditions, and context

**Bedrock Vision Prompt**:
```
Analyze this Health & Safety / Quality report image and provide a detailed description.

Focus on:
- Visible hazards or safety concerns
- Equipment or materials present
- Environmental conditions
- Quality issues or defects
- People and PPE usage

Description: {rewrittenDescription}

Provide a concise 2-3 sentence caption describing what you observe in the image.
```

**Input**:
```json
{
  ...previousData,
  "image": { "s3Url": "..." },
  "rewrittenDescription": "..."
}
```

**Output**:
```json
{
  ...previousData,
  "imageCaption": "Scaffolding structure with unsecured materials on upper platform. No safety netting visible beneath work area. Two workers present, one wearing incomplete PPE."
}
```

---

### 6. Severity Classification
**Lambda**: `severity-classifier`

**Responsibilities**:
- Determine incident severity level
- Use AI model with description + image caption
- Classify as HIGH, MEDIUM, or LOW

**Classification Criteria**:
- **HIGH**: Immediate danger to life, serious injury risk, structural failure
- **MEDIUM**: Potential injury risk, equipment damage, regulatory non-compliance
- **LOW**: Minor issues, maintenance needed, best practice improvements

**Bedrock Classification Prompt**:
```
Classify the severity of this Health & Safety / Quality incident:

Description: {rewrittenDescription}
Visual Analysis: {imageCaption}

Classify as one of: HIGH, MEDIUM, LOW

HIGH: Immediate danger to life or serious injury risk
MEDIUM: Potential injury risk or equipment damage
LOW: Minor issues or preventive maintenance

Classification:
```

**Input**:
```json
{
  ...previousData,
  "rewrittenDescription": "...",
  "imageCaption": "..."
}
```

**Output**:
```json
{
  ...previousData,
  "severity": "HIGH",
  "severityReason": "Unsecured materials at height present serious falling object hazard"
}
```

---

### 7. Hazard Type Classification
**Lambda**: `hazard-classifier`

**Responsibilities**:
- Identify specific hazard type(s)
- Support multiple hazard types per incident
- Use predefined taxonomy

**Hazard Taxonomy**:
```
H&S Categories:
- Falls from Height
- Falling Objects
- Electrical Hazards
- Fire Hazards
- Chemical Exposure
- Manual Handling
- Confined Spaces
- Vehicle Movement
- Slips, Trips, Falls
- Equipment Malfunction
- PPE Non-compliance

Quality Categories:
- Material Defect
- Workmanship Issue
- Specification Deviation
- Dimensional Tolerance
- Surface Finish
- Installation Error
```

**Bedrock Classification Prompt**:
```
Identify the hazard type(s) for this incident:

Description: {rewrittenDescription}
Visual Analysis: {imageCaption}
Severity: {severity}

Select one or more from:
{hazardTaxonomy}

Return as JSON array: ["Hazard Type 1", "Hazard Type 2"]
```

**Input**:
```json
{
  ...previousData,
  "rewrittenDescription": "...",
  "imageCaption": "...",
  "severity": "HIGH"
}
```

**Output**:
```json
{
  ...previousData,
  "hazardTypes": ["Falls from Height", "Falling Objects", "PPE Non-compliance"]
}
```

---

### 8. Control Measure Generation (H&S Only)
**Lambda**: `control-measure-generator`

**Responsibilities**:
- Generate recommended control measures
- Use RAG (Retrieval Augmented Generation) with knowledge base
- Reference relevant safety standards and regulations
- **Skip this step for Quality reports**

**Knowledge Base**:
- HSE regulations
- Company safety procedures
- Best practices database
- Previous similar incidents

**Bedrock RAG Prompt**:
```
Based on this Health & Safety incident, provide ONE concise control measure recommendation with reference:

Description: {rewrittenDescription}
Visual Analysis: {imageCaption}
Severity: {severity}
Hazard Types: {hazardTypes}
Project: {projectName}

Provide:
1. A single, actionable control measure (1 sentence)
2. Reference to relevant standard or regulation

Format:
Control Measure: [action]
Reference: [standard/regulation]
```

**Input**:
```json
{
  ...previousData,
  "reportType": "HS",
  "rewrittenDescription": "...",
  "imageCaption": "...",
  "severity": "HIGH",
  "hazardTypes": ["Falls from Height", "Falling Objects"]
}
```

**Output**:
```json
{
  ...previousData,
  "controlMeasure": "Immediately install debris netting below all scaffolding work areas and secure all materials with tie-downs or edge protection.",
  "reference": "HSE WCFAG 2013 Section 4.7 - Prevention of falling materials"
}
```

**Skip Logic**: If `reportType === "Quality"`, set:
```json
{
  "controlMeasure": null,
  "reference": null
}
```

---

### 9. Database Storage
**Lambda**: `report-storage`

**Responsibilities**:
- Store complete report in DynamoDB
- Create audit trail
- Update project statistics
- Trigger notifications if needed

**DynamoDB Schema**:

**Table**: `IncidentReports`
```json
{
  "PK": "REPORT#uuid",
  "SK": "METADATA",
  "requestId": "uuid",
  "reportType": "HS|QUALITY",
  "timestamp": "ISO8601",
  "sender": {
    "phoneNumber": "+1234567890",
    "name": "John Doe",
    "role": "Site Manager"
  },
  "project": {
    "id": "proj-123",
    "name": "Construction Site A"
  },
  "description": {
    "original": "...",
    "rewritten": "..."
  },
  "image": {
    "s3Key": "...",
    "cdnUrl": "..."
  },
  "imageCaption": "...",
  "severity": "HIGH|MEDIUM|LOW",
  "severityReason": "...",
  "hazardTypes": ["..."],
  "controlMeasure": "...",
  "reference": "...",
  "status": "OPEN",
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601",
  "GSI1PK": "PROJECT#proj-123",
  "GSI1SK": "SEVERITY#HIGH#2025-11-08",
  "GSI2PK": "SENDER#+1234567890",
  "GSI2SK": "2025-11-08"
}
```

**Global Secondary Indexes**:
1. `GSI1`: Project reports by severity and date
2. `GSI2`: Sender reports by date

---

### 10. WhatsApp Response
**Lambda**: `twilio-response-sender`

**Responsibilities**:
- Format final response message
- Send via Twilio WhatsApp API
- Include report summary and reference number
- Different formats for H&S vs Quality

**H&S Response Format**:
```
✅ H&S Report Received - #{requestId}

📋 Description:
{rewrittenDescription}

⚠️ Severity: {SEVERITY}

🎯 Hazard Type:
{hazardTypes[0]}

🛡️ Recommended Action:
{controlMeasure}

📚 Reference: {reference}

Your report has been logged and relevant teams have been notified.
```

**Quality Response Format**:
```
✅ Quality Report Received - #{requestId}

📋 Description:
{rewrittenDescription}

⚠️ Priority: {SEVERITY}

🔍 Issue Type:
{hazardTypes[0]}

Your report has been logged and the quality team will review it shortly.
```

**Twilio API Call**:
```javascript
await twilioClient.messages.create({
  from: 'whatsapp:+14155238886', // Twilio WhatsApp number
  to: senderPhoneNumber,
  body: formattedResponse
});
```

---

## Step Functions State Machine

### State Machine Definition

```json
{
  "Comment": "H&S and Quality Report Processing Workflow",
  "StartAt": "ValidateInput",
  "States": {
    "ValidateInput": {
      "Type": "Pass",
      "Next": "ProjectSelection"
    },
    "ProjectSelection": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:project-selector",
      "Next": "ParallelProcessing",
      "Catch": [{
        "ErrorEquals": ["States.ALL"],
        "Next": "ErrorHandler"
      }]
    },
    "ParallelProcessing": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "RewriteDescription",
          "States": {
            "RewriteDescription": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:${region}:${account}:function:description-rewriter",
              "End": true
            }
          }
        },
        {
          "StartAt": "StoreImage",
          "States": {
            "StoreImage": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:${region}:${account}:function:image-storage-handler",
              "End": true
            }
          }
        }
      ],
      "Next": "ImageCaptioning",
      "ResultPath": "$.parallelResults"
    },
    "ImageCaptioning": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:image-captioning",
      "Next": "SeverityClassification"
    },
    "SeverityClassification": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:severity-classifier",
      "Next": "HazardClassification"
    },
    "HazardClassification": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:hazard-classifier",
      "Next": "CheckReportType"
    },
    "CheckReportType": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.reportType",
          "StringEquals": "HS",
          "Next": "GenerateControlMeasure"
        }
      ],
      "Default": "SkipControlMeasure"
    },
    "GenerateControlMeasure": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:control-measure-generator",
      "Next": "StoreReport"
    },
    "SkipControlMeasure": {
      "Type": "Pass",
      "Result": {
        "controlMeasure": null,
        "reference": null
      },
      "ResultPath": "$.controlMeasureData",
      "Next": "StoreReport"
    },
    "StoreReport": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:report-storage",
      "Next": "SendResponse"
    },
    "SendResponse": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:twilio-response-sender",
      "End": true
    },
    "ErrorHandler": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${region}:${account}:function:error-handler",
      "End": true
    }
  }
}
```

---

## Lambda Function Specifications

### Common Environment Variables (All Lambdas)
```yaml
ENVIRONMENT: dev|staging|prod
REGION: us-east-1
REPORTS_BUCKET: mabani-reports-${env}
REPORTS_TABLE: IncidentReports-${env}
PROJECTS_TABLE: Projects-${env}
USERS_TABLE: UserProjectMappings-${env}
TWILIO_SECRETS_ARN: arn:aws:secretsmanager:...
LOG_LEVEL: INFO
```

### IAM Permissions Summary

**twilio-intake-handler**:
- `states:StartExecution` - Start Step Functions
- `secretsmanager:GetSecretValue` - Get Twilio credentials
- `logs:CreateLogGroup/Stream/Events` - CloudWatch logging

**project-selector**:
- `dynamodb:GetItem` - Query user-project mappings
- `dynamodb:Query` - Query projects table

**description-rewriter**:
- `bedrock:InvokeModel` - Call Bedrock LLM

**image-storage-handler**:
- `s3:PutObject` - Upload images
- `s3:PutObjectTagging` - Add metadata

**image-captioning**:
- `s3:GetObject` - Read image
- `bedrock:InvokeModel` - Call Bedrock vision model

**severity-classifier**:
- `bedrock:InvokeModel` - Call Bedrock for classification

**hazard-classifier**:
- `bedrock:InvokeModel` - Call Bedrock for classification

**control-measure-generator**:
- `bedrock:InvokeModel` - Call Bedrock
- `bedrock:Retrieve` - Query knowledge base (RAG)

**report-storage**:
- `dynamodb:PutItem` - Store report
- `dynamodb:UpdateItem` - Update project stats
- `sns:Publish` - Send high-severity notifications

**twilio-response-sender**:
- `secretsmanager:GetSecretValue` - Get Twilio credentials
- `logs:*` - CloudWatch logging

---

## Twilio Integration

### Webhook Configuration

**Incoming Message Webhook**:
- URL: `https://{api-id}.execute-api.{region}.amazonaws.com/{stage}/twilio/webhook`
- Method: POST
- Content-Type: application/x-www-form-urlencoded

**Webhook Security**:
- Validate Twilio signature using `X-Twilio-Signature` header
- Use Twilio auth token from Secrets Manager
- Reject unsigned requests

**Validation Code** (in intake handler):
```javascript
const twilio = require('twilio');

function validateTwilioSignature(event, authToken) {
  const signature = event.headers['X-Twilio-Signature'];
  const url = `https://${event.headers.Host}${event.requestContext.path}`;
  const params = parseFormData(event.body);
  
  return twilio.validateRequest(authToken, signature, url, params);
}
```

---

## Error Handling Strategy

### Error Categories

1. **Validation Errors** (4xx)
   - Missing image or description
   - Invalid phone number
   - Unsupported media type
   - Response: User-friendly WhatsApp message

2. **Processing Errors** (5xx)
   - AI service failures
   - S3 upload failures
   - Database errors
   - Response: Generic error message + retry logic

3. **External Service Errors**
   - Twilio API failures
   - Bedrock throttling
   - Network timeouts
   - Response: Exponential backoff + dead letter queue

### Retry Configuration

**Step Functions Retry Policy**:
```json
{
  "Retry": [{
    "ErrorEquals": ["States.TaskFailed"],
    "IntervalSeconds": 2,
    "MaxAttempts": 3,
    "BackoffRate": 2.0
  }]
}
```

**Lambda Timeout Settings**:
- Intake Handler: 30 seconds
- Image Processing: 60 seconds
- AI/ML Lambdas: 120 seconds
- Storage Operations: 30 seconds

### Dead Letter Queue
- All lambdas should have DLQ configured
- SNS topic for critical failures
- Alert operations team for DLQ items

---

## Cost Optimization

### Strategies

1. **Lambda Memory Optimization**
   - AI lambdas: 1024 MB (need more for model invocation)
   - I/O lambdas: 256 MB
   - Image processing: 512 MB

2. **Bedrock Model Selection**
   - Text tasks: Claude 3 Haiku (cheapest)
   - Vision tasks: Claude 3 Haiku with vision
   - Complex reasoning: Claude 3 Sonnet (only if needed)

3. **S3 Lifecycle Policies**
   - Transition to S3-IA after 90 days
   - Archive to Glacier after 1 year
   - Delete after 7 years (compliance dependent)

4. **DynamoDB On-Demand vs Provisioned**
   - Start with On-Demand for variable workload
   - Switch to Provisioned if traffic predictable

5. **Step Functions Express vs Standard**
   - Use Express Workflows for high-volume, short-duration
   - Standard for audit trail and long-running processes

### Estimated Monthly Costs (1000 reports/month)

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | ~30,000 invocations | $0.60 |
| Step Functions | 1,000 executions | $0.25 |
| S3 Storage | 10 GB images | $0.23 |
| DynamoDB | 1,000 writes + reads | $2.50 |
| Bedrock | ~8,000 API calls | $40.00 |
| API Gateway | 1,000 requests | $0.01 |
| **Total** | | **~$43.59** |

---

## Security Considerations

### Data Privacy
- Encrypt all data at rest (S3, DynamoDB)
- Use AWS KMS for encryption keys
- Enable S3 bucket versioning
- No PII in logs

### Access Control
- Principle of least privilege for IAM roles
- Separate roles per lambda function
- No public S3 bucket access
- API Gateway with IAM authorization

### Compliance
- GDPR considerations for personal data
- Data retention policies
- Audit trail in CloudWatch and DynamoDB
- Right to deletion workflow

### Secrets Management
- Store Twilio credentials in Secrets Manager
- Rotate secrets regularly
- Never log credentials
- Use VPC endpoints for private communication

---

## Monitoring & Observability

### CloudWatch Metrics

**Custom Metrics to Track**:
- Reports processed per minute
- Processing duration per step
- Error rate by lambda
- Severity distribution
- Response time to user

**Alarms**:
- Error rate > 5%
- Processing time > 5 minutes
- DLQ depth > 10
- High severity incidents

### CloudWatch Logs Insights Queries

**Processing Duration**:
```
fields @timestamp, @duration, requestId, stepName
| filter stepName = "StoreReport"
| stats avg(@duration), max(@duration), count() by bin(5m)
```

**Error Analysis**:
```
fields @timestamp, errorType, errorMessage, requestId
| filter @type = "ERROR"
| stats count() by errorType
```

### X-Ray Tracing
- Enable X-Ray for all lambdas
- Trace complete workflow end-to-end
- Identify bottlenecks
- Track external API calls

---

## Testing Strategy

### Unit Tests
- Test each lambda independently
- Mock AWS service calls
- Test error conditions
- Test edge cases

### Integration Tests
- Test Step Functions workflow
- Use mock Twilio webhooks
- Test database operations
- Test S3 operations

### End-to-End Tests
- Send test messages via Twilio sandbox
- Verify complete workflow
- Check response formatting
- Validate data storage

### Load Testing
- Simulate concurrent reports
- Test Step Functions throttling
- Monitor Lambda cold starts
- Test DynamoDB capacity

---

## Deployment Strategy

### Infrastructure as Code
- Use AWS CDK (TypeScript) for infrastructure
- Separate stacks: Compute, Storage, Networking
- Environment-specific configurations
- Automated deployments via CI/CD

### CI/CD Pipeline
```yaml
Stages:
1. Lint & Format
2. Unit Tests
3. Build Lambda packages
4. Deploy to Dev
5. Integration Tests
6. Deploy to Staging
7. E2E Tests
8. Manual Approval
9. Deploy to Production
10. Smoke Tests
```

### Rollback Strategy
- Use CDK stack versioning
- Blue/Green deployment for lambdas
- Canary deployments for Step Functions
- Database migration rollback plan

---

## Future Enhancements

### Phase 2
- Multi-language support (Arabic, French)
- Voice message support
- Real-time dashboard for managers
- Mobile app integration
- Offline support

### Phase 3
- Predictive analytics for incident patterns
- Computer vision for automatic hazard detection
- Integration with IoT sensors
- Automated corrective action workflows
- Training recommendation engine

### Phase 4
- Multi-tenant architecture
- White-label solution
- API for third-party integrations
- Advanced reporting and analytics
- ML model for incident prediction

---

## Appendix

### Bedrock Model Recommendations

**Text Tasks** (Rewriting, Classification):
- Model: `anthropic.claude-3-haiku-20240307-v1:0`
- Max tokens: 500
- Temperature: 0.3 (more deterministic)

**Vision Tasks** (Image Captioning):
- Model: `anthropic.claude-3-haiku-20240307-v1:0`
- Max tokens: 300
- Temperature: 0.3

**RAG Tasks** (Control Measures):
- Model: `anthropic.claude-3-sonnet-20240229-v1:0`
- Knowledge Base: Custom H&S regulations
- Max tokens: 200
- Temperature: 0.2 (very deterministic)

### Sample Twilio Webhook Payload

```json
{
  "SmsMessageSid": "SM...",
  "NumMedia": "1",
  "ProfileName": "John Doe",
  "MessageType": "text",
  "SmsSid": "SM...",
  "WaId": "1234567890",
  "SmsStatus": "received",
  "Body": "Scaffold material falling - urgent check needed",
  "To": "whatsapp:+14155238886",
  "NumSegments": "1",
  "ReferralNumMedia": "0",
  "MessageSid": "SM...",
  "AccountSid": "AC...",
  "From": "whatsapp:+1234567890",
  "MediaContentType0": "image/jpeg",
  "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/AC.../Messages/SM.../Media/ME...",
  "ApiVersion": "2010-04-01"
}
```

### DynamoDB Access Patterns

1. **Get report by ID**
   - `GetItem(PK=REPORT#uuid, SK=METADATA)`

2. **Get all reports for project**
   - `Query(GSI1, GSI1PK=PROJECT#proj-123)`

3. **Get high-severity reports for project**
   - `Query(GSI1, GSI1PK=PROJECT#proj-123, GSI1SK begins_with SEVERITY#HIGH)`

4. **Get reports by sender**
   - `Query(GSI2, GSI2PK=SENDER#+1234567890)`

5. **Get recent reports across all projects**
   - `Scan` with filter (or time-series table design)

---

## Contact & Support

- Architecture Questions: [Architecture Team]
- Twilio Integration: [Integration Team]
- AWS Resources: [DevOps Team]
- H&S Business Logic: Hicham
- Security Concerns: [Security Team]

---

**Document Version**: 1.0  
**Last Updated**: November 8, 2025  
**Authors**: AI Assistant + Engineering Team  
**Status**: Draft - Pending Review

