#!/bin/bash

# Deployment script with layer syncing
# This script syncs layers from source and then deploys the service

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  TaskFlow Backend - Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Load environment variables from deployment.config.sh or .env.local
if [ -f deployment.config.sh ]; then
    echo -e "${GREEN}✓ Loading environment from deployment.config.sh${NC}"
    source deployment.config.sh
elif [ -f .env.local ]; then
    echo -e "${GREEN}✓ Loading environment from .env.local${NC}"
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# Check required environment variables
if [ -z "$COGNITO_USER_POOL_ARN" ]; then
    echo -e "${YELLOW}COGNITO_USER_POOL_ARN not set, using default...${NC}"
    export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"
fi

echo -e "${GREEN}✓ COGNITO_USER_POOL_ARN: ${COGNITO_USER_POOL_ARN}${NC}"
echo ""

# Set stage
STAGE=${STAGE:-dev}
echo -e "${BLUE}Deploying to stage: ${STAGE}${NC}"
echo ""

# Step 1: Sync layers from source
echo -e "${YELLOW}Step 1: Syncing layers from source...${NC}"
if [ -f layers/sync-from-source.sh ]; then
    ./layers/sync-from-source.sh
    echo -e "${GREEN}✓ Layers synced${NC}"
else
    echo -e "${RED}✗ Error: layers/sync-from-source.sh not found${NC}"
    exit 1
fi
echo ""

# Step 2: Deploy with verbose logging
echo -e "${YELLOW}Step 2: Deploying serverless functions...${NC}"
echo -e "${YELLOW}This will take 5-10 minutes. Watch for any errors below.${NC}"
echo ""
echo "========================================"
echo ""

npx serverless deploy --stage $STAGE --verbose

echo ""
echo "========================================"
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo -e "  - Stage: ${STAGE}"
echo -e "  - Layers synced from lambdas/shared/"
echo -e "  - All Lambda functions deployed"
echo ""

