import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import * as fs from "fs";
import * as path from "path";

export interface BackendStackProps extends cdk.StackProps {
  environment: string;
  userPoolArn?: string;
  dynamoDbTableName?: string;
}

export class MabaniBackendStack extends cdk.Stack {
  public readonly api: apigateway.RestApi;
  public readonly lambdaLayer: lambda.LayerVersion;

  constructor(scope: Construct, id: string, props: BackendStackProps) {
    super(scope, id, props);

    const { environment, userPoolArn, dynamoDbTableName } = props;

    // Lambda Layer for shared dependencies
    // TODO: Create backend/layer/python/ directory structure when ready
    // Expected structure: backend/layer/python/lib/python3.13/site-packages/
    // For now, using lambdas directory as placeholder - will fail if path doesn't exist
    // Update path when layer directory is created
    const layerPath = "../backend/layer";

    // Check if layer directory exists, otherwise use placeholder
    let layerCode: lambda.Code;
    if (fs.existsSync(path.resolve(__dirname, layerPath))) {
      layerCode = lambda.Code.fromAsset(layerPath);
    } else {
      // Placeholder: create empty directory structure or use lambdas
      // This will work for now but should be updated when layer is ready
      layerCode = lambda.Code.fromAsset("../backend/lambdas", {
        exclude: ["*.py", "*.pyc", "__pycache__"],
      });
    }

    this.lambdaLayer = new lambda.LayerVersion(this, "SharedLayer", {
      code: layerCode,
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
      description: "Shared dependencies and utilities for Lambda functions",
      removalPolicy:
        environment === "prod"
          ? cdk.RemovalPolicy.RETAIN
          : cdk.RemovalPolicy.DESTROY,
    });

    // CloudWatch Log Group for Lambda functions
    const logGroup = new logs.LogGroup(this, "LambdaLogGroup", {
      logGroupName: `/aws/lambda/mabani-${environment}`,
      retention:
        environment === "prod"
          ? logs.RetentionDays.ONE_MONTH
          : logs.RetentionDays.THREE_DAYS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // IAM Role for Lambda execution
    const lambdaRole = new iam.Role(this, "LambdaExecutionRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "Execution role for Mabani Lambda functions",
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    // Grant CloudWatch Logs permissions
    logGroup.grantWrite(lambdaRole);

    // DynamoDB permissions (if table name provided)
    if (dynamoDbTableName) {
      lambdaRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "dynamodb:Query",
            "dynamodb:Scan",
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
          ],
          resources: [
            `arn:aws:dynamodb:${this.region}:${this.account}:table/${dynamoDbTableName}`,
            `arn:aws:dynamodb:${this.region}:${this.account}:table/${dynamoDbTableName}/index/*`,
          ],
        })
      );
    }

    // Cognito permissions (if UserPool ARN provided)
    if (userPoolArn) {
      lambdaRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "cognito-idp:AdminGetUser",
            "cognito-idp:AdminUpdateUserAttributes",
          ],
          resources: [userPoolArn],
        })
      );
    }

    // API Gateway REST API
    this.api = new apigateway.RestApi(this, "MabaniApi", {
      restApiName: `mabani-api-${environment}`,
      description: `Mabani REST API for ${environment}`,
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
          "X-Amz-Security-Token",
        ],
      },
      deployOptions: {
        stageName: environment,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: environment !== "prod",
        metricsEnabled: true,
      },
    });

    // Cognito Authorizer (if UserPool ARN provided)
    // Note: This authorizer can be used when adding protected endpoints
    // Example:
    // if (userPoolArn) {
    //   const authorizer = new apigateway.CognitoUserPoolsAuthorizer(
    //     this,
    //     "CognitoAuthorizer",
    //     {
    //       cognitoUserPools: [
    //         cognito.UserPool.fromUserPoolArn(this, "UserPool", userPoolArn),
    //       ],
    //       identitySource: "method.request.header.Authorization",
    //     }
    //   );
    // }

    // Example: Health check endpoint (no auth required)
    // Note: Uncomment and configure when Lambda code is ready
    // const healthCheckLambda = new lambda.Function(this, "HealthCheckLambda", {
    //   runtime: lambda.Runtime.PYTHON_3_13,
    //   handler: "user_profile.health_check",
    //   code: lambda.Code.fromAsset("../backend/lambdas"),
    //   role: lambdaRole,
    //   layers: [this.lambdaLayer],
    //   environment: {
    //     ENVIRONMENT: environment,
    //     DYNAMODB_TABLE_NAME: dynamoDbTableName || "",
    //   },
    //   logGroup,
    //   timeout: cdk.Duration.seconds(30),
    // });
    //
    // const healthCheckResource = this.api.root.addResource("health");
    // healthCheckResource.addMethod(
    //   "GET",
    //   new apigateway.LambdaIntegration(healthCheckLambda),
    //   {
    //     apiKeyRequired: false,
    //   }
    // );

    // Outputs
    new cdk.CfnOutput(this, "ApiEndpoint", {
      value: this.api.url,
      description: "API Gateway endpoint URL",
      exportName: `MabaniApiEndpoint-${environment}`,
    });

    new cdk.CfnOutput(this, "ApiId", {
      value: this.api.restApiId,
      description: "API Gateway REST API ID",
      exportName: `MabaniApiId-${environment}`,
    });

    new cdk.CfnOutput(this, "LambdaLayerArn", {
      value: this.lambdaLayer.layerVersionArn,
      description: "Lambda Layer ARN",
      exportName: `MabaniLambdaLayerArn-${environment}`,
    });
  }
}
