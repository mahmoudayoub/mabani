"""Dynamic Bedrock client that supports multiple foundation models."""

import json
import os
from typing import Dict, List, Optional

import boto3


class DynamicBedrockClient:
    """Invoke Bedrock models with minimal configuration."""

    # Supported Regions pulled from
    # https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
    # Supported Regions and Cross-Region Inference Profiles
    # Based on AWS Bedrock Documentation
    MODEL_REGIONS: Dict[str, List[str]] = {
        # Amazon Nova Pro
        "amazon.nova-pro-v1:0": [
            # Single Region
            "us-east-1",
            "me-central-1",
            # Cross Region Profiles
            "us.amazon.nova-pro-v1:0",  # Supported in us-east-1, etc.
            "eu.amazon.nova-pro-v1:0",  # Supported in eu-central-1, etc.
        ],
        # Amazon Nova Lite
        "amazon.nova-lite-v1:0": [
            # Single Region
            "us-east-1",
            "me-central-1",
            # Cross Region Profiles
            "us.amazon.nova-lite-v1:0",
            "eu.amazon.nova-lite-v1:0",
        ],
        # Amazon Nova Micro
        "amazon.nova-micro-v1:0": [
            # Single Region
            "us-east-1",
            # Cross Region Profiles
            "us.amazon.nova-micro-v1:0",  # Supported in me-central-1 (via US profile)
            "eu.amazon.nova-micro-v1:0",  # Supported in eu-central-1
        ],
    }

    # Profile mapping: Maps a base model ID + region to the correct effective ID
    # If a region supports Single Region, we use base ID.
    # If it only supports Cross Region, we switch to the profile ID.
    # For me-central-1 + Nova Micro: It only supports Cross Region (via US profile).
    INFERENCE_PROFILE_MAP = {
        "amazon.nova-pro-v1:0": {
            "eu-central-1": "eu.amazon.nova-pro-v1:0",  # EU Profile
        },
        "amazon.nova-lite-v1:0": {
            "eu-central-1": "eu.amazon.nova-lite-v1:0",  # EU Profile
        },
        "amazon.nova-micro-v1:0": {
            "eu-central-1": "eu.amazon.nova-micro-v1:0",  # EU Profile
            "me-central-1": "us.amazon.nova-micro-v1:0",  # Fallback to US Profile (common for ME)
        },
    }

    ALLOWED_REGIONS = {"us-east-1", "eu-central-1", "me-central-1"}

    def __init__(self):
        self.default_region = os.environ.get("AWS_REGION", "us-east-1")
        self.clients: Dict[str, object] = {}

    def _get_client(self, region: str):
        if region not in self.clients:
            self.clients[region] = boto3.client(
                "bedrock-runtime", region_name=region or self.default_region
            )
        return self.clients[region]

    def _get_model_region(self, model_id: str) -> str:
        """
        Determine the AWS region to use for a given model.
        Prioritizes current region if supported, else falls back to Allowed Regions.
        """
        overrides = os.environ.get("BEDROCK_MODEL_REGION_OVERRIDES")
        if overrides:
            try:
                override_map = json.loads(overrides)
                if model_id in override_map:
                    return override_map[model_id]
            except Exception as error:
                print(f"Failed to parse BEDROCK_MODEL_REGION_OVERRIDES: {error}")

        # If current region is in ALLOWED_REGIONS, prefer it
        current_region = os.environ.get("AWS_REGION")
        if current_region in self.ALLOWED_REGIONS:
            return current_region

        # Fallback logic: Pick first allowed region that supports the model (heuristically)
        # For Nova models, we know they work in all 3 allowed regions (via single or profile)
        # So we default to us-east-1 if current is not allowed
        return "us-east-1"

    def _get_effective_model_id(self, model_id: str, region: str) -> str:
        """
        Resolve the model ID to an Inference Profile ID if required by the region.
        """
        if model_id in self.INFERENCE_PROFILE_MAP:
            profile_map = self.INFERENCE_PROFILE_MAP[model_id]
            if region in profile_map:
                return profile_map[region]
        return model_id

    def _invoke_claude(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "messages": [{"role": "user", "content": message}],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["content"][0]["text"]

    def _invoke_llama(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "prompt": message,
                "max_gen_len": params["max_tokens"],
                "temperature": params["temperature"],
                "top_p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["generation"]

    def _invoke_titan(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "inputText": message,
                "textGenerationConfig": {
                    "maxTokenCount": params["max_tokens"],
                    "temperature": params["temperature"],
                    "topP": params["top_p"],
                },
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["results"][0]["outputText"]

    def _invoke_nova(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": message}]}],
                "inferenceConfig": {
                    "max_new_tokens": params["max_tokens"],
                    "temperature": params["temperature"],
                    "top_p": params["top_p"],
                },
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["output"]["message"]["content"][0]["text"]

    def _invoke_mistral(
        self, *, message: str, model_id: str, region: str, params: Dict
    ):
        body = json.dumps(
            {
                "prompt": f"<s>[INST] {message} [/INST]",
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "top_p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["outputs"][0]["text"]

    def _invoke_ai21(self, *, message: str, model_id: str, region: str, params: Dict):
        if "jamba" in model_id.lower():
            body = json.dumps(
                {
                    "messages": [{"role": "user", "content": message}],
                    "max_tokens": params["max_tokens"],
                    "temperature": params["temperature"],
                    "top_p": params["top_p"],
                }
            )
            response = self._get_client(region).invoke_model(
                modelId=model_id, body=body
            )
            payload = json.loads(response["body"].read())
            return payload["choices"][0]["message"]["content"]

        body = json.dumps(
            {
                "prompt": message,
                "maxTokens": params["max_tokens"],
                "temperature": params["temperature"],
                "topP": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["completions"][0]["data"]["text"]

    def _invoke_cohere(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "message": message,
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["text"]

    def _invoke_openai(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": message}],
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "top_p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["choices"][0]["message"]["content"]

    def _invoke_deepseek(
        self, *, message: str, model_id: str, region: str, params: Dict
    ):
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": message}],
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "top_p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["choices"][0]["message"]["content"]

    def _invoke_qwen(self, *, message: str, model_id: str, region: str, params: Dict):
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": message}],
                "max_tokens": params["max_tokens"],
                "temperature": params["temperature"],
                "top_p": params["top_p"],
            }
        )
        response = self._get_client(region).invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["choices"][0]["message"]["content"]

    def invoke_model(
        self,
        *,
        prompt: str,
        model_id: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
    ) -> str:
        region = self._get_model_region(model_id)

        # Apply effective model ID (e.g. switch to inference profile if needed)
        effective_model_id = self._get_effective_model_id(model_id, region)

        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }

        if "anthropic.claude" in effective_model_id:
            return self._invoke_claude(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "meta.llama" in effective_model_id:
            return self._invoke_llama(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "amazon.titan" in effective_model_id:
            return self._invoke_titan(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "amazon.nova" in effective_model_id:
            return self._invoke_nova(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "mistral" in effective_model_id:
            return self._invoke_mistral(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "ai21" in effective_model_id:
            return self._invoke_ai21(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "cohere" in effective_model_id:
            return self._invoke_cohere(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "openai" in effective_model_id:
            return self._invoke_openai(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "deepseek" in effective_model_id:
            return self._invoke_deepseek(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )
        if "qwen" in effective_model_id:
            return self._invoke_qwen(
                message=prompt,
                model_id=effective_model_id,
                region=region,
                params=params,
            )

        raise ValueError(f"Unsupported Bedrock model: {effective_model_id}")
