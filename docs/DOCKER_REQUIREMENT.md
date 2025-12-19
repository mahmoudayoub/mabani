# Docker Requirement for Local Development

## Why Docker?

Since `serverless-offline` doesn't support Python 3.13 yet, we're using Docker mode to bypass this limitation.

## Requirements

1. **Install Docker Desktop** (if not already installed):

   - macOS: Download from https://www.docker.com/products/docker-desktop/
   - Or use Homebrew: `brew install --cask docker`

2. **Start Docker Desktop**:

   - Make sure Docker Desktop is running before starting the server

3. **Verify Docker is working**:
   ```bash
   docker --version
   docker ps
   ```

## Starting the Server

Once Docker is running:

```bash
cd backend
./local-server.sh
```

The first time will be slower as Docker images are downloaded, but subsequent starts will be faster.

## If You Don't Want to Use Docker

Alternative: Test against deployed AWS functions instead of local dev. Deploy first, then point your frontend to the AWS API Gateway URL instead of localhost:3001.
