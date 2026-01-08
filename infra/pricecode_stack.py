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

        # 3. ECS Cluster
        cluster = ecs.Cluster(self, "PriceCodeCluster", vpc=vpc)

        # 4. Container Image - uses the same backend but different entrypoint
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend')
        asset = ecr_assets.DockerImageAsset(self, "PriceCodeJobImage",
            directory=backend_dir,
            file="Dockerfile.pricecode",  # Separate Dockerfile for price code
            platform=ecr_assets.Platform.LINUX_AMD64
        )

        # 5. Fargate Task Definition
        task_def = ecs.FargateTaskDefinition(self, "PriceCodeTaskDef",
            memory_limit_mib=2048,
            cpu=1024
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
            "PINECONE_API_KEY": get_ssm_param("PINECONE_API_KEY", os.getenv("PINECONE_API_KEY")),
            "PRICECODE_INDEX_NAME": get_ssm_param("PRICECODE_INDEX_NAME", os.getenv("PRICECODE_INDEX_NAME", "almabani-pricecode")),
            "OPENAI_EMBEDDING_MODEL": get_ssm_param("OPENAI_EMBEDDING_MODEL", os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")),
            "OPENAI_CHAT_MODEL": get_ssm_param("OPENAI_CHAT_MODEL", os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")),
            "PINECONE_ENVIRONMENT": get_ssm_param("PINECONE_ENVIRONMENT", os.getenv("PINECONE_ENVIRONMENT", "us-east-1"))
        }

        container = task_def.add_container("PriceCodeWorkerContainer",
            image=ecs.ContainerImage.from_docker_image_asset(asset),
            logging=ecs.LogDriver.aws_logs(stream_prefix="PriceCodeWorker"),
            environment={
                "STORAGE_TYPE": "s3",
                "S3_BUCKET_NAME": bucket.bucket_name,
                "AWS_REGION": self.region,
            },
            secrets=secrets,
            command=["python3", "pricecode_worker.py"]
        )
        
        # Grant permissions
        bucket.grant_read_write(task_def.task_role)

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
