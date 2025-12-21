"""AWS Bedrock client utilities for AI/ML operations."""

import os
import json
import base64
from typing import Dict, List
import boto3


class BedrockClient:
    """Client for AWS Bedrock AI/ML operations."""

    def __init__(self):
        """Initialize Bedrock client."""
        self.client = boto3.client(
            "bedrock-runtime", region_name=os.environ.get("AWS_REGION", "eu-west-1")
        )
        # Use Nova inference profiles (required for on-demand throughput)
        self.model_id = os.environ.get(
            "BEDROCK_MODEL_ID",
            "eu.amazon.nova-lite-v1:0",
        )
        # Optional: Use Nova Pro for more complex tasks (especially vision)
        self.vision_model_id = os.environ.get(
            "BEDROCK_VISION_MODEL_ID",
            "eu.amazon.nova-pro-v1:0",
        )
        print(f"BedrockClient initialized with model_id: {self.model_id}")
        print(f"BedrockClient initialized with vision_model_id: {self.vision_model_id}")

    def rewrite_description(
        self, original_description: str, timestamp: str = None
    ) -> str:
        """
        Rewrite incident description for clarity and professionalism.

        Args:
            original_description: Original user-provided description
            timestamp: ISO 8601 timestamp when the report was submitted

        Returns:
            Rewritten description
        """
        # Format timestamp for the prompt if provided
        timestamp_info = ""
        if timestamp:
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%B %d, %Y, at %I:%M %p UTC")
                timestamp_info = f"\nReport submitted: {formatted_date}"
            except Exception as e:
                print(f"Warning: Could not parse timestamp: {e}")
                timestamp_info = f"\nReport submitted: {timestamp}"

        prompt = f"""You are a Health & Safety documentation specialist. Rewrite the following incident/quality report description to be clear, professional, and structured while maintaining all factual details.

Original Description: {original_description}{timestamp_info}

Requirements:
- Keep all facts unchanged
- Use the provided submission date/time if describing when the incident occurred (do NOT invent or hallucinate dates)
- If no specific time is mentioned in the original description, use the submission timestamp as the incident time
- Improve grammar and clarity
- Use professional language
- Maximum 3 sentences
- Focus on what, where, when, how

Rewritten Description:"""

        try:
            response = self._invoke_model(prompt, max_tokens=300, temperature=0.3)
            rewritten = response.strip()
            return rewritten if rewritten else original_description
        except Exception as error:
            print(f"Error rewriting description: {error}")
            return original_description

    def caption_image(
        self, image_data: bytes, description: str, report_type: str = "HS"
    ) -> str:
        """
        Generate caption for image using vision model.

        Args:
            image_data: Image bytes
            description: Context description
            report_type: "HS" or "QUALITY"

        Returns:
            Image caption
        """
        focus_area = (
            "visible hazards or safety concerns"
            if report_type == "HS"
            else "quality issues or defects"
        )

        prompt = f"""Analyze this Health & Safety / Quality report image and provide a detailed description.

Context: {description}

Focus on:
- {focus_area}
- Equipment or materials present
- Environmental conditions
- People and PPE usage (if applicable)

Provide a concise 2-3 sentence caption describing what you observe in the image."""

        try:
            # Encode image to base64
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            response = self._invoke_vision_model(
                prompt=prompt,
                image_base64=image_base64,
                max_tokens=300,
                temperature=0.3,
            )

            return response.strip()
        except Exception as error:
            print(f"Error captioning image: {error}")
            return "Unable to analyze image at this time."

    def classify_severity(self, description: str, image_caption: str) -> Dict[str, str]:
        """
        Classify incident severity level.

        Args:
            description: Rewritten description
            image_caption: Image caption

        Returns:
            Dictionary with severity and reason
        """
        prompt = f"""Classify the severity of this Health & Safety / Quality incident:

Description: {description}
Visual Analysis: {image_caption}

Classify as one of: HIGH, MEDIUM, LOW

HIGH: Immediate danger to life or serious injury risk
MEDIUM: Potential injury risk or equipment damage
LOW: Minor issues or preventive maintenance

Respond in JSON format:
{{"severity": "HIGH|MEDIUM|LOW", "reason": "brief explanation"}}

Classification:"""

        try:
            response = self._invoke_model(prompt, max_tokens=200, temperature=0.2)
            # Extract JSON from response (handle cases where AI adds extra text)
            response_text = response.strip()

            # Try to find JSON in the response
            if "{" in response_text and "}" in response_text:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                json_str = response_text[start:end]
                result = json.loads(json_str)
            else:
                result = json.loads(response_text)

            return {
                "severity": result.get("severity", "MEDIUM"),
                "reason": result.get("reason", ""),
            }
        except Exception as error:
            print(f"Error classifying severity: {error}")
            print(f"Response was: {response if 'response' in locals() else 'N/A'}")
            return {"severity": "MEDIUM", "reason": "Unable to classify"}

    def classify_observation_type(
        self, description: str, image_caption: str
    ) -> str:
        """
        Classify the high-level observation type.
        
        Args:
            description: Incident description
            image_caption: Image caption
            
        Returns:
            Observation Type string
        """
        taxonomy = """
- Unsafe Act
- Unsafe Condition
- Positive Observation
- Environmental Protection
- Improvement Opportunity
"""
        prompt = f"""Classify this report into exactly ONE of the following Observation Types:

Description: {description}
Visual Analysis: {image_caption}

Types:
{taxonomy}

Return ONLY the classification name exactly as listed above. Do not include "Classification:" or any other text.
Classification:"""

        try:
            response = self._invoke_model(prompt, max_tokens=50, temperature=0.1)
            return response.strip()
        except Exception as error:
            print(f"Error classifying observation type: {error}")
            return "Unsafe Condition"

    def classify_hazard_type(
        self,
        description: str,
        image_caption: str,
        severity: str,
        report_type: str = "HS",
        taxonomy: str = None
    ) -> List[str]:
        """
        Identify hazard type(s) for the incident.

        Args:
            description: Rewritten description
            image_caption: Image caption
            severity: Severity level
            report_type: "HS" or "QUALITY"
            taxonomy: Optional taxonomy string to use.

        Returns:
            List of hazard types
        """
        if taxonomy:
            # Use provided taxonomy
            pass
        elif report_type == "HS":
            taxonomy = """
A Safety:
A1 Confined Spaces
... (fallback defaults or empty if managed by config)
... Use provided taxonomy mostly.
A41 Others
"""
        else:
            taxonomy = """
- Material Defect
- Workmanship Issue
- Specification Deviation
- Dimensional Tolerance
- Surface Finish
- Installation Error
- Other
"""

        prompt = f"""Identify the specific Hazard Category code(s) for this incident.

Description: {description}
Visual Analysis: {image_caption}
Severity: {severity}

Select the most relevant category from:
{taxonomy}

Return as a strict JSON array of strings. Do not include markdown formatting or explanations.
Example: ["A15 Working at Height"]

Classification:"""

        try:
            response = self._invoke_model(prompt, max_tokens=150, temperature=0.2)
            # Extract JSON from response (handle cases where AI adds extra text)
            response_text = response.strip()

            # Try to find JSON array in the response
            if "[" in response_text and "]" in response_text:
                start = response_text.index("[")
                end = response_text.rindex("]") + 1
                json_str = response_text[start:end]
                hazard_types = json.loads(json_str)
            else:
                # Fallback if no JSON found - try to just take the text if it looks like a category
                if any(x in response_text for x in ["A", "B", "C"]) and len(response_text) < 50:
                     hazard_types = [response_text]
                else: 
                     hazard_types = json.loads(response_text)

            return hazard_types if isinstance(hazard_types, list) else [hazard_types]
        except Exception as error:
            print(f"Error classifying hazard type: {error}")
            print(f"Response was: {response if 'response' in locals() else 'N/A'}")
            return ["A41 Others"]

    def generate_control_measure(
        self,
        description: str,
        image_caption: str,
        severity: str,
        hazard_types: List[str],
        project_name: str,
    ) -> Dict[str, str]:
        """
        Generate control measure recommendation with reference.

        Args:
            description: Rewritten description
            image_caption: Image caption
            severity: Severity level
            hazard_types: List of hazard types
            project_name: Project name

        Returns:
            Dictionary with control measure and reference
        """
        prompt = f"""Based on this Health & Safety incident, provide ONE concise control measure recommendation with reference:

Description: {description}
Visual Analysis: {image_caption}
Severity: {severity}
Hazard Types: {", ".join(hazard_types)}
Project: {project_name}

Provide:
1. A single, specific, and actionable control measure (1-2 sentences) directly addressing the hazard described. Avoid generic "inspect" or "assess" advice if a clear hazard is visible.
2. Reference to relevant standard or regulation.

Respond in strict JSON format:
{{"controlMeasure": "Specific action to take", "reference": "Section X.Y"}}

Response:"""

        try:
            response = self._invoke_model(prompt, max_tokens=250, temperature=0.2)
            # Extract JSON from response (handle cases where AI adds extra text)
            response_text = response.strip()

            # Try to find JSON in the response
            if "{" in response_text and "}" in response_text:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                json_str = response_text[start:end]
                result = json.loads(json_str)
            else:
                result = json.loads(response_text)

            return {
                "controlMeasure": result.get("controlMeasure", ""),
                "reference": result.get("reference", ""),
            }
        except Exception as error:
            print(f"Error generating control measure: {error}")
            print(f"Response was: {response if 'response' in locals() else 'N/A'}")
            return {
                "controlMeasure": "Conduct immediate safety assessment and implement corrective actions.",
                "reference": "General safety guidelines",
            }

    def _invoke_model(
        self, prompt: str, max_tokens: int = 500, temperature: float = 0.3
    ) -> str:
        """
        Invoke Bedrock text model (supports both Claude and Nova).

        Args:
            prompt: Prompt text
            max_tokens: Maximum tokens to generate
            temperature: Temperature for sampling

        Returns:
            Model response text
        """
        # Detect model type and format request accordingly
        if "anthropic.claude" in self.model_id:
            # Claude format
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                }
            )
        else:
            # Nova format (Converse API)
            body = json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {
                        "maxTokens": max_tokens,
                        "temperature": temperature,
                    },
                }
            )

        response = self.client.invoke_model(modelId=self.model_id, body=body)

        response_body = json.loads(response["body"].read())

        # Parse response based on model type
        if "anthropic.claude" in self.model_id:
            return response_body["content"][0]["text"]
        else:
            # Nova response format
            return response_body["output"]["message"]["content"][0]["text"]

    def _invoke_vision_model(
        self,
        prompt: str,
        image_base64: str,
        max_tokens: int = 300,
        temperature: float = 0.3,
    ) -> str:
        """
        Invoke Bedrock vision model (supports both Claude and Nova).

        Args:
            prompt: Prompt text
            image_base64: Base64-encoded image
            max_tokens: Maximum tokens to generate
            temperature: Temperature for sampling

        Returns:
            Model response text
        """
        # Use vision-specific model if set, otherwise use default
        model_id = self.vision_model_id or self.model_id

        # Detect model type and format request accordingly
        if "anthropic.claude" in model_id:
            # Claude format
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": image_base64,
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                }
            )
        else:
            # Nova format (Converse API with image)
            body = json.dumps(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "image": {
                                        "format": "jpeg",
                                        "source": {"bytes": image_base64},
                                    }
                                },
                                {"text": prompt},
                            ],
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": max_tokens,
                        "temperature": temperature,
                    },
                }
            )

        response = self.client.invoke_model(modelId=model_id, body=body)

        response_body = json.loads(response["body"].read())

        # Parse response based on model type
        if "anthropic.claude" in model_id:
            return response_body["content"][0]["text"]
        else:
            # Nova response format
            return response_body["output"]["message"]["content"][0]["text"]
