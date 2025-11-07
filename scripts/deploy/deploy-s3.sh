#!/bin/bash

# S3 deployment script for frontend
# Usage: ./deploy-s3.sh [environment]

set -e

ENVIRONMENT=${1:-dev}
AWS_PROFILE="mia40"
AWS_REGION="eu-west-1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_info "Deploying frontend to S3..."

cd "$PROJECT_ROOT/frontend"

# Build React app
log_info "Building React app..."
npm run build

# Get S3 bucket name from CloudFormation
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name MabaniFrontendStack \
    --profile $AWS_PROFILE \
    --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
    --output text)

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
    log_error "Could not find S3 bucket name. Make sure infrastructure is deployed."
    exit 1
fi

log_info "Uploading to S3 bucket: $BUCKET_NAME"

# Upload to S3
aws s3 sync dist/ s3://$BUCKET_NAME \
    --profile $AWS_PROFILE \
    --delete \
    --cache-control "public, max-age=31536000" \
    --exclude "*.html" \
    --exclude "*.json"

# Upload HTML files with no-cache
aws s3 sync dist/ s3://$BUCKET_NAME \
    --profile $AWS_PROFILE \
    --delete \
    --cache-control "no-cache" \
    --include "*.html" \
    --include "*.json"

# Invalidate CloudFront cache
log_info "Invalidating CloudFront cache..."
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name MabaniFrontendStack \
    --profile $AWS_PROFILE \
    --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
    --output text)

aws cloudfront create-invalidation \
    --distribution-id $DISTRIBUTION_ID \
    --paths "/*" \
    --profile $AWS_PROFILE

log_success "Frontend deployed successfully to S3 and CloudFront cache invalidated"
