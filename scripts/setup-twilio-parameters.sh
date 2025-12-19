#!/bin/bash

# Script to set up Twilio credentials in AWS Systems Manager Parameter Store
# Usage: ./setup-twilio-parameters.sh [environment]

set -e

ENVIRONMENT=${1:-dev}
AWS_PROFILE="mia40"
AWS_REGION="eu-west-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up Twilio credentials in Parameter Store${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

# Prompt for Twilio credentials
echo -e "${YELLOW}Please provide your Twilio credentials:${NC}"
echo ""

read -p "Twilio Account SID: " ACCOUNT_SID
read -sp "Twilio Auth Token: " AUTH_TOKEN
echo ""
read -p "Twilio WhatsApp Number (e.g., whatsapp:+14155238886): " WHATSAPP_NUMBER
echo ""

# Validate inputs
if [ -z "$ACCOUNT_SID" ] || [ -z "$AUTH_TOKEN" ] || [ -z "$WHATSAPP_NUMBER" ]; then
    echo -e "${RED}Error: All fields are required${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Creating parameters in Parameter Store...${NC}"

# Create parameters (using SecureString for sensitive data)
aws ssm put-parameter \
    --name "/mabani/twilio/account_sid" \
    --value "$ACCOUNT_SID" \
    --type "String" \
    --description "Twilio Account SID for Mabani WhatsApp integration" \
    --profile $AWS_PROFILE \
    --region $AWS_REGION \
    --overwrite \
    2>/dev/null && echo -e "${GREEN}✓${NC} Created account_sid" || echo -e "${RED}✗${NC} Failed to create account_sid"

aws ssm put-parameter \
    --name "/mabani/twilio/auth_token" \
    --value "$AUTH_TOKEN" \
    --type "SecureString" \
    --description "Twilio Auth Token for Mabani WhatsApp integration (encrypted)" \
    --profile $AWS_PROFILE \
    --region $AWS_REGION \
    --overwrite \
    2>/dev/null && echo -e "${GREEN}✓${NC} Created auth_token (encrypted)" || echo -e "${RED}✗${NC} Failed to create auth_token"

aws ssm put-parameter \
    --name "/mabani/twilio/whatsapp_number" \
    --value "$WHATSAPP_NUMBER" \
    --type "String" \
    --description "Twilio WhatsApp sandbox number for Mabani" \
    --profile $AWS_PROFILE \
    --region $AWS_REGION \
    --overwrite \
    2>/dev/null && echo -e "${GREEN}✓${NC} Created whatsapp_number" || echo -e "${RED}✗${NC} Failed to create whatsapp_number"

echo ""
echo -e "${GREEN}✓ Twilio parameters created successfully!${NC}"
echo ""
echo "Parameters created at path: /mabani/twilio/"
echo ""
echo "To verify, run:"
echo "  aws ssm get-parameters-by-path --path /mabani/twilio --with-decryption --profile $AWS_PROFILE --region $AWS_REGION"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Deploy the Lambda function:"
echo "   cd backend && npx serverless deploy --stage $ENVIRONMENT --profile $AWS_PROFILE"
echo ""
echo "2. Test the webhook by sending a WhatsApp message with an image"

