#!/bin/bash

# Local Development Server Startup Script
# This script starts the serverless-offline local development server

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  TaskFlow Backend - Local Dev Server  ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if .env.local exists
if [ ! -f .env.local ]; then
    echo -e "${YELLOW}Warning: .env.local not found. Using default environment variables.${NC}"
else
    echo -e "${GREEN}✓ Loading environment from .env.local${NC}"
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# Set dummy Cognito User Pool ARN for local development if not set
if [ -z "$COGNITO_USER_POOL_ARN" ]; then
    export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:000000000000:userpool/eu-west-1_local"
    echo -e "${YELLOW}Using dummy COGNITO_USER_POOL_ARN for local development${NC}"
fi

# Set INDEXING_QUEUE_URL for local development (serverless-offline can't resolve Ref)
if [ -z "$INDEXING_QUEUE_URL" ]; then
    export INDEXING_QUEUE_URL="https://sqs.eu-west-1.amazonaws.com/239146712026/taskflow-backend-dev-kb-indexing"
    echo -e "${YELLOW}Using INDEXING_QUEUE_URL for local development${NC}"
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing npm dependencies...${NC}"
    npm install
fi

# Check if Python dependencies are installed
echo -e "${GREEN}✓ Checking Python dependencies...${NC}"
pip list | grep -q boto3 || echo -e "${YELLOW}Warning: boto3 not found. Run: pip install -r requirements.txt${NC}"

echo ""
echo -e "${GREEN}Starting local development server...${NC}"
echo -e "${BLUE}API will be available at: http://localhost:3001${NC}"
echo ""
echo -e "${GREEN}Available Knowledge Base Endpoints:${NC}"
echo -e "  GET    /knowledge-bases                           - List KBs"
echo -e "  POST   /knowledge-bases                           - Create KB"
echo -e "  GET    /knowledge-bases/{kbId}                    - Get KB"
echo -e "  PUT    /knowledge-bases/{kbId}                    - Update KB"
echo -e "  DELETE /knowledge-bases/{kbId}                    - Delete KB"
echo -e "  POST   /knowledge-bases/{kbId}/upload-url         - Get upload URL"
echo -e "  POST   /knowledge-bases/{kbId}/documents          - Confirm document"
echo -e "  GET    /knowledge-bases/{kbId}/documents          - List documents"
echo -e "  DELETE /knowledge-bases/{kbId}/documents/{docId}  - Delete document"
echo -e "  POST   /knowledge-bases/{kbId}/query              - Query KB (RAG)"
echo ""
echo -e "${GREEN}Other Endpoints:${NC}"
echo -e "  GET    /health                                    - Health check"
echo -e "  GET    /profile                                   - Get user profile"
echo -e "  PUT    /profile                                   - Update profile"
echo -e "  POST   /items                                     - Create item"
echo -e "  GET    /items                                     - List items"
echo -e "  PUT    /items/{itemId}                            - Update item"
echo -e "  DELETE /items/{itemId}                            - Delete item"
echo -e "  POST   /webhook/twilio                            - Twilio webhook"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Start serverless offline
npm run dev

