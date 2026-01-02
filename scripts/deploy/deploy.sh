#!/bin/bash

# Deployment script for Mabani serverless application
# Usage: ./deploy.sh [environment] [component]
# Example: ./deploy.sh dev all
# Example: ./deploy.sh prod frontend

set -e

# Configuration
ENVIRONMENT=${1:-dev}
COMPONENT=${2:-all}
if [ -n "$CI" ]; then
    PROFILE_ARG=""
else
    PROFILE_ARG="--profile mia40"
    export AWS_PROFILE="mia40"
fi
AWS_REGION="eu-west-1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYENV_VERSION=3.11.11

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed and configured
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi

    if ! aws sts get-caller-identity $PROFILE_ARG &> /dev/null; then
        log_error "AWS CLI to communicate with AWS (Caller Identity Check Failed)"
        exit 1
    fi

    log_success "AWS CLI is configured correctly"
}

# Deploy infrastructure (Cognito + S3 + CloudFront)
deploy_infrastructure() {
    log_info "Deploying infrastructure..."
    
    cd "$PROJECT_ROOT/infrastructure"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing infrastructure dependencies..."
        npm install
    fi
    
    # Bootstrap CDK if needed
    log_info "Bootstrapping CDK..."
    npx cdk bootstrap $PROFILE_ARG
    
    # Deploy stacks
    log_info "Deploying Cognito stack..."
    npx cdk deploy MabaniCognitoStack-$ENVIRONMENT $PROFILE_ARG --require-approval never
    
    log_info "Deploying Frontend stack..."
    npx cdk deploy MabaniGeneralStack-$ENVIRONMENT $PROFILE_ARG --require-approval never
    
    log_success "Infrastructure deployment completed"
}

# Deploy backend (Lambda functions)
deploy_backend() {
    log_info "Deploying backend..."
    
    cd "$PROJECT_ROOT/backend"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing backend dependencies..."
        npm install
    fi
    
    # Install Python dependencies
    if [ ! -d "venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    log_info "Installing Python dependencies..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Fetch Cognito User Pool ARN
    log_info "Fetching Cognito User Pool ARN..."
    export COGNITO_USER_POOL_ARN=$(aws cloudformation describe-stacks \
        --stack-name MabaniCognitoStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolArn`].OutputValue' \
        --output text)
    
    log_info "Using Cognito User Pool ARN: $COGNITO_USER_POOL_ARN"

    # Deploy with Serverless Framework
    log_info "Deploying Lambda functions..."
    npx serverless deploy --stage $ENVIRONMENT
    
    log_success "Backend deployment completed"
}

# Deploy frontend (React app)
deploy_frontend() {
    log_info "Deploying frontend..."
    
    cd "$PROJECT_ROOT/frontend"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing frontend dependencies..."
        npm install
    fi
    
    # Build React app
    log_info "Building React app..."
    npm run build
    
    # Upload to S3
    log_info "Uploading to S3..."
    aws s3 sync dist/ s3://$(aws cloudformation describe-stacks \
        --stack-name MabaniGeneralStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
        --output text) \
        $PROFILE_ARG \
        --delete
    
    # Invalidate CloudFront cache
    log_info "Invalidating CloudFront cache..."
    DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
        --stack-name MabaniGeneralStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
        --output text)
    
    aws cloudfront create-invalidation \
        --distribution-id $DISTRIBUTION_ID \
        --paths "/*" \
        $PROFILE_ARG
    
    log_success "Frontend deployment completed"
}

# Update environment variables
update_env_vars() {
    log_info "Updating environment variables..."
    
    # Get Cognito outputs
    USER_POOL_ID=$(aws cloudformation describe-stacks \
        --stack-name MabaniCognitoStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
        --output text)
    
    USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
        --stack-name MabaniCognitoStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
        --output text)
    
    USER_POOL_ARN=$(aws cloudformation describe-stacks \
        --stack-name MabaniCognitoStack-$ENVIRONMENT \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolArn`].OutputValue' \
        --output text)
    
    # Get API Gateway URL
    API_URL=$(aws apigateway get-rest-apis \
        --region $AWS_REGION \
        $PROFILE_ARG \
        --query "items[?name=='${ENVIRONMENT}-taskflow-backend'].id" \
        --output text)
    
    API_URL="https://${API_URL}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}"
    
    # Update frontend .env file
    cat > "$PROJECT_ROOT/frontend/.env" << EOF
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID
VITE_COGNITO_REGION=$AWS_REGION
VITE_API_BASE_URL=$API_URL
EOF
    
    log_success "Environment variables updated"
}

# Main deployment logic
main() {
    log_info "Starting deployment for environment: $ENVIRONMENT, component: $COMPONENT"
    
    check_aws_cli
    
    case $COMPONENT in
        "infra"|"infrastructure")
            deploy_infrastructure
            ;;
        "backend"|"api")
            deploy_backend
            ;;
        "frontend"|"web")
            deploy_frontend
            ;;
        "config"|"env")
            update_env_vars
            ;;
        "all")
            deploy_infrastructure
            deploy_backend
            update_env_vars
            deploy_frontend
            ;;
        *)
            log_error "Invalid component: $COMPONENT"
            log_info "Valid components: infra, backend, frontend, config, all"
            exit 1
            ;;
    esac
    
    log_success "Deployment completed successfully!"
    
    # Show useful URLs
    if [ "$COMPONENT" = "all" ] || [ "$COMPONENT" = "frontend" ]; then
        WEBSITE_URL=$(aws cloudformation describe-stacks \
            --stack-name MabaniGeneralStack-$ENVIRONMENT \
            --region $AWS_REGION \
            $PROFILE_ARG \
            --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' \
            --output text)
        log_info "Website URL: $WEBSITE_URL"
    fi
}

# Run main function
main "$@"
