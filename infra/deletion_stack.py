
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_s3 as s3,
    Duration,
    CfnOutput,
    Size,
)
from constructs import Construct
import os
from layer_utils import build_async_aws_dependencies_layer


def _grant_status_marker_access(grantee: iam.IGrantable, bucket: s3.IBucket) -> None:
    grantee.grant_principal.add_to_principal_policy(
        iam.PolicyStatement(
            actions=["s3:GetObject", "s3:DeleteObject"],
            resources=[bucket.arn_for_objects("deletion-status/*")],
        )
    )

class DeletionStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
                 shared_bucket: s3.IBucket = None,
                 pricecode_bucket: s3.IBucket = None,
                 pricecode_vector_bucket: s3.IBucket = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Access Shared Bucket
        if shared_bucket:
            bucket = shared_bucket
        else:
            raise ValueError(
                "DeletionStack requires shared_bucket from AlmabaniStack. "
                "Pass shared_bucket=main_stack.bucket when instantiating."
            )

        # 1b. Access Price Code Bucket
        if pricecode_bucket:
            pc_bucket = pricecode_bucket
            pc_bucket_name = pc_bucket.bucket_name
        else:
            pc_bucket = None
            pc_bucket_name = ""

        # 1c. Access Price Code Vector Bucket
        if pricecode_vector_bucket:
            pcv_bucket = pricecode_vector_bucket
            pcv_bucket_name = pcv_bucket.bucket_name
        else:
            pcv_bucket = None
            pcv_bucket_name = ""

        # 2. Lambda Functions & Layer
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'boq-backend')
        async_dependencies_layer = build_async_aws_dependencies_layer(
            self,
            "DeletionDependenciesLayer",
            "Async AWS dependencies for deletion lambdas",
        )

        code_asset = _lambda.Code.from_asset(backend_dir, exclude=[
            "*.pyc", "__pycache__", ".venv", "venv", "tests",
            "data", "layers", "*.xlsx", "*.json", "scripts",
            "app", ".env", "*.egg-info"
        ])
        
        # ── WORKER LAMBDAS (do the actual work, invoked async) ──────────

        worker_datasheet = _lambda.Function(self, "WorkerDeleteDatasheetLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.delete_datasheet", 
            code=code_asset,
            layers=[async_dependencies_layer],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
                "S3_VECTORS_BUCKET": os.getenv("S3_VECTORS_BUCKET", "almabani-vectors"),
                "S3_VECTORS_INDEX_NAME": os.getenv("S3_VECTORS_INDEX_NAME", "almabani"),
            },
            timeout=Duration.seconds(120)
        )

        worker_pricecode = _lambda.Function(self, "WorkerDeletePriceCodeLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.delete_price_code_set",
            code=code_asset,
            layers=[],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
            },
            memory_size=2048,
            ephemeral_storage_size=Size.mebibytes(4096),
            timeout=Duration.minutes(15)
        )

        worker_pcv = _lambda.Function(self, "WorkerDeletePriceCodeVectorLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.delete_pricecode_vector_set",
            code=code_asset,
            layers=[async_dependencies_layer],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_VECTOR_BUCKET": pcv_bucket_name,
                "S3_VECTORS_BUCKET": os.getenv("S3_VECTORS_BUCKET", "almabani-vectors"),
            },
            memory_size=512,
            timeout=Duration.seconds(120)
        )

        # ── DISPATCHER LAMBDAS (fast, return 202, invoke workers async) ─

        dispatcher_datasheet = _lambda.Function(self, "DispatchDeleteDatasheetLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.dispatch_delete_datasheet",
            code=code_asset,
            layers=[],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "WORKER_LAMBDA_ARN_DATASHEET": worker_datasheet.function_arn,
            },
            timeout=Duration.seconds(10)
        )

        dispatcher_pricecode = _lambda.Function(self, "DispatchDeletePriceCodeLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.dispatch_delete_price_code_set",
            code=code_asset,
            layers=[],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
                "WORKER_LAMBDA_ARN_PRICECODE": worker_pricecode.function_arn,
            },
            timeout=Duration.seconds(10)
        )

        dispatcher_pcv = _lambda.Function(self, "DispatchDeletePriceCodeVectorLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.dispatch_delete_pricecode_vector_set",
            code=code_asset,
            layers=[],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_VECTOR_BUCKET": pcv_bucket_name,
                "WORKER_LAMBDA_ARN_PCV": worker_pcv.function_arn,
            },
            timeout=Duration.seconds(10)
        )

        # ── STATUS LAMBDA ───────────────────────────────────────────────

        status_lambda = _lambda.Function(self, "DeletionStatusLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.get_deletion_status",
            code=code_asset,
            layers=[],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
                "PRICECODE_VECTOR_BUCKET": pcv_bucket_name,
            },
            timeout=Duration.seconds(10)
        )

        # CloudFormation treats omitted Layers as "leave existing value".
        # Override non-worker lambdas to an explicit empty list so updates
        # remove stale broken layers from previously deployed functions.
        for fn in (
            worker_pricecode,
            dispatcher_datasheet,
            dispatcher_pricecode,
            dispatcher_pcv,
            status_lambda,
        ):
            fn.node.default_child.add_property_override("Layers", [])

        # 3. Permissions — S3
        bucket.grant_read_write(worker_datasheet)
        bucket.grant_write(dispatcher_datasheet)  # Write deletion-status markers
        _grant_status_marker_access(status_lambda, bucket)

        if pc_bucket:
            pc_bucket.grant_read_write(worker_pricecode)
            pc_bucket.grant_write(dispatcher_pricecode)
            _grant_status_marker_access(status_lambda, pc_bucket)

        if pcv_bucket:
            pcv_bucket.grant_read_write(worker_pcv)
            pcv_bucket.grant_write(dispatcher_pcv)
            _grant_status_marker_access(status_lambda, pcv_bucket)
            
        # Grant S3 Vectors data API access to workers
        s3v_policy = iam.PolicyStatement(
            actions=["s3vectors:*"],
            resources=["*"]
        )
        worker_datasheet.add_to_role_policy(s3v_policy)
        worker_pcv.add_to_role_policy(s3v_policy)

        # Grant dispatchers permission to invoke workers
        worker_datasheet.grant_invoke(dispatcher_datasheet)
        worker_pricecode.grant_invoke(dispatcher_pricecode)
        worker_pcv.grant_invoke(dispatcher_pcv)
        
        # 4. API Gateway
        api = apigw.RestApi(self, "DeletionApi",
            rest_api_name="Almabani Sheet Deletion",
            description="API for deleting datasheets and vectors",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization", "X-Amz-Date",
                               "X-Api-Key", "X-Amz-Security-Token"],
            )
        )

        # Gateway responses: add CORS headers to 4XX/5XX errors
        _cors_headers = {
            "Access-Control-Allow-Origin": "'*'",
            "Access-Control-Allow-Methods": "'DELETE,GET,OPTIONS'",
            "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
        }
        api.add_gateway_response("GW4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers=_cors_headers,
        )
        api.add_gateway_response("GW5XX",
            type=apigw.ResponseType.DEFAULT_5_XX,
            response_headers=_cors_headers,
        )

        # Resource: /files/sheets/{sheet_name} → dispatcher
        files = api.root.add_resource("files")
        sheets = files.add_resource("sheets")
        sheet_resource = sheets.add_resource("{sheet_name}")
        sheet_resource.add_method("DELETE", apigw.LambdaIntegration(dispatcher_datasheet))

        # Resource: /pricecode/sets/{set_name} → dispatcher
        pricecode = api.root.add_resource("pricecode")
        sets = pricecode.add_resource("sets")
        set_resource = sets.add_resource("{set_name}")
        set_resource.add_method("DELETE", apigw.LambdaIntegration(dispatcher_pricecode))

        # Resource: /pricecode-vector/sets/{set_name} → dispatcher
        pcv = api.root.add_resource("pricecode-vector")
        pcv_sets = pcv.add_resource("sets")
        pcv_set_resource = pcv_sets.add_resource("{set_name}")
        pcv_set_resource.add_method("DELETE", apigw.LambdaIntegration(dispatcher_pcv))

        # Resource: /deletion-status/{deletion_id} → status lambda
        deletion_status = api.root.add_resource("deletion-status")
        deletion_status_resource = deletion_status.add_resource("{deletion_id}")
        deletion_status_resource.add_method("GET", apigw.LambdaIntegration(status_lambda))

        # Outputs
        CfnOutput(self, "DeletionApiUrl", value=api.url)
