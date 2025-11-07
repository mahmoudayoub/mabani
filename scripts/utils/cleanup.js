#!/bin/bash

# Cleanup script for temporary files and build artifacts
# Usage: ./cleanup.sh

set -e

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

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Clean frontend build artifacts
clean_frontend() {
    log_info "Cleaning frontend build artifacts..."
    cd "$PROJECT_ROOT/frontend"
    
    if [ -d "dist" ]; then
        rm -rf dist
        log_success "Removed frontend dist directory"
    fi
    
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        log_success "Removed frontend node_modules"
    fi
}

# Clean backend build artifacts
clean_backend() {
    log_info "Cleaning backend build artifacts..."
    cd "$PROJECT_ROOT/backend"
    
    if [ -d "dist" ]; then
        rm -rf dist
        log_success "Removed backend dist directory"
    fi
    
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        log_success "Removed backend node_modules"
    fi
    
    if [ -d "venv" ]; then
        rm -rf venv
        log_success "Removed Python virtual environment"
    fi
    
    if [ -d ".serverless" ]; then
        rm -rf .serverless
        log_success "Removed .serverless directory"
    fi
    
    # Remove Python cache files
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    log_success "Removed Python cache files"
}

# Clean infrastructure build artifacts
clean_infrastructure() {
    log_info "Cleaning infrastructure build artifacts..."
    cd "$PROJECT_ROOT/infrastructure"
    
    if [ -d "cdk.out" ]; then
        rm -rf cdk.out
        log_success "Removed cdk.out directory"
    fi
    
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        log_success "Removed infrastructure node_modules"
    fi
}

# Clean root node_modules
clean_root() {
    log_info "Cleaning root node_modules..."
    cd "$PROJECT_ROOT"
    
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        log_success "Removed root node_modules"
    fi
}

# Clean temporary files
clean_temp() {
    log_info "Cleaning temporary files..."
    
    # Remove .env files (keep .env.example)
    find "$PROJECT_ROOT" -name ".env" -not -name ".env.example" -delete 2>/dev/null || true
    
    # Remove log files
    find "$PROJECT_ROOT" -name "*.log" -delete 2>/dev/null || true
    
    # Remove TypeScript build info
    find "$PROJECT_ROOT" -name "*.tsbuildinfo" -delete 2>/dev/null || true
    
    log_success "Removed temporary files"
}

# Main cleanup function
main() {
    log_info "Starting cleanup..."
    
    clean_frontend
    clean_backend
    clean_infrastructure
    clean_root
    clean_temp
    
    log_success "Cleanup completed successfully!"
    log_warning "Note: This script removes all build artifacts and dependencies."
    log_warning "Run 'npm run install:all' to reinstall dependencies."
}

# Run main function
main "$@"
