import os
import boto3
import json
from lambdas.shared.lambda_helpers import create_response, create_error_response, with_error_handling

s3_client = boto3.client("s3")
FILE_PROCESSING_BUCKET = os.environ.get("FILE_PROCESSING_BUCKET")

@with_error_handling
def generate_upload_url(event, context):
    """
    Generates a presigned URL for uploading a file to S3.
    Query params:
        - filename: Name of the file (required)
        - mode: 'fill' or 'parse' (required)
    """
    query_params = event.get("queryStringParameters", {}) or {}
    filename = query_params.get("filename")
    mode = query_params.get("mode")

    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    
    if mode not in ["fill", "parse"]:
        return create_error_response(400, "Invalid mode. Must be 'fill' or 'parse'")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")

    key = f"input/{mode}/{filename}"

    try:
        # Generate presigned URL for PUT operation
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": FILE_PROCESSING_BUCKET,
                "Key": key,
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
            ExpiresIn=300  # 5 minutes
        )

        return create_response(200, {
            "uploadUrl": presigned_url,
            "key": key,
            "bucket": FILE_PROCESSING_BUCKET
        })

    except Exception as e:
        return create_error_response(500, "Failed to generate upload URL", e)

@with_error_handling
def list_output_files(event, context):
    """
    Lists files in the output directory and returns download URLs.
    """
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")

    prefix = "output/fills/"

    try:
        response = s3_client.list_objects_v2(
            Bucket=FILE_PROCESSING_BUCKET,
            Prefix=prefix
        )

        files = []
        if "Contents" in response:
            # Sort by LastModified descending
            sorted_contents = sorted(response["Contents"], key=lambda x: x["LastModified"], reverse=True)
            
            for obj in sorted_contents:
                key = obj["Key"]
                # Skip the folder itself if it appears
                if key == prefix:
                    continue
                
                # Generate presigned download URL
                download_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": FILE_PROCESSING_BUCKET,
                        "Key": key
                    },
                    ExpiresIn=3600  # 1 hour
                )

                files.append({
                    "key": key,
                    "filename": key.replace(prefix, ""),
                    "lastModified": obj["LastModified"].isoformat(),
                    "size": obj["Size"],
                    "downloadUrl": download_url
                })

        return create_response(200, {"files": files})

    except Exception as e:
        return create_error_response(500, "Failed to list output files", e)
