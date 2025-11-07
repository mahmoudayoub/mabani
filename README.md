# TaskFlow - Intelligent Task Management Platform

## Overview

A modern serverless application for intelligent task management and monitoring with React frontend and AWS backend services.

## Architecture

- **Frontend**: React + Vite + Tailwind CSS + AWS Cognito
- **Backend**: AWS Lambda + API Gateway + DynamoDB
- **Deployment**: S3 + CloudFront + AWS CDK/Serverless Framework
- **Region**: eu-west-1
- **Profile**: mia40 (Account: 239146712026)

## Features

- **WhatsApp-Based H&S Monitoring**: Health and safety monitoring via WhatsApp integration
- **Quality-Monitoring via WhatsApp**: Real-time quality control through WhatsApp channels
- **AI-Driven Task-Code Allocation**: Intelligent task assignment using AI algorithms
- **AI-Driven Price-Code Allocation**: Smart pricing system with AI-powered allocation

## Directory Structure

```
├── frontend/                 # React application
├── backend/                  # Lambda functions
├── infrastructure/           # AWS infrastructure as code
├── shared/                   # Shared utilities and types
├── scripts/                  # Deployment and utility scripts
├── docs/                     # Documentation
└── env.example              # Environment variables template
```

## Getting Started

1. Install dependencies: `npm install`
2. Configure AWS credentials
3. Deploy infrastructure: `npm run deploy:infra`
4. Deploy backend: `npm run deploy:backend`
5. Deploy frontend: `npm run deploy:frontend`
