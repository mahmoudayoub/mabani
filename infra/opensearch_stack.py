from aws_cdk import (
    Stack,
    aws_opensearchserverless as aoss,
    CfnOutput
)
from constructs import Construct

class OpenSearchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        collection_name = "almabani-vectors"

        # 1. Encryption Policy
        encryption_policy = aoss.CfnSecurityPolicy(
            self, "VectorSearchEncryptionPolicy",
            name=f"{collection_name}-encryption",
            type="encryption",
            policy=f'''{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/{collection_name}"]
                    }}
                ],
                "AWSOwnedKey": true
            }}'''
        )

        # 2. Network Policy (Public access since we're Serverless/Fargate without strict VPC routing currently)
        # In a production VPC setup, this would be restricted to VPC endpoints
        network_policy = aoss.CfnSecurityPolicy(
            self, "VectorSearchNetworkPolicy",
            name=f"{collection_name}-network",
            type="network",
            policy=f'''[{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/{collection_name}"]
                    }},
                    {{
                        "ResourceType": "dashboard",
                        "Resource": ["collection/{collection_name}"]
                    }}
                ],
                "AllowFromPublic": true
            }}]'''
        )

        # 3. Data Access Policy (Allow full access to the account root for now, 
        # Fargate Task Roles and Lambda Execution Roles will inherit from this account or be added specifically)
        data_policy = aoss.CfnAccessPolicy(
            self, "VectorSearchDataAccessPolicy",
            name=f"{collection_name}-access",
            type="data",
            policy=f'''[{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/{collection_name}"],
                        "Permission": [
                            "aoss:CreateCollectionItems",
                            "aoss:DeleteCollectionItems",
                            "aoss:UpdateCollectionItems",
                            "aoss:DescribeCollectionItems"
                        ]
                    }},
                    {{
                        "ResourceType": "index",
                        "Resource": ["index/{collection_name}/*"],
                        "Permission": [
                            "aoss:CreateIndex",
                            "aoss:DeleteIndex",
                            "aoss:UpdateIndex",
                            "aoss:DescribeIndex",
                            "aoss:ReadDocument",
                            "aoss:WriteDocument"
                        ]
                    }}
                ],
                "Principal": [
                    "arn:aws:iam::{self.account}:root"
                ]
            }}]'''
        )

        # 4. The Collection itself
        self.collection = aoss.CfnCollection(
            self, "VectorSearchCollection",
            name=collection_name,
            type="VECTORSEARCH"
        )

        # Ensure policies are created before the collection
        self.collection.add_dependency(encryption_policy)
        self.collection.add_dependency(network_policy)
        self.collection.add_dependency(data_policy)

        # Output the endpoint to be used by the application
        self.collection_endpoint = self.collection.attr_collection_endpoint
        
        CfnOutput(
            self, "CollectionEndpoint",
            value=self.collection_endpoint,
            description="OpenSearch Serverless Collection Endpoint"
        )
