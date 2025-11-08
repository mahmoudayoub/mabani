#!/bin/bash

# Setup script for H&S + Quality Report Processing System
# This script helps configure AWS resources for the first deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}H&S + Quality Report Processing - Setup${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ AWS CLI installed${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Node.js installed ($(node --version))${NC}"

# Check Serverless
if ! command -v serverless &> /dev/null; then
    echo -e "${YELLOW}⚠ Serverless Framework not found. Installing...${NC}"
    npm install -g serverless
fi
echo -e "${GREEN}✓ Serverless Framework installed${NC}"

# Get configuration
echo ""
echo -e "${YELLOW}Configuration:${NC}"
read -p "AWS Region [eu-west-1]: " AWS_REGION
AWS_REGION=${AWS_REGION:-eu-west-1}

read -p "AWS Profile [mia40]: " AWS_PROFILE
AWS_PROFILE=${AWS_PROFILE:-mia40}

read -p "Environment (dev/staging/prod) [dev]: " ENVIRONMENT
ENVIRONMENT=${ENVIRONMENT:-dev}

echo ""
echo -e "${YELLOW}Twilio Configuration:${NC}"
read -p "Twilio Account SID: " TWILIO_ACCOUNT_SID
read -s -p "Twilio Auth Token: " TWILIO_AUTH_TOKEN
echo ""
read -p "Twilio WhatsApp Number (e.g., whatsapp:+14155238886): " TWILIO_WHATSAPP_NUMBER

# Validate inputs
if [ -z "$TWILIO_ACCOUNT_SID" ] || [ -z "$TWILIO_AUTH_TOKEN" ] || [ -z "$TWILIO_WHATSAPP_NUMBER" ]; then
    echo -e "${RED}❌ Missing required Twilio configuration${NC}"
    exit 1
fi

# Create Secrets Manager secret
echo ""
echo -e "${YELLOW}Creating Secrets Manager secret...${NC}"

SECRET_STRING=$(cat <<EOF
{
  "account_sid": "$TWILIO_ACCOUNT_SID",
  "auth_token": "$TWILIO_AUTH_TOKEN",
  "whatsapp_number": "$TWILIO_WHATSAPP_NUMBER"
}
EOF
)

if aws secretsmanager describe-secret \
    --secret-id mabani/twilio/credentials \
    --region $AWS_REGION \
    --profile $AWS_PROFILE &> /dev/null; then
    
    echo -e "${YELLOW}⚠ Secret already exists. Updating...${NC}"
    aws secretsmanager update-secret \
        --secret-id mabani/twilio/credentials \
        --secret-string "$SECRET_STRING" \
        --region $AWS_REGION \
        --profile $AWS_PROFILE
else
    aws secretsmanager create-secret \
        --name mabani/twilio/credentials \
        --description "Twilio credentials for WhatsApp integration" \
        --secret-string "$SECRET_STRING" \
        --region $AWS_REGION \
        --profile $AWS_PROFILE
fi

echo -e "${GREEN}✓ Secrets Manager configured${NC}"

# Check Bedrock model access
echo ""
echo -e "${YELLOW}Checking Bedrock model access...${NC}"

MODEL_ID_LITE="amazon.nova-lite-v1:0"
MODEL_ID_PRO="amazon.nova-pro-v1:0"

# Check Nova Lite
if aws bedrock list-foundation-models \
    --region $AWS_REGION \
    --profile $AWS_PROFILE \
    --query "modelSummaries[?modelId=='$MODEL_ID_LITE'].modelId" \
    --output text 2>/dev/null | grep -q "$MODEL_ID_LITE"; then
    echo -e "${GREEN}✓ Amazon Nova Lite accessible${NC}"
else
    echo -e "${YELLOW}⚠ Amazon Nova Lite not accessible${NC}"
fi

# Check Nova Pro
if aws bedrock list-foundation-models \
    --region $AWS_REGION \
    --profile $AWS_PROFILE \
    --query "modelSummaries[?modelId=='$MODEL_ID_PRO'].modelId" \
    --output text 2>/dev/null | grep -q "$MODEL_ID_PRO"; then
    echo -e "${GREEN}✓ Amazon Nova Pro accessible${NC}"
else
    echo -e "${YELLOW}⚠ Amazon Nova Pro not accessible${NC}"
fi

# If neither is accessible, prompt for access
if ! aws bedrock list-foundation-models \
    --region $AWS_REGION \
    --profile $AWS_PROFILE \
    --query "modelSummaries[?contains(modelId, 'amazon.nova')].modelId" \
    --output text 2>/dev/null | grep -q "amazon.nova"; then
    echo -e "${RED}❌ No Amazon Nova models accessible${NC}"
    echo -e "${YELLOW}Please enable model access:${NC}"
    echo "1. Go to AWS Console → Bedrock → Model access"
    echo "2. Request access to: Amazon Nova Lite and Amazon Nova Pro"
    echo "3. Wait for approval (usually instant)"
    echo ""
    read -p "Press Enter once you've enabled model access..."
fi

# Install dependencies
echo ""
echo -e "${YELLOW}Installing dependencies...${NC}"
cd backend
npm install
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Deploy
echo ""
echo -e "${YELLOW}Ready to deploy!${NC}"
read -p "Deploy now? (y/n) [y]: " DEPLOY_NOW
DEPLOY_NOW=${DEPLOY_NOW:-y}

if [ "$DEPLOY_NOW" = "y" ] || [ "$DEPLOY_NOW" = "Y" ]; then
    echo -e "${YELLOW}Deploying to $ENVIRONMENT...${NC}"
    serverless deploy --stage $ENVIRONMENT --verbose
    
    echo ""
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Copy the TwilioWebhookUrl from the output above"
    echo "2. Configure it in Twilio Console:"
    echo "   - Go to: Messaging → Try it out → Send a WhatsApp message"
    echo "   - Set webhook URL under 'WHEN A MESSAGE COMES IN'"
    echo "   - Method: POST"
    echo "3. Test by sending a message with an image to your Twilio number"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "  View logs: serverless logs -f reportProcessor --stage $ENVIRONMENT --tail"
    echo "  Update function: serverless deploy function -f reportProcessor --stage $ENVIRONMENT"
    echo "  Remove all: serverless remove --stage $ENVIRONMENT"
    echo ""
else
    echo ""
    echo -e "${YELLOW}Setup complete! To deploy later, run:${NC}"
    echo "  cd backend"
    echo "  serverless deploy --stage $ENVIRONMENT"
fi

echo ""
echo -e "${GREEN}✓ Setup finished successfully${NC}"

