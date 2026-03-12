"""
Price Code Allocation Stack - Separate CDK stack for price code pipeline.

Uses same VPC and bucket as main stack but with separate:
- ECS Task Definition (runs pricecode_worker.py)
- Lambda trigger (listens to input/pricecode/)
- S3 notifications for price code paths
"""

from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3_notifications as s3n,
    aws_ssm as ssm,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Fn
)
from constructs import Construct
import os


class PriceCodeStack(Stack):
    """
    CDK Stack for Price Code Allocation pipeline.
    
    Can either:
    1. Create its own infrastructure (standalone mode)
    2. Reference existing VPC/bucket from AlmabaniStack (shared mode)
    """

    def __init__(self, scope: Construct, construct_id: str, 
                 shared_vpc: ec2.IVpc = None,
                 shared_bucket: s3.IBucket = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. VPC - use shared or create new
        if shared_vpc:
            vpc = shared_vpc
        else:
            vpc = ec2.Vpc(self, "PriceCodeVPC",
                max_azs=2,
                nat_gateways=0,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        name="Public",
                        subnet_type=ec2.SubnetType.PUBLIC,
                        cidr_mask=24
                    )
                ]
            )

        # 2. S3 Bucket - use shared or create new
        if shared_bucket:
            bucket = shared_bucket
        else:
            bucket = s3.Bucket(self, "PriceCodeData",
                versioned=False,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
                cors=[
                    s3.CorsRule(
                        allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
                        allowed_origins=["*"],
                        allowed_headers=["*"]
                    )
                ]
            )
        self.bucket = bucket

        # 3. ECS Cluster
        cluster = ecs.Cluster(self, "PriceCodeCluster", vpc=vpc)

        # 4. Container Image - uses the same backend but different entrypoint
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'boq-backend')
        asset = ecr_assets.DockerImageAsset(self, "PriceCodeJobImage",
            directory=backend_dir,
            file="Dockerfile.pricecode",  # Separate Dockerfile for price code
            platform=ecr_assets.Platform.LINUX_AMD64
        )

        # 5. Fargate Task Definition - 8GB RAM for large Excel files
        task_def = ecs.FargateTaskDefinition(self, "PriceCodeTaskDef",
            memory_limit_mib=16384,  # 16GB RAM
            cpu=4096  # 4 vCPU
        )
        
        # SSM Parameters - reuse from main stack or create new
        def get_ssm_param(name, value):
            param = ssm.StringParameter(self, f"PriceCodeParam{name}",
                parameter_name=f"/pricecode/{name}",
                string_value=value or "CHANGEME"
            )
            return ecs.Secret.from_ssm_parameter(param)

        secrets = {
            "OPENAI_API_KEY": get_ssm_param("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
            "OPENAI_EMBEDDING_MODEL": get_ssm_param("OPENAI_EMBEDDING_MODEL", os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")),
            "OPENAI_CHAT_MODEL": get_ssm_param("OPENAI_CHAT_MODEL", os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini-2025-08-07")),
        }

        container = task_def.add_container("PriceCodeWorkerContainer",
            image=ecs.ContainerImage.from_docker_image_asset(asset),
            logging=ecs.LogDriver.aws_logs(stream_prefix="PriceCodeWorker"),
            environment={
                "STORAGE_TYPE": "s3",
                "S3_BUCKET_NAME": bucket.bucket_name,
                "AWS_REGION": self.region,
                "S3_VECTORS_BUCKET": os.getenv("S3_VECTORS_BUCKET", "almabani-vectors"),
                "S3_VECTORS_INDEX_NAME": os.getenv("S3_VECTORS_INDEX_NAME", "almabani"),
                # Price code settings (can override via env)
                "PRICECODE_BATCH_SIZE": os.getenv("PRICECODE_BATCH_SIZE", "100"),
                "PRICECODE_MAX_CONCURRENT": os.getenv("PRICECODE_MAX_CONCURRENT", "200"),
                "PRICECODE_MAX_CANDIDATES": os.getenv("PRICECODE_MAX_CANDIDATES", "1"),
                "PRICECODE_INDEX_DB": os.getenv("PRICECODE_INDEX_DB", "/tmp/pricecode_index.db"),
            },
            secrets=secrets,
            command=["python3", "pricecode_worker.py"]
        )
        
        # Grant permissions
        bucket.grant_read_write(task_def.task_role)
        
        # Grant S3 Vectors data API access
        task_def.task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3vectors:*"],
            resources=["*"]
        ))

        # Grant the Serverless backend Lambda role access to this bucket.
        # Role name follows Serverless Framework pattern: {service}-{stage}-{region}-lambdaRole
        sls_service = os.getenv("SERVERLESS_SERVICE_NAME", "taskflow-backend")
        sls_stage = os.getenv("SERVERLESS_STAGE", "dev")
        external_role_name = f"{sls_service}-{sls_stage}-{self.region}-lambdaRole"
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"],
                resources=[
                    bucket.bucket_arn,
                    bucket.arn_for_objects("*"),
                ],
                principals=[
                    iam.ArnPrincipal(
                        f"arn:aws:iam::{self.account}:role/{external_role_name}"
                    )
                ],
            )
        )

        # Security Group
        task_sg = ec2.SecurityGroup(self, "PriceCodeTaskSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security Group for Price Code Worker Tasks"
        )
        
        # 6. Trigger Lambda
        lambda_dir = os.path.join(os.path.dirname(__file__), 'lambdas')
        
        trigger_lambda = _lambda.Function(self, "PriceCodeTriggerLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="pricecode_trigger.handler",
            code=_lambda.Code.from_asset(lambda_dir),
            environment={
                "CLUSTER_NAME": cluster.cluster_name,
                "TASK_DEF_ARN": task_def.task_definition_arn,
                "SUBNET_ID": vpc.public_subnets[0].subnet_id,
                "SECURITY_GROUP_ID": task_sg.security_group_id
            },
            timeout=Duration.seconds(30)
        )
        
        # Lambda permissions
        trigger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask"],
            resources=[task_def.task_definition_arn]
        ))
        trigger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[task_def.execution_role.role_arn, task_def.task_role.role_arn]
        ))

        # 7. S3 Notifications for price code paths
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(trigger_lambda),
            s3.NotificationKeyFilter(prefix="input/pricecode/")
        )

        # Outputs
        CfnOutput(self, "PriceCodeS3BucketName", value=bucket.bucket_name)
        CfnOutput(self, "PriceCodeClusterName", value=cluster.cluster_name)
