# Stack Organization Guide: How to Organize Resources Across CDK Stacks

## Core Principles

### 1. **Group by Lifecycle** (Most Important)

Resources that change together should be in the same stack.

- ✅ **Same Stack**: Resources that deploy/update together
- ❌ **Different Stacks**: Resources with different change frequencies

### 2. **Group by Ownership/Team**

Resources managed by different teams should be in separate stacks.

- Frontend team → Frontend stack
- Backend team → Backend stack
- Infrastructure team → Shared resources stack

### 3. **Group by Dependencies**

If Stack B depends heavily on Stack A, they should be separate.

- ✅ **Separate**: Stack B imports outputs from Stack A
- ❌ **Same Stack**: Direct property references (no imports needed)

### 4. **Group by Purpose/Function**

Related functionality should be grouped.

- Authentication → Cognito stack
- Compute → Lambda stack
- Storage → S3 stack
- Networking → CloudFront/VPC stack

---

## Resource Breakdown for Your Project

### Resources to Organize:

1. **Cognito User Pool** (auth)
2. **Cognito User Pool Client** (auth app)
3. **S3 Bucket** (frontend hosting)
4. **S3 Bucket** (access logs - optional)
5. **CloudFront Distribution** (CDN)
6. **Lambda Functions** (backend API)
7. **Lambda Layer** (shared code/dependencies)
8. **API Gateway** (REST API)
9. **DynamoDB Table** (database - if in CDK)
10. **IAM Roles/Policies** (various)
11. **CloudWatch Log Groups** (optional)
12. **VPC/Networking** (if needed)

---

## Recommended Stack Organization

### **Pattern 1: Function-Based (Recommended for Your Project)**

#### Stack 1: `AuthStack` (Authentication)

**Lifecycle**: Changes rarely (auth config)
**Ownership**: Infrastructure/Security team
**Resources**:

- ✅ Cognito User Pool
- ✅ Cognito User Pool Client
- ✅ IAM roles for Cognito integration (if any)

**Why Separate**:

- Auth changes infrequently
- Shared across multiple apps
- Security-sensitive, needs separate access control

---

#### Stack 2: `FrontendStack` (Static Hosting)

**Lifecycle**: Changes frequently (new builds)
**Ownership**: Frontend team
**Resources**:

- ✅ S3 Bucket (frontend hosting)
- ✅ CloudFront Distribution
- ✅ Origin Access Control (OAC)
- ✅ CloudFront Response Headers Policy
- ✅ IAM policies for CloudFront → S3

**Why Separate**:

- Updates frequently (every frontend deployment)
- Independent from backend/auth
- Can be destroyed/recreated easily

---

#### Stack 3: `BackendStack` (Compute & API)

**Lifecycle**: Changes frequently (code updates)
**Ownership**: Backend team
**Resources**:

- ✅ Lambda Layer (shared dependencies)
- ✅ Lambda Functions (all API handlers)
- ✅ API Gateway (REST API)
- ✅ IAM roles for Lambda execution
- ✅ CloudWatch Log Groups (Lambda logs)
- ✅ DynamoDB Table (if managed in CDK)

**Why Separate**:

- Code changes frequently
- Can deploy backend without touching frontend
- Lambda functions grouped logically

---

#### Stack 4: `SharedStack` (Optional - if needed)

**Lifecycle**: Changes rarely
**Ownership**: Infrastructure team
**Resources**:

- ✅ DynamoDB Table (if shared across services)
- ✅ S3 Bucket (shared data/logs)
- ✅ VPC (if networking required)
- ✅ Shared IAM roles/policies

**Why Separate**:

- Shared across multiple services
- Long-lived infrastructure
- Rarely changes

---

### **Pattern 2: Environment-Based** (Alternative)

Separate stacks per environment, with all resources per environment:

- `DevStack` - All dev resources
- `StagingStack` - All staging resources
- `ProdStack` - All prod resources

**❌ Not Recommended For You**:

- Duplicates code across environments
- Harder to maintain
- You're already using context-based config (better approach)

---

### **Pattern 3: Layer-Based** (For Large Projects)

- `NetworkStack` - VPC, subnets, security groups
- `DataStack` - Databases, storage
- `ComputeStack` - Lambda, ECS, EC2
- `ApplicationStack` - API Gateway, Cognito
- `DistributionStack` - CloudFront, S3

**❌ Overkill for Your Project**: Too granular for current scale

---

## Decision Matrix

### When to Put Resources in the Same Stack

| Criteria                   | Same Stack? | Example                             |
| -------------------------- | ----------- | ----------------------------------- |
| Change together frequently | ✅ Yes      | Lambda + API Gateway                |
| Managed by same team       | ✅ Yes      | All frontend resources              |
| Direct property references | ✅ Yes      | CloudFront → S3 bucket              |
| Same lifecycle             | ✅ Yes      | Lambda + Lambda Layer               |
| Atomic deployment needed   | ✅ Yes      | Resources that must deploy together |

### When to Put Resources in Different Stacks

| Criteria                          | Different Stacks? | Example                                     |
| --------------------------------- | ----------------- | ------------------------------------------- |
| Different change frequencies      | ✅ Yes            | Cognito (rare) vs Frontend (frequent)       |
| Different ownership/teams         | ✅ Yes            | Auth (security team) vs Frontend (dev team) |
| Cross-stack reference needed      | ✅ Yes            | Backend needs Cognito User Pool ID          |
| Independent scaling               | ✅ Yes            | Frontend can scale without backend changes  |
| Different cost optimization needs | ✅ Yes            | Can destroy frontend, keep Cognito          |

---

## Specific Recommendations for Your Resources

### ✅ **Keep Together** (Same Stack)

#### **Cognito Stack**:

```
✅ Cognito User Pool
✅ Cognito User Pool Client
```

**Reason**: Tightly coupled, change together, same purpose

---

#### **Frontend Stack**:

```
✅ S3 Bucket (frontend hosting)
✅ CloudFront Distribution
✅ Origin Access Control
✅ Response Headers Policy
✅ IAM policy (CloudFront → S3)
```

**Reason**: All part of frontend deployment, deploy together

---

#### **Backend Stack**:

```
✅ Lambda Layer
✅ All Lambda Functions
✅ API Gateway
✅ Lambda execution IAM roles
✅ CloudWatch Log Groups (Lambda)
```

**Reason**: Backend code components, deploy together

**Note**: DynamoDB can go here OR in a separate stack if:

- Shared across multiple services → Separate stack
- Only used by backend → Same stack

---

### ⚠️ **Consider Separate Stacks**

#### **DynamoDB Table**:

- **Option A**: In `BackendStack` if only used by Lambda functions
- **Option B**: In `SharedStack` if shared across services
- **Option C**: Separate `DatabaseStack` if multiple tables or complex setup

**Decision**: Use Option A for now, migrate to Option B/C later if needed

---

#### **S3 Access Logs Bucket**:

- **Current**: Removed (cost savings)
- **If needed**: Could go in `SharedStack` or `FrontendStack`

**Decision**: Keep removed unless compliance requires it

---

## Real-World Example: Your Current + Expanded Architecture

### **Stack 1: `MabaniAuthStack`**

```typescript
- Cognito User Pool
- Cognito User Pool Client
- Outputs: UserPoolId, ClientId, UserPoolArn
```

### **Stack 2: `MabaniFrontendStack`**

```typescript
- S3 Bucket (frontend)
- CloudFront Distribution
- Origin Access Control
- IAM policies
- Outputs: BucketName, DistributionId, WebsiteURL
```

### **Stack 3: `MabaniBackendStack`** (New)

```typescript
- Lambda Layer
- Lambda Functions (user_profile, items, etc.)
- API Gateway REST API
- IAM roles for Lambda
- CloudWatch Log Groups
- Outputs: ApiEndpoint, ApiId
```

### **Stack 4: `MabaniDatabaseStack`** (Optional)

```typescript
- DynamoDB Table
- DynamoDB Streams (if needed)
- Outputs: TableName, TableArn
```

**Dependency Chain**:

```
AuthStack (no dependencies)
    ↓
FrontendStack (depends on: none, but may reference Auth outputs)
    ↓
BackendStack (depends on: AuthStack for UserPool ARN)
    ↓
DatabaseStack (depends on: BackendStack for Lambda table access)
```

---

## Deployment Strategy

### Initial Deployment Order:

```bash
1. cdk deploy MabaniAuthStack-dev          # Foundation
2. cdk deploy MabaniDatabaseStack-dev      # Data layer
3. cdk deploy MabaniBackendStack-dev       # Uses Auth + DB
4. cdk deploy MabaniFrontendStack-dev      # Independent
```

### Daily Development Workflow:

```bash
# Frontend team (frequent)
cdk deploy MabaniFrontendStack-dev

# Backend team (frequent)
cdk deploy MabaniBackendStack-dev

# Auth changes (rare)
cdk deploy MabaniAuthStack-dev
```

### Using Dependencies:

```typescript
// In app.ts
const authStack = new MabaniAuthStack(...);
const backendStack = new MabaniBackendStack(...);
const frontendStack = new MabaniFrontendStack(...);

// Set dependencies
backendStack.addDependency(authStack);
// Frontend is independent, no dependency needed
```

---

## Cost Optimization Through Stack Separation

### Scenario 1: Development Environment

```bash
# Destroy everything except auth (keep user data)
cdk destroy MabaniFrontendStack-dev
cdk destroy MabaniBackendStack-dev
cdk destroy MabaniDatabaseStack-dev
# AuthStack stays (preserves users, saves ~$0.05/day)
```

### Scenario 2: Frontend Rebuild

```bash
# Only update frontend, nothing else affected
cdk deploy MabaniFrontendStack-dev
# No impact on Lambda cold starts, no DB disruption
```

---

## Anti-Patterns to Avoid

### ❌ **Don't Do This**:

1. **One Giant Stack**:

   - All resources in one stack
   - **Problem**: Deploy everything for any change

2. **Too Many Small Stacks**:

   - One stack per resource
   - **Problem**: Over-complicated, hard to manage

3. **Cross-Cutting Concerns**:

   - Mixing concerns (e.g., Lambda in FrontendStack)
   - **Problem**: Unclear ownership, deployment issues

4. **Circular Dependencies**:

   - Stack A depends on Stack B, Stack B depends on Stack A
   - **Problem**: Can't deploy, deadlock

5. **Resource Per Stack**:
   - Each Lambda function in its own stack
   - **Problem**: Too granular, unnecessary complexity

---

## Migration Strategy

### If Starting Fresh:

Start with **2-3 stacks** (Auth, Frontend, Backend). Add more as needed.

### If Already Deployed:

1. Create new stack
2. Move resources gradually
3. Update imports/references
4. Test thoroughly
5. Remove from old stack

### Best Practice:

Use CloudFormation exports/imports for cross-stack references:

```typescript
// AuthStack exports
new cdk.CfnOutput(this, "UserPoolId", {
  value: userPool.userPoolId,
  exportName: "MabaniUserPoolId", // Unique export name
});

// BackendStack imports
const userPoolId = cdk.Fn.importValue("MabaniUserPoolId");
```

---

## Summary: Quick Decision Tree

```
Q: Does it change with other resources?
├─ Yes → Same stack
└─ No → Continue

Q: Is it managed by different team?
├─ Yes → Different stack
└─ No → Continue

Q: Does it need to be shared across services?
├─ Yes → Separate shared stack
└─ No → Continue

Q: Does it have different lifecycle (rarely vs frequently)?
├─ Yes → Different stack
└─ No → Same stack
```

---

## Your Specific Case: Final Recommendation

### Start with **3 Stacks**:

1. **AuthStack** - Cognito (changes rarely)
2. **FrontendStack** - S3 + CloudFront (changes frequently)
3. **BackendStack** - Lambda + API Gateway + DynamoDB (changes frequently)

### Later, Consider Adding:

4. **SharedStack** - If DynamoDB becomes shared, or add VPC

### Key Benefits:

- ✅ Fast frontend deployments (don't touch backend)
- ✅ Fast backend deployments (don't touch frontend)
- ✅ Auth changes don't affect running services
- ✅ Clear ownership and responsibility
- ✅ Cost optimization (can destroy/recreate independently)
