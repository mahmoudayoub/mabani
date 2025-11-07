# Stack Architecture Decision: Multiple Stacks vs Single Stack

## Current Architecture: **Multiple Stacks** (2 stacks)

### Stack 1: `TaskFlowCognitoStack`

- Cognito User Pool
- Cognito User Pool Client

### Stack 2: `TaskFlowFrontendStack`

- S3 Bucket (frontend hosting)
- CloudFront Distribution
- Origin Access Control (OAC)
- IAM Policies

---

## Comparison: Multiple Stacks vs Single Stack

### ✅ **Advantages of Multiple Stacks** (Current Approach)

#### 1. **Independent Deployment & Lifecycle Management**

- Deploy Cognito once, then update frontend separately
- Cognito changes rarely; frontend changes frequently
- Faster deployments (only deploy what changed)

#### 2. **Clear Separation of Concerns**

- **Cognito Stack**: Authentication infrastructure (long-lived)
- **Frontend Stack**: Application hosting (frequently updated)
- Easier to understand what each stack does

#### 3. **Granular Access Control**

- Different team members can have permissions for different stacks
- Frontend team can deploy frontend without touching auth
- Security team can manage Cognito separately

#### 4. **Easier Rollback**

- If frontend deployment fails, Cognito stays intact
- Can rollback just the frontend stack independently
- Reduces blast radius of failures

#### 5. **Cross-Stack Reusability**

- Cognito stack outputs can be used by other stacks
- Frontend can reference Cognito via CloudFormation exports
- Backend stack can also reference Cognito outputs

#### 6. **Cost Optimization**

- Can delete/destroy frontend stack without affecting Cognito
- Useful for development environments
- Cognito stack retained, frontend can be recreated

#### 7. **Testing & Development**

- Easier to test individual components
- Can deploy only what's needed for testing
- Faster iteration cycles

### ❌ **Disadvantages of Multiple Stacks**

#### 1. **More Complex Initial Setup**

- Need to manage dependencies between stacks
- More files to maintain (`app.ts` orchestrates both)

#### 2. **Cross-Stack Dependencies**

- Frontend stack depends on Cognito stack
- Must deploy in correct order
- If Cognito stack fails, frontend deployment waits

#### 3. **Slightly More CloudFormation Stacks**

- Two stacks in CloudFormation console
- More stacks to monitor (though still manageable)

#### 4. **Deployment Scripts**

- Need to ensure deployment order
- Scripts must handle dependencies correctly

---

## 🔄 **Alternative: Single Stack**

### ✅ **Advantages of Single Stack**

#### 1. **Simpler Initial Setup**

- Everything in one place
- One deployment command
- No dependency management needed

#### 2. **Atomic Operations**

- All resources deployed together
- All or nothing - easier to reason about
- Single rollback point

#### 3. **Fewer Stack Resources**

- One CloudFormation stack to monitor
- Simpler in AWS Console

#### 4. **Easier Cross-Reference**

- Direct property references (no exports/imports)
- Simpler code (no `CfnOutput` needed)

### ❌ **Disadvantages of Single Stack**

#### 1. **Slower Deployments**

- Must deploy everything even if only one resource changed
- Frontend change requires full stack update
- Longer wait times

#### 2. **Larger Blast Radius**

- Single point of failure
- If one resource fails, entire stack fails
- Harder to isolate issues

#### 3. **Less Flexible Lifecycle Management**

- Can't easily delete/recreate frontend without affecting Cognito
- Must maintain all resources together
- Harder to optimize costs per component

#### 4. **Tighter Coupling**

- All resources tied together
- Harder to give different teams different permissions
- Changes require full stack deployment

#### 5. **Harder to Reuse**

- Cognito can't be easily shared with other applications
- Everything bundled together
- Less modular

---

## 📊 **Recommendation: Keep Multiple Stacks**

For this project, **multiple stacks is the better choice** because:

1. **Different Update Frequencies**:

   - Cognito changes rarely (auth config)
   - Frontend changes frequently (new builds)

2. **Team Separation**:

   - Backend/infrastructure team manages Cognito
   - Frontend team manages frontend stack

3. **Cost Efficiency**:

   - Can destroy/recreate frontend in dev environments
   - Cognito remains persistent (user data)

4. **Scalability**:

   - As project grows, you may add more stacks
   - Backend stack (Lambda/API Gateway) can reference Cognito
   - Each component independently manageable

5. **Best Practice**:
   - AWS recommends separating by lifecycle and ownership
   - Matches AWS Well-Architected Framework principles

---

## 🎯 **When to Use Single Stack**

Consider a single stack if:

- Very small project (< 5 resources)
- All resources change together
- Single team owns everything
- Prototype/MVP stage
- Resources have identical lifecycle

---

## 📝 **Current Simplified Stack Summary**

### Removed (Cost Reduction):

- ❌ CloudWatch Log Group (Cognito) - saves ~$0.50/GB/month
- ❌ MFA configuration - saves SMS costs
- ❌ Device tracking - reduces Cognito compute
- ❌ Access log bucket - saves S3 storage costs
- ❌ S3 versioning (non-prod) - saves storage costs
- ❌ S3 lifecycle policies - complexity reduction
- ❌ CloudFront access logging - saves S3 storage
- ❌ Complex security headers (CSP, Frame Options) - reduces complexity

### Kept (Essential):

- ✅ S3 encryption (free)
- ✅ HTTPS enforcement (free)
- ✅ HSTS header (free, security)
- ✅ Public access blocked (free, security)
- ✅ Password policy (free, security)
- ✅ Email verification (free)

### Cost Impact:

- **Before**: ~$5-10/month (with logging, MFA potential costs)
- **After**: ~$1-3/month (minimal - mostly free tier)
- **Savings**: ~70-80% cost reduction

---

## 🚀 **Deployment**

With multiple stacks:

```bash
# Deploy Cognito first (one-time or rare)
cdk deploy MabaniCognitoStack-dev

# Deploy frontend (frequent)
cdk deploy MabaniFrontendStack-dev

# Or deploy both (respects dependencies)
cdk deploy --all
```

The dependency ensures Cognito is created before Frontend tries to use it.
