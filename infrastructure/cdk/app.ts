#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { TaskFlowCognitoStack, MabaniGeneralStack } from "./mabani-stacks";
import { MabaniBackendStack } from "./backend-stack";
import { getConfig } from "./config";

const app = new cdk.App();

// Get environment from context or default to dev
const environment = app.node.tryGetContext("environment") || "dev";
const config = getConfig(environment);

// Validate required context values
if (!config.account || !config.region) {
  throw new Error(
    `Invalid configuration for environment: ${environment}. Account and region are required.`
  );
}

// Environment configuration for stacks
const stackEnv: cdk.Environment = {
  account: config.account,
  region: config.region,
};

// Stack 1: Cognito Stack (Authentication)
const cognitoStack = new TaskFlowCognitoStack(
  app,
  `MabaniCognitoStack-${environment}`,
  {
    env: stackEnv,
    description: `Cognito User Pool for Mabani application (${environment})`,
    environment: config.environment,
    allowedCorsOrigins: config.allowedCorsOrigins,
  }
);

// Stack 2: General Stack (Infrastructure: S3, CloudFront, VPC)
const generalStack = new MabaniGeneralStack(
  app,
  `MabaniGeneralStack-${environment}`,
  {
    env: stackEnv,
    description: `General infrastructure for Mabani (S3, CloudFront) (${environment})`,
    environment: config.environment,
    frontendDomain: config.frontendDomain,
  }
);

// Stack 3: Backend Stack (Compute: Lambda, API Gateway)
const backendStack = new MabaniBackendStack(
  app,
  `MabaniBackendStack-${environment}`,
  {
    env: stackEnv,
    description: `Backend compute resources for Mabani (Lambda, API Gateway) (${environment})`,
    environment: config.environment,
    userPoolArn: cognitoStack.userPool.userPoolArn,
    // Note: DynamoDB table name should come from config or Serverless Framework outputs
    // dynamoDbTableName: config.dynamoDbTableName,
  }
);

// Stack dependencies
backendStack.addDependency(cognitoStack); // Backend needs Cognito for auth
// General stack is independent (no dependencies)

// Apply common tags to all resources
const commonTags = {
  Project: "Mabani",
  Environment: environment,
  ManagedBy: "CDK",
  Repository: "mabani",
};

for (const [key, value] of Object.entries(commonTags)) {
  cdk.Tags.of(cognitoStack).add(key, value);
  cdk.Tags.of(generalStack).add(key, value);
  cdk.Tags.of(backendStack).add(key, value);
}

// Cost allocation tags
cdk.Tags.of(cognitoStack).add("CostCenter", "Engineering");
cdk.Tags.of(generalStack).add("CostCenter", "Engineering");
cdk.Tags.of(backendStack).add("CostCenter", "Engineering");
