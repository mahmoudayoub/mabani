#!/bin/bash

# Quick test script for Knowledge Base endpoints
# Make sure serverless-offline is running first

echo "Testing Knowledge Base endpoints..."
echo ""

# Test health endpoint first (no auth required)
echo "1. Testing health endpoint..."
curl -s http://localhost:3001/health | jq '.' || echo "Failed or jq not installed"
echo ""
echo "---"
echo ""

# Test knowledge bases endpoint (requires auth)
echo "2. Testing /knowledge-bases endpoint..."
echo "Note: This requires a valid JWT token in the Authorization header"
echo ""
echo "Example:"
echo 'curl -X GET http://localhost:3001/knowledge-bases \'
echo '  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"'
echo ""
echo "To get your JWT token:"
echo "1. Sign in via the frontend"
echo "2. Open DevTools → Application → Local Storage"
echo "3. Find the idToken key"
echo ""

