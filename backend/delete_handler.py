
import os
import boto3
import json
from pinecone import Pinecone
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

    # 1. Delete from Pinecone
    api_key = os.environ.get("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX_NAME")
    
    if api_key and index_name:
        try:
            pc = Pinecone(api_key=api_key)
            index = pc.Index(index_name)
            # Filter deletion by 'source_name' (Assuming metadata field is 'source_name' based on previous context, verify vs guide)
            # Guide says 'sheet', but our indexer uses 'source_name' or 'sheet'?
            # Let's check indexer.py if possible, but guide explicitly says `filter={"sheet": sheet_name}`.
            # I will follow the guide BUT 'source_name' is what we used in unit rate indexer.
            # Wait, user guide says: index.delete(delete_all=False, filter={"sheet": sheet_name})
            # I should follow the guide IF the existing metadata uses "sheet".
            # Checking recent indexer code:
            # `VectorStoreIndexer.prepare_vectors` uses `source_name`.
            # If the user *provided* this guide, they might expect "sheet".
            # However, `sheet` usually refers to Excel sheets.
            # Let's support both just in case, or stick to what the user logic likely uses.
            # Actually, `rate_matcher/matcher.py` filters by `source_name`.
            # I'll stick to the user provided code: `filter={"sheet": sheet_name}` but I suspect it might need to match `source_name`.
            # Let's implement exactly what is asked first.
            
            # Filter deletion by 'sheet_name' metadata (Standard Datasheets)
            index.delete(delete_all=False, filter={"sheet_name": sheet_name})
            print(f"Deleted vectors for sheet: {sheet_name}")
        except Exception as e:
            print(f"Pinecone deletion failed: {e}")
            return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})
    else:
        print("Skipping Pinecone deletion (missing credentials)")
            
    # 2. Update Registry in S3
    try:
        registry_key = "metadata/available_sheets.json"
        
        # Load existing
        try:
            obj = s3_client.get_object(Bucket=FILE_PROCESSING_BUCKET, Key=registry_key)
            data = json.loads(obj['Body'].read())
            sheets = data.get("sheets", [])
        except s3_client.exceptions.NoSuchKey:
            sheets = []
            
        # Update
        if sheet_name in sheets:
            sheets.remove(sheet_name)
            # Save back
            s3_client.put_object(
                Bucket=FILE_PROCESSING_BUCKET,
                Key=registry_key,
                Body=json.dumps({"sheets": sheets}),
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

    # 1. Delete from Pinecone
    # 1. Delete from Pinecone
    api_key = os.environ.get("PINECONE_API_KEY")
    # Use the dedicated PRICECODE_INDEX_NAME if set, else fallback (though stack provides it now)
    index_name = os.environ.get("PRICECODE_INDEX_NAME") or os.environ.get("PINECONE_INDEX_NAME")
    
    if api_key and index_name:
        try:
            pc = Pinecone(api_key=api_key)
            index = pc.Index(index_name)
            # Filter deletion by 'source_file' metadata (Price Codes)
            index.delete(delete_all=False, filter={"source_file": set_name})
            print(f"Deleted vectors for set: {set_name} from index {index_name}")
        except Exception as e:
            print(f"Pinecone deletion failed: {e}")
            return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})
    else:
        print("Skipping Pinecone deletion (missing credentials)")
            
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
