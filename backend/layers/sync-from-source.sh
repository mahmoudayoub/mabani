#!/bin/bash
# Sync shared code from source to layer structures
# Run this from the backend directory

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo "Syncing shared code to layer structures..."

# Common shared layer
echo "Syncing common shared code..."
mkdir -p "$SCRIPT_DIR/shared/python/lambdas/shared"
# Ensure lambdas/__init__.py exists as namespace package marker
if [ ! -f "$SCRIPT_DIR/shared/python/lambdas/__init__.py" ]; then
    echo '# Namespace package marker for Lambda layer
# This allows lambdas package to span across function package and layers
__path__ = __import__("pkgutil").extend_path(__path__, __name__)' > "$SCRIPT_DIR/shared/python/lambdas/__init__.py"
fi
cp "$BACKEND_DIR/lambdas/shared/lambda_helpers.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/bedrock_client.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/s3_client.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/twilio_client.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/conversation_state.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/validators.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/config_manager.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/user_project_manager.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"

cp "$BACKEND_DIR/lambdas/shared/__init__.py" "$SCRIPT_DIR/shared/python/lambdas/shared/"

# KB shared layer
echo "Syncing KB-specific shared code..."
mkdir -p "$SCRIPT_DIR/kb/python/lambdas/shared"
# Ensure lambdas/__init__.py exists as namespace package marker
if [ ! -f "$SCRIPT_DIR/kb/python/lambdas/__init__.py" ]; then
    echo '# Namespace package marker for Lambda layer
# This allows lambdas package to span across function package and layers
__path__ = __import__("pkgutil").extend_path(__path__, __name__)' > "$SCRIPT_DIR/kb/python/lambdas/__init__.py"
fi
cp "$BACKEND_DIR/lambdas/shared/lambda_helpers.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/kb_repositories.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/faiss_utils.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/document_processing.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/dynamic_bedrock.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/user_project_manager.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"
cp "$BACKEND_DIR/lambdas/shared/__init__.py" "$SCRIPT_DIR/kb/python/lambdas/shared/"

# Cleanup
find "$SCRIPT_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.pyc" -delete

echo "✓ Common shared layer synced"
echo "✓ KB shared layer synced"
