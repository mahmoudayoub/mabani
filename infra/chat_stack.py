"""
Chat API Stack - CDK infrastructure for the chatbot backend.

Creates:
- Lambda function for chat handling
- API Gateway with POST /chat endpoint
- CORS configuration
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct
import os


class ChatStack(Stack):
    """CDK Stack for Chat API."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get environment variables
        openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        pinecone_api_key = os.environ.get('PINECONE_API_KEY', '')
        
        # Lambda Layer for dependencies (reuse from DeletionStack if available)
        deps_layer = _lambda.LayerVersion(
            self, "ChatDepsLayer",
            code=_lambda.Code.from_asset("backend/layers/chat_deps"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            description="Dependencies for Chat Lambda (openai, pinecone)"
        )
        
        # Chat Lambda Function
        chat_lambda = _lambda.Function(
            self, "ChatHandler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="chat_handler.handler",
            code=_lambda.Code.from_asset("backend", exclude=[
                "*.pyc", "__pycache__", ".venv", "venv", "tests",
                "data", "layers", "*.xlsx", "*.json"
            ]),
            timeout=Duration.seconds(60),
            memory_size=512,
            layers=[deps_layer],
            environment={
                "OPENAI_API_KEY": openai_api_key,
                "PINECONE_API_KEY": pinecone_api_key,
                "PINECONE_INDEX_NAME": os.environ.get('PINECONE_INDEX_NAME', 'almabani-1'),
                "PRICECODE_INDEX_NAME": os.environ.get('PRICECODE_INDEX_NAME', 'almabani-pricecode'),
                "OPENAI_CHAT_MODEL": os.environ.get('OPENAI_CHAT_MODEL', 'gpt-4o-mini'),
            }
        )
        
        # API Gateway with CORS
        api = apigw.RestApi(
            self, "ChatApi",
            rest_api_name="Almabani Chat API",
            description="Natural language interface for price codes and unit rates",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=["POST", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization"],
            ),
            deploy_options=apigw.StageOptions(stage_name="prod")
        )
        
        # Add Gateway Response for 5xx errors with CORS headers
        # This ensures timeout (504) and other server errors include CORS headers
        api.add_gateway_response(
            "GatewayResponse5XX",
            type=apigw.ResponseType.DEFAULT_5_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,Authorization'",
                "Access-Control-Allow-Methods": "'POST,OPTIONS'"
            }
        )
        
        # POST /chat endpoint
        chat_resource = api.root.add_resource("chat")
        chat_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                chat_lambda,
                proxy=True
            )
        )
        
        # Outputs
        CfnOutput(
            self, "ChatApiUrl",
            value=f"{api.url}chat",
            description="Chat API endpoint URL"
        )
        
        CfnOutput(
            self, "ChatApiEndpoint",
            value=api.url,
            description="Chat API base URL"
        )
