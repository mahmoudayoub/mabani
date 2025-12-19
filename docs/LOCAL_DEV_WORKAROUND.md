# Local Development Workaround for Python 3.13

## Problem

`serverless-offline` doesn't officially support Python 3.12 or 3.13 yet, causing "Unsupported runtime" errors.

## Solution: Use Docker Mode

We've configured serverless-offline to use Docker, which bypasses the Python runtime version check.

## Configuration

Changed in `serverless.yml`:

```yaml
serverless-offline:
  useDocker: true # Use Docker to bypass runtime version checks
```

## Prerequisites

**Docker must be installed and running**:

1. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Start Docker Desktop
3. Verify it's working:
   ```bash
   docker --version
   docker ps
   ```

## How It Works

When `useDocker: true`, serverless-offline runs Python Lambda functions inside Docker containers, which allows it to use any Python version (including 3.13) without checking against the supported runtime list.

## Starting the Server

```bash
cd backend
./local-server.sh
```

**Note**: The first run will be slower as Docker downloads images, but subsequent runs will be faster.

## Testing

After starting the server:

```bash
# Test health endpoint
curl http://localhost:3001/health

# Test knowledge bases (with JWT token)
curl http://localhost:3001/knowledge-bases \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## If You Don't Have Docker

**Alternative**: Test against deployed AWS functions instead:

1. Deploy to AWS (Python 3.13 works fine in AWS)
2. Update frontend API base URL to point to AWS API Gateway
3. Test against production endpoints

## Reverting Python 3.13

✅ **Done!** Runtime is back to `python3.13` in serverless.yml

AWS Lambda fully supports Python 3.13, so deployed functions will work perfectly. The Docker workaround is only needed for local development.
