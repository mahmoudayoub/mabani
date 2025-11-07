# CDK Infrastructure

This directory contains AWS CDK (Cloud Development Kit) code for provisioning infrastructure.

## CDK to CloudFormation Relationship

**Yes, CDK synthesizes to CloudFormation stacks!** Here's how it works:

### How CDK Works

1. **CDK Code (TypeScript/JavaScript)** → Your code using CDK constructs
2. **CDK Synthesis** → `cdk synth` converts your code to CloudFormation JSON/YAML
3. **CloudFormation Templates** → Generated templates stored in `cdk.out/`
4. **CloudFormation Stacks** → Deployed to AWS using CloudFormation service

```
CDK Code (app.ts, stacks.ts)
    ↓ (cdk synth)
CloudFormation Template (JSON/YAML)
    ↓ (cdk deploy)
CloudFormation Stack (in AWS)
```

### What Gets Created

When you run `cdk deploy`, it:

- Synthesizes your CDK code into CloudFormation templates
- Creates/updates CloudFormation stacks in AWS
- Each CDK Stack becomes a CloudFormation Stack

### Stack Names

- **CDK Stack ID**: `MabaniCognitoStack-dev` (defined in your code)
- **CloudFormation Stack Name**: Same as CDK Stack ID
- **View in AWS Console**: CloudFormation → Stacks

## Best Practices Implemented

### 1. Environment Configuration

- Centralized config in `config.ts`
- Environment-specific settings (dev/staging/prod)
- Context-based environment selection

### 2. Security

- ✅ S3 encryption at rest
- ✅ Public access blocked
- ✅ Security headers in CloudFront
- ✅ MFA support in Cognito
- ✅ Token revocation enabled
- ✅ Prevent user existence errors

### 3. Monitoring & Logging

- ✅ CloudWatch Log Groups for Cognito
- ✅ S3 access logging
- ✅ CloudFront access logging
- ✅ Environment-specific log retention

### 4. Cost Optimization

- ✅ Lifecycle policies for S3
- ✅ Versioning only in production
- ✅ Auto-delete only in non-prod
- ✅ Price class optimization

### 5. Resource Management

- ✅ Environment-specific naming
- ✅ Proper removal policies
- ✅ Stack dependencies
- ✅ Resource tagging

### 6. Type Safety

- ✅ TypeScript interfaces for stack props
- ✅ Type-safe configuration
- ✅ Compile-time validation

## Deployment

### Prerequisites

```bash
cd infrastructure
npm install
```

### Deploy to Specific Environment

```bash
# Deploy dev environment
npx cdk deploy --context environment=dev --profile mia40

# Deploy staging environment
npx cdk deploy --context environment=staging --profile mia40

# Deploy production environment
npx cdk deploy --context environment=prod --profile mia40
```

### View CloudFormation Template (Before Deploying)

```bash
npx cdk synth --context environment=dev
# Outputs to cdk.out/
```

### Useful Commands

```bash
# List all stacks
npx cdk list --context environment=dev

# Compare deployed stack with current state
npx cdk diff --context environment=dev

# Bootstrap CDK (first time only)
npx cdk bootstrap --profile mia40

# Destroy all resources
npx cdk destroy --context environment=dev
```

## Stack Structure

### MabaniCognitoStack

- **CloudFormation Stack**: `MabaniCognitoStack-{environment}`
- **Resources**:
  - Cognito User Pool
  - Cognito User Pool Client
  - CloudWatch Log Group

### MabaniFrontendStack

- **CloudFormation Stack**: `MabaniFrontendStack-{environment}`
- **Resources**:
  - S3 Bucket (frontend hosting)
  - S3 Bucket (access logs)
  - CloudFront Distribution
  - Origin Access Control
  - IAM Policies

## Configuration

Edit `cdk/config.ts` to modify:

- AWS account/region
- Environment-specific settings
- CORS origins
- Domain names

## Resources Not in CDK

The following are managed separately:

- **Backend (Lambda + API Gateway + DynamoDB)**: Managed by Serverless Framework
- See `../backend/serverless.yml`

## Migration to Full CDK (Future)

Consider migrating backend to CDK for:

- Unified infrastructure management
- Better integration between stacks
- Consistent deployment process
- Cross-stack references
