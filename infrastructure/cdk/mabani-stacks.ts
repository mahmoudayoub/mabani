import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as path from "path";
import { Construct } from "constructs";

export interface CognitoStackProps extends cdk.StackProps {
  environment: string;
  allowedCorsOrigins: string[];
}

export interface GeneralStackProps extends cdk.StackProps {
  environment: string;
  frontendDomain?: string;
}

export class TaskFlowCognitoStack extends cdk.Stack {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: CognitoStackProps) {
    super(scope, id, props);

    const { environment, allowedCorsOrigins } = props;

    // Cognito User Pool - simplified for cost efficiency
    // Note: When email alias is enabled, usernames cannot be in email format.
    // Users will sign in with their email address, and Cognito auto-generates usernames.
    this.userPool = new cognito.UserPool(this, "TaskFlowUserPool", {
      userPoolName: `mabani-user-pool-${environment}`,
      selfSignUpEnabled: environment !== "prod",
      signInAliases: {
        email: true,
        username: false, // Disable username sign-in to avoid conflicts with email alias
      },
      autoVerify: {
        email: true,
      },
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
        givenName: {
          required: true,
          mutable: true,
        },
        familyName: {
          required: true,
          mutable: true,
        },
      },
      // Custom attributes (non-standard)
      customAttributes: {
        position: new cognito.StringAttribute({
          minLen: 1,
          maxLen: 256,
          mutable: true,
        }),
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      signInCaseSensitive: false,
    });

    // Cognito User Pool Client - simplified
    this.userPoolClient = new cognito.UserPoolClient(
      this,
      "TaskFlowUserPoolClient",
      {
        userPool: this.userPool,
        userPoolClientName: `mabani-client-${environment}`,
        generateSecret: false,
        authFlows: {
          userPassword: true,
          userSrp: true,
        },
        oAuth: {
          flows: {
            authorizationCodeGrant: true,
          },
          scopes: [
            cognito.OAuthScope.EMAIL,
            cognito.OAuthScope.OPENID,
            cognito.OAuthScope.PROFILE,
          ],
          callbackUrls: allowedCorsOrigins,
          logoutUrls: allowedCorsOrigins,
        },
        supportedIdentityProviders: [
          cognito.UserPoolClientIdentityProvider.COGNITO,
        ],
      }
    );

    // Outputs
    new cdk.CfnOutput(this, "UserPoolId", {
      value: this.userPool.userPoolId,
      description: "Cognito User Pool ID",
      exportName: "TaskFlowUserPoolId",
    });

    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: this.userPoolClient.userPoolClientId,
      description: "Cognito User Pool Client ID",
      exportName: "TaskFlowUserPoolClientId",
    });

    new cdk.CfnOutput(this, "UserPoolArn", {
      value: this.userPool.userPoolArn,
      description: "Cognito User Pool ARN",
      exportName: "TaskFlowUserPoolArn",
    });
  }
}

export class MabaniGeneralStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: GeneralStackProps) {
    super(scope, id, props);

    const { environment, frontendDomain } = props;

    // S3 Bucket for hosting with best practices
    const account = this.account || props.env?.account || "";
    const region = this.region || props.env?.region || "";

    this.bucket = new s3.Bucket(this, "TaskFlowFrontendBucket", {
      bucketName: `mabani-frontend-${environment}-${account}-${region}`,
      // Encryption at rest
      encryption: s3.BucketEncryption.S3_MANAGED,
      // Public access blocked
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      // Removal policy based on environment
      removalPolicy:
        environment === "prod"
          ? cdk.RemovalPolicy.RETAIN
          : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: environment !== "prod",
    });

    // CloudFront Origin Access Control
    // const oac = new cloudfront.CfnOriginAccessControl(this, "TaskFlowOAC", {
    //   originAccessControlConfig: {
    //     name: "taskflow-oac",
    //     originAccessControlOriginType: "s3",
    //     signingBehavior: "always",
    //     signingProtocol: "sigv4",
    //   },
    // });

    // CloudFront Distribution with best practices
    this.distribution = new cloudfront.Distribution(
      this,
      "TaskFlowDistribution",
      {
        defaultBehavior: {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.bucket),
          viewerProtocolPolicy:
            cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
          cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
          compress: true,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
          // Security headers - simplified (HSTS and HTTPS enforcement)
          responseHeadersPolicy: new cloudfront.ResponseHeadersPolicy(
            this,
            "SecurityHeadersPolicy",
            {
              securityHeadersBehavior: {
                strictTransportSecurity: {
                  accessControlMaxAge: cdk.Duration.seconds(31536000),
                  includeSubdomains: true,
                  preload: true,
                  override: true,
                },
                contentTypeOptions: { override: true },
              },
            }
          ),
        },
        additionalBehaviors: {
          "/static/*": {
            origin: origins.S3BucketOrigin.withOriginAccessControl(this.bucket),
            viewerProtocolPolicy:
              cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
            cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
            compress: true,
            cachePolicy:
              cloudfront.CachePolicy.CACHING_OPTIMIZED_FOR_UNCOMPRESSED_OBJECTS,
          },
        },
        errorResponses: [
          {
            httpStatus: 404,
            responseHttpStatus: 200,
            responsePagePath: "/index.html",
          },
          {
            httpStatus: 403,
            responseHttpStatus: 200,
            responsePagePath: "/index.html",
          },
        ],
        priceClass:
          environment === "prod"
            ? cloudfront.PriceClass.PRICE_CLASS_ALL
            : cloudfront.PriceClass.PRICE_CLASS_100,
        // Custom domain configuration (if provided)
        ...(frontendDomain && {
          domainNames: [frontendDomain],
          // Note: You'll need to create a certificate in ACM and reference it here
          // certificate: acm.Certificate.fromCertificateArn(...)
        }),
      }
    );

    // Grant CloudFront access to S3 bucket
    this.bucket.addToResourcePolicy(
      new cdk.aws_iam.PolicyStatement({
        effect: cdk.aws_iam.Effect.ALLOW,
        principals: [
          new cdk.aws_iam.ServicePrincipal("cloudfront.amazonaws.com"),
        ],
        actions: ["s3:GetObject"],
        resources: [`${this.bucket.bucketArn}/*`],
        conditions: {
          StringEquals: {
            "AWS:SourceArn": `arn:aws:cloudfront::${account}:distribution/${this.distribution.distributionId}`,
          },
        },
      })
    );

    // Outputs
    new cdk.CfnOutput(this, "BucketName", {
      value: this.bucket.bucketName,
      description: "S3 Bucket Name",
      exportName: "TaskFlowBucketName",
    });

    new cdk.CfnOutput(this, "DistributionId", {
      value: this.distribution.distributionId,
      description: "CloudFront Distribution ID",
      exportName: "TaskFlowDistributionId",
    });

    new cdk.CfnOutput(this, "DistributionDomainName", {
      value: this.distribution.distributionDomainName,
      description: "CloudFront Distribution Domain Name",
      exportName: "TaskFlowDistributionDomainName",
    });

    new cdk.CfnOutput(this, "WebsiteURL", {
      value: `https://${this.distribution.distributionDomainName}`,
      description: "Website URL",
      exportName: "TaskFlowWebsiteURL",
    });

    // Deploy site contents to S3 bucket
    new s3deploy.BucketDeployment(this, "TaskFlowDeployWithInvalidation", {
      sources: [s3deploy.Source.asset(path.join(__dirname, "../../frontend/dist"))],
      destinationBucket: this.bucket,
      distribution: this.distribution,
      distributionPaths: ["/*"],
    });
  }
}
