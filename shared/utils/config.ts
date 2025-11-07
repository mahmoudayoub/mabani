import AWS from "aws-sdk";
import dotenv from "dotenv";

// Load environment variables
dotenv.config();

// AWS Configuration
const awsConfig = {
  region: process.env.AWS_REGION || "eu-west-1",
  profile: process.env.AWS_PROFILE || "mia40",
  accountId: process.env.AWS_ACCOUNT_ID || "239146712026",
};

// Initialize AWS services
export const dynamodb = new AWS.DynamoDB.DocumentClient({
  region: awsConfig.region,
});

export const s3 = new AWS.S3({
  region: awsConfig.region,
});

export const cloudfront = new AWS.CloudFront({
  region: awsConfig.region,
});

export const apigateway = new AWS.APIGateway({
  region: awsConfig.region,
});

export const cognito = new AWS.CognitoIdentityServiceProvider({
  region: awsConfig.region,
});

export const lambda = new AWS.Lambda({
  region: awsConfig.region,
});

// Utility function to get DynamoDB table
export const getDynamoDBTable = (tableName?: string) => {
  const name = tableName || process.env.DYNAMODB_TABLE_NAME || "taskflow-table";
  return {
    name,
    client: dynamodb,
  };
};

// Environment configuration
export const config = {
  appName: process.env.APP_NAME || "taskflow-serverless",
  environment: process.env.ENVIRONMENT || "dev",
  region: awsConfig.region,
  accountId: awsConfig.accountId,
  profile: awsConfig.profile,
  frontend: {
    apiBaseUrl: process.env.VITE_API_BASE_URL,
    cognitoUserPoolId: process.env.VITE_COGNITO_USER_POOL_ID,
    cognitoUserPoolClientId: process.env.VITE_COGNITO_USER_POOL_CLIENT_ID,
    cognitoRegion: process.env.VITE_COGNITO_REGION || awsConfig.region,
  },
  backend: {
    dynamodbTableName: process.env.DYNAMODB_TABLE_NAME || "taskflow-table",
    jwtSecret: process.env.JWT_SECRET,
  },
  deployment: {
    s3BucketName: process.env.S3_BUCKET_NAME,
    cloudfrontDistributionId: process.env.CLOUDFRONT_DISTRIBUTION_ID,
    apiGatewayRestApiId: process.env.API_GATEWAY_REST_API_ID,
  },
};

export default config;
