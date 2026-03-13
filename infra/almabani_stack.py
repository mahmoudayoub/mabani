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
    CfnOutput
)
from constructs import Construct
import os

class AlmabaniStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. VPC 
        # Public subnet only to avoid NAT Gateway costs
        vpc = ec2.Vpc(self, "AlmabaniVPC",
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

        # 2. S3 Bucket
        bucket = s3.Bucket(self, "AlmabaniData",
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
        cluster = ecs.Cluster(self, "AlmabaniCluster", vpc=vpc)

        # 4. Container Image
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'boq-backend')
        asset = ecr_assets.DockerImageAsset(self, "AlmabaniJobImage",
            directory=backend_dir,
            file="Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64
        )

        # 5. Fargate Task Definition
        task_def = ecs.FargateTaskDefinition(self, "AlmabaniTaskDef",
            memory_limit_mib=2048,
            cpu=1024
        )
        
        # Helper to create/get SSM Parameter
        # We use StringParameter for simplicity. For stricter security, use SecureString (requires custom resource in CDK)
        # Here we just put them in standard Parameter Store.
        def get_ssm_param(name, value):
            param = ssm.StringParameter(self, f"Param{name}",
                parameter_name=f"/almabani/{name}",
                string_value=value or "CHANGEME"
            )
            return ecs.Secret.from_ssm_parameter(param)

        # Create secrets from local env vars or defaults
        secrets = {
            "OPENAI_API_KEY": get_ssm_param("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
            "OPENAI_EMBEDDING_MODEL": get_ssm_param("OPENAI_EMBEDDING_MODEL", os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")),
            "OPENAI_CHAT_MODEL": get_ssm_param("OPENAI_CHAT_MODEL", os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini-2025-08-07")),
        }

        container = task_def.add_container("WorkerContainer",
            image=ecs.ContainerImage.from_docker_image_asset(asset),
            logging=ecs.LogDriver.aws_logs(stream_prefix="AlmabaniWorker"),
            environment={
                "STORAGE_TYPE": "s3",
                "S3_BUCKET_NAME": bucket.bucket_name,
                "AWS_REGION": self.region,
                "S3_VECTORS_BUCKET": os.getenv("S3_VECTORS_BUCKET", "almabani-vectors"),
                "S3_VECTORS_INDEX_NAME": os.getenv("S3_VECTORS_INDEX_NAME", "almabani")
            },
            secrets=secrets,
            command=["python3", "worker.py"] 
        )
        
        # Grant permissions to Task Role
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

        # Create a Security Group for the task
        task_sg = ec2.SecurityGroup(self, "TaskSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security Group for Almabani Worker Tasks"
        )
        
        # 6. Trigger Lambda
        # Load code from infra/lambdas/trigger.py
        lambda_dir = os.path.join(os.path.dirname(__file__), 'lambdas')
        
        trigger_lambda = _lambda.Function(self, "TriggerLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="trigger.handler", # File is trigger.py, function is handler
            code=_lambda.Code.from_asset(lambda_dir),
            environment={
                "CLUSTER_NAME": cluster.cluster_name,
                "TASK_DEF_ARN": task_def.task_definition_arn,
                "SUBNET_ID": vpc.public_subnets[0].subnet_id, 
                "SECURITY_GROUP_ID": task_sg.security_group_id
            },
            timeout=Duration.seconds(30)
        )
        
        # Permissions for Lambda to run ECS tasks
        trigger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask"],
            resources=[task_def.task_definition_arn]
        ))
        trigger_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[task_def.execution_role.role_arn, task_def.task_role.role_arn]
        ))

        # 7. S3 Notification
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(trigger_lambda),
            s3.NotificationKeyFilter(prefix="input/")
        )

        CfnOutput(self, "S3BucketName", value=bucket.bucket_name)
