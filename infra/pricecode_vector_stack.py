"""
Price Code Vector Stack – CDK stack for the vector-based price code service.

Uses S3 Vectors (embedding similarity) instead of SQLite/TF-IDF.
Separate ECS task definition, Lambda trigger, and S3 notifications
for the ``input/pricecode-vector/`` prefix.
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
)
from constructs import Construct
import os


class PriceCodeVectorStack(Stack):
    """
    CDK Stack for the vector-based Price Code service.

    Can share VPC / bucket from PriceCodeStack or create its own.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        shared_vpc: ec2.IVpc = None,
        shared_bucket: s3.IBucket = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── 1. VPC ─────────────────────────────────────────────────────
        if shared_vpc:
            vpc = shared_vpc
        else:
            vpc = ec2.Vpc(
                self,
                "PriceCodeVectorVPC",
                max_azs=2,
                nat_gateways=0,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        name="Public",
                        subnet_type=ec2.SubnetType.PUBLIC,
                        cidr_mask=24,
                    )
                ],
            )

        # ── 2. S3 Bucket ──────────────────────────────────────────────
        if shared_bucket:
            bucket = shared_bucket
        else:
            bucket = s3.Bucket(
                self,
                "PriceCodeVectorData",
                versioned=False,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
                cors=[
                    s3.CorsRule(
                        allowed_methods=[
                            s3.HttpMethods.GET,
                            s3.HttpMethods.PUT,
                            s3.HttpMethods.POST,
                        ],
                        allowed_origins=["*"],
                        allowed_headers=["*"],
                    )
                ],
            )
        self.bucket = bucket

        # ── 3. ECS Cluster ─────────────────────────────────────────────
        cluster = ecs.Cluster(self, "PriceCodeVectorCluster", vpc=vpc)

        # ── 4. Container Image ─────────────────────────────────────────
        backend_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "boq-backend"
        )
        asset = ecr_assets.DockerImageAsset(
            self,
            "PriceCodeVectorJobImage",
            directory=backend_dir,
            file="Dockerfile.pricecode_vector",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # ── 5. Fargate Task Definition ─────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self,
            "PriceCodeVectorTaskDef",
            memory_limit_mib=8192,   # 8 GB
            cpu=2048,                # 2 vCPU
        )

        # SSM Parameters – secrets
        def _ssm_param(name, value):
            param = ssm.StringParameter(
                self,
                f"PCVParam{name}",
                parameter_name=f"/pricecode-vector/{name}",
                string_value=value or "CHANGEME",
            )
            return ecs.Secret.from_ssm_parameter(param)

        secrets = {
            "OPENAI_API_KEY": _ssm_param(
                "OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")
            ),
            "OPENAI_EMBEDDING_MODEL": _ssm_param(
                "OPENAI_EMBEDDING_MODEL",
                os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            ),
        }

        container = task_def.add_container(
            "PriceCodeVectorWorkerContainer",
            image=ecs.ContainerImage.from_docker_image_asset(asset),
            logging=ecs.LogDriver.aws_logs(stream_prefix="PriceCodeVectorWorker"),
            environment={
                "STORAGE_TYPE": "s3",
                "S3_BUCKET_NAME": bucket.bucket_name,
                "AWS_REGION": self.region,
                "S3_VECTORS_BUCKET": os.getenv(
                    "S3_VECTORS_BUCKET", "almabani-vectors"
                ),
                # Vector-specific settings (overridable via env)
                "PRICECODE_VECTOR_TOP_K": os.getenv("PRICECODE_VECTOR_TOP_K", "5"),
                "PRICECODE_VECTOR_THRESHOLD": os.getenv(
                    "PRICECODE_VECTOR_THRESHOLD", "0.40"
                ),
                "BATCH_SIZE": os.getenv("BATCH_SIZE", "500"),
                "EMBEDDINGS_RPM": os.getenv("EMBEDDINGS_RPM", "3000"),
            },
            secrets=secrets,
            command=["python3", "pricecode_vector_worker.py"],
        )

        # Permissions
        bucket.grant_read_write(task_def.task_role)
        task_def.task_role.add_to_policy(
            iam.PolicyStatement(actions=["s3vectors:*"], resources=["*"])
        )

        # Grant the Serverless Framework Lambda role access to this bucket
        # so the frontend API (taskflow-backend-dev) can list/read/write.
        # We use a bucket policy since the role is external to this stack.
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"],
                resources=[
                    bucket.bucket_arn,
                    bucket.arn_for_objects("*"),
                ],
                principals=[
                    iam.ArnPrincipal(
                        f"arn:aws:iam::{self.account}:role/taskflow-backend-dev-eu-west-1-lambdaRole"
                    )
                ],
            )
        )

        # Security Group
        task_sg = ec2.SecurityGroup(
            self,
            "PriceCodeVectorTaskSG",
            vpc=vpc,
            allow_all_outbound=True,
            description="SG for Price Code Vector Worker Tasks",
        )

        # ── 6. Trigger Lambda ──────────────────────────────────────────
        lambda_dir = os.path.join(os.path.dirname(__file__), "lambdas")

        trigger_lambda = _lambda.Function(
            self,
            "PriceCodeVectorTriggerLambda",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="pricecode_vector_trigger.handler",
            code=_lambda.Code.from_asset(lambda_dir),
            environment={
                "CLUSTER_NAME": cluster.cluster_name,
                "TASK_DEF_ARN": task_def.task_definition_arn,
                "SUBNET_ID": vpc.public_subnets[0].subnet_id,
                "SECURITY_GROUP_ID": task_sg.security_group_id,
            },
            timeout=Duration.seconds(30),
        )

        # Lambda → ECS perms
        trigger_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask"],
                resources=[task_def.task_definition_arn],
            )
        )
        trigger_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    task_def.execution_role.role_arn,
                    task_def.task_role.role_arn,
                ],
            )
        )

        # ── 7. S3 Notifications ────────────────────────────────────────
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(trigger_lambda),
            s3.NotificationKeyFilter(prefix="input/pricecode-vector/"),
        )

        # ── Outputs ────────────────────────────────────────────────────
        CfnOutput(self, "PriceCodeVectorBucketName", value=bucket.bucket_name)
        CfnOutput(self, "PriceCodeVectorClusterName", value=cluster.cluster_name)
