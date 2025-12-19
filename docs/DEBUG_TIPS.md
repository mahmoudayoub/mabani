# Debugging 502 Bad Gateway Error

## Common Causes

The 502 error means the Lambda function is crashing. Here are the most common causes:

### 1. Missing Authorization Header

When testing from the frontend, ensure you're sending the JWT token:

```typescript
// Frontend should include this:
headers: {
  'Authorization': `Bearer ${idToken}`,
  'Content-Type': 'application/json'
}
```

### 2. Check Server Logs

Look at the terminal where you ran `./local-server.sh`. The actual error will be printed there.

### 3. Test Health Endpoint First

```bash
curl http://localhost:3001/health
```

If this works, the server is running correctly.

### 4. Test with a JWT Token

Get your JWT token from the browser:

1. Open DevTools → Application → Local Storage
2. Find `CognitoIdentityServiceProvider.*.idToken`
3. Copy the token value
4. Test with curl:

```bash
curl -X GET http://localhost:3001/knowledge-bases \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

### 5. Common Error Messages

**If you see "Unauthorized":**

- Missing or invalid JWT token
- Token expired

**If you see "500 Internal Server Error":**

- Check server logs for Python import errors
- Missing environment variables
- AWS credentials issue

**If you see "502 Bad Gateway":**

- Lambda function crashed
- Check server logs for Python traceback
- Missing Python dependencies

### 6. Check Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 7. Check Environment Variables

Ensure these are set:

- `KB_TABLE_NAME`
- `DOCS_TABLE_NAME`
- `KB_BUCKET_NAME`
- `COGNITO_USER_POOL_ARN` (can be dummy for local)

### 8. Check AWS Credentials

```bash
aws sts get-caller-identity --profile mia40
```

## Quick Fixes

### Option 1: Get JWT Token from Frontend

1. Run frontend: `cd frontend && npm run dev`
2. Sign in
3. Open DevTools → Console
4. Run: `localStorage.getItem(Object.keys(localStorage).find(k => k.includes('idToken')))`
5. Copy the token
6. Use it in your API calls

### Option 2: Mock User ID for Local Dev

If you want to bypass auth temporarily, you can modify the Lambda handler to accept a mock user in local dev mode. However, this is not recommended for production.

## Getting Help

1. Check the server terminal logs - they show the actual error
2. Check browser console for network errors
3. Verify your JWT token is valid
4. Ensure all dependencies are installed
