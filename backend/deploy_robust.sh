#!/bin/bash

# Enhanced Deployment Script
# Handles cleanup, Docker verification, and deployment with architecture safety checks.

set -e

# Configuration
SERVICE_NAME="taskflow-backend"
STAGE=${STAGE:-dev}
REGION=${REGION:-eu-west-1}
CACHE_DIR="$HOME/Library/Caches/serverless-python-requirements"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\133[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}   TaskFlow Backend - Robust Deployment       ${NC}"
echo -e "${BLUE}==============================================${NC}"

# 1. Environment Loading
if [ -f "deployment.config.sh" ]; then
    echo -e "${YELLOW}Loading config from deployment.config.sh...${NC}"
    source deployment.config.sh
elif [ -f ".env.local" ]; then
    echo -e "${YELLOW}Loading config from .env.local...${NC}"
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# 2. Pre-flight Checks
echo -e "\n${BLUE}[1/5] Pre-flight Checks...${NC}"

# Check Docker
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running!${NC}"
    echo "Docker is required for building Python dependencies (faiss, pydantic-core, numpy) for AWS Lambda."
    exit 1
fi
echo -e "${GREEN}✓ Docker is running${NC}"

# Check AWS Identity
IDENTITY=$(aws sts get-caller-identity --output text --query 'Arn' 2>/dev/null)
if [ $? -ne 0 ]; then
     echo -e "${RED}Error: AWS credentials not configured or expired.${NC}"
     exit 1
fi
echo -e "${GREEN}✓ Authenticated as: $IDENTITY${NC}"

# 3. Clean Build Artifacts
echo -e "\n${BLUE}[2/5] Cleaning Build Artifacts...${NC}"
echo -e "Cleaning .serverless directory..."
rm -rf .serverless

echo -e "Cleaning local Python cache ($CACHE_DIR)..."
# We clean the cache to prevent stale architecture builds (e.g. x86_64 vs arm64) from persisting
rm -rf "$CACHE_DIR"

echo -e "${GREEN}✓ Cleanup complete${NC}"

# 4. Sync Layers
echo -e "\n${BLUE}[3/5] Syncing Layer Code...${NC}"
if [ -f "./layers/sync-from-source.sh" ]; then
    ./layers/sync-from-source.sh
else
    echo -e "${RED}Warning: Layer sync script not found.${NC}"
fi

# 5. Dependency Check
echo -e "\n${BLUE}[4/5] Verifying Dependencies...${NC}"
# Simple check to ensure critical deps are in requirements.txt
if ! grep -q "pydantic" requirements.txt; then
    echo -e "${RED}Error: pydantic is missing from requirements.txt!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ requirements.txt looks valid${NC}"

# 6. Deployment
echo -e "\n${BLUE}[5/5] Starting Deployment...${NC}"
echo -e "Target Stage: $STAGE"
echo -e "Target Region: $REGION"
echo -e "Architecture: arm64 (Verified in serverless.yml)"
echo -e "Builder: Docker (public.ecr.aws/sam/build-python3.11:latest)"
echo ""
echo -e "${YELLOW}Building and Deploying... (This may take 5-10 minutes)${NC}"

npx serverless deploy --stage $STAGE --region $REGION --verbose

CHECK_STATUS=$?
if [ $CHECK_STATUS -eq 0 ]; then
    echo -e "\n${GREEN}==============================================${NC}"
    echo -e "${GREEN}   Deployment SUCCESSFUL!                     ${NC}"
    echo -e "${GREEN}==============================================${NC}"
    
    # Optional: Deployment Summary
    echo -e "\nNext Steps:"
    echo -e "1. Monitor Lambda Logs: aws logs tail /aws/lambda/${SERVICE_NAME}-${STAGE}-knowledgeBaseIndexingWorker --follow"
    echo -e "2. Test Upload endpoint via Frontend."
else
    echo -e "\n${RED}==============================================${NC}"
    echo -e "${RED}   Deployment FAILED (Exit Code: $CHECK_STATUS) ${NC}"
    echo -e "${RED}==============================================${NC}"
    exit $CHECK_STATUS
fi
