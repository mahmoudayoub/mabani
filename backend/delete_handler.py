
import os
import boto3
import json
from urllib.parse import unquote

s3_client = boto3.client("s3")
FILE_PROCESSING_BUCKET = os.environ.get("FILE_PROCESSING_BUCKET")

def create_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": True,
            "Access-Control-Allow-Methods": "DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization"
        },
        "body": json.dumps(body)
    }

def delete_datasheet(event, context):
    """
    Delete a datasheet (vectors + registry entry).
    Path params: sheet_name
    """
    # Handle CORS preflight if API Gateway passes generic proxy
    if event.get('httpMethod') == 'OPTIONS':
         return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    sheet_name = path_params.get("sheet_name")
    
    # URL decode sheet_name
    if sheet_name:
        sheet_name = unquote(sheet_name)
    
    if not sheet_name:
        return create_response(400, {"error": "Missing sheet name"})
        
    print(f"Deleting datasheet: {sheet_name}")

    # 1. Delete from OpenSearch
    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    index_name = os.environ.get("OPENSEARCH_INDEX_NAME", "almabani")
    region = os.environ.get("AWS_REGION", "eu-west-1")
    
    if endpoint:
        try:
            from almabani.core.vector_store import VectorStoreService
            import asyncio
            
            # Use vector store service for standard connection handling
            vector_store = VectorStoreService(
                endpoint=endpoint,
                region=region,
                index_name=index_name
            )
            client = vector_store.get_client()
            
            # Execute deletion asynchronously
            async def run_delete():
                query = {"query": {"term": {"sheet_name": sheet_name}}}
                await client.delete_by_query(index=index_name, body=query)
                
            loop = asyncio.get_event_loop()
            loop.run_until_complete(run_delete())
            print(f"Deleted vectors for sheet: {sheet_name} from index {index_name}")
        except Exception as e:
            print(f"OpenSearch deletion failed: {e}")
            return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})
    else:
        print("Skipping OpenSearch deletion (missing endpoint)")
            
    # 2. Update Registry in S3
    try:
        registry_key = "metadata/available_sheets.json"
        
        # Load existing (includes sheets AND groups)
        try:
            obj = s3_client.get_object(Bucket=FILE_PROCESSING_BUCKET, Key=registry_key)
            data = json.loads(obj['Body'].read())
            sheets = data.get("sheets", [])
            existing_groups = data.get("groups", [])  # Preserve groups!
        except s3_client.exceptions.NoSuchKey:
            sheets = []
            existing_groups = []
            
        # Update
        if sheet_name in sheets:
            sheets.remove(sheet_name)
            
            # Also remove deleted sheet from any groups
            for group in existing_groups:
                if sheet_name in group.get("sheets", []):
                    group["sheets"].remove(sheet_name)
            
            # Save back (preserve groups!)
            s3_client.put_object(
                Bucket=FILE_PROCESSING_BUCKET,
                Key=registry_key,
                Body=json.dumps({"sheets": sheets, "groups": existing_groups}, indent=2),
                ContentType="application/json"
            )
            print(f"Removed {sheet_name} from registry")
        else:
            print(f"Sheet {sheet_name} not found in registry")
            
    except Exception as e:
        return create_response(500, {"error": f"Failed to update registry: {str(e)}"})
        
    return create_response(200, {"message": f"Sheet {sheet_name} deleted successfully"})

def delete_price_code_set(event, context):
    """
    Delete a price code set (vectors + registry entry).
    Path params: set_name (mapped from /pricecode/sets/{set_name})
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
         return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    set_name = path_params.get("set_name")
    
    # URL decode
    if set_name:
        set_name = unquote(set_name)
    
    if not set_name:
        return create_response(400, {"error": "Missing set name"})
        
    print(f"Deleting Price Code Set: {set_name}")

    # 1. Delete from OpenSearch
    endpoint = os.environ.get("OPENSEARCH_ENDPOINT")
    index_name = os.environ.get("PRICECODE_INDEX_NAME", "almabani-pricecode")
    region = os.environ.get("AWS_REGION", "eu-west-1")
    
    if endpoint:
        try:
            from almabani.core.vector_store import VectorStoreService
            import asyncio
            
            vector_store = VectorStoreService(
                endpoint=endpoint,
                region=region,
                index_name=index_name
            )
            client = vector_store.get_client()
            
            async def run_delete():
                query = {"query": {"term": {"source_file": set_name}}}
                await client.delete_by_query(index=index_name, body=query)
                
            loop = asyncio.get_event_loop()
            loop.run_until_complete(run_delete())
            print(f"Deleted vectors for set: {set_name} from index {index_name}")
        except Exception as e:
            print(f"OpenSearch deletion failed: {e}")
            return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})
    else:
        print("Skipping OpenSearch deletion (missing endpoint)")
            
    # 2. Update Registry in PRICECODE_BUCKET
    bucket = os.environ.get("PRICECODE_BUCKET")
    if bucket:
        try:
            registry_key = "metadata/available_price_codes.json"
            
            # Load existing
            try:
                obj = s3_client.get_object(Bucket=bucket, Key=registry_key)
                data = json.loads(obj['Body'].read())
                codes = data.get("price_codes", [])
            except s3_client.exceptions.NoSuchKey:
                codes = []
            except Exception as e:
                print(f"Error reading registry: {e}")
                codes = []
                
            if set_name in codes:
                codes.remove(set_name)
                s3_client.put_object(
                    Bucket=bucket,
                    Key=registry_key,
                    Body=json.dumps({"price_codes": codes}),
                    ContentType="application/json"
                )
                print(f"Removed {set_name} from registry")
            else:
                print(f"Set {set_name} not found in registry")
        except Exception as e:
            return create_response(500, {"error": f"Failed to update registry: {str(e)}"})
    else:
        return create_response(500, {"error": "PRICECODE_BUCKET env var not set"})
            
    return create_response(200, {"message": f"Set {set_name} deleted successfully"})
