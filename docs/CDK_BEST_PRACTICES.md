# CDK Best Practices Summary

## CDK → CloudFormation Relationship

**YES, CDK creates CloudFormation stacks!** Here's the flow:

```
Your CDK Code (TypeScript)
    ↓
cdk synth (synthesis)
    ↓
CloudFormation Template (JSON/YAML in cdk.out/)
    ↓
cdk deploy
    ↓
CloudFormation Stack (in AWS Console)
```

### Key Points:

1. **CDK Stack = CloudFormation Stack**: Each CDK Stack becomes a CloudFormation Stack
2. **View in AWS**: CloudFormation → Stacks → `MabaniCognitoStack-dev`, `MabaniFrontendStack-dev`
3. **Templates**: Generated in `cdk.out/` directory when you run `cdk synth`
4. **Managed by CloudFormation**: All resources are managed via CloudFormation service

## What's Configured (Best Practices)

### ✅ Security Best Practices

1. **Encryption**

   - S3 buckets encrypted at rest (S3-managed keys)
   - HTTPS enforced via CloudFront

2. **Access Control**

   - S3 public access blocked
   - Origin Access Control (OAC) for CloudFront → S3
   - Cognito token revocation enabled
   - Prevent user existence errors (security)

3. **Security Headers** (CloudFront)

   - HSTS (HTTP Strict Transport Security)
   - Content Security Policy
   - X-Frame-Options: DENY
   - X-Content-Type-Options
   - Referrer-Policy

4. **Authentication**
   - MFA optional (can be required)
   - Device tracking enabled
   - Password policy enforced
   - Token expiration configured

### ✅ Monitoring & Observability

1. **CloudWatch Logs**

   - Cognito User Pool logs
   - Environment-based retention (1 month dev, 1 year prod)

2. **Access Logging**
   - S3 bucket access logs
   - CloudFront access logs
   - Separate log bucket for security

### ✅ Cost Optimization

1. **S3 Lifecycle Policies**

   - Transition to Infrequent Access after 90 days
   - Delete old versions (prod only)

2. **Versioning**

   - Enabled only in production

3. **CloudFront Price Class**

   - Dev/Staging: PRICE_CLASS_100 (cheaper)
   - Production: PRICE_CLASS_ALL (global coverage)

4. **Auto-delete**
   - Dev/Staging: Auto-delete on destroy
   - Production: Retain on destroy

### ✅ Environment Management

1. **Multi-Environment Support**

   - Dev, Staging, Prod configurations
   - Environment-specific naming
   - Context-based deployment

2. **Configuration Management**

   - Centralized config in `config.ts`
   - Type-safe environment settings
   - CORS origins per environment

3. **Resource Naming**
   - Environment prefix in all resources
   - Consistent naming convention

### ✅ Operational Excellence

1. **Tagging Strategy**

   - Project, Environment, ManagedBy, Repository tags
   - Cost allocation tags (CostCenter)

2. **Stack Dependencies**

   - Explicit dependencies between stacks
   - Automatic deployment ordering

3. **Removal Policies**

   - Production: RETAIN (prevent accidental deletion)
   - Dev/Staging: DESTROY (easier cleanup)

4. **Outputs**
   - CloudFormation outputs for cross-stack references
   - Export values for external consumption

## Resource Breakdown

### MabaniCognitoStack

**CloudFormation Stack Name**: `MabaniCognitoStack-{environment}`

Resources:

- ✅ Cognito User Pool (with MFA, device tracking)
- ✅ Cognito User Pool Client (OAuth configured)
- ✅ CloudWatch Log Group
- ✅ Stack Outputs (UserPoolId, ClientId, ARN)

### MabaniFrontendStack

**CloudFormation Stack Name**: `MabaniFrontendStack-{environment}`

Resources:

- ✅ S3 Bucket (frontend hosting, encrypted, versioned)
- ✅ S3 Bucket (access logs)
- ✅ CloudFront Distribution (with security headers)
- ✅ Origin Access Control
- ✅ IAM Policies
- ✅ Stack Outputs (BucketName, DistributionId, URL)

## Deployment Commands

```bash
# Install dependencies first
cd infrastructure
npm install

# Synthesize (see CloudFormation templates)
npm run synth

# Deploy dev environment
npm run deploy:dev

# Deploy specific stack
cdk deploy MabaniCognitoStack-dev --context environment=dev --profile mia40

# View differences before deploying
npm run diff

# List all stacks
npm run list
```

## What's NOT in CDK (Managed Separately)

- **Backend**: Lambda + API Gateway + DynamoDB (Serverless Framework)
- **Reason**: Already configured in `serverless.yml`
- **Future**: Consider migrating to CDK for unified management

## Next Steps

1. **Install Dependencies**: `cd infrastructure && npm install`
2. **Bootstrap CDK**: `npm run bootstrap` (first time only)
3. **Deploy Cognito**: `npm run deploy:cognito`
4. **Get Outputs**: Use AWS CLI or CloudFormation console to get UserPool IDs
5. **Update Frontend**: Add environment variables to `frontend/.env`

## CloudFormation Templates Location

After running `cdk synth`, find templates in:

```
infrastructure/cdk.out/
├── MabaniCognitoStack-dev.template.json
└── MabaniFrontendStack-dev.template.json
```

These are the actual CloudFormation templates that get deployed to AWS!
