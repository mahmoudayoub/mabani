import os
import boto3
import json
from lambdas.shared.lambda_helpers import create_response, create_error_response, with_error_handling

s3_client = boto3.client("s3")
FILE_PROCESSING_BUCKET = os.environ.get("FILE_PROCESSING_BUCKET")
PRICECODE_BUCKET = os.environ.get("PRICECODE_BUCKET")

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
    from urllib.parse import unquote
    
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    # URL decode the filename (handles %20 -> space)
    filename = unquote(filename)
    
    # Remove extension if provided
    filename_base = filename.replace('.xlsx', '').replace('_filled', '')
    estimate_key = f"estimates/{filename_base}_estimate.json"
    
    print(f"[DEBUG] get_estimate: filename={filename}, key={estimate_key}")
    
    try:
        response = s3_client.get_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key=estimate_key
        )
        estimate_data = json.loads(response["Body"].read())
        print(f"[DEBUG] get_estimate: found estimate, complete={estimate_data.get('complete')}")
        return create_response(200, estimate_data)
        
    except s3_client.exceptions.NoSuchKey:
        print(f"[DEBUG] get_estimate: file not found at {estimate_key}")
        return create_response(404, {"error": "Estimate not found"})
    except Exception as e:
        print(f"[DEBUG] get_estimate: error {str(e)}")
        return create_error_response(500, f"Failed to get estimate: {str(e)}")


@with_error_handling
def check_file_exists(event, context):
    """
    Check if a file exists in S3.
    Path parameter: filepath (e.g., 'output/fills/filename.xlsx')
    """
    path_params = event.get("pathParameters", {}) or {}
    filepath = path_params.get("filepath")
    
    # DEBUG: Log what we're checking
    print(f"[DEBUG] check_file_exists called")
    print(f"[DEBUG] filepath parameter: {filepath}")
    print(f"[DEBUG] bucket: {FILE_PROCESSING_BUCKET}")
    
    if not filepath:
        return create_error_response(400, "Missing required parameter: filepath")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    try:
        print(f"[DEBUG] Checking S3: s3://{FILE_PROCESSING_BUCKET}/{filepath}")
        s3_client.head_object(
            Bucket=FILE_PROCESSING_BUCKET,
            Key=filepath
        )
        print(f"[DEBUG] File EXISTS!")
        return create_response(200, {"exists": True})
        
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"[DEBUG] File NOT FOUND (404)")
            return create_response(200, {"exists": False})
        print(f"[DEBUG] S3 Error: {str(e)}")
        return create_error_response(500, f"Failed to check file: {str(e)}")
    except Exception as e:
        print(f"[DEBUG] Exception: {str(e)}")
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
    from urllib.parse import unquote
    
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    
    if not FILE_PROCESSING_BUCKET:
        return create_error_response(500, "Server configuration error: FILE_PROCESSING_BUCKET not set")
    
    # URL decode the filename (handles %20 -> space)
    filename = unquote(filename)
    
    # Remove extension if provided
    filename_base = filename.replace('.xlsx', '').replace('_filled', '')
    estimate_key = f"estimates/{filename_base}_estimate.json"
    
    print(f"[DEBUG] delete_estimate: deleting {estimate_key}")
    
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


# ============================================================
# PRICE CODE ALLOCATION HANDLERS
# ============================================================

@with_error_handling
def pricecode_upload_url(event, context):
    """
    Generates a presigned URL for uploading a file for price code allocation.
    Query params:
        - filename: Name of the file (required)
        - mode: 'index' or 'allocate' (required)
        - sourceFiles: Comma-separated list of price code sets (optional, for allocate mode)
    """
    from urllib.parse import unquote
    
    query_params = event.get("queryStringParameters", {}) or {}
    filename = query_params.get("filename")
    mode = query_params.get("mode")
    source_files = query_params.get("sourceFiles")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    if not mode or mode not in ["index", "allocate"]:
        return create_error_response(400, "Mode must be 'index' or 'allocate'")
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    filename = unquote(filename)
    
    # Determine S3 path based on mode
    if mode == "index":
        s3_key = f"input/pricecode/index/{filename}"
    else:
        s3_key = f"input/pricecode/allocate/{filename}"
    
    # Prepare metadata
    metadata = {
        "mode": mode,
        "filename": filename
    }
    
    # Add source-files metadata if present (for allocate mode)
    if source_files:
        metadata["source-files"] = source_files
    
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": PRICECODE_BUCKET,
                "Key": s3_key,
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Metadata": metadata
            },
            ExpiresIn=3600
        )
        return create_response(200, {"url": presigned_url, "key": s3_key})
    except Exception as e:
        return create_error_response(500, f"Failed to generate upload URL: {str(e)}")


@with_error_handling
def pricecode_status(event, context):
    """
    Get processing status/estimate for a price code job.
    Path parameter: filename
    """
    from urllib.parse import unquote
    
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    filename = unquote(filename)
    filename_base = filename.replace('.xlsx', '').replace('_pricecode', '')
    estimate_key = f"estimates/pc_{filename_base}_estimate.json"
    
    print(f"[DEBUG] pricecode_status: looking for {estimate_key}")
    
    try:
        response = s3_client.get_object(
            Bucket=PRICECODE_BUCKET,
            Key=estimate_key
        )
        estimate_data = json.loads(response["Body"].read())
        print(f"[DEBUG] pricecode_status: found, complete={estimate_data.get('complete')}")
        return create_response(200, estimate_data)
        
    except s3_client.exceptions.NoSuchKey:
        return create_response(404, {"error": "Estimate not found"})
    except Exception as e:
        return create_error_response(500, f"Failed to get status: {str(e)}")


@with_error_handling
def pricecode_download(event, context):
    """
    Get presigned download URL for completed price code file.
    Path parameter: filename
    """
    from urllib.parse import unquote
    
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    filename = unquote(filename)
    output_prefix = "output/pricecode/fills/"
    
    # Try multiple key possibilities
    # 1. Exact match (e.g. for .txt files)
    # 2. Standard pricecode format (for base names)
    keys_to_try = [
        f"{output_prefix}{filename}",
    ]
    
    if not filename.endswith('_pricecode.xlsx'):
        base = filename.replace('.xlsx', '').replace('_pricecode', '')
        keys_to_try.append(f"{output_prefix}{base}_pricecode.xlsx")
        
    found_key = None
    for key in keys_to_try:
        try:
            s3_client.head_object(Bucket=PRICECODE_BUCKET, Key=key)
            found_key = key
            break
        except s3_client.exceptions.ClientError:
            continue
            
    if not found_key:
        return create_response(404, {"error": "Output file not found"})
        
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": PRICECODE_BUCKET,
                "Key": found_key
            },
            ExpiresIn=3600
        )
        return create_response(200, {"url": presigned_url, "key": found_key, "filename": found_key.split('/')[-1]})
    except Exception as e:
        return create_error_response(500, f"Failed to generate download URL: {str(e)}")


@with_error_handling
def list_available_price_codes(event, context):
    """List available price code sets from the S3 registry file."""
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    try:
        response = s3_client.get_object(
            Bucket=PRICECODE_BUCKET,
            Key="metadata/available_price_codes.json"
        )
        content = json.loads(response["Body"].read())
        return create_response(200, {"price_codes": content.get("price_codes", [])})
        
    except s3_client.exceptions.NoSuchKey:
        # Registry file doesn't exist yet
        return create_response(200, {"price_codes": []})
    except Exception as e:
        return create_error_response(500, f"Failed to list price codes: {str(e)}")


@with_error_handling
def delete_pricecode_estimate(event, context):
    """
    Delete estimate file for price code job when complete.
    Path parameter: filename
    """
    from urllib.parse import unquote
    
    path_params = event.get("pathParameters", {}) or {}
    filename = path_params.get("filename")
    
    if not filename:
        return create_error_response(400, "Missing required parameter: filename")
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    filename = unquote(filename)
    filename_base = filename.replace('.xlsx', '').replace('_pricecode', '')
    estimate_key = f"estimates/pc_{filename_base}_estimate.json"
    
    try:
        s3_client.delete_object(
            Bucket=PRICECODE_BUCKET,
            Key=estimate_key
        )
        return create_response(200, {"deleted": True, "key": estimate_key})
    except Exception as e:
        return create_error_response(500, f"Failed to delete estimate: {str(e)}")


@with_error_handling
def list_pricecode_output_files(event, context):
    """List completed price code output files from output/pricecode/fills/."""
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=PRICECODE_BUCKET,
            Prefix="output/pricecode/fills/"
        )
        
        files = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            # Skip directory marker
            if key.endswith("/") or key == "output/pricecode/fills/":
                continue
            
            # Generate presigned URL
            try:
                download_url = s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={
                        "Bucket": PRICECODE_BUCKET,
                        "Key": key
                    },
                    ExpiresIn=3600
                )
            except Exception:
                download_url = ""

            filename = key.split("/")[-1]
            files.append({
                "key": key,
                "filename": filename,
                "size": obj["Size"],
                "lastModified": obj["LastModified"].isoformat(),
                "downloadUrl": download_url
            })
        
        # Sort by last modified, newest first
        files.sort(key=lambda x: x["lastModified"], reverse=True)
        
        return create_response(200, {"files": files})
        
    except Exception as e:
        return create_error_response(500, f"Failed to list output files: {str(e)}")


@with_error_handling
def list_pricecode_active_jobs(event, context):
    """
    List all active price code jobs by checking estimates/ directory.
    Should only return 0 or 1 file at a time.
    """
    if not PRICECODE_BUCKET:
        return create_error_response(500, "Server configuration error: PRICECODE_BUCKET not set")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=PRICECODE_BUCKET,
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
                        Bucket=PRICECODE_BUCKET,
                        Key=key
                    )
                    estimate_data = json.loads(estimate_response["Body"].read())
                    active_jobs.append(estimate_data)
                except Exception as e:
                    print(f"Error reading estimate {key}: {str(e)}")
                    continue
        
        return create_response(200, {
            "active_jobs": active_jobs,
            "count": len(active_jobs)
        })
        
    except Exception as e:
        return create_error_response(500, f"Failed to list active jobs: {str(e)}")



