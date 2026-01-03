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
        # Prepare metadata
        metadata = {
            "mode": mode,
            "filename": filename
        }

        # Add sheet selection metadata if present
        # New approach: Simple list of sheet names from available_sheets.json
        sheet_names = query_params.get("sheetNames")
        if sheet_names:
            metadata["sheet-names"] = sheet_names

        # Generate presigned URL for PUT operation
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": FILE_PROCESSING_BUCKET,
                "Key": key,
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Metadata": metadata
            },
            ExpiresIn=300  # 5 minutes
        )

        return create_response(200, {
            "uploadUrl": presigned_url,
            "key": key,
            "bucket": FILE_PROCESSING_BUCKET
        })

    except Exception as e:
        return create_error_response(500, str(e))


@with_error_handling
def list_available_sheets(event, context):
    """List available parsed sheets from the S3 registry file."""
    # Note: This is an open endpoint (authenticated users), 
    # effectively a public registry for all users of the app.
    

    
    try:
        response = s3_client.get_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key="metadata/available_sheets.json"
        )
        content = json.loads(response["Body"].read())
        return create_response(200, {"sheets": content.get("sheets", [])})
        
    except s3_client.exceptions.NoSuchKey:
        # Registry file doesn't exist yet
        return create_response(200, {"sheets": []})
    except Exception as e:
        return create_error_response(500, f"Failed to list sheets: {str(e)}")

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


@with_error_handling
def get_estimate(event, context):
    """
    Get processing estimate for a file.
    Path parameter: filename (without extension)
    """
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    # Remove extension if provided
    filename_base = filename.replace('.xlsx', '').replace('_filled', '')
    estimate_key = f"estimates/{filename_base}_estimate.json"
    
    try:
        response = s3_client.get_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key=estimate_key
        )
        estimate_data = json.loads(response["Body"].read())
        return create_response(200, estimate_data)
        
    except s3_client.exceptions.NoSuchKey:
        return create_response(404, {"error": "Estimate not found"})
    except Exception as e:
        return create_error_response(500, f"Failed to get estimate: {str(e)}")


@with_error_handling
def check_file_exists(event, context):
    """
    Check if a file exists in S3.
    Path parameter: filepath (e.g., 'output/fills/filename.xlsx')
    """
    path_params = event.get("pathParameters", {}) or {}
    filepath = path_params.get("filepath")
    
    if not filepath:
        return create_error_response(400, "Missing required parameter: filepath")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    try:
        s3_client.head_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key=filepath
        )
        return create_response(200, {"exists": True})
        
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return create_response(200, {"exists": False})
        return create_error_response(500, f"Failed to check file: {str(e)}")
    except Exception as e:
        return create_error_response(500, f"Failed to check file: {str(e)}")


@with_error_handling
def list_active_jobs(event, context):
    """
    List all active jobs by checking estimates/ directory.
    Should only return 0 or 1 file at a time.
    """
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=FILE_PROCESSING_BUCKET,
            Prefix="estimates/"
        )
        
        active_jobs = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                # Skip the folder itself
                if key == "estimates/":
                    continue
                
                # Get the estimate data
                try:
                    estimate_response = s3_client.get_object(
                        Bucket=FILE_PROCESSING_BUCKET,
                        Key=key
                    )
                    estimate_data = json.loads(estimate_response["Body"].read())
                    active_jobs.append(estimate_data)
                except Exception as e:
                    print(f"Error reading estimate {key}: {str(e)}")
                    continue
        
        return create_response(200, {
            "active_jobs": active_jobs,
            "has_active_job": len(active_jobs) > 0
        })
        
    except Exception as e:
        return create_error_response(500, f"Failed to list active jobs: {str(e)}")


@with_error_handling
def delete_estimate(event, context):
    """
    Delete estimate file when job completes.
    Path parameter: filename
    """
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    # Remove extension if provided
    filename_base = filename.replace('.xlsx', '').replace('_filled', '')
    estimate_key = f"estimates/{filename_base}_estimate.json"
    
    try:
        s3_client.delete_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key=estimate_key
        )
        return create_response(200, {"deleted": True, "key": estimate_key})
        
    except Exception as e:
        return create_error_response(500, f"Failed to delete estimate: {str(e)}")


@with_error_handling
def check_task_status(event, context):
    """
    Check ECS Fargate task status.
    Query params: task_arn, cluster_name
    """
    query_params = event.get("queryStringParameters", {}) or {}
    task_arn = query_params.get("task_arn")
    cluster_name = query_params.get("cluster_name")
    
    if not task_arn or not cluster_name:
        return create_error_response(400, "Missing task_arn or cluster_name")
    
    try:
        ecs = boto3.client('ecs')
        response = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=[task_arn]
        )
        
        if not response['tasks']:
            return create_response(404, {"error": "Task not found"})
        
        task = response['tasks'][0]
        status = task['lastStatus']
        
        result = {
            "status": status,
            "stopped_reason": task.get('stoppedReason', ''),
            "exit_code": None,
            "is_running": status in ['PENDING', 'RUNNING'],
            "is_complete": status == 'STOPPED',
            "is_success": False
        }
        
        if status == 'STOPPED':
            containers = task.get('containers', [])
            if containers:
                exit_code = containers[0].get('exitCode')
                result['exit_code'] = exit_code
                result['is_success'] = exit_code == 0
        
        return create_response(200, result)
        
    except Exception as e:
        return create_error_response(500, f"Failed to check task status: {str(e)}")


def get_s3_client():
    return boto3.client("s3")
