# Testing with Deployed AWS API

## ✅ Setup Complete

I've configured your frontend to use the deployed AWS Lambda functions instead of local development.

## Configuration

Created `.env.local` in the frontend directory:

```env
VITE_API_BASE_URL=https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev
```

## Next Steps

1. **Restart your frontend dev server** (if it's running):

   ```bash
   cd frontend
   # Stop the current server (Ctrl+C)
   npm run dev
   ```

2. **Sign in to your frontend** - Your Cognito authentication should work as before

3. **Test the Knowledge Base feature**:
   - Navigate to "Knowledge Base" in the menu
   - Try creating a new knowledge base
   - Upload documents
   - Query the knowledge base

## API Endpoint

All API calls will now go to:

```
https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev
```

## Benefits

✅ **No serverless-offline issues** - Uses real AWS Lambda  
✅ **Python 3.13 works perfectly** - AWS fully supports it  
✅ **Real environment** - Tests against actual infrastructure  
✅ **Production-like testing** - Same environment as production

## Switching Back to Local

To switch back to local development later:

1. Edit `.env.local` in the frontend directory:

   ```env
   VITE_API_BASE_URL=http://localhost:3001
   ```

2. Make sure your local server is running:

   ```bash
   cd backend
   ./local-server.sh
   ```

3. Restart your frontend

## Verify It's Working

Check your browser's Network tab - API requests should go to:

- ✅ `https://z83ea8fx85.execute-api.eu-west-1.amazonaws.com/dev/...`
- ❌ NOT `http://localhost:3001/...`

## All Deployed Resources

Your deployed infrastructure includes:

- ✅ DynamoDB tables (knowledge-bases, documents)
- ✅ S3 bucket (for documents and FAISS indexes)
- ✅ SQS queues (for indexing)
- ✅ 10 Lambda functions (all working with Python 3.13)
- ✅ API Gateway endpoint

Everything is ready to test! 🚀
