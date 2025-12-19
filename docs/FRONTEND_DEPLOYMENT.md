# Frontend Deployment Guide

This guide explains how to deploy the Mabani frontend application to AWS S3 and CloudFront.

## Prerequisites

1.  **Node.js & npm**: Ensure you have Node.js and npm installed.
2.  **AWS CLI**: Installed and configured.
3.  **AWS Credentials**: The deployment script uses the `mia40` AWS profile by default. Ensure this profile is configured in your `~/.aws/credentials` or update the script/environment accordingly.
4.  **Infrastructure**: The `MabaniGeneralStack` must be deployed first, as the script fetches the S3 bucket name and CloudFront distribution ID from its outputs.

## Deployment Script

The primary method for deployment is the `deploy-s3.sh` script.

**Location**: `scripts/deploy/deploy-s3.sh`

### Usage

Run the script from the project root directory:

```bash
./scripts/deploy/deploy-s3.sh [environment]
```

-   **`environment`** (optional): The target environment (e.g., `dev`, `prod`). Defaults to `dev` if not specified.

### Example

Deploy to the development environment:

```bash
./scripts/deploy/deploy-s3.sh dev
```

## What the Script Does

The deployment process consists of the following automated steps:

1.  **Build**:
    -   Navigates to the `frontend` directory.
    -   Runs `npm run build` to compile the React application into the `dist/` folder.

2.  **Fetch Configuration**:
    -   Queries AWS CloudFormation (`MabaniGeneralStack-[env]`) to retrieve:
        -   The **S3 Bucket Name** for hosting the frontend.
        -   The **CloudFront Distribution ID** for content delivery.

3.  **Sync to S3**:
    -   Uploads the contents of `dist/` to the targeted S3 bucket.
    -   **Assets**: Sets `Cache-Control: public, max-age=31536000` for static assets (hashed JS/CSS) for optimal performance.
    -   **HTML/JSON**: Sets `Cache-Control: no-cache` for `index.html` and configuration files to ensure immediate updates for users.

4.  **Invalidate Cache**:
    -   Creates a CloudFront invalidation for `/*` to force edge locations to fetch the latest version of the application.

## Troubleshooting

-   **"Could not find S3 bucket name"**:
    -   Check if the infrastructure stack (`MabaniGeneralStack-[env]`) is successfully deployed in the target region.
    -   Verify your AWS credentials and region settings.

-   **Permission Errors**:
    -   Ensure your AWS user/role has permissions for `s3:PutObject`, `s3:ListBucket`, `cloudfront:CreateInvalidation`, and `cloudformation:DescribeStacks`.
