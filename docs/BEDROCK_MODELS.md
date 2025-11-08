# Bedrock Model Configuration

This document explains the Bedrock model options for the H&S + Quality report processing system.

## Default Configuration (Nova Models)

The system is configured to use **Amazon Nova** models by default:

- **Text Tasks** (description rewriting, classification): `amazon.nova-lite-v1:0`
- **Vision Tasks** (image captioning): `amazon.nova-pro-v1:0`

### Why Nova Models?

✅ **Cost-Effective**: Nova models are generally more affordable than Claude  
✅ **Fast**: Lower latency for most tasks  
✅ **AWS Native**: Tighter integration with AWS services  
✅ **Capable**: Excellent performance for structured tasks like classification

## Model Comparison

### Amazon Nova Micro (`amazon.nova-micro-v1:0`)

- **Use Case**: Ultra-fast, simple tasks
- **Capabilities**: Text-only
- **Cost**: Lowest
- **When to Use**: Simple text classification, basic rewriting
- **Limitations**: May struggle with complex reasoning

### Amazon Nova Lite (`amazon.nova-lite-v1:0`) ⭐ Default for Text

- **Use Case**: Balanced performance and cost
- **Capabilities**: Text and basic vision
- **Cost**: Low
- **When to Use**: Description rewriting, severity classification, hazard type detection
- **Strengths**: Great for structured outputs, fast response times

### Amazon Nova Pro (`amazon.nova-pro-v1:0`) ⭐ Default for Vision

- **Use Case**: Complex analysis and vision tasks
- **Capabilities**: Advanced text and vision
- **Cost**: Medium
- **When to Use**: Image captioning, complex hazard analysis, control measure generation
- **Strengths**: Better understanding of visual context, more detailed analysis

### Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`)

- **Use Case**: Fast, high-quality responses
- **Capabilities**: Text and vision
- **Cost**: Medium
- **When to Use**: If you need Claude's reasoning style
- **Strengths**: Excellent at following complex instructions

### Claude 3 Sonnet (`anthropic.claude-3-sonnet-20240229-v1:0`)

- **Use Case**: Complex reasoning and nuanced understanding
- **Capabilities**: Advanced text and vision
- **Cost**: High
- **When to Use**: Complex safety assessments requiring deep reasoning
- **Strengths**: Best reasoning capabilities, very accurate

## Changing Models

### Option 1: Update Environment Variables (Recommended)

Edit `backend/serverless.yml`:

```yaml
environment:
  # Text model (rewriting, classification)
  BEDROCK_MODEL_ID: amazon.nova-lite-v1:0

  # Vision model (image captioning)
  BEDROCK_VISION_MODEL_ID: amazon.nova-pro-v1:0
```

**Alternatives**:

```yaml
# Use Nova Micro for even lower cost
BEDROCK_MODEL_ID: amazon.nova-micro-v1:0

# Use Claude Haiku for all tasks
BEDROCK_MODEL_ID: anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_VISION_MODEL_ID: anthropic.claude-3-haiku-20240307-v1:0

# Use Claude Sonnet for better quality (higher cost)
BEDROCK_MODEL_ID: anthropic.claude-3-sonnet-20240229-v1:0
BEDROCK_VISION_MODEL_ID: anthropic.claude-3-sonnet-20240229-v1:0
```

### Option 2: Update at Runtime

```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name taskflow-backend-dev-reportProcessor \
  --environment Variables={
    BEDROCK_MODEL_ID=amazon.nova-micro-v1:0,
    BEDROCK_VISION_MODEL_ID=amazon.nova-pro-v1:0
  } \
  --region eu-west-1 \
  --profile mia40
```

### Option 3: IAM Permissions

Don't forget to update IAM permissions in `serverless.yml` if using Claude:

```yaml
- Effect: Allow
  Action:
    - bedrock:InvokeModel
  Resource:
    # Nova models
    - "arn:aws:bedrock:${self:provider.region}::foundation-model/amazon.nova-lite-v1:0"
    - "arn:aws:bedrock:${self:provider.region}::foundation-model/amazon.nova-pro-v1:0"
    - "arn:aws:bedrock:${self:provider.region}::foundation-model/amazon.nova-micro-v1:0"
    # Claude models
    - "arn:aws:bedrock:${self:provider.region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
    - "arn:aws:bedrock:${self:provider.region}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
```

## Enabling Model Access

Before using any model, you must enable access in AWS Bedrock:

### Via AWS Console:

1. Go to **AWS Console → Bedrock → Model access**
2. Click **"Manage model access"**
3. Select the models you want to use:
   - ✅ Amazon Nova Micro
   - ✅ Amazon Nova Lite
   - ✅ Amazon Nova Pro
   - ✅ Claude 3 Haiku (optional)
   - ✅ Claude 3 Sonnet (optional)
4. Click **"Request model access"**
5. Wait for approval (usually instant)

### Via AWS CLI:

```bash
# List available models
aws bedrock list-foundation-models \
  --region eu-west-1 \
  --profile mia40

# Check if Nova models are accessible
aws bedrock list-foundation-models \
  --region eu-west-1 \
  --profile mia40 \
  --query 'modelSummaries[?contains(modelId, `amazon.nova`)].{ID:modelId,Name:modelName,Status:modelLifecycle.status}'
```

## Cost Comparison (Estimated per 1,000 Reports)

Based on typical usage patterns:

| Model                       | Text Tasks | Vision Tasks | Total/1000 Reports |
| --------------------------- | ---------- | ------------ | ------------------ |
| **Nova Micro + Nova Pro**   | $5         | $15          | **$20** 💰         |
| **Nova Lite + Nova Pro** ⭐ | $8         | $15          | **$23**            |
| **Nova Pro (All)**          | $15        | $15          | **$30**            |
| **Claude Haiku (All)**      | $20        | $20          | **$40**            |
| **Claude Sonnet (All)**     | $60        | $60          | **$120** 💸        |

_Note: Prices are estimates and subject to change. Check AWS Bedrock pricing for current rates._

## Recommended Configurations

### 💰 **Budget** (Lowest Cost)

```yaml
BEDROCK_MODEL_ID: amazon.nova-micro-v1:0
BEDROCK_VISION_MODEL_ID: amazon.nova-lite-v1:0
```

**Best for**: High volume, cost-sensitive deployments

### ⚖️ **Balanced** (Default) ⭐

```yaml
BEDROCK_MODEL_ID: amazon.nova-lite-v1:0
BEDROCK_VISION_MODEL_ID: amazon.nova-pro-v1:0
```

**Best for**: Most production deployments

### 🎯 **Quality** (Best Performance)

```yaml
BEDROCK_MODEL_ID: amazon.nova-pro-v1:0
BEDROCK_VISION_MODEL_ID: amazon.nova-pro-v1:0
```

**Best for**: Critical safety assessments

### 🚀 **Premium** (Claude)

```yaml
BEDROCK_MODEL_ID: anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_VISION_MODEL_ID: anthropic.claude-3-haiku-20240307-v1:0
```

**Best for**: When you need Claude's reasoning style

## Testing Different Models

Use the test script to compare models:

```bash
# Test with current configuration
cd backend
serverless invoke -f reportProcessor -p test-events.json -s dev

# Test with Nova Micro (update env var first)
aws lambda update-function-configuration \
  --function-name taskflow-backend-dev-reportProcessor \
  --environment Variables={BEDROCK_MODEL_ID=amazon.nova-micro-v1:0}

serverless invoke -f reportProcessor -p test-events.json -s dev
```

## Troubleshooting

### "Model not found" Error

- ✅ Verify model ID is correct
- ✅ Check region (Nova models may not be available in all regions)
- ✅ Ensure you've requested model access in Bedrock console

### "Access denied" Error

- ✅ Check IAM permissions in `serverless.yml`
- ✅ Verify Lambda execution role has `bedrock:InvokeModel` permission
- ✅ Confirm model ARN is correct for your region

### Poor Quality Results

- 📈 Try upgrading to Nova Pro or Claude Haiku
- 🎨 Adjust temperature (lower = more consistent)
- 📝 Improve prompts in `bedrock_client.py`

### High Costs

- 📉 Downgrade to Nova Micro for text tasks
- 🎯 Use Nova Lite for vision instead of Nova Pro
- 📊 Monitor usage in AWS Cost Explorer

## Monitoring Model Performance

Track model performance in CloudWatch:

```bash
# View invocation metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --dimensions Name=ModelId,Value=amazon.nova-lite-v1:0 \
  --start-time 2025-11-01T00:00:00Z \
  --end-time 2025-11-08T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

## Support

For model-related questions:

- 📖 [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- 📖 [Amazon Nova Models](https://aws.amazon.com/bedrock/nova/)
- 📖 [Anthropic Claude Models](https://www.anthropic.com/claude)

---

**Last Updated**: November 8, 2025  
**Version**: 1.0
