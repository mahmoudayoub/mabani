# Switch Frontend to Use Deployed AWS Functions

## Quick Setup

The frontend is already configured to use environment variables. Here's how to switch to the deployed AWS API:

## Option 1: Create .env file (Recommended)

1. **Create `.env` file in the frontend directory**:

   ```bash
   cd frontend
   ```

2. **Copy the example and update**:

   ```bash
   cp ../env.example .env
   ```

3. **Set the API base URL** in `.env`:

   ```env
   VITE_API_BASE_URL=https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev
   ```

4. **Restart your frontend dev server**:
   ```bash
   npm run dev
   ```

## Option 2: Use .env.development (Already Created)

I've created `.env.development` which sets the AWS API URL.

**Vite automatically loads `.env.development` in development mode**, so just restart your frontend:

```bash
cd frontend
npm run dev
```

## Verify It's Working

1. Open your browser console
2. Check the network tab - API calls should go to:
   `https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev/...`

3. Test creating a knowledge base - it should work!

## Deployed API Endpoint

```
https://j8r5sar4mf.execute-api.eu-west-1.amazonaws.com/dev
```

## Switching Back to Local

To switch back to local development later:

1. Change `.env` or `.env.development`:

   ```env
   VITE_API_BASE_URL=http://localhost:3001
   ```

2. Restart the frontend dev server

## Benefits of Using Deployed API

✅ **No serverless-offline issues** - Uses real AWS Lambda  
✅ **Python 3.13 works perfectly** - AWS fully supports it  
✅ **Real environment** - Tests against actual deployed infrastructure  
✅ **No Docker needed** - Everything runs in AWS

## Note

Your deployed functions are already using Python 3.13 and working perfectly in AWS. This is actually the best way to test!
