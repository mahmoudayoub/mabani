#!/bin/bash

# Single Lambda deployment script for Python
# Usage: ./deploy-single-lambda.sh [function-name] [environment]

set -e

FUNCTION_NAME=${1}
ENVIRONMENT=${2:-dev}
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

if [ -z "$FUNCTION_NAME" ]; then
    log_error "Function name is required"
    echo "Usage: $0 <function-name> [environment]"
    echo "Available functions: healthCheck, getUserProfile, updateUserProfile, createItem, getUserItems, updateItem, deleteItem"
    exit 1
fi

log_info "Deploying single Lambda function: $FUNCTION_NAME"

cd "$PROJECT_ROOT/backend"

# Deploy specific function
log_info "Deploying function $FUNCTION_NAME..."
npx serverless deploy function --function $FUNCTION_NAME --stage $ENVIRONMENT --profile $AWS_PROFILE

log_success "Function $FUNCTION_NAME deployed successfully"
