#!/bin/bash

# Deployment Configuration
# Source this file before deploying: source deployment.config.sh

export COGNITO_USER_POOL_ARN="arn:aws:cognito-idp:eu-west-1:239146712026:userpool/eu-west-1_fZsyfIo0M"
export AWS_PROFILE="mia40"
export AWS_REGION="eu-west-1"
export STAGE="dev"

echo "✅ Deployment configuration loaded"

