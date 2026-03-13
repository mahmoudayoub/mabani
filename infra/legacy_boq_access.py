from aws_cdk import Stack, aws_iam as iam, aws_s3 as s3
from constructs import Construct
import os


def import_legacy_boq_api_role(scope: Construct, construct_id: str) -> iam.IRole:
    stack = Stack.of(scope)
    service = os.getenv("SERVERLESS_SERVICE_NAME", "taskflow-backend")
    stage = os.getenv("SERVERLESS_STAGE", "dev")
    role_arn = os.getenv(
        "BOQ_LEGACY_LAMBDA_ROLE_ARN",
        f"arn:aws:iam::{stack.account}:role/{service}-{stage}-{stack.region}-lambdaRole",
    )

    return iam.Role.from_role_arn(scope, construct_id, role_arn, mutable=True)


def attach_legacy_boq_api_access_policy(
    scope: Construct,
    construct_id: str,
    role: iam.IRole,
    bucket: s3.IBucket,
    *,
    allow_describe_tasks: bool = False,
) -> iam.ManagedPolicy:
    statements = [
        iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetBucketLocation"],
            resources=[bucket.bucket_arn],
        ),
        iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:AbortMultipartUpload",
            ],
            resources=[bucket.arn_for_objects("*")],
        ),
    ]

    if allow_describe_tasks:
        statements.append(
            iam.PolicyStatement(actions=["ecs:DescribeTasks"], resources=["*"])
        )

    return iam.ManagedPolicy(
        scope,
        construct_id,
        statements=statements,
        roles=[role],
    )
