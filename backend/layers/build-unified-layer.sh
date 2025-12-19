#!/bin/bash
# Build a unified layer with both dependencies and shared code

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building unified layer with dependencies + shared code..."

# Create unified layer structure
mkdir -p "$SCRIPT_DIR/unified/python/lib/python3.13/site-packages"
mkdir -p "$SCRIPT_DIR/unified/python/lambdas/shared"

# Install Python dependencies into layer
echo "Installing Python dependencies..."
pip install -r "$BACKEND_DIR/requirements.txt" \
  --target "$SCRIPT_DIR/unified/python/lib/python3.13/site-packages" \
  --platform linux_x86_64 \
  --only-binary :all: \
  --python-version 3.13 \
  --exclude numpy \
  --exclude faiss-cpu

# Copy shared code
echo "Copying shared code..."
cp -r "$BACKEND_DIR/lambdas/shared"/* "$SCRIPT_DIR/unified/python/lambdas/shared/"

# Cleanup
find "$SCRIPT_DIR/unified" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/unified" -name "*.pyc" -delete

echo "✓ Unified layer built at layers/unified/"
