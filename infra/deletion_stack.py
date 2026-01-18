
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_s3 as s3,
    Duration,
    CfnOutput
)
from constructs import Construct
import os

class DeletionStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
                 shared_bucket: s3.IBucket = None,
                 pricecode_bucket: s3.IBucket = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Access Shared Bucket
        if shared_bucket:
            bucket = shared_bucket
        else:
            # Fallback if not passed (not recommended)
            bucket = s3.Bucket.from_bucket_name(self, "ImportedBucket", "almabanistack-almabanidata...")

        # 1b. Access Price Code Bucket
        if pricecode_bucket:
            pc_bucket = pricecode_bucket
            pc_bucket_name = pc_bucket.bucket_name
        else:
            pc_bucket = None
            pc_bucket_name = ""

        # 2. Lambda Function & Layer
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend')
        layer_dir = os.path.join(os.path.dirname(__file__), 'layers', 'deletion_dependencies')
        
        dependencies_layer = _lambda.LayerVersion(self, "DeletionDependenciesLayer",
            code=_lambda.Code.from_asset(layer_dir),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="Dependencies for deletion lambda (pinecone-client, boto3)"
        )
        
        deletion_lambda = _lambda.Function(self, "DeleteDatasheetLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.delete_datasheet", 
            code=_lambda.Code.from_asset(backend_dir),
            layers=[dependencies_layer],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
                "PINECONE_API_KEY": os.getenv("PINECONE_API_KEY", ""),
                "PINECONE_INDEX_NAME": os.getenv("PINECONE_INDEX_NAME", "almabani-1")
            },
            timeout=Duration.seconds(30)
        )

        # 2b. Price Code Deletion Lambda (Separate Function for specific handler)
        # Using the SAME code asset but different handler
        pc_deletion_lambda = _lambda.Function(self, "DeletePriceCodeLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="delete_handler.delete_price_code_set",
            code=_lambda.Code.from_asset(backend_dir),
            layers=[dependencies_layer],
            environment={
                "FILE_PROCESSING_BUCKET": bucket.bucket_name,
                "PRICECODE_BUCKET": pc_bucket_name,
                "PINECONE_API_KEY": os.getenv("PINECONE_API_KEY", ""),
                "PINECONE_INDEX_NAME": os.getenv("PINECONE_INDEX_NAME", "almabani-1"),
                "PRICECODE_INDEX_NAME": os.getenv("PRICECODE_INDEX_NAME", "almabani-pricecode")
            },
            timeout=Duration.seconds(30)
        )

        # 3. Permissions
        bucket.grant_read_write(deletion_lambda)
        if pc_bucket:
            pc_bucket.grant_read_write(pc_deletion_lambda)
        
        # 4. API Gateway
        api = apigw.RestApi(self, "DeletionApi",
            rest_api_name="Almabani Sheet Deletion",
            description="API for deleting datasheets from Pinecone and Registry",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS
            )
        )

        # Resource: /files/sheets/{sheet_name}
        files = api.root.add_resource("files")
        sheets = files.add_resource("sheets")
        sheet_resource = sheets.add_resource("{sheet_name}")
        sheet_resource.add_method("DELETE", apigw.LambdaIntegration(deletion_lambda))

        # Resource: /pricecode/sets/{set_name}
        pricecode = api.root.add_resource("pricecode")
        sets = pricecode.add_resource("sets")
        set_resource = sets.add_resource("{set_name}")
        set_resource.add_method("DELETE", apigw.LambdaIntegration(pc_deletion_lambda))

        # Outputs
        CfnOutput(self, "DeletionApiUrl", value=api.url)
