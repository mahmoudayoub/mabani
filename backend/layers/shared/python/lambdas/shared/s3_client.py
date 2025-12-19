"""S3 client utilities for image storage."""

import os
from datetime import datetime
from typing import Dict, Any
import boto3
import requests


class S3Client:
    """Client for S3 image storage operations."""

    def __init__(self):
        """Initialize S3 client."""
        self.s3_client = boto3.client("s3")
        self.bucket_name = os.environ.get("REPORTS_BUCKET", "mabani-reports-dev")
        self.region = os.environ.get("AWS_REGION", "eu-west-1")

    def upload_image(
        self, image_url: str, request_id: str, metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Download image from URL and upload to S3.

        Args:
            image_url: URL of the image to download
            request_id: Unique request identifier
            metadata: Additional metadata to attach

        Returns:
            Dictionary with S3 information
        """
        try:
            # Get Twilio credentials for authenticated download from Parameter Store
            ssm_client = boto3.client("ssm")
            parameter_path = os.environ.get("TWILIO_PARAMETER_PATH", "/mabani/twilio")

            try:
                response_params = ssm_client.get_parameters_by_path(
                    Path=parameter_path,
                    Recursive=True,
                    WithDecryption=True,
                )

                parameters = response_params.get("Parameters", [])

                # Convert parameters to dictionary
                credentials = {}
                for param in parameters:
                    key = param["Name"].split("/")[-1]
                    credentials[key] = param["Value"]

                account_sid = credentials.get("account_sid")
                auth_token = credentials.get("auth_token")
            except Exception as e:
                print(
                    f"Warning: Could not get Twilio credentials from Parameter Store: {e}"
                )
                account_sid = None
                auth_token = None

            # Download image from Twilio with authentication
            if account_sid and auth_token:
                from requests.auth import HTTPBasicAuth

                response = requests.get(
                    image_url, timeout=30, auth=HTTPBasicAuth(account_sid, auth_token)
                )
            else:
                # Try without auth (may fail)
                response = requests.get(image_url, timeout=30)

            response.raise_for_status()
            image_data = response.content

            # Determine file extension from content type
            content_type = response.headers.get("Content-Type", "image/jpeg")
            extension = self._get_extension_from_content_type(content_type)

            # Create S3 key with organized structure
            now = datetime.utcnow()
            s3_key = f"images/{now.year}/{now.month:02d}/{request_id}{extension}"

            # Sanitize metadata to ensure ASCII compliance (S3 requirement)
            sanitized_metadata = {}
            for k, v in metadata.items():
                if v:
                    # Replace non-ascii characters with equivalent or question mark
                    sanitized_metadata[k] = str(v).encode("ascii", "ignore").decode("ascii")

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_data,
                ContentType=content_type,
                Metadata=sanitized_metadata,
            )

            # Generate URLs
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            https_url = (
                f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            )

            return {
                "s3Bucket": self.bucket_name,
                "s3Key": s3_key,
                "s3Url": s3_url,
                "httpsUrl": https_url,
                "size": len(image_data),
                "contentType": content_type,
            }

        except Exception as error:
            print(f"Error uploading image to S3: {error}")
            raise

    def download_image(self, s3_key: str) -> bytes:
        """
        Download image from S3.

        Args:
            s3_key: S3 object key

        Returns:
            Image bytes
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response["Body"].read()
        except Exception as error:
            print(f"Error downloading image from S3: {error}")
            raise

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """
        Get file extension from content type.

        Args:
            content_type: MIME type

        Returns:
            File extension with dot
        """
        extensions = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        return extensions.get(content_type, ".jpg")
