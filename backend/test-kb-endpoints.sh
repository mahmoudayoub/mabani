#!/bin/bash

# Test script for Knowledge Base endpoints
# Usage: ./test-kb-endpoints.sh <jwt-token>

set -e

# Configuration
BASE_URL="http://localhost:3001"
JWT_TOKEN="${1}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ -z "$JWT_TOKEN" ]; then
    echo -e "${RED}Error: JWT token is required${NC}"
    echo "Usage: $0 <jwt-token>"
    echo ""
    echo "Get a JWT token by:"
    echo "1. Running the frontend and signing in"
    echo "2. Copying the idToken from browser localStorage"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Testing Knowledge Base Endpoints     ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Test 1: List Knowledge Bases
echo -e "${YELLOW}Test 1: List Knowledge Bases${NC}"
curl -X GET "$BASE_URL/knowledge-bases" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 2: Create Knowledge Base
echo -e "${YELLOW}Test 2: Create Knowledge Base${NC}"
KB_RESPONSE=$(curl -X POST "$BASE_URL/knowledge-bases" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test KB - Local Dev",
    "description": "Testing local development server",
    "embeddingModel": "amazon.titan-embed-text-v2:0",
    "llmModel": "eu.amazon.nova-lite-v1:0"
  }' \
  -w "\nStatus: %{http_code}\n" \
  -s)

echo "$KB_RESPONSE" | head -n -1 | jq '.' || echo "$KB_RESPONSE"
KB_ID=$(echo "$KB_RESPONSE" | head -n -1 | jq -r '.kbId' 2>/dev/null || echo "")
echo ""

if [ -z "$KB_ID" ] || [ "$KB_ID" = "null" ]; then
    echo -e "${RED}Failed to create KB. Stopping tests.${NC}"
    exit 1
fi

echo -e "${GREEN}Created KB with ID: $KB_ID${NC}"
echo ""

# Test 3: Get Knowledge Base
echo -e "${YELLOW}Test 3: Get Knowledge Base${NC}"
curl -X GET "$BASE_URL/knowledge-bases/$KB_ID" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 4: Update Knowledge Base
echo -e "${YELLOW}Test 4: Update Knowledge Base${NC}"
curl -X PUT "$BASE_URL/knowledge-bases/$KB_ID" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Test KB",
    "description": "Updated description for testing"
  }' \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 5: Generate Upload URL
echo -e "${YELLOW}Test 5: Generate Upload URL${NC}"
curl -X POST "$BASE_URL/knowledge-bases/$KB_ID/upload-url" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test-document.pdf",
    "contentType": "application/pdf"
  }' \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 6: List Documents (should be empty)
echo -e "${YELLOW}Test 6: List Documents${NC}"
curl -X GET "$BASE_URL/knowledge-bases/$KB_ID/documents" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 7: Query Knowledge Base (should return no results)
echo -e "${YELLOW}Test 7: Query Knowledge Base (empty KB)${NC}"
curl -X POST "$BASE_URL/knowledge-bases/$KB_ID/query" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is this about?",
    "modelId": "eu.amazon.nova-lite-v1:0",
    "k": 5
  }' \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

# Test 8: Delete Knowledge Base
echo -e "${YELLOW}Test 8: Delete Knowledge Base${NC}"
read -p "Press Enter to delete the test KB (or Ctrl+C to keep it)..."
curl -X DELETE "$BASE_URL/knowledge-bases/$KB_ID" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nStatus: %{http_code}\n\n" \
  -s | jq '.' || echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  All tests completed!                 ${NC}"
echo -e "${GREEN}========================================${NC}"

